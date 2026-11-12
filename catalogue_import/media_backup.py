"""Portable media backups: internal file links only, verified by a real restore."""
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import tarfile
from tempfile import TemporaryDirectory

from .excel import digest
from .sql_dump import ImportDataError


def snapshot_media(root):
    root = Path(root).resolve(strict=True)
    entries = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            try:
                target = path.resolve(strict=True)
            except (OSError, RuntimeError):
                raise ImportDataError(f'Invalid media symlink: {name}') from None
            if not target.is_relative_to(root) or not target.is_file():
                raise ImportDataError(f'Unsafe media symlink: {name}; target must be a file inside media.')
            entries[name] = {'type': 'symlink', 'target': target.relative_to(root).as_posix(),
                             'sha256': digest(target)}
        elif path.is_file():
            entries[name] = {'type': 'file', 'sha256': digest(path)}
        elif path.is_dir():
            entries[name] = {'type': 'directory'}
        else:
            raise ImportDataError(f'Unsupported media entry: {name}')
    return entries


def safe_name(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or str(path) != name or '\\' in name:
        raise ImportDataError(f'Unsafe archive path: {name}')
    return path


def restore_media(archive_path, manifest, destination):
    """Restore only into a new empty directory; never follow archive links."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or any(destination.iterdir()):
        raise ImportDataError('Restore destination must be an empty real directory.')
    for name, entry in manifest.items():
        safe_name(name)
        if entry['type'] == 'symlink':
            safe_name(entry['target'])
            if manifest.get(entry['target'], {}).get('type') != 'file':
                raise ImportDataError('Symlink target must be an archived regular file.')
        for parent in PurePosixPath(name).parents:
            if str(parent) != '.' and manifest.get(str(parent), {}).get('type') != 'directory':
                raise ImportDataError('Archive parent is not a declared directory.')
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = archive.getmembers()
        expected = {'media', *('media/' + name for name in manifest)}
        if len(members) != len(expected) or {m.name for m in members} != expected:
            raise ImportDataError('Archive members do not match media manifest.')
        for member in members:
            if member.name == 'media':
                if not member.isdir():
                    raise ImportDataError('Invalid archive root.')
                continue
            name = member.name.removeprefix('media/')
            safe_name(name)
            entry = manifest[name]
            if entry['type'] == 'directory' and member.isdir():
                continue
            if entry['type'] == 'file' and member.isfile():
                continue
            if entry['type'] == 'symlink' and member.issym():
                link = posixpath.relpath(entry['target'], posixpath.dirname(name) or '.')
                if member.linkname == link:
                    continue
            raise ImportDataError(f'Unexpected archive entry type or link: {name}')
        for name, entry in manifest.items():
            if entry['type'] == 'directory':
                (destination / name).mkdir(parents=True, exist_ok=True)
        for name, entry in manifest.items():
            if entry['type'] == 'file':
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile('media/' + name) as source, path.open('xb') as output:
                    import shutil
                    shutil.copyfileobj(source, output)
                if digest(path) != entry['sha256']:
                    raise ImportDataError(f'Restored media checksum mismatch: {name}')
        for name, entry in manifest.items():
            if entry['type'] == 'symlink':
                path = destination / name
                path.symlink_to(posixpath.relpath(entry['target'], posixpath.dirname(name) or '.'))
    if snapshot_media(destination) != manifest:
        raise ImportDataError('Restored media manifest mismatch.')


def backup_media(root, archive_path):
    root = Path(root).resolve(strict=True)
    manifest = snapshot_media(root)  # Validate ALL links before writing the archive.
    with tarfile.open(archive_path, 'w:gz') as archive:
        info = tarfile.TarInfo('media'); info.type = tarfile.DIRTYPE; info.mode = 0o755
        archive.addfile(info)
        for name, entry in manifest.items():
            info = tarfile.TarInfo('media/' + name)
            if entry['type'] == 'directory':
                info.type = tarfile.DIRTYPE; info.mode = 0o755
                archive.addfile(info)
            elif entry['type'] == 'symlink':
                info.type = tarfile.SYMTYPE; info.mode = 0o777
                info.linkname = posixpath.relpath(entry['target'], posixpath.dirname(name) or '.')
                archive.addfile(info)
            else:
                info.mode = 0o644
                # Refuse a file swapped for a symlink since the scan.
                fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as source:
                    info.size = os.fstat(source.fileno()).st_size
                    archive.addfile(info, source)
    if snapshot_media(root) != manifest:
        raise ImportDataError('Media changed during backup.')
    with TemporaryDirectory(prefix='abdeen-media-restore-') as temporary:
        restore_media(archive_path, manifest, Path(temporary) / 'media')
    return manifest
