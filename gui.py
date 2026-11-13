"""Desktop app: pick your .nup dump, choose settings, get a romfs mod for your emulator.

    py gui.py        (or double-click OoTRando.pyw, or run the built OoTRando.exe)

The window is an HTML page (ui/index.html) shown with pywebview, which uses the Edge
WebView2 runtime that ships with Windows 11. The page calls the methods of `Api` below.
"""
import collections, json, os, sys, threading, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import randomize
from randomizer import source, settings as cfg, tracker, updater
import nup_patch  # tools/ is on sys.path via randomize

TITLE = 'OoT Remake Randomizer'
SETTINGS = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'OoTRando', 'settings.json')
DEFAULT_OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'OoT Randomizer')
UI = os.path.join(HERE, 'ui', 'index.html')
TRACKER_UI = os.path.join(HERE, 'ui', 'tracker.html')
TRACKER_TITLE = 'OoT Rando Tracker'


def load_settings():
    try:
        return json.load(open(SETTINGS, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_settings(d):
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        json.dump(d, open(SETTINGS, 'w', encoding='utf-8'), indent=1)
    except OSError:
        pass


def app_state():
    """Everything the page needs to draw itself."""
    saved = load_settings()
    counts = collections.Counter(l['kind'] for l in randomize.load_locations())
    rando = cfg.normalize(saved.get('randomizer') or {
        # settings files from 0.2 stored this one flag at the top level
        'keep_event_chests': saved.get('keep_event_chests', False)})
    return {
        'version': randomize.VERSION,
        'nup': saved.get('nup', ''),
        'out': saved.get('out') or DEFAULT_OUT,
        'zip': saved.get('zip', False),
        'make_nup': saved.get('make_nup', True),
        'nup_title': saved.get('nup_title', randomize.DEFAULT_TITLE),
        'folder': saved.get('folder', False),
        'spoiler': saved.get('spoiler', True),
        'randomizer': rando,
        'cached': bool(source.cached()),
        'categories': [dict(key=k, count=counts.get(k, 0), **{f: c[f] for f in ('label', 'note', 'experimental')})
                       for k, c in cfg.CATEGORIES.items()],
        'unavailable': [dict(key=k, **v) for k, v in cfg.UNAVAILABLE.items()],
        'dungeon_items': [{'key': k, 'label': v['label'], 'choices': v['choices'],
                           'locked': v.get('locked', {}), 'notes': v.get('notes', {})}
                          for k, v in cfg.DUNGEON_ITEMS.items()],
        'choice_labels': cfg.CHOICE_LABELS,
        'shops': cfg.SHOPS,
        'world': {k: {f: v for f, v in c.items() if f != 'flags'} for k, c in cfg.WORLD.items()},
        'cutscene_options': cfg.CUTSCENE_OPTIONS,
        'auto_skip_note': cfg.AUTO_SKIP_NOTE,
        'auto_update': saved.get('auto_update', True),
        'frozen': updater.frozen(),
    }


class Api:
    """Methods the page calls (window.pywebview.api.*). Each runs on its own thread."""

    def __init__(self):
        self._window = None
        self._busy = False
        self._last_pct = -1
        self._update = {'state': 'idle'}
        self._update_started = False

    # --- state ------------------------------------------------------------------------------
    def init(self):
        return app_state()

    def save(self, opts):
        save_settings({'nup': opts.get('nup', ''), 'out': opts.get('out', ''), 'zip': bool(opts.get('zip')),
                       'make_nup': bool(opts.get('make_nup', True)), 'folder': bool(opts.get('folder')),
                       'nup_title': opts.get('nup_title', randomize.DEFAULT_TITLE),
                       'spoiler': bool(opts.get('spoiler', True)),
                       'randomizer': cfg.normalize(opts.get('randomizer')),
                       'tracker': load_settings().get('tracker', {}),
                       'auto_update': load_settings().get('auto_update', True)})
        return True

    # --- updates ----------------------------------------------------------------------------
    def update_state(self):
        return self._update

    def start_update_check(self):
        """Check GitHub for a newer build (and download it) in the background, once."""
        if self._update_started or not load_settings().get('auto_update', True):
            return self._update
        self._update_started = True

        def report(st):
            self._update = st
            if self._window:
                self._window.evaluate_js('window.onUpdate && window.onUpdate(%s)' % json.dumps(st))
        updater.Checker(randomize.VERSION, report).start()
        return self._update

    def restart_to_update(self):
        if self._busy:
            return {'ok': False, 'error': 'Wait for the current seed to finish.'}
        if updater.apply_and_restart():
            os._exit(0)
        return {'ok': False, 'error': 'No update is ready.'}

    def set_auto_update(self, on):
        s = load_settings(); s['auto_update'] = bool(on); save_settings(s)
        return True

    def open_tracker(self):
        open_tracker()
        return True

    def preview_title(self, template, seed=''):
        return randomize.game_title(template, seed or '<seed>') or '(original name)'

    def random_seed(self):
        return randomize.random_seed()

    # --- files ------------------------------------------------------------------------------
    def _dialog(self, kind, **kw):
        import webview
        fd = getattr(webview, 'FileDialog', None)
        kind = getattr(fd, kind) if fd else {'OPEN': webview.OPEN_DIALOG, 'FOLDER': webview.FOLDER_DIALOG}[kind]
        r = self._window.create_file_dialog(kind, **kw)
        return os.path.normpath(r[0]) if r else None

    def browse_nup(self, current=''):
        start = os.path.dirname(current) if current and os.path.isdir(os.path.dirname(current)) else os.path.expanduser('~')
        return self._dialog('OPEN', directory=start, file_types=('Switch 2 dump (*.nup)', 'All files (*.*)'))

    def browse_out(self, current=''):
        start = current if current and os.path.isdir(current) else os.path.expanduser('~')
        return self._dialog('FOLDER', directory=start)

    def check_nup(self, path):
        path = (path or '').strip()
        cached = bool(source.cached())
        if not path:
            return {'state': 'cached' if cached else 'empty', 'cached': cached}
        if not os.path.isfile(path):
            return {'state': 'error', 'message': 'File not found.', 'cached': cached}
        try:
            n, found = source.inspect(path)
            n.f.close()
        except source.SourceError as e:
            return {'state': 'error', 'message': str(e), 'cached': cached}
        return {'state': 'ok', 'count': len(found), 'cached': cached}

    def open_path(self, path):
        if path and os.path.exists(path):
            os.startfile(path)
        return True

    # --- generate ---------------------------------------------------------------------------
    def _log(self, msg):
        if self._window:
            self._window.evaluate_js('window.onLog && window.onLog(%s)' % json.dumps(msg))

    def _progress(self, done, total):
        pct = int(done * 1000 / max(total, 1))
        if pct != self._last_pct and self._window:
            self._last_pct = pct
            self._window.evaluate_js('window.onProgress && window.onProgress(%d, %d)' % (done // (1 << 20), total // (1 << 20)))

    def generate(self, opts):
        if self._busy:
            return {'ok': False, 'error': 'Already generating.'}
        self._busy = True
        self._last_pct = -1
        seed = (opts.get('seed') or '').strip() or randomize.random_seed()
        try:
            self.save(opts)
            make_nup, folder, zipped = bool(opts.get('make_nup', True)), bool(opts.get('folder')), bool(opts.get('zip'))
            if not (make_nup or folder or zipped):
                return {'ok': False, 'error': 'Choose at least one output: .nup, mod folder or .zip.'}
            res = randomize.generate(seed=seed, out=(opts.get('out') or '').strip() or DEFAULT_OUT,
                                     settings=opts.get('randomizer'), nup=(opts.get('nup') or '').strip() or None,
                                     write_spoiler=bool(opts.get('spoiler', True)), make_zip=zipped,
                                     make_nup=make_nup, make_folder=folder, progress=self._progress,
                                     nup_title=opts.get('nup_title', randomize.DEFAULT_TITLE),
                                     overwrite=bool(opts.get('overwrite')), log=self._log)
            res['name'] = 'OoTRando-' + randomize.safe_name(seed)
            return {'ok': True, 'result': res}
        except FileExistsError:
            return {'ok': False, 'exists': True, 'seed': seed}
        except (source.SourceError, nup_patch.NupError) as e:
            return {'ok': False, 'error': str(e)}
        except Exception as e:
            self._log(traceback.format_exc())
            return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}
        finally:
            self._busy = False


class TrackerApi:
    """Methods the tracker overlay calls. The overlay reads the newest save every 1.5 s."""

    def __init__(self):
        self._window = None
        self._mtime = None
        self._overlay = tracker.Overlay(TRACKER_TITLE)
        self._toggle = None

    def _settings(self):
        t = dict(tracker.DEFAULTS, alpha=0.9)
        t.update(load_settings().get('tracker') or {})
        return t

    def _start_toggle(self):
        if self._toggle is None:
            t = self._settings()
            self._toggle = tracker.Toggle(self._overlay.toggle, t['combo'], t['key'])
            self._toggle.start()

    def _icons(self):
        """Item icons decoded from the game files (cached). Empty if the game files aren't available."""
        try:
            rom = source.cached()
            if not rom:
                nup = load_settings().get('nup')
                if not nup or not os.path.isfile(nup):
                    return {}
                rom = source.prepare(nup, log=lambda *_: None)
            return tracker.icons(rom, os.path.join(os.path.dirname(rom), 'icons-' + os.path.basename(rom)[6:]))
        except Exception:
            return {}

    def init(self):
        self._start_toggle()
        snap = tracker.snapshot()
        self._mtime = snap.get('mtime')
        return {'state': snap, 'settings': self._settings(), 'icons': self._icons(),
                'combos': {k: v[0] for k, v in tracker.COMBOS.items()}, 'keys': list(tracker.KEYS)}

    def poll(self):
        """The new state when the save changed since the last call, else None."""
        path = tracker.latest_save()
        m = os.path.getmtime(path) if path else None
        if m == self._mtime:
            return None
        self._mtime = m
        return tracker.snapshot()

    def set_option(self, key, value):
        s = load_settings()
        t = dict(s.get('tracker') or {})
        if key in ('combo', 'key'):
            t[key] = value or ''
        elif key == 'alpha':
            t[key] = max(0.4, min(1.0, float(value)))
        s['tracker'] = t
        save_settings(s)
        if self._toggle:
            st = self._settings()
            self._toggle.set(st['combo'], st['key'])
        return True

    def hide(self):
        self._overlay.hide()
        return True


_tracker_window = None


def _screen_width():
    try:
        import ctypes
        return ctypes.windll.user32.GetSystemMetrics(0)
    except Exception:
        return 1920


def open_tracker():
    """Create the overlay window, or show it again if it exists."""
    global _tracker_window
    import webview
    if _tracker_window is not None:
        tracker.Overlay(TRACKER_TITLE).show()
        return _tracker_window
    api = TrackerApi()
    w, h = 380, 820
    _tracker_window = webview.create_window(TRACKER_TITLE, url=TRACKER_UI, js_api=api, width=w, height=h,
                                            x=max(0, _screen_width() - w - 24), y=72, frameless=True,
                                            easy_drag=False, on_top=True, transparent=True, focus=False,
                                            background_color='#06120c', resizable=True, min_size=(300, 320))
    api._window = _tracker_window
    return _tracker_window


def main():
    import webview
    updater.cleanup()
    if '--tracker' not in sys.argv and updater.pending():
        # a verified update was downloaded last time: switch to it before showing anything
        if updater.apply_and_restart():
            return
    if '--tracker' in sys.argv:  # just the overlay, for while you play
        open_tracker()
        webview.start(debug='--debug' in sys.argv)
        return
    api = Api()
    win = webview.create_window('%s %s' % (TITLE, randomize.VERSION), url=UI, js_api=api,
                                width=1180, height=860, min_size=(900, 680), background_color='#06120c')
    api._window = win
    webview.start(debug='--debug' in sys.argv)


if __name__ == '__main__':
    main()
