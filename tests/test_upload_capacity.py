"""Public upload capacity regression tests use only explicit SYNTHETIC data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from business_fixtures import csv_bytes, synthetic_rows
from business_store import BusinessError, BusinessStore, owner_key
import business_service as service
import business_worker as worker
from runtime_config import configure, LOCAL_UPLOAD_LIMITS, PUBLIC_UPLOAD_LIMITS


META = {'currency': 'AUD', 'time_zone': 'Australia/Sydney', 'sales_basis': 'gross_units',
        'tax_basis': 'exclusive', 'authorized': 'true'}


class PublicUploadPolicyTests(unittest.TestCase):
    def configured(self, public, **values):
        app = Flask('SYNTHETIC_capacity_policy')
        with patch.dict(os.environ, {}, clear=True):
            configure(app, dict(PUBLIC_MODE=public, SECRET_KEY='SYNTHETIC-test-secret-' * 3, **values))
        return app

    def test_public_budget_is_small_without_opening_uploads(self):
        app = self.configured(True)
        self.assertFalse(app.config['ENABLE_BUSINESS_UPLOAD'])
        for key, value in PUBLIC_UPLOAD_LIMITS.items():
            self.assertEqual(app.config[key], value)
        self.assertEqual(app.config['BUSINESS_MAX_FILE_BYTES'], 1024 * 1024)
        self.assertEqual(app.config['BUSINESS_MAX_JOBS'], 1)
        self.assertEqual(app.config['BUSINESS_WORKER_MEMORY_BYTES'], 128 * 1024 * 1024)

    def test_local_limits_remain_compatible(self):
        app = self.configured(False)
        for key, value in LOCAL_UPLOAD_LIMITS.items():
            self.assertEqual(app.config[key], value)
        self.assertEqual(app.config['BUSINESS_MAX_FILE_BYTES'], 5 * 1024 * 1024)
        self.assertEqual(app.config['BUSINESS_MAX_ROWS'], 50000)

    def test_public_configuration_cannot_raise_capacity(self):
        app = self.configured(True, BUSINESS_MAX_JOBS=500, BUSINESS_MAX_ROWS=900000,
                              BUSINESS_MAX_FILE_BYTES=1)
        self.assertEqual(app.config['BUSINESS_MAX_JOBS'], 1)
        self.assertEqual(app.config['BUSINESS_MAX_ROWS'], 10000)
        self.assertEqual(app.config['BUSINESS_MAX_FILE_BYTES'], 1)
        with self.assertRaises(ValueError):
            self.configured(True, BUSINESS_MAX_SESSIONS=False)

    def test_linux_refuses_to_run_if_resource_policy_cannot_be_applied(self):
        with patch.object(worker.sys, 'platform', 'linux'), \
                patch('resource.setrlimit', side_effect=OSError('SYNTHETIC unavailable')):
            with self.assertRaises(RuntimeError):
                worker.apply_resource_limits()

    def test_linux_uses_only_server_supplied_bounded_memory_limit(self):
        with patch.object(worker.sys, 'platform', 'linux'), \
                patch.dict(os.environ, {'MARGINGUARD_WORKER_MEMORY_BYTES': str(128 * 1024 * 1024)}), \
                patch('resource.setrlimit') as setter:
            worker.apply_resource_limits()
            self.assertEqual(setter.call_args.args[1], (128 * 1024 * 1024,) * 2)
        with patch.object(worker.sys, 'platform', 'linux'), \
                patch.dict(os.environ, {'MARGINGUARD_WORKER_MEMORY_BYTES': '99999999999999'}), \
                patch('resource.setrlimit'):
            with self.assertRaises(RuntimeError):
                worker.apply_resource_limits()

    def test_oversized_worker_output_is_replaced_without_original_content(self):
        result = worker.encode_output({'ok': True, 'result': 'SYNTHETIC_PRIVATE_VALUE' * 500}, 1024)
        self.assertLessEqual(len(result), 1024)
        self.assertNotIn(b'SYNTHETIC_PRIVATE_VALUE', result)
        self.assertEqual(json.loads(result)['status'], 413)


class PublicUploadCapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='marginguard-synthetic-capacity-')
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000000.0
        self.store = BusinessStore(
            self.temp.name, clock=lambda: self.now, max_file_bytes=1024 * 1024,
            max_rows=10000, max_series=20, max_dataset_bytes=2 * 1024 * 1024,
            max_bytes=16 * 1024 * 1024, max_jobs=1, max_sessions=20,
            worker_memory_bytes=128 * 1024 * 1024,
            max_worker_output_bytes=2 * 1024 * 1024 + 64 * 1024)
        token, _, _ = self.store.create_session()
        self.owner = owner_key(token)

    def assert_no_jobs(self):
        with sqlite3.connect(str(self.store.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)

    def test_global_rate_shared_by_store_instances_and_atomic(self):
        second = BusinessStore(self.temp.name, clock=lambda: self.now)
        def attempt(store):
            try:
                store.global_rate('SYNTHETIC_global_upload', 1, 60)
                return 'allowed'
            except BusinessError as error:
                self.assertEqual(error.status, 429)
                return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(attempt, (self.store, second))), ['allowed', 'blocked'])

    def test_new_owner_and_cleanup_do_not_reset_current_global_window(self):
        self.store.global_rate('SYNTHETIC_upload', 1, 60)
        self.store.delete_session(self.owner)
        self.store.create_session()
        self.store.cleanup()
        with self.assertRaises(BusinessError) as caught:
            self.store.global_rate('SYNTHETIC_upload', 1, 60)
        self.assertEqual(caught.exception.code, 'global_rate_limit')
        self.now += 61
        self.store.cleanup()
        with sqlite3.connect(str(self.store.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM global_rates').fetchone()[0], 0)
        self.store.global_rate('SYNTHETIC_upload', 1, 60)

    def test_global_rate_rejects_invalid_policy_without_sql_effects(self):
        for args in (('', 1, 60), ('SYNTHETIC', 0, 60), ('SYNTHETIC', 1, False)):
            with self.assertRaises(ValueError):
                self.store.global_rate(*args)

    def test_public_session_limit_rejects_without_affecting_existing_owner(self):
        for _ in range(19):
            self.store.create_session()
        with self.assertRaises(BusinessError) as caught:
            self.store.create_session()
        self.assertEqual(caught.exception.status, 429)
        self.store.authenticate(self.owner)

    def test_file_above_public_limit_is_rejected_before_worker(self):
        with patch('business_service.run_worker') as call:
            with self.assertRaises(BusinessError) as caught:
                service.upload(self.store, self.owner, b'x' * (1024 * 1024 + 1), META)
            self.assertEqual(caught.exception.status, 413)
            call.assert_not_called()
        self.assert_no_jobs()

    def test_public_rows_and_series_caps_use_existing_parser(self):
        batches = [
            [row for k in range(10) for row in synthetic_rows(1000, product='SYNTHETIC_%02d' % k,
                                                            start=date(2020, 1, 1))]
            + synthetic_rows(1, product='SYNTHETIC_EXTRA'),
            [row for k in range(21) for row in synthetic_rows(42, product='SYNTHETIC_%02d' % k)],
        ]
        for rows, code in zip(batches, ('too_many_rows', 'too_many_series')):
            content = csv_bytes(rows)
            self.assertLess(len(content), 1024 * 1024)
            with self.assertRaises(BusinessError) as caught:
                service.upload(self.store, self.owner, content, META)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(caught.exception.status, 413)
            self.assert_no_jobs()

    def test_worker_rejects_normalized_oversize_and_releases_capacity(self):
        self.store.max_dataset_bytes = 100
        with self.assertRaises(BusinessError) as caught:
            service.upload(self.store, self.owner, csv_bytes(synthetic_rows()), META)
        self.assertEqual(caught.exception.code, 'normalized_too_large')
        self.assert_no_jobs()
        self.assertIsNone(self.store.active(self.owner))

    def test_maximum_public_rows_and_series_complete_real_worker_pipeline(self):
        rows = [row for k in range(20) for row in synthetic_rows(
            500, product='SYNTHETIC_%02d' % k, start=date(2020, 1, 1))]
        content = csv_bytes(rows)
        self.assertLess(len(content), self.store.max_file_bytes)
        pending = service.upload(self.store, self.owner, content, META)
        self.assertEqual(pending['report']['summary']['row_count'], 10000)
        self.assertEqual(len(pending['series']), 20)
        choices = [{key: row[key] for key in ('series_id', 'start_date', 'end_date')}
                   for row in pending['series']]
        ready = service.confirm(self.store, self.owner, pending['upload_id'],
                                {'revision': pending['revision'], 'selections': choices})
        self.assertEqual(len(ready['series']), 20)
        self.assertTrue(all(row['observations'] == 500 for row in ready['series']))
        self.assert_no_jobs()

    def test_processing_slot_is_held_until_parent_saves_and_confirmation_finishes(self):
        other, _, _ = self.store.create_session()
        other_owner = owner_key(other)
        original = self.store.save_pending
        def checked_save(*args):
            with self.assertRaises(BusinessError) as caught:
                self.store.acquire_job(other_owner, 30)
            self.assertEqual(caught.exception.code, 'processing_busy')
            return original(*args)
        with patch.object(self.store, 'save_pending', side_effect=checked_save):
            pending = service.upload(self.store, self.owner, csv_bytes(synthetic_rows(84)), META)
        self.assert_no_jobs()
        original_confirm = self.store.confirm
        def checked_confirm(*args):
            with self.assertRaises(BusinessError):
                self.store.acquire_job(other_owner, 30)
            return original_confirm(*args)
        selections = [{key: row[key] for key in ('series_id', 'start_date', 'end_date')}
                      for row in pending['series']]
        with patch.object(self.store, 'confirm', side_effect=checked_confirm):
            ready = service.confirm(self.store, self.owner, pending['upload_id'],
                                    {'revision': pending['revision'], 'selections': selections})
        self.assert_no_jobs()
        self.assertEqual(ready['meta']['currency'], 'AUD')
        self.assertEqual(ready['series'][0]['observations'], 84)

    def test_failed_parent_persistence_releases_the_single_shared_slot(self):
        with patch.object(self.store, 'save_pending', side_effect=BusinessError('storage_capacity', 'SYNTHETIC full', 429)):
            with self.assertRaises(BusinessError):
                service.upload(self.store, self.owner, csv_bytes(synthetic_rows()), META)
        self.assert_no_jobs()
        lease = self.store.acquire_job(self.owner, 30)
        self.store.release_job(lease)


if __name__ == '__main__':
    unittest.main()
