"""SYNTHETIC regressions for integer boundaries, never real business claims."""
from datetime import date, timedelta
from decimal import Decimal
import io
import json
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

from business_api import create_business_blueprint
from batch_inventory import RISK_CALCULATION_VERSION
from business_fixtures import csv_bytes, synthetic_rows
from business_service import saved_risk_overview
from forecast import predict
from inventory import inventory_risk


# The two synthetic trial files exposed these last-week totals. Short generated
# histories below reproduce the numeric boundary without copying private data.
CASES = (([86, 46, 196, 67, 168, 30, 26], 130, 259, 748),
         ([5, 275, 108, 381, 99, 40, 28], 97, 193, 1032))


class InventoryPrecisionTests(unittest.TestCase):
    def test_forecast_float_residual_does_not_add_one_unit(self):
        for tail, stock, safety, expected in CASES:
            history = [{'date': date(2024, 1, 1) + timedelta(days=day), 'units_sold': value}
                       for day, value in enumerate([100] * 77 + tail)]
            demand = [row['prediction'] for row in predict(history, 'moving_average_7')]
            risk = inventory_risk('ANY_SYNTHETIC_PRODUCT', demand, stock, 7, safety)
            self.assertEqual(risk['suggested_reorder_quantity'], expected)
            # Forecast values and reported demand have not been rounded away.
            self.assertEqual(risk['lead_time_demand'], Decimal(str(sum(tail) / 7)) * 7)
            self.assertTrue(risk['stockout_risk'])

    def test_real_fraction_still_rounds_up(self):
        for daily in (1.01, 1.000000001, Decimal('1.0000000000000001'),
                      '1.0000000000000001'):
            with self.subTest(daily=daily):
                risk = inventory_risk('SYNTHETIC', [daily] * 14, 0, 1)
                self.assertEqual(risk['suggested_reorder_quantity'], 2)

    def test_precision_budget_scales_to_extended_delivery_time(self):
        risk = inventory_risk('SYNTHETIC', [619 / 7] * 14, 0, 21)
        self.assertEqual(risk['suggested_reorder_quantity'], 1857)
        self.assertTrue(risk['extrapolated'])

    def test_exact_integer_zero_and_negative_gaps_unchanged(self):
        for stock, on_order, expected in ((60, 0, 10), (70, 0, 0), (71, 0, 0), (60, 10, 0)):
            risk = inventory_risk('SYNTHETIC', [10] * 14, stock, 7, on_order_units=on_order)
            self.assertEqual(risk['suggested_reorder_quantity'], expected)
        self.assertEqual(inventory_risk('SYNTHETIC', [619 / 7] * 14, 0, 0)
                         ['suggested_reorder_quantity'], 0)

    def test_float_correction_does_not_change_existing_risk_comparisons(self):
        risk = inventory_risk('SYNTHETIC', [619 / 7] * 14, 619, 7)
        self.assertTrue(risk['stockout_risk'])
        self.assertEqual(risk['status'], 'Stockout Risk')
        self.assertEqual(risk['suggested_reorder_quantity'], 0)


class InventoryPrecisionAPITests(unittest.TestCase):
    def test_overview_inventory_and_decision_lab_proposal_agree(self):
        self.exercise_cases()

    def test_old_cached_reorder_results_refresh_without_refitting_forecasts(self):
        for legacy_version in (None, 1):
            with self.subTest(legacy_version=legacy_version), patch(
                    'forecast.analyse', side_effect=AssertionError('Cached histories must not be refitted')):
                # Confirmation runs the normal existing worker in a subprocess;
                # subsequent GET handlers run here and must use stored forecasts.
                self.exercise_cases(legacy_version=legacy_version)

    def test_current_cached_overview_is_reused_without_recalculation(self):
        cached = {'calculation_version': RISK_CALCULATION_VERSION, 'rows': [], 'summary': {}}
        with patch('batch_inventory.build_risk_overview', side_effect=AssertionError('Cache was recalculated')):
            self.assertIs(saved_risk_overview({'inventory': {'overview': cached}}, 20), cached)
            self.assertIs(saved_risk_overview({'risk_overview': cached}, 20), cached)

    def exercise_cases(self, legacy_version=RISK_CALCULATION_VERSION):
        with tempfile.TemporaryDirectory(prefix='marginguard-SYNTHETIC-precision-') as private:
            app = Flask('SYNTHETIC_precision')
            app.config.update(TESTING=True, SECRET_KEY='SYNTHETIC local test key',
                              ENABLE_BUSINESS_UPLOAD=True, BUSINESS_STORAGE_ROOT=private)
            app.register_blueprint(create_business_blueprint())
            client = app.test_client()
            csrf = {'X-CSRF-Token': client.get('/api/business/session').get_json()['csrf_token']}

            def post(path, status=201, **kwargs):
                response = client.post(path, headers=csrf, **kwargs)
                self.assertEqual(response.status_code, status, response.get_json())
                return response.get_json()

            sales = []
            for index, (tail, _, _, _) in enumerate(CASES):
                sales += synthetic_rows(84, product='SYNTHETIC_' + str(index),
                                        store='SYNTHETIC_STORE', values=[100] * 77 + tail)
            pending = post('/api/business/uploads', data={
                'currency': 'USD', 'time_zone': 'Australia/Sydney', 'tax_basis': 'exclusive',
                'sales_basis': 'gross_units', 'authorized': 'true',
                'file': (io.BytesIO(csv_bytes(sales)), 'SYNTHETIC_sales.csv')})
            ready = post('/api/business/uploads/' + pending['upload_id'] + '/confirm', json={
                'revision': pending['revision'], 'include_unassessed': True,
                'selections': [{key: entry[key] for key in ('series_id', 'start_date', 'end_date')}
                               for entry in pending['series']]})
            prefix = '/api/business/datasets/' + ready['dataset_id']
            fields = ['Product', 'Store', 'Stock As Of Date', 'Current Stock',
                      'Supplier Lead Time', 'Safety Stock', 'On-order Units']
            stock_rows = [dict(zip(fields, [entry['item_id'], entry['store_id'], entry['end_date'],
                                           CASES[int(entry['item_id'][-1])][1], 7,
                                           CASES[int(entry['item_id'][-1])][2], 0]))
                          for entry in ready['series']]
            pending_stock = post(prefix + '/inventory-uploads', data={
                'revision': ready['revision'], 'excess_cover_days': '30', 'assume_no_on_order': 'false',
                'file': (io.BytesIO(csv_bytes(stock_rows, fields)), 'SYNTHETIC_inventory.csv')})
            ready = post(prefix + '/inventory-uploads/' + pending_stock['upload_id'] + '/confirm',
                         json={'revision': ready['revision'], 'upload_revision': pending_stock['revision']})
            stored_before = None
            if legacy_version != RISK_CALCULATION_VERSION:
                # Simulate a live pre-fix session in this test-only private DB.
                store = app.extensions['business_store']
                with store._connect() as database:
                    original = database.execute('SELECT payload FROM datasets WHERE id=?',
                                                (ready['dataset_id'],)).fetchone()['payload']
                    payload = json.loads(original)
                    cached = payload['inventory']['overview']
                    if legacy_version is None:
                        cached.pop('calculation_version', None)
                    else:
                        cached['calculation_version'] = legacy_version
                    for row in cached['rows']:
                        row['risk']['suggested_reorder_quantity'] += 1
                    stored_before = json.dumps(payload)
                    database.execute('UPDATE datasets SET payload=?, bytes=? WHERE id=?',
                                     (stored_before, len(stored_before.encode()), ready['dataset_id']))
            overview_response = client.get(prefix + '/inventory-risk', query_string={'revision': ready['revision']})
            self.assertEqual(overview_response.status_code, 200)
            self.assertEqual(overview_response.get_json()['calculation_version'], RISK_CALCULATION_VERSION)
            overview = {row['series_id']: row for row in overview_response.get_json()['rows']}
            for entry in ready['series']:
                expected = CASES[int(entry['item_id'][-1])][3]
                selection = {'revision': ready['revision'], 'series_id': entry['series_id']}
                response = client.get(prefix + '/analysis', query_string=selection)
                self.assertEqual(response.status_code, 200)
                detail = response.get_json()
                proposal = detail['inventory_import']
                inventory = post(prefix + '/inventory', 200,
                                 json=dict(proposal['inputs'], **selection, currency='USD'))
                self.assertEqual(overview[entry['series_id']]['risk']['suggested_reorder_quantity'], expected)
                self.assertEqual(inventory['suggested_reorder_quantity'], expected)
                self.assertEqual(proposal['suggested_reorder_quantity'], expected)
                # The Financial Decision Lab imports this same proposal, then
                # the unchanged financial engine consumes its whole-unit order.
                result = post(prefix + '/scenarios', 200, json=dict(
                    selection, currency='USD', current_stock=proposal['inputs']['current_stock'],
                    stock_as_of=entry['end_date'], hypothetical_stock_at_origin=False,
                    lead_time_days=7, selling_price=10, existing_unit_cost=2, cash_budget=10000,
                    order_quantity=proposal['suggested_reorder_quantity'], unit_purchase_cost=2,
                    freight=0, other_costs=0, moq=0, discount_percent=0, demand_uplift_percent=0))
                reorder = next(row for row in result['strategies'] if row['strategy'] == 'Reorder')
                self.assertEqual(Decimal(reorder['procurement_cash_outlay']), Decimal(expected * 2))
                self.assertEqual(reorder['daily'][7]['received_units'], expected)
            if stored_before is not None:
                with store._connect() as database:
                    record = database.execute('SELECT revision,payload FROM datasets WHERE id=?',
                                              (ready['dataset_id'],)).fetchone()
                    self.assertEqual(record['revision'], ready['revision'])
                    self.assertEqual(record['payload'], stored_before)


if __name__ == '__main__':
    unittest.main()
