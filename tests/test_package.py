import os
import stat
from zipfile import ZipFile

import pytest

from scripts.package import package


@pytest.mark.parametrize('system,machine,folder,executable,architecture', [
    ('Windows', 'AMD64', 'PDFUkrainian', 'PDFUkrainian.exe', 'x86_64'),
    ('Linux', 'x86_64', 'PDFUkrainian', 'PDFUkrainian', 'x86_64'),
    ('Darwin', 'arm64', 'PDFUkrainian.app', 'Contents/MacOS/PDFUkrainian', 'arm64'),
])
def test_package_contains_executable_and_dependencies(tmp_path, system, machine, folder, executable, architecture):
    source = tmp_path / 'dist' / folder
    binary = source / executable
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'application')
    dependency = source / '_internal' / 'QtCore'
    dependency.parent.mkdir()
    dependency.write_bytes(b'library')
    result = package(tmp_path, system=system, machine=machine)
    assert result.name == f'PDFUkrainian-{system}-{architecture}.zip'
    with ZipFile(result) as archive:
        assert archive.read(f'{folder}/{executable}') == b'application'
        assert archive.read(f'{folder}/_internal/QtCore') == b'library'


@pytest.mark.skipif(os.name == 'nt', reason='Creating symlinks needs extra Windows privileges')
def test_mac_zip_preserves_symlinks_and_executable_permissions(tmp_path):
    source = tmp_path / 'dist' / 'PDFUkrainian.app'
    version = source / 'Versions' / 'A'
    version.mkdir(parents=True)
    binary = version / 'binary'
    binary.write_bytes(b'application')
    binary.chmod(0o755)
    (source / 'Versions' / 'Current').symlink_to('A', target_is_directory=True)
    result = package(tmp_path, system='Darwin', machine='arm64')
    with ZipFile(result) as archive:
        info = archive.getinfo('PDFUkrainian.app/Versions/Current')
        assert stat.S_ISLNK(info.external_attr >> 16)
        assert archive.read(info) == b'A'
        executable = archive.getinfo('PDFUkrainian.app/Versions/A/binary')
        assert executable.external_attr >> 16 & 0o111 == 0o111
