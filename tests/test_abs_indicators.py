"""ABS calendar/units/ratio rules; never call product-level engines."""
import copy
import unittest
from decimal import Decimal
from abs_indicators import (growth_rates, convert_value,
                            official_inventory_sales_ratio, validate_ratio_against_components)


def business_series(table, measure, observation_type, values, unit='AUD million'):
    return {'dataset_id': 'abs_business_indicators', 'series_id': 'test_%d' % table,
            'table_ids': [table], 'measure': measure, 'observation_type': observation_type,
            'geography': 'Australia', 'category': 'Retail trade', 'classification': 'ANZSIC',
            'frequency': 'quarterly', 'unit': unit, 'adjustment': 'Original',
            'price_basis': 'current_prices', 'business_scope': 'TOTAL (SCP_SCOPE)',
            'source': {'release_date': '2026-08-31'},
            'periods': ['2026-Q2'], 'values': values}


class ABSIndicatorTests(unittest.TestCase):
    def test_monthly_growth_uses_actual_calendar_lags(self):
        periods = ['2025-%02d' % month for month in range(1, 13)] + ['2026-01']
        values = [100] * 12 + [125]
        result = growth_rates(periods, values, 'monthly')
        self.assertIsNone(result['period_change_pct'][0])
        self.assertEqual(result['year_change_pct'][:12], [None] * 12)
        self.assertAlmostEqual(result['year_change_pct'][12], 25)
        self.assertAlmostEqual(result['period_change_pct'][12], 25)
        self.assertEqual(values, [100] * 12 + [125])

    def test_quarterly_growth_is_not_monthly_or_annualised(self):
        periods = ['2025-Q2', '2025-Q3', '2025-Q4', '2026-Q1', '2026-Q2']
        result = growth_rates(periods, [80, 100, 100, 120, 160], 'quarterly')
        self.assertAlmostEqual(result['period_change_pct'][-1], 100 / 3)
        self.assertAlmostEqual(result['year_change_pct'][-1], 100)
        self.assertEqual(result['year_change_pct'][:4], [None] * 4)

    def test_missing_values_do_not_become_zero_or_bridge_gaps(self):
        result = growth_rates(['2026-01', '2026-02', '2026-03'], [100, None, 120], 'monthly')
        self.assertEqual(result['period_change_pct'], [None, None, None])
        self.assertIsNone(convert_value(None, 'AUD million', 'AUD'))

    def test_zero_and_negative_bases_are_unavailable(self):
        result = growth_rates(['2026-01', '2026-02', '2026-03', '2026-04', '2026-05'],
                              [100, 0, -10, 20, -20], 'monthly')
        self.assertEqual(result['period_change_pct'], [None, -100, None, None, -200])

    def test_dates_must_be_valid_ordered_unique_and_complete(self):
        for periods in (['2026-01', '2026-03'], ['2026-02', '2026-01'],
                        ['2026-01', '2026-01'], ['2026-13'], ['0000-01'], ['2026-1']):
            with self.subTest(periods=periods), self.assertRaises(ValueError):
                growth_rates(periods, [1] * len(periods), 'monthly')
        with self.assertRaises(ValueError):
            growth_rates(['2026-Q1', '2026-Q3'], [1, 2], 'quarterly')
        with self.assertRaises(ValueError):
            growth_rates(['2026-Q5'], [1], 'quarterly')
        with self.assertRaises(ValueError):
            growth_rates(['2025-26'], [1], 'financial_year')

    def test_numeric_validation_and_length(self):
        for value in (True, '100', float('inf'), float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                growth_rates(['2026-01'], [value], 'monthly')
        with self.assertRaises(ValueError):
            growth_rates(['2026-01'], [], 'monthly')
        self.assertEqual(growth_rates([], [], 'monthly'),
                         {'period_change_pct': [], 'year_change_pct': []})

    def test_explicit_aud_magnitude_conversion(self):
        self.assertEqual(convert_value(Decimal('47803'), 'AUD million', 'AUD'), 47_803_000_000)
        self.assertAlmostEqual(convert_value(47803, 'AUD million', 'AUD billion'), 47.803)
        self.assertEqual(convert_value(0, 'AUD', 'AUD million'), 0)
        self.assertEqual(convert_value(15.7, 'percent', 'percent'), 15.7)

    def test_incompatible_units_cannot_silently_convert(self):
        for original, target in [('ratio', 'percent'), ('businesses', 'AUD'),
                                 ('USD', 'AUD'), ('percent', 'AUD million')]:
            with self.subTest(original=original, target=target), self.assertRaises(ValueError):
                convert_value(1, original, target)
        with self.assertRaises(ValueError):
            convert_value(None, 'ratio', 'percent')

    def test_official_ratio_is_read_not_recomputed(self):
        ratio = business_series(23, 'inventory_to_sales_ratio', 'RATIO', [0.32], 'ratio')
        snapshot = copy.deepcopy(ratio)
        self.assertEqual(official_inventory_sales_ratio(ratio), [{'period': '2026-Q2', 'value': 0.32}])
        self.assertEqual(ratio, snapshot)
        ratio['values'] = [None]
        self.assertEqual(official_inventory_sales_ratio(ratio)[0]['value'], None)

    def test_ratio_requires_correct_source_and_statistical_basis(self):
        ratio = business_series(23, 'inventory_to_sales_ratio', 'RATIO', [0.32], 'ratio')
        for field, value in [('dataset_id', 'abs_mhsi'), ('table_ids', [19]),
                             ('adjustment', 'Seasonally Adjusted'), ('price_basis', 'chain_volume'),
                             ('classification', 'COICOP'), ('unit', 'percent'),
                             ('frequency', 'monthly'), ('observation_type', 'FLOW'),
                             ('business_scope', 'CORP (SCP_SCOPE)')]:
            bad = dict(ratio, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                official_inventory_sales_ratio(bad)

    def test_ratio_reconciles_published_retail_example(self):
        ratio = business_series(23, 'inventory_to_sales_ratio', 'RATIO', [0.32], 'ratio')
        stock = business_series(3, 'inventories', 'STOCK_CLOSE', [47803])
        sales = business_series(6, 'business_sales', 'FLOW', [147756])
        result = validate_ratio_against_components(ratio, stock, sales)
        self.assertTrue(result['consistent'])
        self.assertEqual(result['checked_periods'], 1)
        self.assertAlmostEqual(result['max_absolute_difference'], 47803 / 147756 - .32)
        stock['unit'], stock['values'] = 'AUD', [47_803_000_000]
        self.assertTrue(validate_ratio_against_components(ratio, stock, sales)['consistent'])

    def test_ratio_wrong_category_vintage_or_price_basis_rejected(self):
        ratio = business_series(23, 'inventory_to_sales_ratio', 'RATIO', [.32], 'ratio')
        stock = business_series(3, 'inventories', 'STOCK_CLOSE', [47803])
        sales = business_series(6, 'business_sales', 'FLOW', [147756])
        for field, value in [('category', 'Wholesale trade'), ('geography', 'NSW'),
                             ('price_basis', 'chain_volume_measures'),
                             ('business_scope', 'CORP (SCP_SCOPE)'),
                             ('source', {'release_date': '2026-05-01'})]:
            bad = dict(sales, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_ratio_against_components(ratio, stock, bad)

    def test_ratio_missing_and_zero_sales_not_imputed(self):
        ratio = business_series(23, 'inventory_to_sales_ratio', 'RATIO', [.32], 'ratio')
        stock = business_series(3, 'inventories', 'STOCK_CLOSE', [None])
        sales = business_series(6, 'business_sales', 'FLOW', [147756])
        result = validate_ratio_against_components(ratio, stock, sales)
        self.assertEqual(result['missing_periods'], 1)
        self.assertFalse(result['consistent'])
        self.assertIsNone(result['max_absolute_difference'])
        stock['values'], sales['values'] = [47803], [0]
        result = validate_ratio_against_components(ratio, stock, sales)
        self.assertEqual(result['nonpositive_sales_periods'], 1)

    def test_ratio_mismatch_is_reported_and_nonoverlap_rejected(self):
        ratio = business_series(23, 'inventory_to_sales_ratio', 'RATIO', [.50], 'ratio')
        stock = business_series(3, 'inventories', 'STOCK_CLOSE', [47803])
        sales = business_series(6, 'business_sales', 'FLOW', [147756])
        result = validate_ratio_against_components(ratio, stock, sales)
        self.assertFalse(result['consistent'])
        self.assertEqual(result['mismatches'][0]['period'], '2026-Q2')
        sales['periods'] = ['2026-Q1']
        with self.assertRaises(ValueError):
            validate_ratio_against_components(ratio, stock, sales)


if __name__ == '__main__':
    unittest.main()
