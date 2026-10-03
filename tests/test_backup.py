import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import backup_proof as tool


class BackupTests(unittest.TestCase):
    def test_windows_creation_and_change_times_do_not_cause_false_failure(self):
        common = dict(st_dev=1, st_ino=42, st_size=4, st_mtime_ns=100, st_birthtime_ns=50)
        path_metadata = SimpleNamespace(**common, st_ctime_ns=50)
        handle_metadata = SimpleNamespace(**common, st_ctime_ns=150)
        with patch.object(tool.os, 'name', 'nt'):
            self.assertEqual(tool.signature(path_metadata), tool.signature(handle_metadata))
            handle_metadata.st_mtime_ns = 200
            self.assertNotEqual(tool.signature(path_metadata), tool.signature(handle_metadata))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source'
        self.backup = Path(self.temp.name) / 'backup'
        self.source.mkdir()
        self.backup.mkdir()
        for root in (self.source, self.backup):
            (root / 'same.txt').write_text('same content')

    def test_matching_content_verified(self):
        result = tool.audit(self.source, self.backup)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['counts']['matched'], 1)

    def test_same_size_same_timestamp_different_content_detected(self):
        (self.backup / 'same.txt').write_text('evil content')
        src = (self.source / 'same.txt').stat()
        os.utime(self.backup / 'same.txt', ns=(src.st_atime_ns, src.st_mtime_ns))
        result = tool.audit(self.source, self.backup)
        self.assertEqual(result['status'], 'attention')
        self.assertEqual(result['findings'][0]['status'], 'mismatch')

    def test_missing_and_retained_history_reported_without_deletion(self):
        (self.source / 'missing.txt').write_text('new')
        (self.backup / 'old.txt').write_text('old')
        result = tool.audit(self.source, self.backup)
        self.assertEqual({f['status'] for f in result['findings']}, {'missing', 'extra'})
        self.assertTrue((self.backup / 'old.txt').exists())

    def test_empty_source_cannot_get_false_success(self):
        (self.source / 'same.txt').unlink()
        self.assertEqual(tool.audit(self.source, self.backup)['status'], 'incomplete')

    def test_exclusion_scope_is_disclosed(self):
        (self.source / 'temp.log').write_text('log')
        result = tool.audit(self.source, self.backup, ['*.log'])
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['excluded_paths']['source'], ['temp.log'])

    def test_unreadable_file_cannot_get_false_success(self):
        with patch.object(tool, 'digest', side_effect=PermissionError('Access denied')):
            result = tool.audit(self.source, self.backup)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['counts']['matched'], 0)

    def test_changed_tree_invalidates_audit(self):
        real_digest = tool.digest
        def changing(path, expected):
            value = real_digest(path, expected)
            if path.parent == self.source.resolve():
                (self.source / 'arrived.txt').write_text('new arrival')
            return value
        with patch.object(tool, 'digest', side_effect=changing):
            result = tool.audit(self.source, self.backup)
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(any('Tree changed' in i['reason'] for i in result['issues']))

    def test_overlap_and_output_in_tree_are_rejected(self):
        with self.assertRaises(ValueError):
            tool.audit(self.source, self.source)
        nested = self.source / 'nested'
        nested.mkdir()
        with self.assertRaises(ValueError):
            tool.audit(self.source, nested)
        with self.assertRaises(ValueError):
            tool.audit(self.source, self.backup, output=self.source / 'report')

    def test_links_are_not_followed(self):
        try:
            (self.source / 'link.txt').symlink_to(self.source / 'same.txt')
        except OSError:
            self.skipTest('This OS/user cannot create symlinks')
        result = tool.audit(self.source, self.backup)
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(any('link' in i['reason'].lower() for i in result['issues']))

    def test_hard_link_is_not_independent_backup(self):
        (self.backup / 'same.txt').unlink()
        try:
            os.link(self.source / 'same.txt', self.backup / 'same.txt')
        except OSError:
            self.skipTest('Hard links not supported here')
        self.assertEqual(tool.audit(self.source, self.backup)['status'], 'incomplete')

    def test_case_collision_is_visible_on_case_sensitive_filesystems(self):
        (self.source / 'Case.txt').write_text('a')
        (self.source / 'case.txt').write_text('b')
        if len(list(self.source.glob('*ase.txt'))) < 2:
            self.skipTest('Filesystem is case-insensitive')
        result = tool.audit(self.source, self.backup)
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(any('Case-colliding' in i['reason'] for i in result['issues']))


if __name__ == '__main__':
    unittest.main()
