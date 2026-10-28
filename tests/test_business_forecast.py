"""Forecast adapter contracts; all input sales here are explicitly SYNTHETIC."""
import copy
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from business_csv import load_business_csv, parse_business_csv
from business_forecast import BusinessForecastError, analyse_business_series
from business_fixtures import AS_OF, PRODUCT, START, STORE, csv_bytes, synthetic_rows
from forecast import METHODS, analyse


class BusinessForecastTests(unittest.TestCase):
    def dataset(self, days=84, *, values=None, rows=None, currency='AUD', as_of_date=AS_OF):
        return parse_business_csv(csv_bytes(synthetic_rows(days, values=values) if rows is None else rows),
                                  currency, sales_basis='gross_units', as_of_date=as_of_date)

    def run_analysis(self, dataset, **kwargs):
        return analyse_business_series(dataset, PRODUCT, STORE, **kwargs)

    def test_41_days_rejected_for_complete_forecast_backtest(self):
        with self.assertRaises(BusinessForecastError):
            self.run_analysis(self.dataset(41))

    def test_42_days_allow_two_method_14_day_backtest_and_future_forecast(self):
        result = self.run_analysis(self.dataset(42))
        analysis = result['analysis']
        self.assertEqual(analysis['observations'], 42)
        self.assertEqual(set(analysis['backtest']), set(METHODS))
        self.assertEqual(analysis['training_end'], START + timedelta(days=27))
        for method in METHODS:
            self.assertEqual(len(analysis['backtest'][method]['daily']), 14)
        self.assertEqual(len(analysis['future']), 14)
        self.assertFalse(result['quality']['recommended_history'])
        self.assertTrue(result['quality']['warnings'])

    def test_84_days_are_recommended_and_engine_output_is_unchanged(self):
        dataset = self.dataset(84)
        result = self.run_analysis(dataset)
        expected = analyse([{'date': row['date'], 'units_sold': row['units_sold']}
                            for row in dataset['groups'][(PRODUCT, STORE)]])
        self.assertEqual(result['analysis'], expected)
        self.assertEqual(result['quality']['observations'], 84)
        self.assertTrue(result['quality']['recommended_history'])

    def test_forecast_dates_follow_history_not_today(self):
        result = self.run_analysis(self.dataset(42))
        self.assertEqual(result['forecast_start'], START + timedelta(days=42))
        self.assertEqual(result['forecast_end'], START + timedelta(days=55))
        self.assertEqual(result['analysis']['future'][0]['date'], result['forecast_start'])
        self.assertEqual(result['analysis']['future'][-1]['date'], result['forecast_end'])

    def test_zero_sales_are_valid_but_not_claimed_as_positive_demand_evidence(self):
        result = self.run_analysis(self.dataset(42, values=[0] * 42))
        self.assertEqual(result['analysis']['selected_method'], METHODS[0])
        self.assertEqual(result['analysis']['total_forecast_demand'], 0)
        self.assertEqual(result['quality']['zero_sales_days'], 42)
        self.assertTrue(result['quality']['warnings'])
        self.assertTrue(all(value['mae'] == 0 for value in result['analysis']['backtest'].values()))

    def test_weekday_pattern_keeps_existing_selection_rule(self):
        result = self.run_analysis(self.dataset(84, values=[0, 0, 0, 0, 0, 0, 14] * 12))
        self.assertEqual(result['analysis']['selected_method'], METHODS[1])
        self.assertEqual(result['analysis']['backtest'][METHODS[1]]['mae'], 0)

    def test_missing_day_is_not_filled_or_automatically_cropped(self):
        rows = synthetic_rows(84)
        del rows[20]
        dataset = self.dataset(rows=rows)
        before = copy.deepcopy(dataset)
        with self.assertRaises(BusinessForecastError):
            self.run_analysis(dataset)
        self.assertEqual(dataset, before)

    def test_explicit_continuous_range_is_supported_and_exclusions_are_visible(self):
        rows = synthetic_rows(84)
        del rows[20]
        dataset = self.dataset(rows=rows)
        first, last = START + timedelta(days=21), START + timedelta(days=83)
        result = self.run_analysis(dataset, start_date=str(first), end_date=str(last))
        self.assertEqual(result['quality']['observations'], 63)
        self.assertEqual(result['quality']['excluded_record_count'], 20)
        self.assertEqual(result['analysis']['history_start'], first)
        self.assertEqual(result['analysis']['history_end'], last)
        self.assertEqual(result['forecast_start'], last + timedelta(days=1))

    def test_blank_sales_are_unknown_and_cannot_enter_forecast(self):
        rows = synthetic_rows(84)
        rows[41]['Units Sold'] = ''
        dataset = self.dataset(rows=rows)
        with self.assertRaises(BusinessForecastError):
            self.run_analysis(dataset)
        result = self.run_analysis(dataset, start_date=START + timedelta(days=42),
                                   end_date=START + timedelta(days=83))
        self.assertEqual(result['quality']['observations'], 42)
        self.assertEqual(result['quality']['excluded_record_count'], 42)

    def test_invalid_or_partial_ranges_do_not_guess_boundaries(self):
        dataset = self.dataset()
        ranges = [
            {'start_date': START}, {'end_date': START + timedelta(days=83)},
            {'start_date': '2024-1-01', 'end_date': '2024-03-24'},
            {'start_date': START + timedelta(days=50), 'end_date': START},
            {'start_date': START - timedelta(days=1), 'end_date': START + timedelta(days=83)},
            {'start_date': START, 'end_date': START + timedelta(days=84)},
        ]
        for values in ranges:
            with self.subTest(values=values), self.assertRaises(BusinessForecastError):
                self.run_analysis(dataset, **values)

    def test_selected_range_must_still_have_42_days(self):
        with self.assertRaises(BusinessForecastError):
            self.run_analysis(self.dataset(), start_date=START, end_date=START + timedelta(days=40))

    def test_multiple_products_and_stores_do_not_mix_histories(self):
        rows = synthetic_rows(42, values=[2] * 42)
        rows += synthetic_rows(42, product=PRODUCT, store='SYNTHETIC_STORE_B', values=[9] * 42)
        rows += synthetic_rows(42, product='SYNTHETIC_SKU_B', store=STORE, values=[4] * 42)
        dataset = self.dataset(rows=rows)
        self.assertEqual(self.run_analysis(dataset)['analysis']['total_forecast_demand'], 28)
        second = analyse_business_series(dataset, PRODUCT, 'SYNTHETIC_STORE_B')
        third = analyse_business_series(dataset, 'SYNTHETIC_SKU_B', STORE)
        self.assertEqual(second['analysis']['total_forecast_demand'], 126)
        self.assertEqual(third['analysis']['total_forecast_demand'], 56)

    def test_unknown_product_store_is_rejected(self):
        dataset = self.dataset()
        for product, store in [('unknown', STORE), (PRODUCT, 'unknown')]:
            with self.subTest(product=product, store=store), self.assertRaises(BusinessForecastError):
                analyse_business_series(dataset, product, store)

    def test_aud_usd_preserve_metadata_but_do_not_claim_finance_support(self):
        aud = self.run_analysis(self.dataset(currency='AUD'))
        usd = self.run_analysis(self.dataset(currency='USD'))
        self.assertEqual(aud['analysis'], usd['analysis'])
        self.assertEqual(aud['currency'], 'AUD')
        self.assertEqual(usd['currency'], 'USD')
        for result in (aud, usd):
            self.assertFalse(result['financial_analysis_available'])
            self.assertEqual(result['source_kind'], 'user_csv')
            self.assertFalse(result['source_verified'])
            self.assertEqual(result['sales_basis'], 'gross_units')

    def test_price_cost_fields_do_not_change_demand_or_validation_mae(self):
        rows = synthetic_rows()
        other = copy.deepcopy(rows)
        for index, row in enumerate(other):
            row['Unit Price'] = '' if index % 2 else '999.123456'
            row['Unit Cost'] = ''
        first = self.run_analysis(self.dataset(rows=rows))
        second = self.run_analysis(self.dataset(rows=other))
        self.assertEqual(first['analysis'], second['analysis'])

    def test_adapter_does_not_mutate_parsed_dataset(self):
        dataset = self.dataset()
        before = copy.deepcopy(dataset)
        self.run_analysis(dataset)
        self.assertEqual(dataset, before)

    def test_holdout_actuals_cannot_leak_into_validation_predictions(self):
        low = self.run_analysis(self.dataset(42, values=[2] * 28 + [3] * 14))['analysis']
        high = self.run_analysis(self.dataset(42, values=[2] * 28 + [100] * 14))['analysis']
        for method in METHODS:
            self.assertEqual([row['prediction'] for row in low['backtest'][method]['daily']], [2] * 14)
            self.assertEqual([row['prediction'] for row in high['backtest'][method]['daily']], [2] * 14)
        self.assertNotEqual(low['future'], high['future'])

    def test_excluded_later_observations_do_not_affect_selected_analysis(self):
        first_rows = synthetic_rows(84)
        other_rows = copy.deepcopy(first_rows)
        for row in other_rows[42:]:
            row['Units Sold'] = '999999'
        selected = {'start_date': START, 'end_date': START + timedelta(days=41)}
        first = self.run_analysis(self.dataset(rows=first_rows), **selected)
        second = self.run_analysis(self.dataset(rows=other_rows), **selected)
        self.assertEqual(first['analysis'], second['analysis'])
        self.assertEqual(first['quality']['excluded_record_count'], 42)

    def test_historical_references_do_not_read_excluded_future_prices_or_costs(self):
        rows = synthetic_rows(84)
        rows[40]['Unit Price'], rows[40]['Unit Cost'] = '9.75', '3.125'
        rows[41]['Unit Price'] = rows[41]['Unit Cost'] = ''
        for row in rows[42:]:
            row['Unit Price'], row['Unit Cost'] = '999.99', '888.88'
        result = self.run_analysis(self.dataset(rows=rows), start_date=START,
                                   end_date=START + timedelta(days=41))
        references = result['references']
        self.assertEqual(references['unit_price']['date'], START + timedelta(days=40))
        self.assertEqual(references['unit_price']['value'], Decimal('9.75'))
        self.assertEqual(references['unit_cost']['date'], START + timedelta(days=40))
        self.assertEqual(references['unit_cost']['value'], Decimal('3.125'))
        # If the selected history has no cost at all, a future cost cannot fill it.
        for row in rows[:42]:
            row['Unit Cost'] = ''
        result = self.run_analysis(self.dataset(rows=rows), start_date=START,
                                   end_date=START + timedelta(days=41))
        self.assertIsNone(result['references']['unit_cost'])

    def test_documented_synthetic_example_has_complete_84_day_analysis(self):
        path = Path(__file__).resolve().parents[1] / 'examples/business_csv/synthetic_84_days.csv'
        dataset = load_business_csv(path, 'AUD', sales_basis='gross_units', as_of_date=AS_OF)
        result = self.run_analysis(dataset)
        history = dataset['groups'][(PRODUCT, STORE)]
        self.assertEqual(len(history), 84)
        self.assertEqual(history[0]['date'], date(2024, 1, 1))
        self.assertEqual(history[-1]['date'], date(2024, 3, 24))
        self.assertTrue(all(right['date'] - left['date'] == timedelta(days=1)
                            for left, right in zip(history, history[1:])))
        self.assertEqual(result['forecast_start'], date(2024, 3, 25))
        self.assertEqual(result['forecast_end'], date(2024, 4, 7))
        self.assertEqual(result['analysis']['total_forecast_demand'], 84)
        expected = analyse([{'date': row['date'], 'units_sold': row['units_sold']}
                            for row in history])
        self.assertEqual(result['analysis'], expected)

    def test_adapter_rechecks_units_instead_of_trusting_report_flags(self):
        for value in (-1, 1.5, True, None, float('nan')):
            dataset = self.dataset()
            dataset['groups'][(PRODUCT, STORE)][0]['units_sold'] = value
            with self.subTest(value=value), self.assertRaises(BusinessForecastError):
                self.run_analysis(dataset)

    def test_overflowing_future_calendar_is_a_clear_adapter_error(self):
        end = date.max - timedelta(days=11)
        rows = synthetic_rows(42, start=end - timedelta(days=41))
        dataset = self.dataset(rows=rows, as_of_date=date.max)
        with self.assertRaises(BusinessForecastError):
            self.run_analysis(dataset)


if __name__ == '__main__':
    unittest.main()

