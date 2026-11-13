"""Item tracker: reads found items from the game's save, toggled with a controller combo.

Source: Lichii writes the game's saves to
  %APPDATA%\\lichii\\nand\\user\\save\\<zeros>\\<user>\\0400486024DEC000\\slot_NN\\progress.sav
whenever the game saves (autosaves included). The newest progress.sav is the current game.
Its layout is TotK-style: magic 04 03 02 01, u32, u32 data offset, then (u32 hash, u32 value)
pairs from 0x28 up to the data offset, grouped by type. Items are found when their
IsGet.<actor> flag (murmur3 of the name, see data/tracker.json) is 1.

Toggle: the overlay window shows and hides on a controller button combo (read with XInput,
which sees Xbox controllers) or a keyboard key, polled at 60 Hz. Showing never activates the
window, so the game keeps focus and input.
"""
import base64, ctypes, glob, json, os, struct, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data', 'tracker.json')
TITLE_ID = '0400486024DEC000'
SAVE_ROOT = os.path.join(os.environ.get('APPDATA') or '', 'lichii', 'nand', 'user', 'save')

# XInput button bits
XI = {'up': 0x1, 'down': 0x2, 'left': 0x4, 'right': 0x8, 'start': 0x10, 'back': 0x20,
      'ls': 0x40, 'rs': 0x80, 'lb': 0x100, 'rb': 0x200, 'a': 0x1000, 'b': 0x2000, 'x': 0x4000, 'y': 0x8000}
COMBOS = {  # key: (label, buttons)
    'ls_rs': ('Click both sticks (L3 + R3)', ('ls', 'rs')),
    'back_rs': ('View + right stick click', ('back', 'rs')),
    'lb_rb_back': ('LB + RB + View', ('lb', 'rb', 'back')),
    'back_dup': ('View + D-pad up', ('back', 'up')),
}
KEYS = {'F8': 0x77, 'F9': 0x78, 'F10': 0x79, 'F11': 0x7A}
DEFAULTS = {'combo': 'ls_rs', 'key': 'F10'}


def items():
    return json.load(open(DATA, encoding='utf-8'))


# ------------------------------------------------------------------ icons (from the user's own game files)
ICON_SIZE = 96


def icon_actors():
    return sorted({s['actor'] for g in items()['groups'] for i in g['items'] for s in i['stages'] if s['icon']})


def needed_files():
    """Game files the tracker reads (for data/romfs_manifest.json)."""
    return ['UI/Tex/Icon/%s.bntx.zs' % a for a in icon_actors()]


def icons(rom, cache_dir, log=lambda *_: None):
    """{actor: PNG data URI}. Decoded from the game's ASTC textures once, then read from cache_dir."""
    sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
    import zs, bntx
    os.makedirs(cache_dir, exist_ok=True)
    out = {}
    for a in icon_actors():
        png = os.path.join(cache_dir, a + '.png')
        if not os.path.exists(png):
            src = os.path.join(rom, 'UI', 'Tex', 'Icon', a + '.bntx.zs')
            if not os.path.exists(src):
                continue
            w, h, rgba = bntx.decode(zs.decompress(rom, src))
            tmp = png + '.tmp'
            open(tmp, 'wb').write(bntx.png(*bntx.downscale(w, h, rgba, ICON_SIZE)))
            os.replace(tmp, png)
        out[a] = 'data:image/png;base64,' + base64.b64encode(open(png, 'rb').read()).decode()
    log('tracker icons ready: %d' % len(out))
    return out


# ------------------------------------------------------------------ save reading
def save_files():
    found = {}
    for tid in (TITLE_ID, TITLE_ID.lower()):  # the folder name's case varies; Windows matches both
        for f in glob.glob(os.path.join(SAVE_ROOT, '*', '*', tid, 'slot_*', 'progress.sav')):
            found[os.path.normcase(os.path.abspath(f))] = f
    return list(found.values())


def latest_save():
    files = save_files()
    return max(files, key=os.path.getmtime) if files else None


def read_save(path, string_hashes=()):
    """({hash: u32 value}, {hash: string}) from a progress.sav. Strings are only read for
    string_hashes (String64 flags: the value is the offset of a 64-byte NUL-padded string)."""
    p = open(path, 'rb').read()
    if p[:4] != b'\x04\x03\x02\x01':
        raise ValueError('not a save file')
    end, = struct.unpack_from('<I', p, 8)
    end = min(end, len(p))
    values = dict(struct.unpack_from('<II', p, o) for o in range(0x28, end - 7, 8))
    strings = {}
    for h in string_hashes:
        v = values.get(h)
        if v is not None and end <= v < len(p):
            strings[h] = p[v:v + 64].split(b'\0')[0].decode('utf-8', 'replace')
    return values, strings


def read_values(path):
    return read_save(path)[0]


def bottle_count(strings, data):
    skip = set(data.get('not_slots', []))
    return sum(1 for h, s in strings.items() if h not in skip and s.startswith('Item_Bottle'))


def state(values, data=None, strings=None):
    """What the overlay shows: every item's highest found stage, and the counters."""
    data = data or items()
    strings = strings or {}
    groups = []
    for g in data['groups']:
        out = []
        for it in g['items']:
            level = 0
            for k, s in enumerate(it['stages'], 1):
                if values.get(s['flag']): level = k
            stage = it['stages'][max(level, 1) - 1]
            row = {'key': it['key'], 'name': stage['name'], 'level': level, 'stages': len(it['stages']),
                   'tint': it.get('tint'), 'actor': stage['actor'] if stage.get('icon') else None,
                   'drawn': it.get('drawn')}
            if it.get('count') == 'bottles':
                n = min(it['max'], max(bottle_count(strings, data), 1 if level else 0))
                row.update(count=n, max=it['max'], name='Bottles', level=1 if n else 0)
            out.append(row)
        groups.append({'title': g['title'], 'color': g['color'], 'items': out,
                       'found': sum(1 for i in out if i['level']), 'total': len(out)})
    counters = []
    for c in data['counters']:
        v = values.get(c['flag'], 0)
        v = v - (1 << 32) if v & 0x80000000 else v
        if c['key'] == 'hearts':
            v = v / 4  # MaxLife counts quarter hearts
        counters.append({'key': c['key'], 'label': 'Hearts' if c['key'] == 'hearts' else c['label'],
                         'value': v, 'total': c['total']})
    return {'groups': groups, 'counters': counters}


def snapshot():
    """Current tracker state from the newest save, or a 'no save' marker."""
    path = latest_save()
    if not path:
        return {'ok': False, 'error': 'No Ocarina of Time save found in Lichii yet. Play until the game saves once.'}
    try:
        data = items()
        values, strings = read_save(path, data.get('string64', []))
        st = state(values, data, strings)
    except (OSError, ValueError, struct.error) as e:
        return {'ok': False, 'error': 'Could not read the save (%s).' % e}
    st.update({'ok': True, 'source': path, 'slot': os.path.basename(os.path.dirname(path)), 'mtime': os.path.getmtime(path),
               'saved': time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(path)))})
    return st


# ------------------------------------------------------------------ input (XInput + keyboard)
class _Pad(ctypes.Structure):
    _fields_ = [('wButtons', ctypes.c_ushort), ('bLeftTrigger', ctypes.c_ubyte), ('bRightTrigger', ctypes.c_ubyte),
                ('sThumbLX', ctypes.c_short), ('sThumbLY', ctypes.c_short), ('sThumbRX', ctypes.c_short), ('sThumbRY', ctypes.c_short)]


class _State(ctypes.Structure):
    _fields_ = [('dwPacketNumber', ctypes.c_uint), ('Gamepad', _Pad)]


def _xinput():
    for name in ('xinput1_4', 'xinput1_3', 'xinput9_1_0'):
        try:
            return ctypes.WinDLL(name)
        except OSError:
            pass
    return None


class Toggle(threading.Thread):
    """Calls on_toggle() each time the combo (or key) goes from released to fully pressed."""

    def __init__(self, on_toggle, combo='ls_rs', key='F10'):
        super().__init__(daemon=True)
        self.on_toggle, self.stop = on_toggle, threading.Event()
        self.set(combo, key)
        self.xi = _xinput()
        self.user32 = ctypes.WinDLL('user32') if os.name == 'nt' else None

    def set(self, combo, key):
        self.mask = 0
        for b in COMBOS.get(combo, COMBOS[DEFAULTS['combo']])[1]:
            self.mask |= XI[b]
        self.vk = KEYS.get(key)

    def pressed(self):
        if self.xi:
            st = _State()
            for i in range(4):
                if self.xi.XInputGetState(i, ctypes.byref(st)) == 0 and st.Gamepad.wButtons & self.mask == self.mask:
                    return True
        if self.vk and self.user32 and self.user32.GetAsyncKeyState(self.vk) & 0x8000:
            return True
        return False

    def run(self):
        was = False
        while not self.stop.is_set():
            now = self.pressed()
            if now and not was:
                try:
                    self.on_toggle()
                except Exception:
                    pass
            was = now
            time.sleep(1 / 60)


# ------------------------------------------------------------------ overlay window helpers (Windows)
GWL_EXSTYLE, WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x8, 0x80, 0x08000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40


class Overlay:
    """Show/hide a top-level window by title without ever giving it focus."""

    def __init__(self, title):
        self.title = title
        self.u = ctypes.WinDLL('user32')
        self.u.FindWindowW.restype = ctypes.c_void_p
        self.u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        self.u.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        self.u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.u.IsWindowVisible.argtypes = [ctypes.c_void_p]
        self.hwnd = None

    def find(self):
        if not self.hwnd:
            self.hwnd = self.u.FindWindowW(None, self.title)
            if self.hwnd:
                ex = self.u.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
                self.u.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        return self.hwnd

    def visible(self):
        return bool(self.find() and self.u.IsWindowVisible(self.hwnd))

    def show(self):
        if self.find():
            self.u.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.u.SetWindowPos(self.hwnd, ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0,
                                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def hide(self):
        if self.find():
            self.u.ShowWindow(self.hwnd, SW_HIDE)

    def toggle(self):
        self.hide() if self.visible() else self.show()
