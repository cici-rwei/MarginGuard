"""Public-demo checks use only the explicitly synthetic bundled 84-day fixture."""
import json
import unittest
from datetime import date
from unittest.mock import patch

from flask import Flask

import synthetic_demo as demo
from business_csv import parse_business_csv
from forecast import analyse
from inventory import inventory_risk
from scenario import compare_strategies


class SyntheticDemoTests(unittest.TestCase):
    def setUp(self):
        demo._trusted_analysis.cache_clear()
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, ENABLE_SYNTHETIC_DEMO=True)
        self.app.register_blueprint(demo.create_synthetic_blueprint())
        self.client = self.app.test_client()
        self.query = '?item_id=' + demo.ITEM_ID + '&store_id=' + demo.STORE_ID

    def tearDown(self):
        demo._trusted_analysis.cache_clear()

    def analysis(self):
        response = self.client.get('/api/demo/analysis' + self.query)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def payload(self, kind='scenarios', **changes):
        data = self.analysis()
        names = demo.INVENTORY_FIELDS if kind == 'inventory' else demo.SCENARIO_FIELDS
        params = {key: data['defaults'][key] for key in names}
        params.update(item_id=demo.ITEM_ID, store_id=demo.STORE_ID,
                      revision=data['context']['revision'], currency='AUD',
                      hypothetical_stock_at_origin=True)
        params.update(changes)
        return params

    def post(self, kind='scenarios', **changes):
        return self.client.post('/api/demo/' + kind, json=self.payload(kind, **changes))

    def test_disabled_gate_never_loads_file(self):
        self.app.config['ENABLE_SYNTHETIC_DEMO'] = False
        with patch.object(demo, '_trusted_analysis') as loader:
            for path in ('catalog', 'analysis'):
                result = self.client.get('/api/demo/' + path)
                self.assertEqual(result.status_code, 503)
                self.assertEqual(result.get_json()['code'], 'demo_disabled')
                self.assertEqual(result.headers['Cache-Control'], 'no-store')
            self.assertEqual(self.client.post('/api/demo/scenarios', json={}).status_code, 503)
            loader.assert_not_called()

    def test_catalog_has_synthetic_identity_and_explicit_aud(self):
        result = self.client.get('/api/demo/catalog').get_json()
        self.assertEqual(result['currency'], 'AUD')
        self.assertEqual(result['source_kind'], 'synthetic_demo')
        self.assertIn('Not real business transactions', result['source_label'])
        self.assertEqual([(s['item_id'], s['store_id']) for s in result['series']],
                         [(demo.ITEM_ID, demo.STORE_ID)])

    def test_forecast_is_exact_unchanged_engine_output(self):
        data = parse_business_csv(demo.SAMPLE_FILE.read_bytes(), 'AUD',
                                  sales_basis='gross_units', as_of_date=date(2024, 3, 25))
        expected = analyse(data['groups'][(demo.ITEM_ID, demo.STORE_ID)])
        result = self.analysis()
        self.assertEqual(result['analysis'], demo.serial(expected))
        self.assertEqual(len(result['history']), 84)
        self.assertEqual(sum(row['units'] == 0 for row in result['history']), 12)
        self.assertEqual(result['historical_units'], 504)
        self.assertEqual(result['analysis']['future'][0]['date'], '2024-03-25')
        self.assertEqual(result['analysis']['future'][-1]['date'], '2024-04-07')
        self.assertIn('historical simulation', result['limitations'])

    def test_context_references_and_default_risk_are_consistent(self):
        result = self.analysis()
        self.assertEqual(result['context']['source_kind'], 'synthetic_demo')
        self.assertEqual(result['context']['currency'], 'AUD')
        self.assertEqual(result['context']['forecast_origin'], '2024-03-24')
        self.assertEqual(result['price_reference']['value'], '14.50')
        self.assertEqual(result['cost_reference']['value'], '8.20')
        demand = [row['prediction'] for row in result['analysis']['future']]
        expected = inventory_risk(demo.ITEM_ID, demand, **{k: result['defaults'][k] for k in demo.INVENTORY_FIELDS})
        self.assertEqual(result['inventory'], demo.serial(expected))

    def test_trusted_file_is_parsed_once_per_worker(self):
        with patch.object(demo, 'parse_business_csv', wraps=parse_business_csv) as parse:
            self.client.get('/api/demo/catalog')
            self.analysis()
            self.analysis()
            self.assertEqual(parse.call_count, 1)

    def test_private_parameters_are_not_stored_or_cookies_set(self):
        original = self.analysis()
        response = self.post('inventory', current_stock=321)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Set-Cookie', response.headers)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        other_client = self.app.test_client()
        self.assertEqual(other_client.get('/api/demo/analysis' + self.query).get_json(), original)

    def test_inventory_matches_core_and_changes_with_inputs(self):
        params = self.payload('inventory', current_stock=2, lead_time_days=20)
        result = self.client.post('/api/demo/inventory', json=params).get_json()
        demand = [row['prediction'] for row in self.analysis()['analysis']['future']]
        expected = demo.serial(inventory_risk(demo.ITEM_ID, demand, **{k: params[k] for k in demo.INVENTORY_FIELDS}))
        for key, value in expected.items():
            self.assertEqual(result[key], value)
        self.assertTrue(result['extrapolated'])
        self.assertTrue(result['stockout_risk'])
        high_stock = self.post('inventory', current_stock=1000).get_json()
        self.assertNotEqual(result['days_of_cover'], high_stock['days_of_cover'])

    def test_scenarios_match_core_and_all_amounts_use_aud(self):
        params = self.payload()
        result = self.client.post('/api/demo/scenarios', json=params)
        self.assertEqual(result.status_code, 200)
        data = result.get_json()
        demand = [row['prediction'] for row in self.analysis()['analysis']['future']]
        expected = demo.serial(compare_strategies(demand, **{k: params[k] for k in demo.SCENARIO_FIELDS}, currency='AUD'))
        for key, value in expected.items():
            self.assertEqual(data[key], value)
        self.assertEqual({row['currency'] for row in data['strategies']}, {'AUD'})
        self.assertEqual(data['recommendation'], 'Reorder')

    def test_order_and_discount_inputs_change_financial_results(self):
        normal = self.post().get_json()['strategies']
        changed = self.post(order_quantity=80, discount_percent=20).get_json()['strategies']
        self.assertNotEqual(normal[1]['procurement_cash_outlay'], changed[1]['procurement_cash_outlay'])
        self.assertNotEqual(normal[2]['revenue'], changed[2]['revenue'])
        self.assertNotEqual(normal[2]['gross_margin'], changed[2]['gross_margin'])

    def test_constraints_and_arrival_timing_still_apply(self):
        low_budget = self.post(cash_budget=1).get_json()
        self.assertFalse(low_budget['strategies'][1]['feasible'])
        self.assertNotEqual(low_budget['recommendation'], 'Reorder')
        moq = self.post(order_quantity=10, moq=20).get_json()['strategies'][1]
        self.assertFalse(moq['feasible'])
        late = self.post(current_stock=0, lead_time_days=14).get_json()['strategies'][1]
        self.assertEqual(late['units_sold'], '0')
        self.assertEqual(late['in_transit_units'], 60)

    def test_currency_mismatch_is_rejected_without_relabelling(self):
        for currency in ('USD', 'aud', '', None, ['AUD']):
            with self.subTest(currency=currency):
                self.assertEqual(self.post(currency=currency).status_code, 400)

    def test_old_revision_rejected(self):
        response = self.post(revision='old-revision')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['code'], 'revision_conflict')

    def test_unknown_selection_and_file_paths_rejected(self):
        self.assertEqual(self.client.get('/api/demo/analysis?item_id=FOODS_3_252&store_id=CA_1').status_code, 400)
        self.assertEqual(self.client.get('/api/demo/analysis' + self.query + '&path=/tmp/private.csv').status_code, 400)
        self.assertEqual(self.client.get('/api/demo/catalog?file=../../private.csv').status_code, 400)
        for key in ('path', 'dataset_id', 'daily_demand', 'source_kind'):
            self.assertEqual(self.post(**{key: 'untrusted'}).status_code, 400)

    def test_repeated_fields_are_rejected(self):
        self.assertEqual(self.client.get('/api/demo/analysis' + self.query + '&item_id=' + demo.ITEM_ID).status_code, 400)
        raw = json.dumps(self.payload())[:-1] + ', "currency":"AUD"}'
        self.assertEqual(self.client.post('/api/demo/scenarios', data=raw, content_type='application/json').status_code, 400)

    def test_invalid_numeric_values_and_missing_inputs(self):
        for bad in (-1, True, 'NaN', 'Infinity', {}, [], '9' * 129):
            with self.subTest(bad=bad):
                self.assertEqual(self.post('inventory', current_stock=bad).status_code, 400)
        self.assertEqual(self.post('inventory', current_stock=1.5).status_code, 400)
        self.assertEqual(self.post(discount_percent=101).status_code, 400)
        params = self.payload()
        del params['selling_price']
        self.assertEqual(self.client.post('/api/demo/scenarios', json=params).status_code, 400)

    def test_json_content_and_size_bounds(self):
        self.assertEqual(self.client.post('/api/demo/scenarios', data='{}', content_type='text/plain').status_code, 415)
        for raw in ('[]', '{', '{"value":NaN}', '{"value":Infinity}'):
            self.assertEqual(self.client.post('/api/demo/scenarios', data=raw, content_type='application/json').status_code, 400)
        large = '{"padding":"' + ('x' * demo.MAX_BODY_BYTES) + '"}'
        self.assertEqual(self.client.post('/api/demo/scenarios', data=large, content_type='application/json').status_code, 413)

    def test_extreme_exponents_precision_and_nonfinite_values_reject_safely(self):
        for bad in ('1e999999', '1e-999999', 'Infinity', '-Infinity',
                    'nan', 'NaN', '0.0000001', '9' * 120, 10**100, True):
            with self.subTest(bad=bad):
                response = self.post(selling_price=bad)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(str(bad), response.get_json()['error'])
        raw = json.dumps(self.payload()).replace('"selling_price": "14.50"', '"selling_price": 1e999999')
        self.assertEqual(self.client.post('/api/demo/scenarios', data=raw, content_type='application/json').status_code, 400)
        self.assertEqual(self.post(selling_price='0.000001').status_code, 200)
        self.assertEqual(self.post(max_unmet_units='').status_code, 200)

    def test_cross_site_posts_rejected_and_same_origin_accepted(self):
        params = self.payload()
        for headers in ({'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}, {'Origin': 'null'}):
            self.assertEqual(self.client.post('/api/demo/scenarios', json=params, headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/api/demo/scenarios', json=params, headers={'Origin': 'http://localhost'}).status_code, 200)

    def test_existing_on_order_requires_explicit_exclusion(self):
        self.assertEqual(self.post(on_order_units=5).status_code, 400)
        self.assertEqual(self.post(on_order_units=5, acknowledge_excluded_on_order='true').status_code, 400)
        accepted = self.post(on_order_units=5, acknowledge_excluded_on_order=True)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()['excluded_on_order_units'], 5)
        self.assertIn('explicitly excluded', accepted.get_json()['limitations'])

    def test_historical_stock_metadata_is_checked(self):
        self.assertEqual(self.post(hypothetical_stock_at_origin=False).status_code, 400)
        self.assertEqual(self.post(stock_as_of='2026-10-28').status_code, 400)
        self.assertEqual(self.post(stock_as_of='2024-03-24').status_code, 200)

    def test_missing_asset_returns_safe_error_without_path(self):
        with patch.object(demo.Path, 'read_bytes', side_effect=OSError('/private/secret.csv')):
            result = self.client.get('/api/demo/catalog')
        self.assertEqual(result.status_code, 503)
        self.assertNotIn('/private', result.get_data(as_text=True))
        self.assertEqual(result.get_json()['code'], 'demo_unavailable')


if __name__ == '__main__':
    unittest.main()
