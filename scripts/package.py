"""Zip the complete onedir build; preserve executable bits and macOS symlinks."""
import os
import platform
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

root = Path(__file__).resolve().parents[1]
dist = root / "dist"
source = dist / ("PDFUkrainian.app" if platform.system() == "Darwin" else "PDFUkrainian")
destination = dist / f"PDFUkrainian-{platform.system()}-{platform.machine()}.zip"
if not source.is_dir():
    raise SystemExit("Build the app with PyInstaller first.")
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for directory, directories, files in os.walk(source, followlinks=False):
        for name in directories + files:
            path = Path(directory) / name
            relative = path.relative_to(dist).as_posix()
            if path.is_symlink():
                entry = ZipInfo(relative)
                entry.create_system = 3
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(entry, os.readlink(path))
            elif path.is_file():
                archive.write(path, relative)
print(destination)
