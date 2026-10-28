"""Business CSV contracts using only explicitly synthetic test fixtures."""
import copy
import json
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from business_csv import BusinessCSVError, load_business_csv, parse_business_csv
from business_fixtures import AS_OF, FIELDS, PRODUCT, START, STORE, csv_bytes, synthetic_rows


class BusinessCSVTests(unittest.TestCase):
    def parse(self, rows=None, *, content=None, currency='AUD', **kwargs):
        if content is None:
            content = csv_bytes(synthetic_rows() if rows is None else rows)
        return parse_business_csv(content, currency, sales_basis='gross_units',
                                  as_of_date=AS_OF, **kwargs)

    def quality(self, dataset, product=PRODUCT, store=STORE):
        return next(row for row in dataset['report']['series']
                    if row['product'] == product and row['store'] == store)

    def test_utf8_and_bom_preserve_sorted_observations_and_decimal_amounts(self):
        rows = synthetic_rows(42)
        for bom in (False, True):
            with self.subTest(bom=bom):
                result = self.parse(content=csv_bytes(list(reversed(rows)), bom=bom))
                history = result['groups'][(PRODUCT, STORE)]
                self.assertEqual(history[0]['date'], START)
                self.assertEqual(history[-1]['date'], START + timedelta(days=41))
                self.assertEqual(history[0]['unit_price'], Decimal('4.50'))
                self.assertEqual(history[0]['unit_cost'], Decimal('2.10'))
                self.assertIsInstance(history[0]['units_sold'], int)

    def test_optional_columns_can_be_absent_without_fabricating_costs(self):
        result = self.parse(content=csv_bytes(synthetic_rows(42), FIELDS[:4]))
        history = result['groups'][(PRODUCT, STORE)]
        self.assertTrue(all(row['unit_price'] is None and row['unit_cost'] is None
                            for row in history))
        report = self.quality(result)
        self.assertEqual(report['price_missing_days'], 42)
        self.assertEqual(report['cost_missing_days'], 42)
        self.assertIsNone(report['last_price_reference'])
        self.assertIsNone(report['last_cost_reference'])

    def test_documented_header_aliases_are_supported(self):
        data = b' date ,PRODUCT, store ,units_sold,unit_price,unit_cost\n2024-01-01,SYNTHETIC_SKU,SYNTHETIC_STORE,1,2.5,1.2\n'
        result = self.parse(content=data)
        self.assertEqual(result['groups'][('SYNTHETIC_SKU', 'SYNTHETIC_STORE')][0]['units_sold'], 1)

    def test_missing_unknown_and_duplicate_headers_are_rejected(self):
        headers = [
            'Date,Product,Store',
            'Date,Product,Store,Units Sold,Customer Email',
            'Date,Product,Store,Units Sold,units_sold',
            'Date,Product,Store,Units Sold,',
            'Date,Product,Store,Units Sold,Unit Price,Unit Cost,Extra Column',
        ]
        for header in headers:
            with self.subTest(header=header), self.assertRaises(BusinessCSVError):
                self.parse(content=(header + '\n').encode())

    def test_empty_header_only_and_malformed_rows_are_rejected(self):
        inputs = [b'', b'Date,Product,Store,Units Sold\n',
                  b'Date,Product,Store,Units Sold\n2024-01-01,SYNTHETIC,STORE\n',
                  b'Date,Product,Store,Units Sold\n2024-01-01,SYNTHETIC,STORE,1,extra\n',
                  b'Date,Product,Store,Units Sold\n2024-01-01,"unfinished,STORE,1\n']
        for data in inputs:
            with self.subTest(data=data), self.assertRaises(BusinessCSVError):
                self.parse(content=data)

    def test_invalid_encoding_and_nul_are_rejected(self):
        for data in (b'\xff\xfe\x00\x01', csv_bytes(synthetic_rows(1)) + b'\x00'):
            with self.subTest(data=data), self.assertRaises(BusinessCSVError):
                self.parse(content=data)

    def test_dates_must_be_strict_real_iso_dates(self):
        for value in ('2024-1-01', '20240101', '01/02/2024', '2023-02-29',
                      '2024-02-30', '2024-01-01T12:00:00', ''):
            rows = synthetic_rows(1)
            rows[0]['Date'] = value
            with self.subTest(value=value), self.assertRaises(BusinessCSVError):
                self.parse(rows)

    def test_leap_day_and_year_boundary_are_daily_consecutive(self):
        rows = synthetic_rows(84, start=date(2023, 12, 20))
        report = self.quality(self.parse(rows))
        self.assertEqual(report['calendar_days'], 84)
        self.assertEqual(report['missing_dates'], [])
        self.assertEqual(report['longest_continuous_days'], 84)
        self.assertTrue(report['forecast_eligible'])

    def test_incomplete_current_day_and_future_records_are_rejected(self):
        for value in (str(AS_OF), str(AS_OF + timedelta(days=1))):
            rows = synthetic_rows(1)
            rows[0]['Date'] = value
            with self.subTest(value=value), self.assertRaises(BusinessCSVError):
                self.parse(rows)

    def test_identifier_strings_keep_leading_zero_case_and_unicode(self):
        rows = synthetic_rows(1, product='0001_合成商品', store='a001')
        rows += synthetic_rows(1, product='0001_合成商品', store='A001')
        result = self.parse(rows)
        self.assertEqual(set(result['groups']),
                         {('0001_合成商品', 'a001'), ('0001_合成商品', 'A001')})

    def test_blank_long_control_and_formula_identifiers_are_rejected(self):
        for column in ('Product', 'Store'):
            for value in ('', '   ', 'X' * 81, 'bad\nname', '=SUM(1)',
                          '+CODE', '-CODE', '@CODE', 'bad\x7fname'):
                rows = synthetic_rows(1)
                rows[0][column] = value
                with self.subTest(column=column, value=value), self.assertRaises(BusinessCSVError):
                    self.parse(rows)

    def test_identifier_trimming_is_reported_and_cannot_hide_duplicates(self):
        rows = synthetic_rows(1)
        rows[0]['Product'] = ' ' + PRODUCT + ' '
        result = self.parse(rows)
        self.assertIn((PRODUCT, STORE), result['groups'])
        self.assertEqual(result['report']['summary']['trimmed_identifier_count'], 1)
        rows += synthetic_rows(1)
        with self.assertRaises(BusinessCSVError):
            self.parse(rows)

    def test_identical_and_conflicting_duplicate_keys_are_both_rejected(self):
        for units in ('2', '999'):
            rows = synthetic_rows(1)
            duplicate = dict(rows[0], **{'Units Sold': units})
            with self.subTest(units=units), self.assertRaises(BusinessCSVError):
                self.parse(rows + [duplicate])

    def test_negative_fractional_and_nonfinite_sales_are_rejected(self):
        for value in ('-1', '-0', '1.5', '1.0', 'NaN', 'Infinity', '1e2',
                      '1000001', 'true', '１２', '+1'):
            rows = synthetic_rows(1)
            rows[0]['Units Sold'] = value
            with self.subTest(value=value), self.assertRaises(BusinessCSVError):
                self.parse(rows)

    def test_explicit_zero_and_blank_sales_are_distinct(self):
        rows = synthetic_rows(3, values=[0, '', 4])
        result = self.parse(rows)
        history = result['groups'][(PRODUCT, STORE)]
        self.assertEqual([row['units_sold'] for row in history], [0, None, 4])
        report = self.quality(result)
        self.assertEqual(report['zero_sales_days'], 1)
        self.assertEqual(report['positive_sales_days'], 1)
        self.assertEqual(report['known_sales_days'], 2)
        self.assertEqual(report['unknown_sales_dates'], ['2024-01-02'])
        self.assertEqual(report['unknown_days'], 1)
        self.assertAlmostEqual(report['unknown_ratio'], 1 / 3)

    def test_missing_dates_remain_absent_and_are_reported(self):
        rows = synthetic_rows(3)
        del rows[1]
        result = self.parse(rows)
        self.assertEqual(len(result['groups'][(PRODUCT, STORE)]), 2)
        report = self.quality(result)
        self.assertEqual(report['calendar_days'], 3)
        self.assertEqual(report['recorded_days'], 2)
        self.assertEqual(report['missing_dates'], ['2024-01-02'])
        self.assertEqual(report['zero_sales_days'], 0)
        self.assertEqual(report['unknown_days'], 1)
        self.assertAlmostEqual(report['unknown_ratio'], 1 / 3)

    def test_continuous_ranges_do_not_silently_select_a_good_fragment(self):
        rows = synthetic_rows(84)
        del rows[20]
        result = self.parse(rows)
        report = self.quality(result)
        self.assertEqual([part['days'] for part in report['continuous_ranges']], [20, 63])
        self.assertEqual(report['longest_continuous_days'], 63)
        self.assertFalse(report['forecast_eligible'])
        self.assertEqual(result['report']['summary']['series_with_eligible_range_count'], 1)

    def test_eligibility_and_recommended_history_are_different_thresholds(self):
        for days, eligible, recommended in [(41, False, False), (42, True, False),
                                             (83, True, False), (84, True, True)]:
            with self.subTest(days=days):
                report = self.quality(self.parse(synthetic_rows(days)))
                self.assertEqual(report['forecast_eligible'], eligible)
                self.assertEqual(report['recommended_history'], recommended)

    def test_missing_prices_costs_and_zero_references_keep_real_dates(self):
        rows = synthetic_rows(3)
        rows[0]['Unit Price'] = '0'
        rows[1]['Unit Price'] = rows[2]['Unit Price'] = ''
        rows[1]['Unit Cost'] = '0.123456'
        rows[0]['Unit Cost'] = rows[2]['Unit Cost'] = ''
        result = self.parse(rows)
        report = self.quality(result)
        self.assertEqual(report['price_missing_days'], 2)
        self.assertEqual(report['cost_missing_days'], 2)
        self.assertAlmostEqual(report['price_coverage_ratio'], 1 / 3)
        self.assertAlmostEqual(report['cost_coverage_ratio'], 1 / 3)
        self.assertEqual(report['last_price_reference']['date'], '2024-01-01')
        self.assertEqual(Decimal(report['last_price_reference']['value']), 0)
        self.assertEqual(report['last_cost_reference']['date'], '2024-01-02')
        self.assertEqual(Decimal(report['last_cost_reference']['value']), Decimal('0.123456'))
        self.assertIsNone(result['groups'][(PRODUCT, STORE)][2]['unit_price'])

    def test_illegal_amounts_in_either_optional_column_are_rejected(self):
        for column in ('Unit Price', 'Unit Cost'):
            for value in ('-1', 'NaN', 'Infinity', '$4.50', '1e3', '1,000',
                          '1000000001', '0.1234567', '=1+1'):
                rows = synthetic_rows(1)
                rows[0][column] = value
                with self.subTest(column=column, value=value), self.assertRaises(BusinessCSVError):
                    self.parse(rows)

    def test_multiple_products_and_stores_remain_separate(self):
        rows = []
        for product in ('SYNTHETIC_A', 'SYNTHETIC_B'):
            for store in ('SYNTHETIC_X', 'SYNTHETIC_Y'):
                rows.extend(synthetic_rows(42, product=product, store=store))
        result = self.parse(list(reversed(rows)))
        summary = result['report']['summary']
        self.assertEqual(summary['product_count'], 2)
        self.assertEqual(summary['store_count'], 2)
        self.assertEqual(summary['series_count'], 4)
        self.assertEqual(summary['eligible_series_count'], 4)
        self.assertEqual(summary['row_count'], 168)
        self.assertTrue(all(len(group) == 42 for group in result['groups'].values()))

    def test_currency_metadata_is_retained_without_source_verification_claim(self):
        for currency in ('AUD', 'USD'):
            with self.subTest(currency=currency):
                result = self.parse(currency=currency)
                self.assertEqual(result['currency'], currency)
                self.assertEqual(result['source_kind'], 'user_csv')
                self.assertFalse(result['source_verified'])
                self.assertEqual(result['sales_basis'], 'gross_units')

    def test_invalid_currency_and_returns_basis_are_not_inferred(self):
        for currency in ('EUR', '', None):
            with self.subTest(currency=currency), self.assertRaises(BusinessCSVError):
                self.parse(currency=currency)
        for basis in ('net_units', 'returns', '', None):
            with self.subTest(basis=basis), self.assertRaises(BusinessCSVError):
                parse_business_csv(csv_bytes(synthetic_rows()), 'AUD', sales_basis=basis,
                                   as_of_date=AS_OF)
        with self.assertRaises(TypeError):
            parse_business_csv(csv_bytes(synthetic_rows()), 'AUD', as_of_date=AS_OF)

    def test_error_report_is_bounded_and_does_not_echo_sales_details(self):
        rows = synthetic_rows(60)
        for row in rows:
            row['Units Sold'] = 'SENSITIVE_BAD_VALUE_12345'
        with self.assertRaises(BusinessCSVError) as caught:
            self.parse(rows)
        error = caught.exception
        self.assertGreaterEqual(error.error_count, 60)
        self.assertLessEqual(len(error.errors), 50)
        self.assertTrue(error.code)
        self.assertTrue(all('code' in item and 'line' in item and 'field' in item
                            for item in error.errors))
        self.assertNotIn('SENSITIVE_BAD_VALUE_12345', str(error))
        self.assertNotIn('SENSITIVE_BAD_VALUE_12345', json.dumps(error.errors))

    def test_local_file_read_preserves_original_bytes(self):
        content = csv_bytes(synthetic_rows(42), bom=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'SYNTHETIC_business.csv'
            path.write_bytes(content)
            result = load_business_csv(path, 'AUD', sales_basis='gross_units', as_of_date=AS_OF)
            self.assertEqual(result['report']['summary']['row_count'], 42)
            self.assertEqual(path.read_bytes(), content)

    def test_byte_and_field_size_limits_fail_before_analysis(self):
        with self.assertRaises(BusinessCSVError):
            self.parse(content=b'x' * (5 * 1024 * 1024 + 1))
        rows = synthetic_rows(1)
        rows[0]['Unit Cost'] = '1' * 1025
        with self.assertRaises(BusinessCSVError):
            self.parse(rows)

    def test_group_and_date_span_limits_are_enforced(self):
        rows = [synthetic_rows(1, product='SYNTHETIC_%03d' % i)[0] for i in range(101)]
        with self.assertRaises(BusinessCSVError):
            self.parse(rows)
        rows = synthetic_rows(1, start=date(2020, 1, 1))
        rows += synthetic_rows(1, start=date(2024, 1, 1))
        with self.assertRaises(BusinessCSVError):
            self.parse(rows)

    def test_row_count_limit_is_enforced(self):
        # Entirely synthetic daily data: 50 groups x 1,000 days, then one more row.
        rows = []
        for index in range(50):
            rows.extend(synthetic_rows(1000, product='SYNTHETIC_%02d' % index,
                                       start=date(2020, 1, 1)))
        rows += synthetic_rows(1, product='SYNTHETIC_EXTRA')
        with self.assertRaises(BusinessCSVError):
            self.parse(rows)

    def test_report_is_json_serializable_without_mutating_input(self):
        rows = synthetic_rows()
        before = copy.deepcopy(rows)
        result = self.parse(rows)
        json.dumps(result['report'], allow_nan=False)
        self.assertEqual(rows, before)

    def test_blank_physical_lines_are_counted_not_observations(self):
        content = csv_bytes(synthetic_rows(42)) + b'\r\n\n'
        result = self.parse(content=content)
        self.assertEqual(result['report']['summary']['row_count'], 42)
        self.assertEqual(result['report']['summary']['blank_lines_skipped'], 2)


if __name__ == '__main__':
    unittest.main()

