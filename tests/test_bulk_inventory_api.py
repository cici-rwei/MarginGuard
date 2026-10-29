"""Bulk business integration uses explicitly SYNTHETIC daily sales and stock."""
from datetime import date
import io
import tempfile
import unittest

from flask import Flask
from business_api import create_business_blueprint
from business_fixtures import csv_bytes, synthetic_rows
from business_worker import serial
from inventory import inventory_risk


INVENTORY_FIELDS = ['Product', 'Store', 'Stock As Of Date', 'Current Stock',
                    'Supplier Lead Time', 'Safety Stock', 'On-order Units']


class BulkInventoryAPITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='marginguard-SYNTHETIC-bulk-')
        self.addCleanup(temporary.cleanup)
        self.now = 1800000000.0
        self.app = Flask('SYNTHETIC_bulk')
        self.app.config.update(TESTING=True, SECRET_KEY='SYNTHETIC test key',
                               ENABLE_BUSINESS_UPLOAD=True, BUSINESS_STORAGE_ROOT=temporary.name,
                               BUSINESS_CLOCK=lambda: self.now, BUSINESS_MAX_SERIES=20)
        self.app.register_blueprint(create_business_blueprint())
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/business/session').get_json()['csrf_token']

    def headers(self):
        return {'X-CSRF-Token': self.csrf}

    def ready(self, rows=None, currency='AUD', eligible_only=False):
        data = dict(currency=currency, time_zone='Australia/Sydney', sales_basis='gross_units',
                    tax_basis='exclusive', authorized='true',
                    file=(io.BytesIO(csv_bytes(rows if rows is not None else synthetic_rows())), 'SYNTHETIC_sales.csv'))
        response = self.client.post('/api/business/uploads', data=data, headers=self.headers())
        self.assertEqual(response.status_code, 201, response.get_json())
        pending = response.get_json()
        selections = [{key: entry[key] for key in ('series_id', 'start_date', 'end_date')}
                      for entry in pending['series']
                      if not eligible_only or entry['longest_continuous_days'] >= 42]
        response = self.client.post('/api/business/uploads/%s/confirm' % pending['upload_id'],
                                    json=dict(revision=pending['revision'], selections=selections,
                                              include_unassessed=True), headers=self.headers())
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def prefix(self, ready):
        return '/api/business/datasets/' + ready['dataset_id']

    def stock(self, ready, *, stock=10, on_order=0, **changes):
        entry = ready['series'][0]
        row = dict(zip(INVENTORY_FIELDS, [entry['item_id'], entry['store_id'], entry['end_date'], stock, 7, 5, on_order]))
        row.update(changes)
        return row

    def pending(self, ready, rows, *, assume='false'):
        response = self.client.post(self.prefix(ready) + '/inventory-uploads',
                                    data=dict(revision=ready['revision'], excess_cover_days='30',
                                              assume_no_on_order=assume,
                                              file=(io.BytesIO(csv_bytes(rows, INVENTORY_FIELDS)), 'SYNTHETIC_inventory.csv')),
                                    headers=self.headers())
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def attach(self, ready, rows, **options):
        pending = self.pending(ready, rows, **options)
        response = self.client.post(self.prefix(ready) + '/inventory-uploads/%s/confirm' % pending['upload_id'],
                                    json=dict(revision=ready['revision'], upload_revision=pending['revision']),
                                    headers=self.headers())
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def overview(self, ready, **filters):
        response = self.client.get(self.prefix(ready) + '/inventory-risk',
                                   query_string=dict(revision=ready['revision'], **filters))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def detail(self, ready, entry=None):
        return self.client.get(self.prefix(ready) + '/analysis', query_string=dict(
            revision=ready['revision'], series_id=(entry or ready['series'][0])['series_id']))

    def test_sales_only_keeps_forecasts_and_inventory_unknown(self):
        ready = self.ready()
        result = self.overview(ready)
        self.assertEqual(result['summary']['products_analysed'], 1)
        self.assertEqual(result['summary']['data_incomplete'], 1)
        row = result['rows'][0]
        self.assertIsNone(row['current_stock'])
        self.assertIsNone(row['risk'])
        self.assertGreater(row['forecast_demand'], 0)
        self.assertEqual(row['action'], 'Complete Missing Data')

    def test_attachment_rotates_version_and_preserves_exact_forecasts_and_currency(self):
        ready = self.ready(currency='USD')
        before = self.detail(ready).get_json()
        updated = self.attach(ready, [self.stock(ready)])
        self.assertEqual(updated['dataset_id'], ready['dataset_id'])
        self.assertNotEqual(updated['revision'], ready['revision'])
        self.assertEqual(self.detail(ready).status_code, 409)
        after = self.detail(updated).get_json()
        self.assertEqual(before['analysis'], after['analysis'])
        self.assertEqual(before['history'], after['history'])
        self.assertEqual(after['currency'], 'USD')
        proposal = after['inventory_import']
        self.assertEqual(proposal['context'], after['context'])
        self.assertEqual(proposal['inputs']['current_stock'], 10)
        self.assertEqual(proposal['inputs']['stock_as_of'], updated['series'][0]['end_date'])
        self.assertFalse(proposal['inputs']['hypothetical_stock_at_origin'])
        self.assertTrue(all(value is None for value in after['defaults'].values()))

    def test_batch_is_identical_to_single_inventory_engine_and_endpoint(self):
        ready = self.ready()
        ready = self.attach(ready, [self.stock(ready)])
        detail = self.detail(ready).get_json()
        proposal = detail['inventory_import']
        expected = inventory_risk(detail['item_id'], [r['prediction'] for r in detail['analysis']['future']],
                                  current_stock=10, lead_time_days=7, safety_stock=5, on_order_units=0,
                                  excess_cover_days=30)
        self.assertEqual(self.overview(ready)['rows'][0]['risk'], serial(expected))
        inputs = dict(proposal['inputs'], series_id=ready['series'][0]['series_id'],
                      revision=ready['revision'], currency='AUD')
        response = self.client.post(self.prefix(ready) + '/inventory', json=inputs, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.get_json())
        for key, value in serial(expected).items():
            self.assertEqual(response.get_json()[key], value)

    def test_multiple_products_stores_have_separate_risks_and_python_filters(self):
        rows = synthetic_rows(84, product='SYNTHETIC_A', store='SYNTHETIC_1', values=[3]*84)
        rows += synthetic_rows(84, product='SYNTHETIC_A', store='SYNTHETIC_2', values=[7]*84)
        rows += synthetic_rows(84, product='SYNTHETIC_B', store='SYNTHETIC_1', values=[11]*84)
        ready = self.ready(rows)
        stock_rows = []
        quantities = {('SYNTHETIC_A', 'SYNTHETIC_1'): 5, ('SYNTHETIC_A', 'SYNTHETIC_2'): 500,
                      ('SYNTHETIC_B', 'SYNTHETIC_1'): 100}
        for entry in ready['series']:
            stock_rows.append(dict(zip(INVENTORY_FIELDS, [entry['item_id'], entry['store_id'], entry['end_date'],
                                                          quantities[(entry['item_id'], entry['store_id'])], 7, 5, 0])))
        ready = self.attach(ready, stock_rows)
        overview = self.overview(ready)
        self.assertEqual(overview['summary']['high_stockout_risk'], 1)
        self.assertEqual(overview['summary']['excess_inventory_risk'], 1)
        self.assertEqual(overview['summary']['sufficient_inventory'], 1)
        self.assertEqual(overview['rows'][0]['risk_code'], 'stockout')
        self.assertEqual(self.overview(ready, risk='excess')['filtered_count'], 1)
        self.assertEqual(self.overview(ready, store='SYNTHETIC_1')['filtered_count'], 2)
        self.assertEqual(self.overview(ready, search='SYNTHETIC_B')['filtered_count'], 1)
        self.assertEqual(self.overview(ready, sort='demand_desc')['rows'][0]['forecast_demand'], 154)
        self.assertEqual(self.overview(ready, sort='stock_asc')['rows'][0]['current_stock'], 5)

    def test_invalid_date_alignment_remains_not_assessed_without_manual_proposal(self):
        ready = self.ready()
        ready = self.attach(ready, [self.stock(ready, **{'Stock As Of Date': '2024-03-23'})])
        row = self.overview(ready)['rows'][0]
        self.assertEqual(row['risk_code'], 'not_assessed')
        self.assertIsNone(row['risk'])
        self.assertEqual(row['stock_as_of_date'], '2024-03-23')
        self.assertEqual(row['expected_stock_date'], '2024-03-24')
        self.assertIsNone(self.detail(ready).get_json()['inventory_import'])

    def test_unknown_on_order_requires_explicit_no_orders_declaration(self):
        ready = self.ready()
        ready = self.attach(ready, [self.stock(ready, on_order='')])
        self.assertEqual(self.overview(ready)['rows'][0]['risk_code'], 'not_assessed')
        ready = self.attach(ready, [self.stock(ready, on_order='')], assume='true')
        self.assertEqual(self.overview(ready)['rows'][0]['risk_code'], 'stockout')
        self.assertEqual(self.detail(ready).get_json()['inventory_import']['inputs']['on_order_units'], 0)

    def test_41_day_and_unselected_combinations_stay_in_overview_without_forecast(self):
        rows = synthetic_rows(41, product='SYNTHETIC_SHORT') + synthetic_rows(84, product='SYNTHETIC_LONG')
        ready = self.ready(rows, eligible_only=True)
        result = self.overview(ready)
        self.assertEqual(len(ready['series']), 1)
        self.assertEqual(len(ready['catalog_series']), 2)
        self.assertEqual(result['summary']['total_products'], 2)
        self.assertEqual(result['summary']['products_analysed'], 1)
        short = next(r for r in result['rows'] if r['item_id'] == 'SYNTHETIC_SHORT')
        self.assertIsNone(short['forecast_demand'])
        self.assertEqual(short['risk_code'], 'not_assessed')

    def test_all_short_history_can_be_confirmed_only_as_unassessed(self):
        ready = self.ready(synthetic_rows(41), eligible_only=True)
        self.assertEqual(ready['series'], [])
        self.assertEqual(self.overview(ready)['summary']['data_incomplete'], 1)
        self.assertEqual(self.overview(ready)['summary']['products_analysed'], 0)

    def test_unmatched_inventory_never_creates_sales_or_silent_zero_stock(self):
        ready = self.ready()
        ready = self.attach(ready, [self.stock(ready, Product='SYNTHETIC_UNMATCHED')])
        result = self.overview(ready)
        self.assertEqual(result['summary']['total_products'], 1)
        self.assertEqual(result['summary']['data_incomplete'], 1)
        self.assertIsNone(result['rows'][0]['current_stock'])
        self.assertTrue(result['inventory_quality'])

    def test_new_inventory_context_works_in_aud_and_usd_financial_engine(self):
        for currency in ('AUD', 'USD'):
            self.now += 601  # Independent synthetic runs, no upload-limit bypass in production.
            ready = self.ready(currency=currency)
            ready = self.attach(ready, [self.stock(ready)])
            info = self.detail(ready).get_json()
            values = dict(series_id=ready['series'][0]['series_id'], revision=ready['revision'], currency=currency,
                          stock_as_of=ready['series'][0]['end_date'], hypothetical_stock_at_origin=False,
                          current_stock=10, selling_price='4.50', existing_unit_cost='2.10', cash_budget=1000,
                          order_quantity=80, unit_purchase_cost='2', freight=5, other_costs=0, moq=10,
                          lead_time_days=7, discount_percent=10, demand_uplift_percent=20)
            response = self.client.post(self.prefix(ready) + '/scenarios', json=values, headers=self.headers())
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(response.get_json()['context'], info['inventory_import']['context'])
            self.assertEqual(response.get_json()['currency'], currency)
            self.assertEqual(len(response.get_json()['strategies']), 3)


if __name__ == '__main__':
    unittest.main()
