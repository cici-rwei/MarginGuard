"""Packaging tests use disposable, explicitly SYNTHETIC source/data fixtures."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.package_final import ALLOWLIST, ARCHIVE_NAME, REQUIRED_FILES, package


class FinalPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'MarginGuard'
        self.root.mkdir()
        for relative in REQUIRED_FILES:
            self.write(relative, 'SYNTHETIC packaging fixture: ' + relative)
        self.target = self.base / ARCHIVE_NAME

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def test_manifest_hashes_match_every_source_and_raw_directory_is_empty(self):
        result = package(source_root=self.root)
        self.assertEqual(Path(result['path']), self.target)
        with ZipFile(self.target) as archive:
            self.assertIsNone(archive.testzip())
            manifest = json.loads(archive.read('MarginGuard/MANIFEST.json'))
            self.assertFalse(manifest['contains_walmart_history'])
            self.assertFalse(manifest['contains_private_business_uploads'])
            self.assertEqual(manifest['missing_required_files'], [])
            self.assertEqual(len(manifest['files']), result['files'])
            for entry in manifest['files']:
                payload = archive.read('MarginGuard/' + entry['path'])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), entry['sha256'])
                self.assertEqual(len(payload), entry['size_bytes'])
            self.assertIn('MarginGuard/data/raw/', archive.namelist())
            self.assertFalse(any(name.startswith('MarginGuard/data/raw/') and not name.endswith('/') for name in archive.namelist()))
            self.assertIn('M5 sales history', archive.read('MarginGuard/PACKAGE_SCOPE.md').decode())

    def test_private_observed_data_unknown_code_and_historical_evidence_are_excluded(self):
        excluded = (
            '.env', '.env.production', 'secret.fake.py', 'private/customer.db',
            'tests/test_secret.py', 'tests/secret.fake.py', 'scripts/secret.fake.py',
            'static/js/secrets.js', 'templates/private.html', '.runtime/server.log',
            'research/download.zip', '.venv/bin/python', '__pycache__/app.pyc',
            'data/raw/sales_train_validation.csv', 'data/calendar.csv',
            'data/processed_sales.csv', 'data/processed_sales.validation.json',
            'data/forecast_results.json', 'data/forecast_results_future.json',
            'data/phase2_demo.json', 'data/source_audit.json', 'data/business.sqlite3',
            'data/abs/private.db', 'examples/business_csv/private_sales.csv',
            'PHASE1_REPORT.md', 'PHASE2_REPORT.md', 'PHASE3_REPORT.md',
            'phase3_preview.png', 'screenshots/m5_history.png',
            'screenshots/synthetic_notes.txt', 'screenshots/abs_private.sqlite',
            'screenshots/nested/synthetic_hidden.png', 'MarginGuard_old.zip',
        )
        for relative in excluded:
            self.write(relative, 'SYNTHETIC sensitive sentinel')
        self.write('screenshots/synthetic_upload.png', 'SYNTHETIC image fixture')
        self.write('screenshots/abs_market.webp', 'SYNTHETIC image fixture')
        package(self.target, source_root=self.root)
        with ZipFile(self.target) as archive:
            names = set(archive.namelist())
            for relative in excluded:
                self.assertNotIn('MarginGuard/' + relative, names)
            self.assertIn('MarginGuard/screenshots/synthetic_upload.png', names)
            self.assertIn('MarginGuard/screenshots/abs_market.webp', names)
            self.assertTrue(all(name.startswith('MarginGuard/') for name in names))

    def test_existing_archive_is_never_overwritten(self):
        self.target.write_bytes(b'SYNTHETIC earlier backup')
        with self.assertRaises(FileExistsError):
            package(self.target, source_root=self.root)
        self.assertEqual(self.target.read_bytes(), b'SYNTHETIC earlier backup')

    def test_source_bytes_and_modification_times_are_preserved(self):
        self.write('data/raw/original.csv', 'SYNTHETIC raw data should remain untouched')
        paths = [path for path in self.root.rglob('*') if path.is_file()]
        before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
        package(self.target, source_root=self.root)
        after = {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
        self.assertEqual(before, after)

    def test_allowlisted_file_symlink_is_rejected_without_reading_target(self):
        outside = self.base / 'SYNTHETIC_SECRET.txt'
        outside.write_text('SYNTHETIC secret', encoding='utf-8')
        self.root.joinpath('README.md').unlink()
        self.root.joinpath('README.md').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            package(self.target, source_root=self.root)
        self.assertFalse(self.target.exists())

    def test_symlink_directory_cannot_smuggle_an_allowlisted_file(self):
        outside = self.base / 'SYNTHETIC_OUTSIDE'
        outside.mkdir()
        (outside / 'main.js').write_text('SYNTHETIC private data', encoding='utf-8')
        for path in (self.root / 'static/js').iterdir():
            path.unlink()
        (self.root / 'static/js').rmdir()
        (self.root / 'static/js').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            package(self.target, source_root=self.root)
        self.assertFalse(self.target.exists())

    def test_unlisted_symlink_is_not_followed_or_packaged(self):
        outside = self.base / 'SYNTHETIC_OUTSIDE'
        outside.mkdir()
        (outside / 'private.db').write_text('SYNTHETIC private data', encoding='utf-8')
        (self.root / 'private_uploads').symlink_to(outside, target_is_directory=True)
        package(self.target, source_root=self.root)
        with ZipFile(self.target) as archive:
            self.assertFalse(any('private_uploads' in name for name in archive.namelist()))

    def test_allowed_screenshot_symlink_is_rejected(self):
        outside = self.base / 'SYNTHETIC_SECRET.txt'
        outside.write_text('SYNTHETIC secret', encoding='utf-8')
        (self.root / 'screenshots').mkdir()
        (self.root / 'screenshots/synthetic_upload.png').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            package(self.target, source_root=self.root)
        self.assertFalse(self.target.exists())

    def test_missing_final_report_prevents_incomplete_final_handoff(self):
        self.root.joinpath('FINAL_QA_REPORT.md').unlink()
        with self.assertRaisesRegex(ValueError, 'FINAL_QA_REPORT.md'):
            package(self.target, source_root=self.root)
        self.assertFalse(self.target.exists())

    def test_archive_cannot_be_written_inside_project(self):
        with self.assertRaisesRegex(ValueError, 'outside the project'):
            package(self.root / ARCHIVE_NAME, source_root=self.root)

    def test_reviewed_backend_frontend_config_and_abs_files_are_allowlisted(self):
        expected = {
            'currency.py', 'runtime_config.py', 'business_api.py', 'business_store.py',
            'business_service.py', 'business_worker.py', 'static/js/business_context.js',
            'static/js/business_upload.js', 'tests/business_context.test.js',
            'requirements-production.txt', 'gunicorn.conf.py',
            'wsgi.py', '.python-version', 'render.yaml', '.gitignore', 'start.command',
            'data/abs/market_data.json.gz', 'data/abs/sources.json',
            'examples/business_csv/synthetic_multi_series.csv',
            'synthetic_demo.py', 'tests/test_synthetic_demo.py',
            '.github/workflows/ci.yml', 'PUBLIC_DEPLOYMENT_REPORT.md',
            'DEPLOYMENT_FILE_AUDIT.md', 'deployment_files.json',
        }
        self.assertTrue(expected.issubset(ALLOWLIST))


if __name__ == '__main__':
    unittest.main()
