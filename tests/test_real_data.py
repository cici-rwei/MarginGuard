"""Integration checks against the user's local genuine M5 files.

Explicitly skipped in a source-only ZIP until preprocessing is rerun locally.
"""
import csv
import json
import unittest
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from data_loader import load_series
from forecast import METHODS, analyse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = [DATA / 'processed_sales.csv', DATA / 'source_audit.json',
                    DATA / 'raw' / 'sales_train_validation.csv', DATA / 'raw' / 'calendar.csv']
        if not all(p.exists() for p in required):
            raise unittest.SkipTest('Local M5 files/processed data absent; run README reproduction commands.')
        cls.groups = load_series(DATA / 'processed_sales.csv')
        cls.audit = json.loads((DATA / 'source_audit.json').read_text())

    def test_five_complete_selected_series(self):
        expected = {(r['item_id'], r['store_id']) for r in self.audit['selected']}
        self.assertEqual(set(self.groups), expected)
        self.assertEqual(len(self.groups), 5)
        for rows in self.groups.values():
            self.assertEqual(len(rows), 365)
            self.assertEqual(rows[0]['date'], date(2015, 4, 26))
            self.assertEqual(rows[-1]['date'], date(2016, 4, 24))
            self.assertTrue(all(r['sell_price_usd'] is not None and r['sell_price_usd'] > 0 for r in rows))

    def test_processed_units_match_original_sales(self):
        with (DATA / 'raw' / 'calendar.csv').open(newline='') as handle:
            calendar = {date.fromisoformat(r['date']): r['d'] for r in csv.DictReader(handle)}
        checked = 0
        with (DATA / 'raw' / 'sales_train_validation.csv').open(newline='') as handle:
            for raw in csv.DictReader(handle):
                key = (raw['item_id'], raw['store_id'])
                if key in self.groups:
                    for row in self.groups[key]:
                        self.assertEqual(row['units_sold'], int(raw[calendar[row['date']]]))
                        checked += 1
        self.assertEqual(checked, 1825)

    def test_real_backtests_against_fraction_arithmetic(self):
        for rows in self.groups.values():
            train, actual = rows[:-14], rows[-14:]
            output = analyse(rows)
            mean = Fraction(sum(r['units_sold'] for r in train[-7:]), 7)
            weekday = {w: Fraction(sum(r['units_sold'] for r in train[-28:] if r['date'].weekday() == w), 4) for w in range(7)}
            manual = {METHODS[0]: [mean] * 14, METHODS[1]: [weekday[r['date'].weekday()] for r in actual]}
            for method, predictions in manual.items():
                error = sum(abs(Fraction(a['units_sold']) - p) for a, p in zip(actual, predictions)) / 14
                self.assertAlmostEqual(output['backtest'][method]['mae'], float(error), places=10)
                for saved, expected in zip(output['backtest'][method]['daily'], predictions):
                    self.assertAlmostEqual(saved['prediction'], float(expected), places=10)
            self.assertEqual(output['future'][0]['date'], rows[-1]['date'] + timedelta(days=1))
            self.assertEqual(len(output['future']), 14)

    def test_series_selection_changes_forecast_and_totals_reconcile(self):
        totals = []
        for rows in self.groups.values():
            output = analyse(rows)
            totals.append(output['total_forecast_demand'])
            self.assertAlmostEqual(totals[-1], sum(r['prediction'] for r in output['future']))
        self.assertEqual(len(set(totals)), 5)
