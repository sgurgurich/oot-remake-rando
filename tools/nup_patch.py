"""Write a patched COPY of a .nup: same container, some files replaced.

    py tools/nup_patch.py <original.nup> <new.nup> <mod_dir>   # mod_dir holds romfs/... (patcher output)

The original is only opened for reading. The copy is made first, then:
  - each replacement file is appended at the end of the copy (16-byte aligned, raw codec),
  - its entry in the update package's tree points at the new data (size, offset, sha256),
  - optionally, the game's name (the title TLV in the base package's meta block) is changed:
    a new meta block is appended and the package record points at it,
  - the superblock's file_size and TOC SHA-256 are recomputed.
The old data stays in the copy, unreferenced (base-game files may share it, so it is never
overwritten). Nothing else changes: same packages, same UUID, same TOC size and layout.
"""
import ctypes, hashlib, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nup

ALIGN = 16
PACKAGES_OFF = 0x30  # package records start 0x30 bytes into the TOC, 0x40 bytes each
TLV_TITLE = 0x0005   # UTF-8 title name in a package meta block
MAX_TITLE = 0x200    # bytes; the size of a NACP name field


def parse_tlvs(meta):
    out, o = [], 0
    while o + 8 <= len(meta):
        t, _, n = struct.unpack_from('<HHI', meta, o)
        if o + 8 + n > len(meta): break
        out.append((t, meta[o + 8:o + 8 + n]))
        o += 8 + n
    return out


def build_tlvs(items):
    return b''.join(struct.pack('<HHI', t, 0, len(p)) + p for t, p in items)


def with_title(meta, title):
    """Meta block with its title TLV replaced (or added after the NPDM)."""
    data = title.encode('utf-8')
    items = parse_tlvs(meta)
    if any(t == TLV_TITLE for t, _ in items):
        items = [(t, data if t == TLV_TITLE else p) for t, p in items]
    else:
        items.insert(1 if items and items[0][0] == 1 else 0, (TLV_TITLE, data))
    return build_tlvs(items)


def package_records(f, toc_off):
    f.seek(toc_off + 4)
    count, = struct.unpack('<I', f.read(4))
    recs = []
    for k in range(count):
        o = toc_off + PACKAGES_OFF + 0x40 * k
        f.seek(o)
        raw = f.read(0x40)
        tid, = struct.unpack_from('<Q', raw, 0)
        kind = raw[0x18]
        moff, msz = struct.unpack_from('<QI', raw, 0x20)
        recs.append({'off': o, 'title_id': tid, 'kind': kind, 'meta_off': moff, 'meta_size': msz})
    return recs


def read_title(path):
    """The title TLV of the base package (or the first package), or None."""
    with open(path, 'rb') as f:
        recs = package_records(f, 0x80)
        rec = next((r for r in recs if r['kind'] == 0), recs[0])
        if not rec['meta_size']: return None
        f.seek(rec['meta_off'])
        for t, p in parse_tlvs(f.read(rec['meta_size'])):
            if t == TLV_TITLE: return p.decode('utf-8')
    return None


class NupError(Exception):
    pass


def same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def copy_file(src, dst, progress=None):
    """Copy src to dst (dst must not exist), reporting progress(done, total)."""
    total = os.path.getsize(src)
    if sys.platform == 'win32':
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        Routine = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64,
                                     ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        def cb(tot, done, *_):
            if progress: progress(done, tot)
            return 0  # PROGRESS_CONTINUE
        routine = Routine(cb)
        COPY_FILE_FAIL_IF_EXISTS, COPY_FILE_NO_BUFFERING = 0x1, 0x1000
        ok = k32.CopyFileExW(ctypes.c_wchar_p(src), ctypes.c_wchar_p(dst), routine, None, None,
                             COPY_FILE_FAIL_IF_EXISTS | COPY_FILE_NO_BUFFERING)
        if not ok:
            raise NupError('copy failed: %s' % ctypes.FormatError(ctypes.get_last_error()).strip())
        return
    with open(src, 'rb') as fi, open(dst, 'xb') as fo:
        done = 0
        while True:
            b = fi.read(16 << 20)
            if not b: break
            fo.write(b); done += len(b)
            if progress: progress(done, total)


def write_patched(src, dst, replacements, progress=None, log=print, title=None):
    """replacements: {container path, e.g. '131072/romfs/Banc/...': new bytes}.
    title: new game name shown by emulators, or None to keep the original."""
    if title is not None:
        title = title.strip()
        if not title or len(title.encode('utf-8')) > MAX_TITLE:
            raise NupError('The game name must be 1 to %d bytes long.' % MAX_TITLE)
    if same_file(src, dst):
        raise NupError('The output must be a new file, not the original dump.')
    if os.path.exists(dst):
        raise FileExistsError(dst)
    src_n = nup.Nup(src)
    index = {p: i for p, i in src_n.walk_ids() if p in replacements}
    missing = sorted(set(replacements) - set(index))
    if missing:
        raise NupError('not in the dump: %s' % missing[:3])
    toc_off, files_off = src_n.toc_off, src_n.files_off
    src_n.f.close()

    need = os.path.getsize(src) + sum(len(d) + ALIGN for d in replacements.values()) + (64 << 20)
    free = shutil.disk_usage(os.path.dirname(os.path.abspath(dst))).free
    if free < need:
        raise NupError('Not enough disk space for the new .nup: needs %.1f GB, %.1f GB free.' % (need / 1e9, free / 1e9))

    part = dst + '.part'
    if os.path.exists(part):
        os.remove(part)
    log('Copying the dump (%.1f GB) ...' % (os.path.getsize(src) / 1e9))
    try:
        copy_file(src, part, progress)
        with open(part, 'r+b') as f:
            f.seek(0, 2)
            end = f.tell()
            for path in sorted(replacements):
                data = replacements[path]
                pad = (-end) % ALIGN
                f.write(b'\0' * pad); end += pad
                off = end
                f.write(data); end += len(data)
                i = index[path]
                ent = files_off + i * 0x50
                f.seek(ent + 0x08)
                f.write(struct.pack('<QQQ', len(data), off, len(data)))
                f.write(hashlib.sha256(data).digest())
                f.write(bytes(16))  # codec 0 (raw), codec_flags 0, reserved
                f.seek(0, 2)
            if title is not None:
                recs = package_records(f, toc_off)
                rec = next((r for r in recs if r['kind'] == 0), recs[0])
                f.seek(rec['meta_off'])
                meta = with_title(f.read(rec['meta_size']), title)
                f.seek(0, 2)
                pad = (-end) % ALIGN
                f.write(b'\0' * pad); end += pad
                meta_off = end
                f.write(meta); end += len(meta)
                f.seek(rec['off'] + 0x20)
                f.write(struct.pack('<QI', meta_off, len(meta)))
                log('Game name in the patched dump: %s' % title)
            f.seek(0x40)
            f.write(struct.pack('<Q', end))  # file_size
            f.seek(0x10)
            toc_size, = struct.unpack('<Q', f.read(8))
            f.seek(toc_off)
            digest = hashlib.sha256(f.read(toc_size)).digest()
            f.seek(0x18)
            f.write(digest)
            f.flush()
            os.fsync(f.fileno())
        log('Wrote %d replaced files into the copy; verifying ...' % len(replacements))
        verify(part, src, replacements, title)
        os.replace(part, dst)
    except BaseException:
        if os.path.exists(part):
            os.remove(part)
        raise
    return dst


def verify(path, original, replacements, title=None):
    """Re-read the new container like a strict reader would and compare it with the original."""
    n = nup.Nup(path)
    f = n.f
    f.seek(0)
    hdr = f.read(0x80)
    toc_size, = struct.unpack_from('<Q', hdr, 0x10)
    blob_off, file_size = struct.unpack_from('<QQ', hdr, 0x38)
    if file_size != os.path.getsize(path):
        raise NupError('verify: file_size %d != actual %d' % (file_size, os.path.getsize(path)))
    f.seek(n.toc_off)
    if hashlib.sha256(f.read(toc_size)).digest() != hdr[0x18:0x38]:
        raise NupError('verify: TOC hash mismatch')
    if blob_off % ALIGN or blob_off < n.toc_off + toc_size:
        raise NupError('verify: bad blob_offset')
    o = nup.Nup(original)
    f.seek(0); o.f.seek(0)
    a, b = f.read(0x80), o.f.read(0x80)
    if a[:0x18] != b[:0x18] or a[0x38:0x40] != b[0x38:0x40] or a[0x48:] != b[0x48:]:
        raise NupError('verify: superblock changed outside file_size and TOC hash')
    new_recs, old_recs = package_records(f, n.toc_off), package_records(o.f, o.toc_off)
    for a, b in zip(new_recs, old_recs):
        same = {k: v for k, v in a.items() if k not in ('meta_off', 'meta_size')} == \
               {k: v for k, v in b.items() if k not in ('meta_off', 'meta_size')}
        if not same or len(new_recs) != len(old_recs):
            raise NupError('verify: package records changed')
        if (a['meta_off'], a['meta_size']) != (b['meta_off'], b['meta_size']):
            if title is None or a['kind'] != 0 or a['meta_off'] + a['meta_size'] > file_size or a['meta_off'] < blob_off:
                raise NupError('verify: unexpected meta change')
    if title is not None and read_title(path) != title.strip():
        raise NupError('verify: game name did not read back')
    new_entries = dict(n.walk())
    old_entries = dict(o.walk())
    if set(new_entries) != set(old_entries):
        raise NupError('verify: file tree changed')
    changed = {p for p in new_entries if new_entries[p] != old_entries[p]}
    if changed != set(replacements):
        raise NupError('verify: unexpected entries changed: %s' % sorted(changed ^ set(replacements))[:3])
    for p, data in replacements.items():
        fe = new_entries[p]
        if fe[2] != len(data) or fe[4] != len(data) or fe[3] % ALIGN or fe[6][0] != 0:
            raise NupError('verify: bad entry for %s' % p)
        got = n.read(fe)
        if got != data or hashlib.sha256(got).digest() != fe[5]:
            raise NupError('verify: data mismatch for %s' % p)
    # no extent may overlap another (shared identical extents are allowed)
    ext = sorted({(fe[3], fe[4]) for fe in n.files if fe[4]})
    for (o1, s1), (o2, s2) in zip(ext, ext[1:]):
        if o2 < o1 + s1:
            raise NupError('verify: overlapping extents at %#x' % o2)
    if ext and ext[-1][0] + ext[-1][1] > file_size or ext[0][0] < blob_off:
        raise NupError('verify: extent out of bounds')
    n.f.close(); o.f.close()
    return True


def mod_replacements(mod_dir, prefix='131072/romfs/'):
    """{container path: bytes} for every file under <mod_dir>/romfs."""
    root = os.path.join(mod_dir, 'romfs')
    out = {}
    for dp, _, fs in os.walk(root):
        for fn in fs:
            full = os.path.join(dp, fn)
            out[prefix + os.path.relpath(full, root).replace(os.sep, '/')] = open(full, 'rb').read()
    return out


if __name__ == '__main__':
    src, dst, mod = sys.argv[1:4]
    last = [-1]
    def prog(done, total):
        pct = int(done * 100 / total)
        if pct != last[0] and pct % 5 == 0:
            last[0] = pct; print('  %d%%' % pct)
    write_patched(src, dst, mod_replacements(mod), prog)
    print('wrote', dst)
