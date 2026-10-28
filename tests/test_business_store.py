"""Private-storage tests use artificial JSON only, never real business data."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from business_store import BusinessError, BusinessStore, owner_key


class BusinessStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000000.0
        self.store = BusinessStore(self.temp.name, clock=lambda: self.now)
        token, self.csrf, _ = self.store.create_session()
        self.owner = owner_key(token)

    def pending(self, payload=None):
        return self.store.save_pending(self.owner, payload or {'fixture': 'SYNTHETIC'})

    def test_private_location_and_permissions(self):
        self.assertEqual(self.store.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            BusinessStore(Path(__file__).resolve().parents[1])

    def test_cross_owner_read_and_delete_are_rejected(self):
        identifier, revision = self.pending()
        other, _, _ = self.store.create_session()
        for action in (lambda: self.store.load(owner_key(other), identifier),
                       lambda: self.store.delete(owner_key(other), identifier)):
            with self.assertRaises(BusinessError) as caught:
                action()
            self.assertEqual(caught.exception.status, 404)
        self.assertEqual(self.store.load(self.owner, identifier)['revision'], revision)

    def test_new_pending_replaces_only_pending_preserving_ready(self):
        first, rev = self.pending()
        confirmed = self.store.confirm(self.owner, first, rev, {'fixture': 'SYNTHETIC ready'})
        second, _ = self.pending({'fixture': 'SYNTHETIC pending one'})
        third, _ = self.pending({'fixture': 'SYNTHETIC pending two'})
        self.assertEqual(self.store.load(self.owner, first)['revision'], confirmed)
        with self.assertRaises(BusinessError):
            self.store.load(self.owner, second)
        self.assertEqual(self.store.load(self.owner, third)['state'], 'pending')

    def test_confirmation_is_atomic_and_invalidates_previous_dataset(self):
        first, rev = self.pending()
        self.store.confirm(self.owner, first, rev, {'fixture': 'SYNTHETIC ready'})
        second, rev2 = self.pending()
        with self.assertRaises(BusinessError):
            self.store.confirm(self.owner, second, 'wrong', {'fixture': 'SYNTHETIC'})
        self.store.load(self.owner, first)
        self.store.confirm(self.owner, second, rev2, {'fixture': 'SYNTHETIC replacement'})
        with self.assertRaises(BusinessError):
            self.store.load(self.owner, first)
        self.assertEqual(self.store.active(self.owner)['dataset_id'], second)

    def test_duplicate_confirmation_does_not_create_another_dataset(self):
        identifier, revision = self.pending()
        self.store.confirm(self.owner, identifier, revision, {'fixture': 'SYNTHETIC'})
        with self.assertRaises(BusinessError) as caught:
            self.store.confirm(self.owner, identifier, revision, {'fixture': 'SYNTHETIC'})
        self.assertEqual(caught.exception.status, 409)

    def test_pending_expiry_is_checked_without_a_sweeper(self):
        identifier, _ = self.pending()
        self.now += 901
        with self.assertRaises(BusinessError) as caught:
            self.store.load(self.owner, identifier)
        self.assertEqual(caught.exception.status, 410)

    def test_idle_expiry_rejects_all_resources(self):
        identifier, _ = self.pending()
        self.now += 1801
        with self.assertRaises(BusinessError) as caught:
            self.store.load(self.owner, identifier)
        self.assertEqual(caught.exception.status, 401)

    def test_touches_cannot_extend_absolute_expiry(self):
        for _ in range(7):
            self.now += 1000
            self.store.authenticate(self.owner)
        self.now += 201
        with self.assertRaises(BusinessError):
            self.store.authenticate(self.owner)

    def test_cleanup_removes_expired_payloads_and_startup_can_repeat(self):
        self.pending()
        self.now += 8000
        self.store.cleanup()
        self.store.cleanup()
        with sqlite3.connect(str(self.store.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM datasets').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)

    def test_delete_session_removes_payload_and_access(self):
        identifier, _ = self.pending()
        self.store.delete_session(self.owner)
        with self.assertRaises(BusinessError):
            self.store.load(self.owner, identifier)
        with sqlite3.connect(str(self.store.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM datasets').fetchone()[0], 0)

    def test_storage_and_dataset_quotas_do_not_destroy_existing_data(self):
        identifier, _ = self.pending()
        self.store.max_dataset_bytes = 10
        with self.assertRaises(BusinessError) as caught:
            self.pending({'fixture': 'SYNTHETIC too large'})
        self.assertEqual(caught.exception.status, 413)
        self.store.max_dataset_bytes = 1000
        self.store.max_bytes = 1
        with self.assertRaises(BusinessError) as caught:
            self.pending({'fixture': 'SYNTHETIC blocked'})
        self.assertEqual(caught.exception.status, 429)
        self.store.load(self.owner, identifier)

    def test_concurrent_rate_limit_is_atomic(self):
        def attempt(_):
            try:
                self.store.rate(self.owner, 'synthetic', 1, 60)
                return 'allowed'
            except BusinessError:
                return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(attempt, range(2))), ['allowed', 'blocked'])

    def test_job_slots_are_global_and_expire_after_worker_failure(self):
        self.store.max_jobs = 1
        job = self.store.acquire_job(self.owner, 10)
        other, _, _ = self.store.create_session()
        with self.assertRaises(BusinessError):
            self.store.acquire_job(owner_key(other), 10)
        self.now += 11
        replacement = self.store.acquire_job(owner_key(other), 10)
        self.store.release_job(job)
        self.store.release_job(replacement)

    def test_connections_are_closed_even_after_errors(self):
        with self.store._connect() as db:
            db.execute('BEGIN IMMEDIATE')
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute('SELECT 1')
        with self.assertRaises(RuntimeError):
            with self.store._connect() as failed:
                failed.execute('BEGIN IMMEDIATE')
                raise RuntimeError('SYNTHETIC')
        with self.assertRaises(sqlite3.ProgrammingError):
            failed.execute('SELECT 1')


if __name__ == '__main__':
    unittest.main()
