"""Build dist/OoTRando.exe, a single-file Windows app (no Python needed to run it).

    py -m pip install pyinstaller zstandard pywebview texture2ddecoder
    py build_exe.py

The exe carries the randomizer code, ui/ (the app's page) and data/ (location list, item
names and forms, file manifest). The window needs the Edge WebView2 runtime (part of Windows 11).
It contains no game files: those are read from the user's own .nup at run time.
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == '__main__':
    sep = ';' if os.name == 'nt' else ':'
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
           '--name', 'OoTRando',
           '--paths', os.path.join(HERE, 'tools'),
           '--add-data', os.path.join(HERE, 'data') + sep + 'data',
           '--add-data', os.path.join(HERE, 'ui') + sep + 'ui',
           '--exclude-module', 'tkinter',
           '--distpath', os.path.join(HERE, 'dist'),
           '--workpath', os.path.join(HERE, 'build'),
           '--specpath', os.path.join(HERE, 'build'),
           os.path.join(HERE, 'OoTRando.pyw')]
    subprocess.check_call(cmd, cwd=HERE)
    print('built', os.path.join(HERE, 'dist', 'OoTRando.exe'))
