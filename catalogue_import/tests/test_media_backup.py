from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile

from django.test import SimpleTestCase

from catalogue_import.excel import digest
from catalogue_import.media_backup import backup_media, restore_media
from catalogue_import.sql_dump import ImportDataError


class MediaBackupTests(SimpleTestCase):
    def setUp(self):
        self.temp = self.enterContext(TemporaryDirectory())
        self.base = Path(self.temp)
        self.media = self.base / 'media'
        (self.media / 'photos').mkdir(parents=True)
        (self.media / 'photos/watch.jpg').write_bytes(b'original-photo')
        self.archive = self.base / 'backup.tar.gz'

    def test_regular_files_restore_with_identical_bytes(self):
        manifest = backup_media(self.media, self.archive)
        restore_media(self.archive, manifest, self.base / 'restored')
        self.assertEqual(digest(self.media / 'photos/watch.jpg'), digest(self.base / 'restored/photos/watch.jpg'))

    def test_internal_relative_and_absolute_links_restore_portably(self):
        (self.media / 'relative.jpg').symlink_to('photos/watch.jpg')
        (self.media / 'absolute.jpg').symlink_to(self.media / 'photos/watch.jpg')
        manifest = backup_media(self.media, self.archive)
        restored = self.base / 'restored'
        restore_media(self.archive, manifest, restored)
        for name in ['relative.jpg', 'absolute.jpg']:
            self.assertTrue((restored / name).is_symlink())
            self.assertEqual((restored / name).readlink(), Path('photos/watch.jpg'))
            self.assertEqual((restored / name).resolve(), restored / 'photos/watch.jpg')

    def test_external_target_is_rejected_even_when_readable(self):
        (self.base / 'outside.jpg').write_bytes(b'external')
        (self.media / 'bad.jpg').symlink_to('../outside.jpg')
        with self.assertRaises(ImportDataError):
            backup_media(self.media, self.archive)
        self.assertFalse(self.archive.exists())

    def test_dangling_target_is_rejected(self):
        (self.media / 'bad.jpg').symlink_to('missing.jpg')
        with self.assertRaises(ImportDataError):
            backup_media(self.media, self.archive)

    def test_link_loop_is_rejected(self):
        (self.media / 'a').symlink_to('b')
        (self.media / 'b').symlink_to('a')
        with self.assertRaises(ImportDataError):
            backup_media(self.media, self.archive)

    def test_directory_link_is_rejected(self):
        (self.media / 'directory').symlink_to('photos', target_is_directory=True)
        with self.assertRaises(ImportDataError):
            backup_media(self.media, self.archive)

    def test_corrupt_content_rejected_during_restore(self):
        manifest = backup_media(self.media, self.archive)
        manifest['photos/watch.jpg']['sha256'] = '0' * 64
        with self.assertRaises(ImportDataError):
            restore_media(self.archive, manifest, self.base / 'restored')

    def test_archive_link_tampering_is_rejected(self):
        (self.media / 'link.jpg').symlink_to('photos/watch.jpg')
        manifest = backup_media(self.media, self.archive)
        with tarfile.open(self.archive, 'r:gz') as source:
            entries = [(m, source.extractfile(m).read() if m.isfile() else None) for m in source.getmembers()]
        with tarfile.open(self.archive, 'w:gz') as archive:
            for member, content in entries:
                if member.issym():
                    member.linkname = '/etc/passwd'
                archive.addfile(member, BytesIO(content) if content is not None else None)
        with self.assertRaises(ImportDataError):
            restore_media(self.archive, manifest, self.base / 'restored')

    def test_traversal_manifest_and_nonempty_destination_rejected(self):
        manifest = backup_media(self.media, self.archive)
        with self.assertRaises(ImportDataError):
            restore_media(self.archive, {'../escape': {'type': 'file'}}, self.base / 'restored')
        with self.assertRaises(ImportDataError):
            restore_media(self.archive, manifest, self.media)
