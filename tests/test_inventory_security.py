"""Public-profile inventory security integration with SYNTHETIC data only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import io
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from flask.wrappers import Request

from business_api import create_business_blueprint, get_business_store
from business_fixtures import csv_bytes, synthetic_rows, PRODUCT, STORE, START
from business_store import owner_key
from runtime_config import configure


class InventorySecurityTests(unittest.TestCase):
    """Independent fixture; intentionally does not inherit existing API tests."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000001.0
        self.app = Flask(__name__)
        configure(self.app, {
            'TESTING': True, 'PUBLIC_MODE': True,
            'SECRET_KEY': 'SYNTHETIC inventory security key ' * 3,
            'ENABLE_BUSINESS_UPLOAD': True, 'ENABLE_M5_DEMO': False,
            'BUSINESS_STORAGE_ROOT': self.temp.name,
            'BUSINESS_CLOCK': lambda: self.now,
            'TRUSTED_HOSTS': ['security.example'],
        })
        self.app.register_blueprint(create_business_blueprint())
        self.base = 'https://security.example'
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/business/session', base_url=self.base).get_json()['csrf_token']
        with self.app.app_context():
            self.store = get_business_store()
        with self.client.session_transaction(base_url=self.base) as session:
            self.owner = owner_key(session['business_owner'])
        self.ready = self.sales_ready()

    def post(self, path, *, client=None, headers=None, **kwargs):
        response = (client or self.client).post(path, base_url=self.base,
            headers={'X-CSRF-Token': self.csrf} if headers is None else headers, **kwargs)
        response.request.environ['wsgi.input'].close()
        return response

    def sales_ready(self, *, first_days=None):
        response = self.post('/api/business/uploads', data={
            'currency': 'AUD', 'time_zone': 'Australia/Sydney', 'sales_basis': 'gross_units',
            'tax_basis': 'exclusive', 'authorized': 'true',
            'file': (io.BytesIO(csv_bytes(synthetic_rows())), 'SYNTHETIC.csv'),
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        pending = response.get_json()
        selections = [{k: row[k] for k in ('series_id', 'start_date', 'end_date')} for row in pending['series']]
        if first_days is not None:
            selections[0]['end_date'] = str(START + timedelta(days=first_days - 1))
        response = self.post('/api/business/uploads/' + pending['upload_id'] + '/confirm',
                             json={'revision': pending['revision'], 'selections': selections})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def prefix(self, dataset=None):
        return '/api/business/datasets/' + (dataset or self.ready)['dataset_id']

    def inventory_bytes(self, *, rows=1, stock_date=None):
        header = 'Product,Store,Stock As Of Date,Current Stock,Supplier Lead Time,Safety Stock,On-order Units\n'
        day = stock_date or self.ready['series'][0]['end_date']
        body = [','.join((PRODUCT if index == 0 else 'SYNTHETIC_OTHER_' + str(index),
                          STORE, day, '5', '7', '2', '0')) for index in range(rows)]
        return (header + '\n'.join(body) + '\n').encode()

    def inventory_upload(self, *, content=None, dataset=None, client=None, headers=None, extra=None):
        dataset = dataset or self.ready
        data = {'revision': dataset['revision'], 'excess_cover_days': '30', 'assume_no_on_order': 'false',
                'file': (io.BytesIO(self.inventory_bytes() if content is None else content), 'SYNTHETIC_inventory.csv')}
        data.update(extra or {})
        return self.post(self.prefix(dataset) + '/inventory-uploads', data=data, client=client, headers=headers)

    def pending(self):
        response = self.inventory_upload()
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def confirm_path(self, pending):
        return self.prefix() + '/inventory-uploads/' + pending['upload_id'] + '/confirm'

    def confirmation(self, pending):
        return {'revision': self.ready['revision'], 'upload_revision': pending['revision']}

    def assert_safe_error(self, response, status):
        self.assertEqual(response.status_code, status, response.get_json())
        text = response.get_data(as_text=True)
        for secret in (self.temp.name, self.app.secret_key, self.csrf,
                       'SYNTHETIC_PRIVATE_DETAIL', 'Traceback', '/Users/', '/opt/render/'):
            self.assertNotIn(secret, text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def assert_no_jobs(self):
        with self.store._connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)

    def test_inventory_upload_uses_public_file_cap_before_worker(self):
        with patch('business_service.run_worker') as worker:
            response = self.inventory_upload(content=b'x' * (1024 * 1024 + 1))
        self.assert_safe_error(response, 413)
        worker.assert_not_called()
        self.assertEqual(self.store.max_jobs, 1)
        self.assertEqual(self.store.worker_memory_bytes, 128 * 1024 * 1024)

    def test_inventory_uses_shared_global_upload_admission_before_body_parse(self):
        # The sales upload in setUp used one of the same twelve global slots.
        for _ in range(11):
            self.store.global_rate('uploads', 12, 60)
        with patch.object(Request, '_load_form_data', side_effect=AssertionError('Do not parse rejected multipart')):
            response = self.inventory_upload()
        self.assert_safe_error(response, 429)
        self.assertEqual(response.get_json()['code'], 'global_rate_limit')

    def test_inventory_and_sales_share_per_owner_upload_limit(self):
        self.assertEqual(self.inventory_upload().status_code, 201)
        self.assertEqual(self.inventory_upload().status_code, 201)
        response = self.inventory_upload()
        self.assert_safe_error(response, 429)
        self.assertEqual(response.get_json()['code'], 'rate_limit')

    def test_new_mutations_require_csrf_and_same_origin(self):
        pending = self.pending()
        self.assert_safe_error(self.inventory_upload(headers={}), 403)
        self.assert_safe_error(self.post(self.confirm_path(pending), json=self.confirmation(pending),
            headers={'X-CSRF-Token': self.csrf, 'Origin': 'https://SYNTHETIC-attacker.invalid'}), 403)
        response = self.client.delete(self.prefix() + '/inventory-uploads/' + pending['upload_id'],
                                       base_url=self.base, headers={'X-CSRF-Token': '0' * 64})
        self.assert_safe_error(response, 403)
        self.assertEqual(self.store.load(self.owner, pending['upload_id'])['state'], 'inventory_pending')

    def test_foreign_session_cannot_read_upload_confirm_or_delete_inventory(self):
        pending = self.pending()
        other = self.app.test_client()
        csrf = other.get('/api/business/session', base_url=self.base).get_json()['csrf_token']
        self.assert_safe_error(other.get(self.prefix() + '/inventory-risk', base_url=self.base,
                                         query_string={'revision': self.ready['revision']}), 404)
        self.assert_safe_error(self.inventory_upload(client=other, headers={'X-CSRF-Token': csrf}), 404)
        self.assert_safe_error(self.post(self.confirm_path(pending), client=other,
            headers={'X-CSRF-Token': csrf}, json=self.confirmation(pending)), 404)
        self.assert_safe_error(other.delete(self.prefix() + '/inventory-uploads/' + pending['upload_id'],
            base_url=self.base, headers={'X-CSRF-Token': csrf}), 404)
        self.assertEqual(self.store.load(self.owner, pending['upload_id'])['state'], 'inventory_pending')

    def test_unknown_paths_filters_and_duplicate_queries_are_rejected(self):
        path = self.prefix() + '/inventory-risk'
        for query in ({'revision': self.ready['revision'], 'path': '/etc/passwd'},
                      {'revision': self.ready['revision'], 'risk': 'invented-score'},
                      {'revision': self.ready['revision'], 'sort': 'filename'},
                      {'revision': self.ready['revision'], 'search': 'x' * 81},
                      [('revision', self.ready['revision']), ('revision', 'another')]):
            self.assert_safe_error(self.client.get(path, base_url=self.base, query_string=query), 400)
        self.assert_safe_error(self.client.get('/api/business/inventory-template.csv?path=/etc/passwd',
                                               base_url=self.base), 400)

    def test_confirm_rejects_unknown_json_duplicate_json_and_path_query(self):
        pending = self.pending()
        self.assert_safe_error(self.post(self.confirm_path(pending),
            json=dict(self.confirmation(pending), forecast=[999999])), 400)
        self.assert_safe_error(self.post(self.confirm_path(pending) + '?path=/etc/passwd',
                                         json=self.confirmation(pending)), 400)
        self.assert_safe_error(self.post(self.confirm_path(pending), data='{"revision":"a","revision":"b"}',
                                         content_type='application/json'), 400)
        self.assertEqual(self.store.load(self.owner, self.ready['dataset_id'])['revision'], self.ready['revision'])

    def test_unknown_upload_metadata_cannot_override_forecasts(self):
        with patch('business_service.run_worker') as worker:
            response = self.inventory_upload(extra={'path': '/etc/passwd', 'future_demand': '99999'})
        self.assert_safe_error(response, 400)
        worker.assert_not_called()

    def test_maximum_inventory_series_count_cannot_be_raised_by_csv(self):
        response = self.inventory_upload(content=self.inventory_bytes(rows=21))
        self.assert_safe_error(response, 422)
        self.assertEqual(response.get_json()['code'], 'too_many_rows')
        self.assert_no_jobs()
        self.assertEqual(self.store.load(self.owner, self.ready['dataset_id'])['revision'], self.ready['revision'])

    def test_new_worker_receives_fixed_limits_not_private_environment(self):
        original = subprocess.Popen
        calls = []
        def capture(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)
        with patch('business_service.subprocess.Popen', side_effect=capture):
            response = self.inventory_upload()
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(len(calls), 1)
        arguments, options = calls[0]
        self.assertTrue(arguments[0][1].endswith('/business_worker.py'))
        self.assertEqual(options['env']['MARGINGUARD_WORKER_MEMORY_BYTES'], str(128 * 1024 * 1024))
        self.assertEqual(set(options['env']), {'PYTHONDONTWRITEBYTECODE',
            'MARGINGUARD_WORKER_MEMORY_BYTES', 'MARGINGUARD_WORKER_MAX_OUTPUT_BYTES'})
        self.assertIs(options['stderr'], subprocess.DEVNULL)
        self.assertTrue(options['start_new_session'])
        self.assert_no_jobs()

    def test_real_inventory_timeout_reaps_worker_and_preserves_sales_then_recovers(self):
        original = subprocess.Popen
        processes = []
        def capture(*args, **kwargs):
            process = original(*args, **kwargs)
            processes.append(process)
            return process
        self.app.config['BUSINESS_WORKER_TIMEOUT'] = 0.000001
        with patch('business_service.subprocess.Popen', side_effect=capture):
            response = self.inventory_upload()
        self.assert_safe_error(response, 503)
        self.assertEqual(response.get_json()['code'], 'processing_timeout')
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdin.closed)
        self.assertTrue(processes[0].stdout.closed)
        self.assert_no_jobs()
        self.assertNotIn('inventory', self.store.load(self.owner, self.ready['dataset_id'])['payload'])
        self.app.config['BUSINESS_WORKER_TIMEOUT'] = 5
        self.assertEqual(self.inventory_upload().status_code, 201)

    def test_capacity_failure_during_confirmation_does_not_destroy_saved_data(self):
        pending = self.pending()
        before = self.store.load(self.owner, self.ready['dataset_id'])
        self.store.max_dataset_bytes = 1
        response = self.post(self.confirm_path(pending), json=self.confirmation(pending))
        self.assert_safe_error(response, 413)
        self.assertEqual(self.store.load(self.owner, self.ready['dataset_id']), before)
        self.assertEqual(self.store.load(self.owner, pending['upload_id'])['state'], 'inventory_pending')
        self.assert_no_jobs()

    def test_confirmation_and_upload_share_the_single_processing_slot(self):
        pending = self.pending()
        job = self.store.acquire_job(self.owner, 30)
        try:
            self.assert_safe_error(self.post(self.confirm_path(pending), json=self.confirmation(pending)), 429)
            self.assert_safe_error(self.inventory_upload(), 429)
        finally:
            self.store.release_job(job)
        self.assertEqual(self.post(self.confirm_path(pending), json=self.confirmation(pending)).status_code, 201)
        self.assert_no_jobs()

    def test_two_confirmations_cannot_publish_or_reuse_a_stale_snapshot(self):
        pending = self.pending()
        cookie = self.client.get_cookie('marginguard_session', domain='security.example')
        clients = [self.app.test_client(), self.app.test_client()]
        for client in clients:
            client.set_cookie('marginguard_session', cookie.value, domain='security.example')
        def attempt(client):
            return self.post(self.confirm_path(pending), client=client, json=self.confirmation(pending)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(attempt, clients))
        self.assertEqual(statuses.count(201), 1)
        self.assertTrue(all(status in (201, 409, 429) for status in statuses), statuses)
        self.assert_safe_error(self.post(self.confirm_path(pending), json=self.confirmation(pending)), 409)
        self.assert_safe_error(self.client.get(self.prefix() + '/inventory-risk', base_url=self.base,
            query_string={'revision': self.ready['revision']}), 409)
        self.assert_no_jobs()

    def test_expired_pending_is_unavailable_without_affecting_live_sales(self):
        pending = self.pending()
        self.now += 901
        self.assert_safe_error(self.post(self.confirm_path(pending), json=self.confirmation(pending)), 404)
        response = self.client.get(self.prefix() + '/catalog', base_url=self.base)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['revision'], self.ready['revision'])
        self.assertFalse(response.get_json()['has_inventory'])

    def test_session_deletion_removes_sales_and_inventory_without_readoption(self):
        pending = self.pending()
        response = self.client.delete('/api/business/session', base_url=self.base,
                                       headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, 204)
        with self.store._connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM datasets').fetchone()[0], 0)
        fresh = self.client.get('/api/business/session', base_url=self.base).get_json()
        self.assertIsNone(fresh['active_dataset'])
        self.assertNotEqual(fresh['csrf_token'], self.csrf)
        self.assert_safe_error(self.client.get(self.prefix() + '/inventory-risk', base_url=self.base,
            query_string={'revision': self.ready['revision']}), 404)
        response = self.post(self.confirm_path(pending), json=self.confirmation(pending),
                             headers={'X-CSRF-Token': fresh['csrf_token']})
        self.assert_safe_error(response, 404)

    def test_later_stock_cannot_enter_an_explicit_earlier_forecast_window(self):
        self.ready = self.sales_ready(first_days=42)
        query = {'revision': self.ready['revision'], 'series_id': self.ready['series'][0]['series_id']}
        before = self.client.get(self.prefix() + '/analysis', base_url=self.base, query_string=query).get_json()
        response = self.inventory_upload(content=self.inventory_bytes(stock_date=str(START + timedelta(days=83))))
        self.assertEqual(response.status_code, 201, response.get_json())
        pending = response.get_json()
        row = pending['overview']['rows'][0]
        self.assertEqual(row['assessment_status'], 'not_assessed')
        self.assertIn('snapshot_date_mismatch', [issue['code'] for issue in row['issues']])
        confirmed = self.post(self.confirm_path(pending), json=self.confirmation(pending)).get_json()
        query['revision'] = confirmed['revision']
        after = self.client.get(self.prefix() + '/analysis', base_url=self.base, query_string=query).get_json()
        self.assertEqual(after['analysis'], before['analysis'])
        self.assertIsNone(after['inventory_import'])


if __name__ == '__main__':
    unittest.main()
