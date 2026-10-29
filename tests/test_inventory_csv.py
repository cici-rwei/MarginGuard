"""SYNTHETIC inventory snapshots only; no enterprise or Walmart records."""
import csv
import io
from datetime import date, datetime
from pathlib import Path
import unittest

from business_csv import BusinessCSVError
from inventory_csv import InventoryCSVError, parse_inventory_csv

AS_OF = date(2025, 1, 1)
FIELDS = ['Product', 'Store', 'Stock As Of Date', 'Current Stock',
          'Supplier Lead Time', 'Safety Stock', 'On-order Units']


def snapshot(**changes):
    row = dict(zip(FIELDS, ['SYNTHETIC_PRODUCT', 'SYNTHETIC_STORE', '2024-03-24', '30', '7', '10', '0']))
    row.update(changes)
    return row


def csv_data(rows, fields=FIELDS, bom=False):
    content = io.StringIO(newline='')
    writer = csv.DictWriter(content, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return content.getvalue().encode('utf-8-sig' if bom else 'utf-8')


class InventoryCSVTests(unittest.TestCase):
    def parse(self, rows, **kwargs):
        return parse_inventory_csv(csv_data(rows), as_of_date=AS_OF, **kwargs)

    def error(self, content, code, **kwargs):
        with self.assertRaises(InventoryCSVError) as caught:
            parse_inventory_csv(content, as_of_date=AS_OF, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertIsInstance(caught.exception, BusinessCSVError)
        return caught.exception

    def test_normal_snapshot_has_iso_date_and_integer_units(self):
        result = self.parse([snapshot()])
        self.assertEqual(result['rows'][0], dict(product='SYNTHETIC_PRODUCT', store='SYNTHETIC_STORE',
            stock_as_of_date='2024-03-24', current_stock=30, lead_time_days=7, safety_stock=10, on_order_units=0))
        self.assertEqual(result['report']['complete_rows'], 1)
        self.assertEqual(result['report']['issues'], [])

    def test_bom_and_explicit_supported_header_aliases(self):
        fields = ['product', 'store', 'stock_as_of_date', 'current_stock', 'lead_time_days', 'safety_stock', 'on_order_units']
        row = dict(zip(fields, ['SYNTHETIC_A', 'SYNTHETIC_B', '2024-03-24', '0', '0', '0', '0']))
        parsed = parse_inventory_csv(csv_data([row], fields, True), as_of_date=AS_OF)
        self.assertEqual(parsed['rows'][0]['current_stock'], 0)

    def test_header_missing_fails_even_if_cells_can_be_unknown(self):
        self.error(csv_data([snapshot()], FIELDS[:-2]), 'missing_column')

    def test_unknown_and_duplicate_canonical_headers_rejected(self):
        self.error(csv_data([snapshot()], FIELDS[:-1] + ['Extra']), 'unknown_column')
        self.error(csv_data([snapshot()], FIELDS[:-1] + ['current_stock']), 'duplicate_column')

    def test_required_blank_cells_remain_unknown_with_issues(self):
        row = {field: '' for field in FIELDS}
        result = self.parse([row])
        self.assertTrue(all(value is None for value in result['rows'][0].values()))
        self.assertEqual(len(result['report']['issues']), 7)
        self.assertEqual(result['report']['incomplete_rows'], 1)
        self.assertTrue(all(issue['row_index'] == 0 for issue in result['report']['issues']))

    def test_missing_optional_on_order_never_becomes_zero(self):
        parsed = parse_inventory_csv(csv_data([snapshot()], FIELDS[:-1]), as_of_date=AS_OF)
        self.assertIsNone(parsed['rows'][0]['on_order_units'])
        self.assertEqual(parsed['report']['missing_values']['on_order_units'], 1)

    def test_duplicate_product_store_rejected_even_on_different_date(self):
        self.error(csv_data([snapshot(), snapshot(**{'Stock As Of Date': '2024-03-25'})]), 'duplicate_record')

    def test_identical_product_across_different_stores_is_valid(self):
        result = self.parse([snapshot(), snapshot(Store='SYNTHETIC_OTHER_STORE')])
        self.assertEqual(len(result['rows']), 2)

    def test_strict_calendar_and_date_format(self):
        for value in ['2024-02-30', '24-03-24', '2024-3-24', '2024-03-24T00:00:00', '２０２４-03-24']:
            with self.subTest(value=value):
                self.error(csv_data([snapshot(**{'Stock As Of Date': value})]), 'invalid_date')

    def test_first_incomplete_or_future_day_rejected(self):
        for value in ['2025-01-01', '2026-01-01']:
            self.error(csv_data([snapshot(**{'Stock As Of Date': value})]), 'incomplete_or_future_date')

    def test_numeric_literals_reject_returns_fractions_exponents_boolean_and_unicode(self):
        for field in FIELDS[3:]:
            for value in ['-1', '1.0', '1e2', '+1', 'NaN', 'True', '１２', '1,000']:
                with self.subTest(field=field, value=value):
                    self.error(csv_data([snapshot(**{field: value})]), 'invalid_units')

    def test_core_numeric_limits_and_zero(self):
        result = self.parse([snapshot(**{'Current Stock': '1000000', 'Supplier Lead Time': '365',
                                         'Safety Stock': '000', 'On-order Units': '0'})])
        self.assertEqual(result['rows'][0]['safety_stock'], 0)
        for field, value in [('Current Stock', '1000001'), ('Supplier Lead Time', '366'),
                             ('Safety Stock', '1000001'), ('On-order Units', '1000001')]:
            self.error(csv_data([snapshot(**{field: value})]), 'units_out_of_range')

    def test_identifiers_preserve_case_and_trim_only_outer_whitespace(self):
        result = self.parse([snapshot(Product=' SYNTHETIC_MiXeD ', Store=' SYNTHETIC_門店 ')])
        self.assertEqual(result['rows'][0]['product'], 'SYNTHETIC_MiXeD')
        self.assertEqual(result['rows'][0]['store'], 'SYNTHETIC_門店')

    def test_formula_control_and_long_identifiers_rejected_without_value_echo(self):
        for value, code in [('=SYNTHETIC_SECRET', 'invalid_identifier'), ('SYNTHETIC\u200bSECRET', 'invalid_identifier'),
                            ('S' * 81, 'identifier_too_long')]:
            exception = self.error(csv_data([snapshot(Product=value)]), code)
            self.assertNotIn(value, str(exception))
            self.assertNotIn(value, str(exception.errors))

    def test_row_limit_20_default_and_100_local(self):
        rows = [snapshot(Product='SYNTHETIC_' + str(i)) for i in range(21)]
        self.error(csv_data(rows), 'too_many_rows')
        self.assertEqual(len(self.parse(rows, max_rows=100)['rows']), 21)
        for value in [0, 101, True, '20']:
            self.error(csv_data([snapshot()]), 'invalid_limit', max_rows=value)

    def test_encoding_nul_and_size_rejected(self):
        self.error(b'\xff\xfe', 'invalid_encoding')
        self.error(b'\x00', 'invalid_csv')
        self.error(b'x' * (5 * 1024 * 1024 + 1), 'file_too_large')
        self.error('not bytes', 'invalid_content')

    def test_empty_header_only_invalid_quote_and_wrong_cell_count(self):
        self.error(b'', 'empty_csv')
        self.error(csv_data([]), 'empty_csv')
        self.error((','.join(FIELDS) + '\n"unterminated').encode(), 'invalid_csv')
        self.error((','.join(FIELDS) + '\na,b\n').encode(), 'column_count')

    def test_as_of_requires_date_and_long_field_rejected(self):
        for invalid in [None, '2025-01-01', datetime(2025, 1, 1)]:
            with self.assertRaises(InventoryCSVError) as caught:
                parse_inventory_csv(csv_data([snapshot()]), as_of_date=invalid)
            self.assertEqual(caught.exception.code, 'invalid_as_of_date')
        self.error(csv_data([snapshot(**{'Current Stock': '0' * 1025})]), 'field_too_long')

    def test_blank_lines_skipped_but_comma_filled_row_retained(self):
        content = b'\n' + csv_data([{field: '' for field in FIELDS}]) + b'\n'
        self.assertEqual(len(parse_inventory_csv(content, as_of_date=AS_OF)['rows']), 1)

    def test_shipped_synthetic_fixture_is_valid_and_template_has_required_headers(self):
        folder = Path(__file__).resolve().parents[1] / 'examples/business_csv'
        result = parse_inventory_csv((folder / 'synthetic_inventory_multi_series.csv').read_bytes(), as_of_date=AS_OF)
        self.assertEqual(len(result['rows']), 3)
        self.assertTrue(all(row['product'].startswith('SYNTHETIC_') for row in result['rows']))
        self.assertEqual(next(csv.reader((folder / 'inventory_template.csv').read_text().splitlines())), FIELDS)


if __name__ == '__main__':
    unittest.main()
