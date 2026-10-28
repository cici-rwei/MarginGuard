"""Synthetic fixtures only: these are not Walmart observations or accuracy claims."""
import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from forecast import METHODS, analyse, mae, predict
from data_loader import FIELDS, load_series
from scripts.prepare_m5 import prepare


def history(values):
    return [{"date": date(2020, 1, 6) + timedelta(days=i), "units_sold": value}
            for i, value in enumerate(values)]


def write_csv(path, fields, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ForecastTests(unittest.TestCase):
    def test_moving_average_manual(self):
        output = predict(history([1, 2, 3, 4, 5, 6, 7] * 4), METHODS[0])
        self.assertEqual(len(output), 14)
        self.assertEqual([r['prediction'] for r in output], [4] * 14)

    def test_weekday_four_prior_weeks(self):
        rows = history(list(range(28)))
        expected = [10.5 + i for i in range(7)] * 2
        self.assertEqual([r['prediction'] for r in predict(rows, METHODS[1])], expected)

    def test_mae_manual(self):
        self.assertEqual(mae([2, 4, 6], [1, 6, 3]), 2)

    def test_holdout_does_not_leak(self):
        first = analyse(history([2] * 28 + [3] * 14))
        second = analyse(history([2] * 28 + [100] * 14))
        for method in METHODS:
            self.assertEqual([r['prediction'] for r in first['backtest'][method]['daily']], [2] * 14)
            self.assertEqual([r['prediction'] for r in second['backtest'][method]['daily']], [2] * 14)
        self.assertNotEqual(first['future'], second['future'])

    def test_future_refit_and_dates(self):
        rows = history([2] * 28 + [9] * 14)
        result = analyse(rows)
        self.assertEqual(result['future'][0]['date'], rows[-1]['date'] + timedelta(days=1))
        self.assertEqual(result['future'][-1]['date'], rows[-1]['date'] + timedelta(days=14))
        self.assertEqual(result['total_forecast_demand'], 126)

    def test_tie_and_zero_demand(self):
        result = analyse(history([0] * 42))
        self.assertEqual(result['selected_method'], METHODS[0])
        self.assertEqual(result['total_forecast_demand'], 0)

    def test_weekday_wins_on_weekly_pattern(self):
        result = analyse(history([0, 0, 0, 0, 0, 0, 14] * 8))
        self.assertEqual(result['selected_method'], METHODS[1])
        self.assertEqual(result['backtest'][METHODS[1]]['mae'], 0)
        self.assertTrue(all(r['prediction'] >= 0 for r in result['future']))

    def test_bad_history(self):
        for values in ([1] * 27, [1] * 27 + [-1], [1] * 27 + [float('nan')], [float('inf')] * 28):
            with self.assertRaises(ValueError):
                predict(history(values), METHODS[0])
        rows = history([1] * 28)
        rows[-1]['date'] = rows[0]['date']
        with self.assertRaises(ValueError):
            predict(rows, METHODS[0])
        with self.assertRaises(ValueError):
            analyse(history([1] * 41))

    def test_bad_method_horizon_and_mae(self):
        for method, horizon in [('unknown', 14), (METHODS[0], 0), (METHODS[0], 1.5)]:
            with self.assertRaises(ValueError):
                predict(history([1] * 28), method, horizon)
        for actual, predicted in [([], []), ([1], [1, 2]), ([float('nan')], [1])]:
            with self.assertRaises(ValueError):
                mae(actual, predicted)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        days = ['d_%d' % i for i in range(1794, 1914)]
        self.calendar = [{'d': day, 'date': str(date(2020, 1, 1) + timedelta(days=i)),
                          'wm_yr_wk': str(i // 7)} for i, day in enumerate(days)]
        write_csv(self.root / 'calendar.csv', ['d', 'date', 'wm_yr_wk'], self.calendar)
        sales_fields = ['id', 'item_id', 'store_id', 'cat_id', 'dept_id', 'state_id'] + days
        sales = []
        for item, count in [('TEST_A', 2), ('TEST_B', 7)]:
            row = dict(id=item + '_TEST_STORE_validation', item_id=item, store_id='TEST_STORE',
                       cat_id='TEST_CAT', dept_id='TEST_DEPT', state_id='TEST_STATE')
            row.update({d: count for d in days})
            row[days[0]] = 0
            sales.append(row)
        write_csv(self.root / 'sales_train_validation.csv', sales_fields, sales)
        self.price_fields = ['item_id', 'store_id', 'wm_yr_wk', 'sell_price']
        self.prices = [{'item_id': item, 'store_id': 'TEST_STORE', 'wm_yr_wk': str(week),
                        'sell_price': '0' if week == 0 else '4.25'}
                       for item in ['TEST_A', 'TEST_B'] for week in range(17)]
        write_csv(self.root / 'sell_prices.csv', self.price_fields, self.prices)
        self.output = self.root / 'processed.csv'

    def run_prepare(self, items=None):
        return prepare(self.root, self.output, items or ['TEST_A', 'TEST_B'], ['TEST_STORE'], 120)

    def test_pipeline_two_series_and_missing_prices(self):
        report = self.run_prepare()
        groups = load_series(self.output)
        a, b = groups[('TEST_A', 'TEST_STORE')], groups[('TEST_B', 'TEST_STORE')]
        self.assertEqual(len(a), 120)
        self.assertEqual(a[0]['units_sold'], 0)
        self.assertEqual(a[0]['sell_price_usd'], 0)
        self.assertIsNone(a[-1]['sell_price_usd'])
        self.assertNotEqual(analyse(a)['total_forecast_demand'], analyse(b)['total_forecast_demand'])
        self.assertEqual(report['series'][0]['missing_price_days'], 1)
        self.assertEqual(len(report['sha256']['calendar']), 64)

    def test_duplicate_price(self):
        write_csv(self.root / 'sell_prices.csv', self.price_fields, self.prices + [self.prices[0]])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.run_prepare()
        self.assertFalse(self.output.exists())

    def test_unknown_product(self):
        with self.assertRaisesRegex(ValueError, 'Missing requested'):
            self.run_prepare(['MISSING'])

    def test_missing_file(self):
        with self.assertRaisesRegex(ValueError, 'Missing processed data'):
            load_series(self.output)
        (self.root / 'calendar.csv').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing original'):
            self.run_prepare()

    def test_invalid_schema(self):
        self.output.write_text('wrong,columns\n1,2\n')
        with self.assertRaisesRegex(ValueError, 'columns'):
            load_series(self.output)

    def test_duplicate_processed_row(self):
        self.run_prepare()
        lines = self.output.read_text().splitlines()
        self.output.write_text('\n'.join(lines + [lines[1]]) + '\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            load_series(self.output)

    def test_invalid_price(self):
        for value in ['NaN', 'Infinity', '-1', 'nonsense']:
            self.prices[0]['sell_price'] = value
            write_csv(self.root / 'sell_prices.csv', self.price_fields, self.prices)
            with self.assertRaises((ValueError, ArithmeticError)):
                self.run_prepare()


if __name__ == '__main__':
    unittest.main()
