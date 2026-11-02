"""Zip the complete onedir build; preserve executable bits and macOS symlinks."""
import argparse
import os
import platform
import stat
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def package(root: Path, *, smoke_test=False, system=None, machine=None) -> Path:
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    dist = root / "dist"
    source = dist / ("PDFUkrainian.app" if system == "Darwin" else "PDFUkrainian")
    destination = dist / f"PDFUkrainian-{system}-{machine}.zip"
    if not source.is_dir():
        raise SystemExit("Build the app with PyInstaller first.")
    if smoke_test:
        executable = {
            "Darwin": source / "Contents/MacOS/PDFUkrainian",
            "Linux": source / "PDFUkrainian",
            "Windows": source / "PDFUkrainian.exe",
        }[system]
        command = [str(executable), "--smoke-test"]
        environment = os.environ.copy()
        environment.pop("QT_QPA_PLATFORM", None)
        if system == "Linux":
            command = ["xvfb-run", "-a", *command]
            environment["QT_QPA_PLATFORM"] = "xcb"
        subprocess.run(command, env=environment, check=True, timeout=60)
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
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true", help="Launch the packaged app before archiving")
    args = parser.parse_args()
    print(package(Path(__file__).resolve().parents[1], smoke_test=args.smoke_test))
