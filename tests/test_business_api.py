"""Anonymous upload integration tests use explicitly SYNTHETIC sales only."""
from datetime import date
from decimal import Decimal
import io
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from business_api import create_business_blueprint
from business_fixtures import csv_bytes, synthetic_rows
from business_store import owner_key
from forecast import analyse
from business_worker import serial
from scenario import compare_strategies


class BusinessAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000000.0
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='SYNTHETIC test-only key',
                               ENABLE_BUSINESS_UPLOAD=True, BUSINESS_STORAGE_ROOT=self.temp.name,
                               BUSINESS_CLOCK=lambda: self.now, MAX_CONTENT_LENGTH=32768)
        self.app.register_blueprint(create_business_blueprint())
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/business/session').get_json()['csrf_token']

    def headers(self):
        return {'X-CSRF-Token': self.csrf}

    def upload(self, *, rows=None, currency='AUD', content=None, client=None, headers=None, extra=None):
        data = {'currency': currency, 'time_zone': 'Australia/Sydney', 'sales_basis': 'gross_units',
                'tax_basis': 'exclusive', 'authorized': 'true',
                'file': (io.BytesIO(content if content is not None else csv_bytes(synthetic_rows() if rows is None else rows)),
                         'SYNTHETIC.csv')}
        data.update(extra or {})
        response = (client or self.client).post('/api/business/uploads', data=data,
                                                headers=self.headers() if headers is None else headers)
        # Werkzeug's test builder may spool a large multipart request to disk;
        # unlike a production WSGI server it leaves that input owned by the test.
        response.request.environ['wsgi.input'].close()
        return response

    def ready(self, *, currency='AUD', rows=None):
        response = self.upload(currency=currency, rows=rows)
        self.assertEqual(response.status_code, 201, response.get_json())
        pending = response.get_json()
        selections = [{'series_id': row['series_id'], 'start_date': row['start_date'], 'end_date': row['end_date']}
                      for row in pending['series']]
        response = self.client.post('/api/business/uploads/' + pending['upload_id'] + '/confirm',
                                    json={'revision': pending['revision'], 'selections': selections}, headers=self.headers())
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def selection(self, ready):
        return {'series_id': ready['series'][0]['series_id'], 'revision': ready['revision']}

    def analysis(self, ready):
        return self.client.get('/api/business/datasets/' + ready['dataset_id'] + '/analysis', query_string=self.selection(ready))

    def inputs(self, ready):
        return dict(self.selection(ready), currency=ready['meta']['currency'], hypothetical_stock_at_origin=True,
                    current_stock=10, selling_price='4.50', existing_unit_cost='2.10', cash_budget=1000,
                    order_quantity=80, unit_purchase_cost='2', freight=5, other_costs=0, moq=10,
                    lead_time_days=7, discount_percent=10, demand_uplift_percent=20)

    def scenarios(self, ready, inputs):
        return self.client.post('/api/business/datasets/' + ready['dataset_id'] + '/scenarios', json=inputs, headers=self.headers())

    def test_session_is_private_and_no_business_values_in_cookie(self):
        response = self.client.get('/api/business/session')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        with self.client.session_transaction() as values:
            self.assertEqual(set(values), {'business_owner', '_permanent'})
        self.assertEqual(response.get_json()['limits']['rows'], 50000)

    def test_template_is_fixed_and_rejects_path_parameter(self):
        response = self.client.get('/api/business/template.csv')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Date,Product,Store,Units Sold', response.data)
        response.close()
        self.assertEqual(self.client.get('/api/business/template.csv?path=/etc/passwd').status_code, 400)

    def test_disabled_feature_exposes_no_private_endpoints(self):
        self.app.config['ENABLE_BUSINESS_UPLOAD'] = False
        self.assertEqual(self.client.get('/api/business/session').status_code, 503)
        self.assertEqual(self.upload().status_code, 503)

    def test_missing_session_csrf_and_foreign_origin_are_rejected(self):
        fresh = self.app.test_client()
        self.assertEqual(self.upload(client=fresh, headers={}).status_code, 401)
        self.assertEqual(self.upload(headers={}).status_code, 403)
        self.assertEqual(self.upload(headers={'X-CSRF-Token': 'é'}).status_code, 403)
        self.assertEqual(self.upload(headers=dict(self.headers(), Origin='https://attacker.invalid')).status_code, 403)

    def test_upload_validate_confirm_catalog_and_analysis_use_real_supplied_rows(self):
        rows = synthetic_rows(42, values=[13] * 42)
        ready = self.ready(rows=rows)
        response = self.analysis(ready)
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        expected = analyse([{'date': date.fromisoformat(row['Date']), 'units_sold': 13} for row in rows])
        self.assertEqual(result['analysis'], serial(expected))
        self.assertEqual(result['historical_units'], 546)
        self.assertEqual(result['analysis']['total_forecast_demand'], 182)
        self.assertIsNone(result['inventory'])
        self.assertTrue(all(value is None for value in result['defaults'].values()))
        self.assertEqual(result['context']['currency'], 'AUD')

    def test_41_days_cannot_confirm_but_42_can(self):
        pending = self.upload(rows=synthetic_rows(41)).get_json()
        entry = pending['series'][0]
        response = self.client.post('/api/business/uploads/' + pending['upload_id'] + '/confirm',
                                    json={'revision': pending['revision'], 'selections': [{key: entry[key] for key in ('series_id', 'start_date', 'end_date')}]},
                                    headers=self.headers())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()['code'], 'insufficient_history')
        self.ready(rows=synthetic_rows(42))

    def test_missing_day_not_zero_and_explicit_valid_range_is_required(self):
        rows = synthetic_rows(84, values=[0] * 84)
        del rows[20]
        pending = self.upload(rows=rows).get_json()
        entry = pending['series'][0]
        self.assertEqual(entry['zero_sales_days'], 83)
        self.assertEqual(len(entry['missing_dates']), 1)
        selection = {key: entry[key] for key in ('series_id', 'start_date', 'end_date')}
        url = '/api/business/uploads/' + pending['upload_id'] + '/confirm'
        self.assertEqual(self.client.post(url, json={'revision': pending['revision'], 'selections': [selection]}, headers=self.headers()).status_code, 422)
        selection['start_date'] = entry['continuous_ranges'][1]['start_date']
        response = self.client.post(url, json={'revision': pending['revision'], 'selections': [selection]}, headers=self.headers())
        self.assertEqual(response.status_code, 201)

    def test_duplicate_records_have_structured_report_without_raw_values(self):
        rows = synthetic_rows(1)
        response = self.upload(rows=rows + rows)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()['code'], 'duplicate_record')
        self.assertTrue(response.get_json()['issues'])
        self.assertNotIn('SYNTHETIC_SKU', response.get_data(as_text=True))

    def test_cross_session_catalog_analysis_and_delete_are_unavailable(self):
        ready = self.ready()
        other = self.app.test_client()
        token = other.get('/api/business/session').get_json()['csrf_token']
        prefix = '/api/business/datasets/' + ready['dataset_id']
        self.assertEqual(other.get(prefix + '/catalog').status_code, 404)
        self.assertEqual(other.get(prefix + '/analysis', query_string=self.selection(ready)).status_code, 404)
        self.assertEqual(other.delete(prefix, headers={'X-CSRF-Token': token}).status_code, 404)

    def test_multiple_products_and_stores_keep_separate_predictions(self):
        rows = synthetic_rows(42, values=[2] * 42)
        rows += synthetic_rows(42, store='SYNTHETIC_OTHER_STORE', values=[7] * 42)
        rows += synthetic_rows(42, product='SYNTHETIC_OTHER_PRODUCT', values=[11] * 42)
        ready = self.ready(rows=rows)
        totals = []
        for entry in ready['series']:
            response = self.client.get('/api/business/datasets/' + ready['dataset_id'] + '/analysis',
                                       query_string=dict(series_id=entry['series_id'], revision=ready['revision']))
            totals.append(response.get_json()['analysis']['total_forecast_demand'])
        self.assertCountEqual(totals, [28, 98, 154])

    def test_aud_usd_scenarios_match_existing_engine_with_correct_currency(self):
        for currency in ('AUD', 'USD'):
            ready = self.ready(currency=currency)
            data = self.analysis(ready).get_json()
            parameters = self.inputs(ready)
            response = self.scenarios(ready, parameters)
            self.assertEqual(response.status_code, 200, response.get_json())
            inputs = {key: value for key, value in parameters.items()
                      if key not in ('series_id', 'revision', 'hypothetical_stock_at_origin')}
            expected = compare_strategies([row['prediction'] for row in data['analysis']['future']], **inputs)
            actual = response.get_json()
            self.assertEqual(actual['strategies'], serial(expected['strategies']))
            self.assertEqual(actual['currency'], currency)
            self.assertEqual(actual['recommendation'], expected['recommendation'])

    def test_currency_conflict_missing_cost_and_false_service_limit_rejected(self):
        ready = self.ready()
        for changes in ({'currency': 'USD'}, {'existing_unit_cost': None}, {'max_unmet_units': False}):
            inputs = dict(self.inputs(ready), **changes)
            self.assertIn(self.scenarios(ready, inputs).status_code, (400, 422))

    def test_stock_date_and_hypothetical_declaration_checked_for_both_apis(self):
        ready = self.ready()
        parameters = self.inputs(ready)
        parameters.pop('hypothetical_stock_at_origin')
        self.assertEqual(self.scenarios(ready, parameters).status_code, 422)
        parameters['stock_as_of'] = ready['series'][0]['end_date']
        self.assertEqual(self.scenarios(ready, parameters).status_code, 200)
        inventory = dict(self.selection(ready), currency='AUD', current_stock=10, lead_time_days=7,
                         safety_stock=5, on_order_units=0, excess_cover_days=30)
        url = '/api/business/datasets/' + ready['dataset_id'] + '/inventory'
        self.assertEqual(self.client.post(url, json=inventory, headers=self.headers()).status_code, 422)
        inventory['hypothetical_stock_at_origin'] = 'true'
        self.assertEqual(self.client.post(url, json=inventory, headers=self.headers()).status_code, 422)
        inventory['hypothetical_stock_at_origin'] = True
        self.assertEqual(self.client.post(url, json=inventory, headers=self.headers()).status_code, 200)

    def test_existing_on_order_requires_explicit_exclusion_and_is_not_added_to_stock(self):
        ready = self.ready()
        parameters = dict(self.inputs(ready), on_order_units=200)
        self.assertEqual(self.scenarios(ready, parameters).status_code, 422)
        parameters['acknowledge_excluded_on_order'] = True
        result = self.scenarios(ready, parameters).get_json()
        self.assertEqual(result['excluded_on_order_units'], 200)
        self.assertIn('excludes existing on-order', result['limitations'])
        wait = next(item for item in result['strategies'] if item['strategy'] == 'Wait')
        self.assertEqual(Decimal(wait['units_sold']), 10)

    def test_unknown_duplicate_and_local_path_parameters_are_rejected(self):
        ready = self.ready()
        url = '/api/business/datasets/' + ready['dataset_id'] + '/analysis'
        params = self.selection(ready)
        self.assertEqual(self.client.get(url, query_string=dict(params, path='/etc/passwd')).status_code, 400)
        query = [('series_id', params['series_id']), ('series_id', params['series_id']), ('revision', params['revision'])]
        self.assertEqual(self.client.get(url, query_string=query).status_code, 400)
        response = self.client.post('/api/business/datasets/' + ready['dataset_id'] + '/scenarios',
                                    data='{"currency":"AUD","currency":"USD"}', content_type='application/json', headers=self.headers())
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/business/uploads/' + ready['dataset_id'] + '/confirm',
                                    json={'revision': ['not a scalar'], 'selections': []}, headers=self.headers())
        self.assertEqual(response.status_code, 400)

    def test_delete_removes_active_dataset_and_old_version_access(self):
        ready = self.ready()
        self.assertEqual(self.client.delete('/api/business/datasets/' + ready['dataset_id'], headers=self.headers()).status_code, 204)
        self.assertEqual(self.analysis(ready).status_code, 404)
        self.assertIsNone(self.client.get('/api/business/session').get_json()['active_dataset'])

    def test_replace_invalidates_old_dataset_and_revision(self):
        first = self.ready()
        second = self.ready(currency='USD')
        self.assertEqual(self.analysis(first).status_code, 404)
        self.assertEqual(self.analysis(second).status_code, 200)
        wrong = dict(self.selection(second), revision='wrong')
        self.assertEqual(self.client.get('/api/business/datasets/' + second['dataset_id'] + '/analysis', query_string=wrong).status_code, 409)

    def test_expired_session_has_no_access_and_can_start_fresh(self):
        ready = self.ready()
        self.now += 1801
        self.assertEqual(self.analysis(ready).status_code, 401)
        fresh = self.client.get('/api/business/session').get_json()
        self.assertIsNone(fresh['active_dataset'])
        self.assertNotEqual(fresh['csrf_token'], self.csrf)

    def test_signing_key_rotation_does_not_adopt_old_private_data(self):
        ready = self.ready()
        self.app.config['SECRET_KEY'] = 'SYNTHETIC different signing key for rotation test'
        self.assertEqual(self.analysis(ready).status_code, 401)
        fresh = self.client.get('/api/business/session').get_json()
        self.assertIsNone(fresh['active_dataset'])
        self.assertNotEqual(fresh['csrf_token'], self.csrf)
        self.assertEqual(self.analysis(ready).status_code, 404)

    def test_forged_cookie_cannot_claim_a_dataset(self):
        ready = self.ready()
        other = self.app.test_client()
        other.set_cookie('session', 'SYNTHETIC_forged_cookie')
        prefix = '/api/business/datasets/' + ready['dataset_id']
        self.assertEqual(other.get(prefix + '/catalog').status_code, 401)
        fresh = other.get('/api/business/session').get_json()
        self.assertIsNone(fresh['active_dataset'])
        self.assertEqual(other.get(prefix + '/catalog').status_code, 404)

    def test_compute_rate_limit_is_separate_from_upload_rate(self):
        ready = self.ready()
        # Confirmation consumed one computation in this fixed minute.
        for _ in range(29):
            self.assertEqual(self.analysis(ready).status_code, 200)
        self.assertEqual(self.analysis(ready).status_code, 429)

    def test_independent_app_worker_can_read_only_same_signed_owner(self):
        ready = self.ready()
        app = Flask('SYNTHETIC_second_worker')
        app.config.update(self.app.config)
        app.register_blueprint(create_business_blueprint())
        client = app.test_client()
        cookie = self.client.get_cookie('session').value
        client.set_cookie('session', cookie)
        prefix = '/api/business/datasets/' + ready['dataset_id']
        self.assertEqual(client.get(prefix + '/catalog').status_code, 200)
        other = app.test_client()
        other.get('/api/business/session')
        self.assertEqual(other.get(prefix + '/catalog').status_code, 404)

    def test_delete_session_removes_cookie_and_private_data(self):
        ready = self.ready()
        self.assertEqual(self.client.delete('/api/business/session', headers=self.headers()).status_code, 204)
        self.assertEqual(self.analysis(ready).status_code, 401)

    def test_file_limit_and_multipart_limit_return_safe_413(self):
        self.assertEqual(self.upload(content=b'x' * (5 * 1024 * 1024 + 1)).status_code, 413)
        response = self.upload(content=b'x' * (6 * 1024 * 1024 + 1))
        self.assertEqual(response.status_code, 413)
        self.assertNotIn(self.temp.name, response.get_data(as_text=True))

    def test_valid_file_over_64kib_passes_multipart_buffer_but_large_metadata_does_not(self):
        content = csv_bytes(synthetic_rows(1000, product='SYNTHETIC_LONG_PRODUCT_' + 'X' * 40))
        self.assertGreater(len(content), 64 * 1024)
        response = self.upload(content=content)
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()['report']['summary']['row_count'], 1000)
        response = self.upload(extra={'tax_basis': 'x' * (16 * 1024)})
        self.assertEqual(response.status_code, 413)

    def test_upload_rate_limit_is_enforced(self):
        for _ in range(3):
            self.assertEqual(self.upload().status_code, 201)
        self.assertEqual(self.upload().status_code, 429)

    def test_row_and_series_limits_are_enforced_through_upload_worker(self):
        rows = [synthetic_rows(1, product='SYNTHETIC_%03d' % i)[0] for i in range(101)]
        response = self.upload(rows=rows)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()['code'], 'too_many_series')
        rows = []
        for index in range(50):
            rows.extend(synthetic_rows(1000, product='SYNTHETIC_%02d' % index, start=date(2020, 1, 1)))
        rows.extend(synthetic_rows(1, product='SYNTHETIC_EXTRA'))
        content = csv_bytes(rows)
        self.assertLess(len(content), 5 * 1024 * 1024)
        response = self.upload(content=content)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()['code'], 'too_many_rows')

    def test_processing_timeout_kills_worker_and_releases_job(self):
        with patch('business_service.subprocess.Popen') as factory:
            process = factory.return_value
            process.communicate.side_effect = [subprocess.TimeoutExpired('fixed-worker', 5), (b'', b'')]
            process.poll.return_value = 0
            response = self.upload()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json()['code'], 'processing_timeout')
            process.kill.assert_called_once()
        self.assertEqual(self.upload().status_code, 201)

    def test_real_worker_is_terminated_on_wall_timeout(self):
        original = subprocess.Popen
        processes = []
        def capture(*args, **kwargs):
            process = original(*args, **kwargs)
            processes.append(process)
            return process
        self.app.config['BUSINESS_WORKER_TIMEOUT'] = 0.000001
        with patch('business_service.subprocess.Popen', side_effect=capture):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['code'], 'processing_timeout')
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdin.closed)
        self.assertTrue(processes[0].stdout.closed)
        self.app.config['BUSINESS_WORKER_TIMEOUT'] = 5
        self.assertEqual(self.upload().status_code, 201)

    def test_worker_failure_does_not_return_stderr_or_leak_slot(self):
        with patch('business_service.subprocess.Popen') as factory:
            process = factory.return_value
            process.communicate.return_value = (b'SYNTHETIC_PRIVATE_MALFORMED_OUTPUT', None)
            process.returncode = 1
            process.poll.return_value = 1
            response = self.upload()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('SYNTHETIC_PRIVATE', response.get_data(as_text=True))
            self.assertEqual(factory.call_args.kwargs['stderr'], subprocess.DEVNULL)
        self.assertEqual(self.upload().status_code, 201)

    def test_preview_is_bounded_and_failed_validation_is_not_stored(self):
        response = self.upload()
        self.assertEqual(len(response.get_json()['preview']), 20)
        rows = synthetic_rows(1)
        rows[0]['Units Sold'] = '-1'
        response = self.upload(rows=rows)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(self.temp.name, response.get_data(as_text=True))
        self.assertNotIn('SYNTHETIC_SKU', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
