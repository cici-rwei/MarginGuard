"""Batch inventory checks using clearly SYNTHETIC sales and stock fixtures."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from batch_inventory import BatchInventoryError, build_risk_overview, filter_risk_overview
from business_csv import parse_business_csv
from business_forecast import analyse_business_series
from inventory import inventory_risk
from inventory_csv import parse_inventory_csv
from business_fixtures import synthetic_rows, csv_bytes, AS_OF


def serial(value):
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serial(item) for item in value]
    if isinstance(value, (date, Decimal)):
        return str(value)
    return value


def synthetic_payload(count=1, days=84, values=None):
    rows = []
    for index in range(count):
        rows += synthetic_rows(days=days, product='SYNTHETIC_PRODUCT_' + str(index),
                               store='SYNTHETIC_STORE_' + str(index % 2),
                               values=[10] * days if values is None else values)
    parsed = parse_business_csv(csv_bytes(rows), 'AUD', sales_basis='gross_units', as_of_date=AS_OF)
    catalog, selected = [], []
    for index, report in enumerate(parsed['report']['series']):
        entry = dict(report, series_id='synthetic_' + str(index), item_id=report['product'], store_id=report['store'])
        catalog.append(entry)
        if days >= 42:
            result = analyse_business_series(parsed, report['product'], report['store'])
            selected.append(dict(series_id=entry['series_id'], item_id=report['product'], store_id=report['store'],
                                 start_date=str(result['analysis']['history_start']), end_date=str(result['analysis']['history_end']),
                                 observations=result['analysis']['observations'], result=serial(result)))
    return {'meta': {'source_kind': 'user_csv', 'currency': 'AUD'}, 'catalog_series': catalog, 'series': selected}


def attach_inventory(payload, stocks=None, **options):
    if stocks is None:
        stocks = [100] * len(payload['catalog_series'])
    rows = [dict(product=entry['product'], store=entry['store'], stock_as_of_date=entry['end_date'],
                 current_stock=stock, lead_time_days=7, safety_stock=10, on_order_units=0)
            for entry, stock in zip(payload['catalog_series'], stocks)]
    payload['inventory'] = dict(rows=rows, excess_cover_days=30, assume_no_on_order=False, report={'synthetic': True})
    payload['inventory'].update(options)
    return payload


class BatchInventoryTests(unittest.TestCase):
    def overview(self, payload):
        return build_risk_overview(payload, max_series=20)

    def test_forecasts_visible_without_stock_and_no_zero_imputation(self):
        result = self.overview(synthetic_payload())
        row = result['rows'][0]
        self.assertEqual(result['summary']['products_analysed'], 1)
        self.assertEqual(result['summary']['data_incomplete'], 1)
        self.assertEqual(row['forecast_demand'], 140)
        self.assertIsNone(row['current_stock'])
        self.assertIsNone(row['risk'])
        self.assertIsNone(row['inventory_inputs'])
        self.assertEqual(row['status'], 'Not assessed')
        self.assertEqual(result['inventory_quality']['missing_snapshot_count'], 1)

    def test_matching_snapshot_calls_core_unchanged_and_keeps_forecast_and_mae(self):
        payload = attach_inventory(synthetic_payload(), [35])
        result = self.overview(payload)
        row = result['rows'][0]
        core = inventory_risk(row['item_id'], [10] * 14, 35, 7, 10, 0, 30)
        self.assertEqual(row['risk'], core)
        self.assertEqual(row['forecast_method'], 'moving_average_7')
        self.assertEqual(row['mae'], 0)
        self.assertEqual(row['forecast_start'], '2024-03-25')
        self.assertEqual(row['forecast_end'], '2024-04-07')
        self.assertEqual(row['expected_stock_date'], '2024-03-24')
        self.assertEqual(row['assessment_status'], 'assessed')
        self.assertEqual(row['risk_code'], 'stockout')
        self.assertEqual(row['action'], 'Evaluate Reorder')
        self.assertIn('not independently verified', row['assessment_provenance'])
        self.assertEqual(row['inventory_inputs'], dict(current_stock=35, lead_time_days=7, safety_stock=10,
                                                      on_order_units=0, excess_cover_days=Decimal(30)))
        self.assertIn('not purchasing recommendations', row['action_reason'])

    def test_primary_categories_exclusive_and_forecast_count_is_separate(self):
        payload = attach_inventory(synthetic_payload(5), [1, 75, 400, 100, 100])
        payload['inventory']['rows'][4]['safety_stock'] = None
        result = self.overview(payload)
        summary = result['summary']
        self.assertEqual([row['risk_code'] for row in result['rows']],
                         ['stockout', 'reorder_attention', 'excess', 'sufficient', 'not_assessed'])
        self.assertEqual([summary[key] for key in ('total_products', 'products_analysed', 'high_stockout_risk',
                         'reorder_attention', 'excess_inventory_risk', 'sufficient_inventory', 'data_incomplete')],
                         [5, 5, 1, 1, 1, 1, 1])
        self.assertIn('mutually exclusive', summary['classification_note'])

    def test_stockout_priority_kept_even_when_excess_flag_also_true(self):
        payload = attach_inventory(synthetic_payload(), [100], excess_cover_days=5)
        payload['inventory']['rows'][0]['lead_time_days'] = 20
        row = self.overview(payload)['rows'][0]
        self.assertTrue(row['risk']['stockout_risk'])
        self.assertTrue(row['risk']['excess_inventory_warning'])
        self.assertEqual(row['risk_code'], 'stockout')
        self.assertEqual(row['priority'], 1)
        self.assertTrue(row['risk']['extrapolated'])
        self.assertEqual(row['risk']['lead_time_demand'], 200)

    def test_snapshot_before_or_after_selected_end_never_adjusted(self):
        for day in ['2024-03-23', '2024-03-25']:
            payload = attach_inventory(synthetic_payload())
            payload['inventory']['rows'][0]['stock_as_of_date'] = day
            result = self.overview(payload)
            row = result['rows'][0]
            self.assertEqual(row['risk_code'], 'not_assessed')
            self.assertEqual(row['stock_as_of_date'], day)
            self.assertEqual(result['inventory_quality']['date_mismatch_count'], 1)
            self.assertIn('snapshot_date_mismatch', [item['code'] for item in row['issues']])

    def test_missing_snapshot_date_and_each_required_input_not_assessed(self):
        for field in ['stock_as_of_date', 'current_stock', 'lead_time_days', 'safety_stock', 'on_order_units']:
            payload = attach_inventory(synthetic_payload())
            payload['inventory']['rows'][0][field] = None
            row = self.overview(payload)['rows'][0]
            self.assertEqual(row['risk_code'], 'not_assessed', field)
            self.assertIsNone(row['inventory_inputs'])
            self.assertIsNone(row['risk'])

    def test_missing_on_order_requires_explicit_boolean_declaration(self):
        for flag in [False, None, 'true', 1, True]:
            payload = attach_inventory(synthetic_payload(), assume_no_on_order=flag)
            payload['inventory']['rows'][0]['on_order_units'] = None
            result = self.overview(payload)
            row = result['rows'][0]
            self.assertEqual(row['assessment_status'], 'assessed' if flag is True else 'not_assessed')
            if flag is True:
                self.assertEqual(row['inventory_inputs']['on_order_units'], 0)
                self.assertIn('assumed_no_on_order', [issue['code'] for issue in row['issues']])
                self.assertEqual(result['inventory_quality']['assumed_no_on_order_count'], 1)

    def test_explicit_pending_units_not_overridden_or_counted_as_current_stock(self):
        payload = attach_inventory(synthetic_payload(), [1], assume_no_on_order=True)
        payload['inventory']['rows'][0]['on_order_units'] = 1000
        row = self.overview(payload)['rows'][0]
        self.assertEqual(row['risk_code'], 'stockout')
        self.assertEqual(row['risk']['inventory_position'], 1001)
        self.assertEqual(row['risk']['suggested_reorder_quantity'], 0)
        self.assertEqual(row['current_stock'], 1)
        self.assertEqual(row['inventory_inputs']['on_order_units'], 1000)

    def test_excess_threshold_is_explicit_and_validated(self):
        for threshold in [None, 0, -1, 3651, 'NaN', True]:
            payload = attach_inventory(synthetic_payload(), excess_cover_days=threshold)
            row = self.overview(payload)['rows'][0]
            self.assertEqual(row['risk_code'], 'not_assessed')
        row = self.overview(attach_inventory(synthetic_payload(), excess_cover_days='30'))['rows'][0]
        self.assertEqual(row['risk']['excess_cover_days'], Decimal('30'))

    def test_zero_demand_and_zero_delivery_keep_original_rules(self):
        payload = attach_inventory(synthetic_payload(values=[0] * 84), [10])
        row = self.overview(payload)['rows'][0]
        self.assertEqual(row['risk_code'], 'reorder_attention' if row['risk']['inventory_position'] < 10 else 'excess')
        self.assertIsNone(row['risk']['days_of_cover'])
        self.assertEqual(row['forecast_demand'], 0)
        payload['inventory']['rows'][0].update(current_stock=0, lead_time_days=0, safety_stock=0)
        row = self.overview(payload)['rows'][0]
        self.assertEqual(row['risk_code'], 'sufficient')

    def test_41_day_catalog_is_retained_without_forecasting(self):
        result = self.overview(attach_inventory(synthetic_payload(days=41)))
        row = result['rows'][0]
        self.assertEqual(result['summary']['total_products'], 1)
        self.assertEqual(result['summary']['products_analysed'], 0)
        self.assertIn('insufficient_history', [item['code'] for item in row['issues']])
        self.assertIsNone(row['forecast_demand'])

    def test_42_day_confirmed_history_allowed(self):
        row = self.overview(attach_inventory(synthetic_payload(days=42)))['rows'][0]
        self.assertEqual(row['assessment_status'], 'assessed')

    def test_missing_unknown_and_unselected_window_reasons_are_retained(self):
        payload = synthetic_payload()
        payload['series'] = []
        payload['catalog_series'][0].update(missing_dates=['2024-02-01'], unknown_sales_dates=['2024-02-02'],
                                             longest_continuous_days=50)
        row = self.overview(payload)['rows'][0]
        codes = {issue['code'] for issue in row['issues']}
        self.assertTrue({'missing_dates', 'unknown_sales', 'forecast_not_selected'} <= codes)
        self.assertNotIn('insufficient_history', codes)

    def test_selected_valid_window_not_invalidated_by_gaps_outside_it(self):
        payload = attach_inventory(synthetic_payload())
        payload['catalog_series'][0].update(missing_dates=['2023-12-01'], unknown_sales_dates=['2023-12-02'])
        self.assertEqual(self.overview(payload)['rows'][0]['assessment_status'], 'assessed')

    def test_selected_window_stock_date_uses_window_end_not_catalog_end(self):
        payload = attach_inventory(synthetic_payload())
        payload['catalog_series'][0]['end_date'] = '2024-12-01'
        row = self.overview(payload)['rows'][0]
        self.assertEqual(row['expected_stock_date'], '2024-03-24')
        self.assertEqual(row['assessment_status'], 'assessed')

    def test_unmatched_inventory_not_dropped_and_exact_case_sensitive_matching(self):
        payload = attach_inventory(synthetic_payload())
        payload['inventory']['rows'][0]['product'] = 'synthetic_product_0'
        payload['inventory']['rows'].append(dict(product=None, store='SYNTHETIC_STORE_0', stock_as_of_date=None))
        result = self.overview(payload)
        self.assertEqual(result['inventory_quality']['unmatched_rows'], 2)
        self.assertEqual(result['inventory_quality']['matched_rows'], 0)
        self.assertEqual(result['summary']['total_products'], 1)
        self.assertEqual(result['summary']['data_incomplete'], 1)

    def test_duplicate_inventory_and_catalog_rejected(self):
        payload = attach_inventory(synthetic_payload())
        payload['inventory']['rows'].append(deepcopy(payload['inventory']['rows'][0]))
        with self.assertRaises(BatchInventoryError):
            self.overview(payload)
        payload = synthetic_payload()
        payload['catalog_series'].append(deepcopy(payload['catalog_series'][0]))
        with self.assertRaises(BatchInventoryError):
            self.overview(payload)

    def test_catalog_fallback_for_existing_ready_payload(self):
        payload = attach_inventory(synthetic_payload())
        del payload['catalog_series']
        self.assertEqual(self.overview(payload)['summary']['sufficient_inventory'], 1)

    def test_catalog_and_snapshot_caps_never_silently_truncate(self):
        payload = synthetic_payload(21)
        with self.assertRaises(BatchInventoryError):
            self.overview(payload)
        self.assertEqual(build_risk_overview(payload, max_series=100)['summary']['total_products'], 21)
        payload = attach_inventory(synthetic_payload())
        payload['inventory']['rows'] *= 21
        with self.assertRaises(BatchInventoryError):
            self.overview(payload)

    def test_inconsistent_confirmed_forecast_never_assessed(self):
        changes = [lambda e: e.update(observations=41),
                   lambda e: e['result']['history'][1].update(date='2024-01-03'),
                   lambda e: e['result']['history'][0].update(units_sold=None),
                   lambda e: e['result']['analysis']['future'][0].update(date='2024-03-24'),
                   lambda e: e['result']['analysis']['future'][0].update(prediction=-1),
                   lambda e: e['result'].update(product='SYNTHETIC_OTHER')]
        for change in changes:
            payload = attach_inventory(synthetic_payload())
            change(payload['series'][0])
            row = self.overview(payload)['rows'][0]
            self.assertEqual(row['risk_code'], 'not_assessed')
            self.assertIsNone(row['forecast_demand'])

    def test_invalid_inventory_values_do_not_reach_core(self):
        for field, value in [('current_stock', -1), ('lead_time_days', 366), ('safety_stock', True), ('on_order_units', 1.5)]:
            payload = attach_inventory(synthetic_payload())
            payload['inventory']['rows'][0][field] = value
            row = self.overview(payload)['rows'][0]
            self.assertEqual(row['risk_code'], 'not_assessed')
            self.assertIsNone(row['inventory_inputs'])

    def test_filters_keep_full_summary_and_sort_without_mutation(self):
        payload = attach_inventory(synthetic_payload(4), [5, 75, 400, 100])
        original_payload = deepcopy(payload)
        overview = self.overview(payload)
        self.assertEqual(payload, original_payload)
        original_overview = deepcopy(overview)
        filtered = filter_risk_overview(overview, risk='stockout', store='SYNTHETIC_STORE_0', search='product_0')
        self.assertEqual(filtered['filtered_count'], 1)
        self.assertEqual(filtered['summary'], overview['summary'])
        self.assertEqual(filtered['summary']['total_products'], 4)
        self.assertEqual([row['current_stock'] for row in filter_risk_overview(overview, sort='stock_asc')['rows']], [5, 75, 100, 400])
        self.assertEqual(len(filter_risk_overview(overview, sort='demand_desc')['rows']), 4)
        self.assertEqual(filter_risk_overview(overview, search='DOES_NOT_EXIST')['filtered_count'], 0)
        self.assertEqual(overview, original_overview)

    def test_unknown_values_sort_last_and_illegal_filter_rejected(self):
        payload = attach_inventory(synthetic_payload(2), [None, 100])
        overview = self.overview(payload)
        self.assertIsNone(filter_risk_overview(overview, sort='stock_asc')['rows'][-1]['current_stock'])
        for options in [dict(risk='guessed_high'), dict(sort='arbitrary'), dict(search=True), dict(store=1)]:
            with self.assertRaises(BatchInventoryError):
                filter_risk_overview(overview, **options)

    def test_shipped_sales_and_inventory_samples_yield_expected_core_categories(self):
        folder = Path(__file__).resolve().parents[1] / 'examples/business_csv'
        sales = parse_business_csv((folder / 'synthetic_multi_series.csv').read_bytes(), 'AUD',
                                   sales_basis='gross_units', as_of_date=AS_OF)
        payload = {'meta': {'currency': 'AUD'}, 'series': [], 'catalog_series': []}
        for index, entry in enumerate(sales['report']['series']):
            sid = 'synthetic_' + str(index)
            result = analyse_business_series(sales, entry['product'], entry['store'])
            payload['catalog_series'].append(dict(entry, series_id=sid))
            payload['series'].append(dict(series_id=sid, item_id=entry['product'], store_id=entry['store'],
                start_date=str(result['analysis']['history_start']), end_date=str(result['analysis']['history_end']),
                observations=result['analysis']['observations'], result=serial(result)))
        payload['inventory'] = dict(parse_inventory_csv((folder / 'synthetic_inventory_multi_series.csv').read_bytes(),
                                                        as_of_date=AS_OF), excess_cover_days=30, assume_no_on_order=False)
        overview = self.overview(payload)
        summary = overview['summary']
        self.assertEqual([summary[key] for key in ('products_analysed', 'high_stockout_risk', 'excess_inventory_risk', 'sufficient_inventory', 'data_incomplete')], [3, 1, 1, 1, 0])
        # The worker's standard Decimal/date conversion can encode the pure result.
        json.dumps(serial(overview), allow_nan=False)


if __name__ == '__main__':
    unittest.main()
