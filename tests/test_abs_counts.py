"""Tests for separate business Counts data; no generated Excel workbooks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from abs_counts import FLOW_LABELS, read_business_counts


SOURCE = {
    "url": "https://www.abs.gov.au/example/counts_cube1.xlsx",
    "release_date": "2026-08-18", "download_date": "2026-10-27",
    "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
}


def tables():
    flow = [[None] + list(FLOW_LABELS), [None] + ["no."] * 9 + ["%"] * 3]
    records = [
        ("2022-23", 157321, 18129, 5637, 23766, 20295, 3811, 24106, 156981, -340, -0.2, 15.1, 15.3),
        ("2023-24", 156981, 18043, 6441, 24484, 20741, 4089, 24830, 156635, -346, -0.2, 15.6, 15.8),
        ("2024-25", 156635, 17947, 6245, 24192, 20844, 3965, 24809, 156018, -617, -0.4, 15.4, 15.8),
        ("2025-26", 156018, 17925, 6643, 24568, 20569, 3874, 24443, 156143, 125, 0.1, 15.7, 15.7),
    ]
    for year, *numbers in records:
        flow.extend([[year] + [None] * 12, ["Retail Trade"] + numbers])
    existing = [
        [None, "Operating in June 2022", "Survived to June 2023", "Survival rate",
         "Survived to June 2024", "Survival rate", "Survived to June 2025", "Survival rate",
         "Survived to June 2026", "Survival rate"],
        [None, "no.", "no.", "%", "no.", "%", "no.", "%", "no.", "%"],
        ["Retail Trade", 157321, 133215, 84.7, 114392, 72.7, 100311, 63.8, 88856, 56.5],
    ]
    entrants = [
        [None, "Entries in 2022-23", "Survived to June 2024", "Survival rate",
         "Survived to June 2025", "Survival rate", "Survived to June 2026", "Survival rate"],
        [None, "no.", "no.", "%", "no.", "%", "no.", "%"],
        ["Retail Trade", 23766, 17759, 74.7, 13344, 56.1, 10979, 46.2],
    ]
    return {"Table 1": flow, "Table 2": existing, "Table 3": entrants}


class Sheet:
    def __init__(self, rows):
        self.rows = rows

    def iter_rows(self, values_only=False):
        assert values_only
        return iter(self.rows)


class Workbook:
    def __init__(self, rows):
        self.rows = rows
        self.sheetnames = list(rows)
        self.closed = False

    def __getitem__(self, name):
        return Sheet(self.rows[name])

    def close(self):
        self.closed = True


class CountsTests(unittest.TestCase):
    def read(self, rows=None, source=None):
        book = Workbook(tables() if rows is None else rows)
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as file:
            with patch("abs_counts.load_workbook", return_value=book) as mocked:
                result = read_business_counts(file.name, SOURCE if source is None else source)
                mocked.assert_called_once_with(Path(file.name), read_only=True, data_only=True)
        self.assertTrue(book.closed)
        return result

    def test_annual_counts_reconcile_and_growth_uses_counts(self):
        result = self.read()
        latest = result["annual_flows"]["observations"][-1]
        self.assertEqual((latest["closing"], latest["entries_total"], latest["exits_total"]),
                         (156143, 24568, 24443))
        self.assertEqual(latest["derived_net_change"], 125)
        self.assertAlmostEqual(latest["derived_change_pct"], 125 / 156018 * 100)
        self.assertEqual(latest["official_change_pct"], 0.1)
        self.assertEqual(result["annual_flows"]["frequency"], "financial_year")
        self.assertEqual(result["annual_flows"]["field_units"]["closing"], "businesses")

    def test_survival_cohorts_and_frequencies_remain_distinct(self):
        existing, entrants = self.read()["survival_cohorts"]
        self.assertEqual((existing["cohort_period"], existing["cohort_size"]), ("2022-06", 157321))
        self.assertEqual((entrants["cohort_period"], entrants["cohort_size"]), ("2022-23", 23766))
        self.assertEqual(existing["observations"][-1]["surviving_businesses"], 88856)
        self.assertEqual(entrants["observations"][-1]["surviving_businesses"], 10979)
        self.assertEqual(existing["frequency"], "annual_snapshot")
        self.assertEqual(entrants["cohort_frequency"], "financial_year")
        self.assertAlmostEqual(existing["observations"][-1]["derived_survival_rate_pct"], 88856/157321*100)

    def test_named_columns_can_move_and_wrapped_headers_are_normalised(self):
        rows = tables()
        for row in rows["Table 1"]:
            row[2], row[3] = row[3], row[2]
        rows["Table 1"][0][2] = "Entries - \nOther"
        result = self.read(rows)
        self.assertEqual(result["annual_flows"]["observations"][-1]["entries_births"], 17925)
        self.assertEqual(result["annual_flows"]["observations"][-1]["entries_other"], 6643)

    def test_missing_counts_and_rates_are_not_zero(self):
        rows = tables()
        rows["Table 1"][-1][8] = None  # Closing stock, while flows remain available.
        rows["Table 3"][-1][-1] = "np"
        result = self.read(rows)
        latest = result["annual_flows"]["observations"][-1]
        self.assertIsNone(latest["closing"])
        self.assertEqual(latest["status"], "partial")
        self.assertEqual(latest["derived_net_change"], 125)
        self.assertIsNone(result["survival_cohorts"][1]["observations"][-1]["official_survival_rate_pct"])
        self.assertEqual(result["quality"]["missing_flow_values"], 1)
        json.dumps(result, allow_nan=False)

    def test_wrong_units_and_missing_headers_fail(self):
        for alteration in ("unit", "header"):
            with self.subTest(alteration=alteration):
                rows = tables()
                if alteration == "unit":
                    rows["Table 1"][1][1] = "$ Millions"
                else:
                    rows["Table 1"][0][1] = "Different field"
                with self.assertRaises(ValueError):
                    self.read(rows)

    def test_inconsistent_counts_and_rates_fail(self):
        for column in (2, 8, 9, 10, 11, 12):
            with self.subTest(column=column):
                rows = tables()
                rows["Table 1"][-1][column] += 1
                with self.assertRaises(ValueError):
                    self.read(rows)

    def test_duplicate_or_missing_financial_year_fails(self):
        rows = tables()
        del rows["Table 1"][4:6]  # Missing 2023-24.
        with self.assertRaisesRegex(ValueError, "continuous"):
            self.read(rows)
        rows = tables()
        rows["Table 1"].extend(deepcopy(rows["Table 1"][-2:]))
        with self.assertRaisesRegex(ValueError, "continuous"):
            self.read(rows)

    def test_invalid_or_nonfinite_count_fails(self):
        for value in (-1, 1.5, True, "broken", float("nan"), float("inf")):
            with self.subTest(value=value):
                rows = tables()
                rows["Table 1"][-1][8] = value
                with self.assertRaises(ValueError):
                    self.read(rows)

    def test_missing_source_or_future_release_fails(self):
        for key in ("url", "release_date", "download_date", "license"):
            source = dict(SOURCE)
            source.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.read(source=source)
        with self.assertRaisesRegex(ValueError, "after the recorded download"):
            self.read(source=dict(SOURCE, download_date="2026-08-17"))
        with self.assertRaisesRegex(ValueError, "after the release"):
            self.read(source=dict(SOURCE, release_date="2025-08-18"))

    def test_source_and_dataset_metadata_are_preserved(self):
        result = self.read()
        self.assertEqual(result["dataset_id"], "abs_business_counts")
        self.assertEqual(result["source"], SOURCE)
        self.assertEqual(result["classification"], "ANZSIC")
        self.assertEqual(result["adjustment"], "Original")
        self.assertIsNone(result["official_series_ids"])
        self.assertEqual(result["quality"]["annual_flow_rows"], 4)
        self.assertEqual(result["quality"]["survival_rows"], 7)

    def test_cohort_rate_and_baseline_mismatch_fail(self):
        rows = tables()
        rows["Table 2"][-1][-1] = 80.0
        with self.assertRaisesRegex(ValueError, "rate reconciliation"):
            self.read(rows)
        rows = tables()
        rows["Table 2"][-1][1] = 157322
        with self.assertRaisesRegex(ValueError, "cohort vs Table 1"):
            self.read(rows)

    def test_missing_worksheet_fails_and_closes_book(self):
        rows = tables()
        rows.pop("Table 3")
        book = Workbook(rows)
        with tempfile.NamedTemporaryFile() as file, patch("abs_counts.load_workbook", return_value=book):
            with self.assertRaisesRegex(ValueError, "Missing ABS Counts worksheet"):
                read_business_counts(file.name, SOURCE)
        self.assertTrue(book.closed)


REAL_FILE = Path(__file__).resolve().parents[3] / "research/datasets/abs_business/counts_cube1.xlsx"


@unittest.skipUnless(REAL_FILE.is_file(), "Optional original ABS research workbook not present")
class RealCountsTests(unittest.TestCase):
    def test_downloaded_workbook_retail_data(self):
        result = read_business_counts(REAL_FILE, SOURCE)
        self.assertEqual(result["annual_flows"]["observations"][-1]["closing"], 156143)
        self.assertEqual(result["survival_cohorts"][0]["observations"][-1]["official_survival_rate_pct"], 56.5)
        self.assertEqual(result["survival_cohorts"][1]["observations"][-1]["official_survival_rate_pct"], 46.2)
        self.assertEqual(result["quality"]["missing_flow_values"], 0)


if __name__ == "__main__":
    unittest.main()
