"""Refuse to commit or publish game files.

    py tools/check_no_game_files.py            # checks every file git tracks (CI does this)
    py tools/check_no_game_files.py --staged   # checks what is about to be committed (pre-commit hook)

Fails on dumps (.nup, .nsp, .xci, ...), on the game's own file formats (zstd, BNTX, event
flows, BYML, packs, ...), on anything under the folders that hold extracted or generated game
data (work/, out/, build/, dist/), and on any file over 2 MB. The repository only holds code
and small JSON tables; game files are always read from the user's own dump at run time.
"""
import os, subprocess, sys

BLOCKED_EXT = {
    '.nup', '.nsp', '.nsz', '.xci', '.xcz', '.nca', '.nro', '.nso', '.kip',        # dumps and executables
    '.zs', '.zst', '.bntx', '.bfevfl', '.byml', '.bgyml', '.pack', '.sarc', '.bfres',  # game file formats
    '.msbt', '.rsizetable', '.bcett', '.ainb', '.asb', '.baev', '.bars', '.bwav', '.bfsar', '.bnsh',
    '.part', '.sav',
}
BLOCKED_DIRS = ('work/', 'out/', 'build/', 'dist/', 'romfs/', 'exefs/')
MAX_BYTES = 2 * 1024 * 1024


def git_files(staged):
    cmd = ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'] if staged else ['git', 'ls-files']
    return [f for f in subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.splitlines() if f]


def problems(files):
    out = []
    for f in files:
        p = f.replace('\\', '/')
        low = p.lower()
        ext = os.path.splitext(low)[1]
        if ext in BLOCKED_EXT or any(low.endswith(e) for e in ('.byml.zs', '.pack.zs', '.bfevfl.zs')):
            out.append('%s: game file type (%s)' % (p, ext))
        elif any(low.startswith(d) or ('/' + d) in low for d in BLOCKED_DIRS):
            out.append('%s: inside a folder for extracted or generated game data' % p)
        elif os.path.isfile(p) and os.path.getsize(p) > MAX_BYTES:
            out.append('%s: %.1f MB is too big for this repository' % (p, os.path.getsize(p) / 1e6))
    return out


if __name__ == '__main__':
    bad = problems(git_files('--staged' in sys.argv))
    if bad:
        print('Blocked: these must never be committed or published:')
        for b in bad: print('  ' + b)
        sys.exit(1)
    print('ok: no game files')
