"""Self-update from GitHub Releases.

At launch the app asks the GitHub API for the latest release of REPO. If its tag (vX.Y.Z) is
newer than VERSION, the release's OoTRando.exe is downloaded next to the running exe as
OoTRando.exe.new and checked against the SHA-256 in the release's OoTRando.exe.sha256 (written
by the release workflow). Nothing is replaced until that matches.

Applying: Windows lets a running exe be renamed, so the running OoTRando.exe becomes
OoTRando.exe.old, the verified download takes its name, the new exe is started with the same
arguments, and this one exits. The .old file is deleted by the next launch. A verified download
that was not applied yet is applied at the next launch.

Only a frozen build (the exe) updates itself. Running from source just reports the new version.
No personal data is sent: the requests carry a generic User-Agent and nothing else.
"""
import hashlib, json, os, subprocess, sys, threading, urllib.request

REPO = 'sgurgurich/oot-remake-rando'
ASSET = 'OoTRando.exe'
API = 'https://api.github.com/repos/%s/releases/latest' % REPO
UA = {'User-Agent': 'OoTRando-updater', 'Accept': 'application/vnd.github+json'}
TIMEOUT = 8


def parse(tag):
    t = (tag or '').strip().lstrip('vV')
    try:
        return tuple(int(x) for x in t.split('.')[:3])
    except ValueError:
        return None


def frozen():
    return bool(getattr(sys, 'frozen', False))


def exe_path():
    return os.path.abspath(sys.executable) if frozen() else None


def _get(url, raw=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    return data if raw else json.loads(data.decode('utf-8'))


def latest():
    """{'version', 'tag', 'url', 'sha_url', 'size', 'notes', 'page'} for the newest release, or None."""
    rel = _get(API)
    if rel.get('draft') or rel.get('prerelease'):
        return None
    assets = {a['name']: a for a in rel.get('assets', [])}
    exe, sha = assets.get(ASSET), assets.get(ASSET + '.sha256')
    ver = parse(rel.get('tag_name'))
    if not (exe and sha and ver):
        return None
    prefix = 'https://github.com/%s/releases/download/' % REPO
    if not exe['browser_download_url'].startswith(prefix) or not sha['browser_download_url'].startswith(prefix):
        return None  # only ever download from this repository's own releases
    return {'version': ver, 'tag': rel['tag_name'], 'url': exe['browser_download_url'], 'sha_url': sha['browser_download_url'],
            'size': exe.get('size'), 'notes': (rel.get('body') or '')[:2000], 'page': rel.get('html_url')}


def newer(current, rel):
    cur = parse(current)
    return bool(rel and cur and rel['version'] > cur)


def _paths():
    exe = exe_path()
    return exe, exe + '.new', exe + '.new.sha256', exe + '.old'


def cleanup():
    """Delete what an earlier update left behind (the replaced exe)."""
    if not frozen(): return
    _, _, _, old = _paths()
    try:
        if os.path.exists(old): os.remove(old)
    except OSError:
        pass


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def pending():
    """True if a verified download is waiting to be applied."""
    if not frozen(): return False
    _, new, shaf, _ = _paths()
    try:
        return os.path.exists(new) and os.path.exists(shaf) and _sha(new) == open(shaf).read().strip()
    except OSError:
        return False


def download(rel, progress=lambda done, total: None):
    """Fetch and verify the release exe. Returns True when it is ready to apply."""
    exe, new, shaf, _ = _paths()
    want = _get(rel['sha_url'], raw=True).decode('ascii', 'replace').split()[0].strip().lower()
    if len(want) != 64:
        raise ValueError('bad checksum file in the release')
    tmp = new + '.part'
    req = urllib.request.Request(rel['url'], headers={'User-Agent': UA['User-Agent']})
    h = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, 'wb') as f:
        total = int(r.headers.get('Content-Length') or rel.get('size') or 0)
        for b in iter(lambda: r.read(1 << 20), b''):
            f.write(b); h.update(b); done += len(b)
            progress(done, total)
    if h.hexdigest() != want:
        os.remove(tmp)
        raise ValueError('the download did not match its checksum')
    os.replace(tmp, new)
    open(shaf, 'w').write(want)
    return True


def apply_and_restart(args=None):
    """Swap in the verified download and start it. Returns False if there is nothing to apply."""
    if not pending(): return False
    exe, new, shaf, old = _paths()
    try:
        if os.path.exists(old): os.remove(old)
    except OSError:
        pass
    os.replace(exe, old)          # a running exe can be renamed on Windows
    try:
        os.replace(new, exe)
    except OSError:
        os.replace(old, exe)      # put the running one back
        raise
    try: os.remove(shaf)
    except OSError: pass
    subprocess.Popen([exe] + list(sys.argv[1:] if args is None else args), close_fds=True)
    return True


class Checker(threading.Thread):
    """Background check + download at launch. on_state(dict) reports progress to the page."""

    def __init__(self, version, on_state):
        super().__init__(daemon=True)
        self.version, self.on_state = version, on_state

    def run(self):
        try:
            rel = latest()
        except Exception:
            return self.on_state({'state': 'offline'})
        if not newer(self.version, rel):
            return self.on_state({'state': 'current'})
        info = {'version': rel['tag'], 'notes': rel['notes'], 'page': rel['page']}
        if not frozen():
            return self.on_state(dict(info, state='available'))  # from source: just say so
        self.on_state(dict(info, state='downloading', done=0, total=rel.get('size') or 0))
        last = [0]

        def prog(done, total):
            if done - last[0] >= (1 << 20) or done == total:
                last[0] = done
                self.on_state(dict(info, state='downloading', done=done, total=total))
        try:
            download(rel, prog)
        except Exception as e:
            return self.on_state(dict(info, state='failed', error=str(e)))
        self.on_state(dict(info, state='ready'))
