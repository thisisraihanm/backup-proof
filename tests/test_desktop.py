import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import desktop
from friendly import explain, friendly_error, UserInputError
from report import write_report


class DesktopTests(unittest.TestCase):
    def test_offline_example_explained_without_claiming_repair(self):
        result = desktop.demo()
        headline, meaning, action = explain(result, desktop.TITLE)
        self.assertTrue(headline and meaning and action)
        self.assertNotIn('everything is healthy', (headline+meaning).lower())

    def test_example_label_and_plain_language_report(self):
        result = desktop.demo(); result['demo'] = True
        with tempfile.TemporaryDirectory() as temp:
            path = write_report(result, Path(temp)/'example', desktop.TITLE)
            page = path.read_text()
            self.assertIn('Fictional data', page)
            self.assertIn('What you can do next', page)
            self.assertIn('Details for IT support', page)
            self.assertNotIn('<script', page.lower())

    def test_actionable_validation_message(self):
        self.assertEqual(friendly_error(UserInputError('Choose both folders first.')), 'Choose both folders first.')
        self.assertIn('different computers', friendly_error(ValueError('Snapshots must describe the same host and platform')))
        self.assertIn('separate folders', friendly_error(ValueError('Source and backup must be separate, non-overlapping trees')))

    def test_real_widgets_and_async_example_when_display_available(self):
        import tkinter as tk
        try:
            root = tk.Tk(); root.destroy()
        except tk.TclError:
            self.skipTest('No desktop display in this environment; Windows packaging runs this check.')
        self.assertEqual(desktop.self_test(), 0)

    def test_folder_selection_required(self):
        with self.assertRaises(UserInputError):desktop.check({'first':'','second':''})

    def test_matching_folders_and_report_not_written_inside_them(self):
        import backup_proof as core
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source';backup=Path(directory)/'backup'
            source.mkdir();backup.mkdir()
            (source/'a.txt').write_text('same');(backup/'a.txt').write_text('same')
            result=desktop.check({'first':str(source),'second':str(backup)})
            self.assertEqual(result['status'],'verified')
            with self.assertRaises(ValueError):core.validate_roots(source,backup,source/'report')
