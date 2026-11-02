# Build on the target OS: python -m PyInstaller --noconfirm --clean PDFUkrainian.spec
import sys

a = Analysis(['main.py'], pathex=[], binaries=[], datas=[], hiddenimports=[],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PDFUkrainian',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PDFUkrainian')
if sys.platform == 'darwin':
    app = BUNDLE(collection, name='PDFUkrainian.app', icon=None,
                 bundle_identifier='dev.learning.pdfukrainian',
                 info_plist={'CFBundleShortVersionString': '0.4.0',
                             'NSHighResolutionCapable': True})
