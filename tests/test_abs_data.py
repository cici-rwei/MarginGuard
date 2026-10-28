"""ABS parser and prepared-file tests, independent of the Flask pages."""
import copy
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from abs_data import (parse_timeseries_frame, read_timeseries_excel, merge_series,
                      load_registry, validate_source, source_path, dimensions,
                      number_or_none)
from abs_indicators import (growth_rates, official_inventory_sales_ratio,
                            validate_ratio_against_components)
from scripts.prepare_abs import build

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "abs"
RESEARCH = ROOT.parents[1] / "research" / "datasets"


def source():
    return dict(source_id="test_mhsi", dataset_id="abs_mhsi", table_id=1,
                frequency="monthly", relative_path="sample.xlsx", sha256="test",
                url="https://www.abs.gov.au/sample.xlsx", release_date="2026-09-29",
                download_date="2026-10-27", reference_end_date="2026-08-31",
                license="CC BY 4.0", license_url="https://creativecommons.org/licenses/by/4.0/")


def frame():
    dates = [datetime(2026, m, 1) for m in (6, 7, 8)]
    return pd.DataFrame([
        [None, "Household spending ; Total (Household Spending Categories) ; Australia ; Current Price ;"],
        ["Unit", "$ Millions"], ["Series Type", "Original"], ["Data Type", "FLOW"],
        ["Frequency", "Month"], ["Collection Month", 1],
        ["Series Start", dates[0]], ["Series End", dates[-1]], ["No. Obs", 3],
        ["Series ID", "A12345X"],
        [dates[0], 100], [dates[1], None], [dates[2], 120],
    ], dtype=object)


class ABSParserTests(unittest.TestCase):
    def test_metadata_and_missing_values(self):
        s = parse_timeseries_frame(frame(), source())[0]
        self.assertEqual(s["series_id"], "A12345X")
        self.assertEqual(s["unit"], "AUD million")
        self.assertEqual(s["classification"], "spending_aggregate")
        self.assertEqual(s["periods"], ["2026-06", "2026-07", "2026-08"])
        self.assertEqual(s["values"], [100, None, 120])
        self.assertEqual(s["status"], ["observed", "missing", "observed"])

    def test_excel_reader_preserves_missing_markers(self):
        with patch("abs_data.pd.read_excel", return_value=frame()) as read:
            s = read_timeseries_excel("not-opened.xlsx", source())
        self.assertEqual(len(s), 1)
        self.assertFalse(read.call_args.kwargs["keep_default_na"])
        self.assertEqual(read.call_args.kwargs["sheet_name"], "Data1")

    def test_missing_metadata_and_bad_numeric_rejected(self):
        for mutate in ("metadata", "text", "infinity", "boolean"):
            f = frame()
            if mutate == "metadata":
                f.iat[9, 0] = "Wrong ID label"
            else:
                f.iat[10, 1] = {"text": "invalid", "infinity": float("inf"), "boolean": True}[mutate]
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                parse_timeseries_frame(f, source())
        self.assertIsNone(number_or_none(".."))
        self.assertEqual(number_or_none(0), 0)
        self.assertEqual(number_or_none(-12.5), -12.5)

    def test_date_gap_duplicate_and_declaration_rejected(self):
        for mutate in ("gap", "duplicate", "count", "end"):
            f = frame()
            if mutate == "gap":
                f = f.drop(index=11).reset_index(drop=True)
            elif mutate == "duplicate":
                f.iat[11, 0] = f.iat[10, 0]
            elif mutate == "count":
                f.iat[8, 1] = 4
            else:
                f.iat[7, 1] = datetime(2026, 9, 1)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                parse_timeseries_frame(f, source())

    def test_quarters_and_declared_start_trim(self):
        f = frame()
        f.iat[0, 1] = "Sales ; Total (State) ; Retail trade ; Current Price ; TOTAL (SCP_SCOPE) ;"
        f.iat[4, 1] = "Quarter"
        f.iat[6, 1], f.iat[7, 1] = datetime(2026, 3, 1), datetime(2026, 6, 1)
        f.iat[8, 1] = 2
        f.iat[10, 0], f.iat[11, 0], f.iat[12, 0] = (
            datetime(2025, 12, 1), datetime(2026, 3, 1), datetime(2026, 6, 1))
        f.iat[10, 1] = None  # Outside declared coverage, not an internal null.
        f.iat[11, 1] = 100
        cfg = dict(source(), dataset_id="abs_business_indicators", table_id=6,
                   frequency="quarterly", reference_end_date="2026-06-30")
        s = parse_timeseries_frame(f, cfg)[0]
        self.assertEqual(s["periods"], ["2026-Q1", "2026-Q2"])
        self.assertEqual(s["values"], [100, 120])
        self.assertEqual(s["measure"], "business_sales")

    def test_adjustment_and_price_basis_not_silently_changed(self):
        f = frame()
        f.iat[2, 1] = "Seasonally Adjusted"
        self.assertEqual(parse_timeseries_frame(f, source())[0]["adjustment"], "Seasonally Adjusted")
        f.iat[0, 1] = f.iat[0, 1].replace("Current Price", "Chain Volume Measures")
        with self.assertRaises(ValueError):
            parse_timeseries_frame(f, source())

    def test_experimental_and_classification(self):
        d = dimensions("Turnover ; Food retailing ; New South Wales ; Current Price ;",
                       dict(source(), table_id=19), "AUD million")
        self.assertTrue(d["experimental"])
        self.assertEqual(d["classification"], "ANZSIC_retail_groups")
        d = dimensions("Household spending ; Non Discretionary ; Australia ; Current Price ;",
                       source(), "AUD million")
        self.assertEqual(d["classification"], "spending_aggregate")

    def test_measure_unit_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            dimensions("Turnover ; Food retailing ; Australia ; Current Price ;",
                       dict(source(), table_id=19), "ratio")
        with self.assertRaises(ValueError):
            dimensions("Sales ; Total (State) ; Retail trade ; Current Price ; TOTAL (SCP_SCOPE) ;",
                       dict(source(), dataset_id="abs_business_indicators", table_id=6), "percent")

    def test_duplicate_references_merge_only_if_exact(self):
        s = parse_timeseries_frame(frame(), source())[0]
        t = copy.deepcopy(s)
        t["table_ids"], t["source_ids"] = [2], ["t2"]
        merged, count = merge_series([copy.deepcopy(s), t])
        self.assertEqual(count, 1)
        self.assertEqual(merged[0]["table_ids"], [1, 2])
        conflict = copy.deepcopy(t)
        conflict["values"][0] = 999
        with self.assertRaises(ValueError):
            merge_series([s, conflict])

    def test_datasets_with_same_id_remain_separate(self):
        a = parse_timeseries_frame(frame(), source())[0]
        b = copy.deepcopy(a)
        b["dataset_id"] = "abs_business_indicators"
        combined, count = merge_series([a, b])
        self.assertEqual((len(combined), count), (2, 0))

    def test_provenance_dates_and_local_hash(self):
        cfg = source()
        validate_source(cfg, "2026-10-28")
        with self.assertRaises(ValueError):
            validate_source(cfg, "2026-08-01")
        with self.assertRaises(ValueError):
            validate_source(dict(cfg, download_date="2026-09-01"), "2026-10-28")
        with self.assertRaises(ValueError):
            validate_source(dict(cfg, url="https://example.com/pretend.xlsx"), "2026-10-28")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.xlsx"
            path.write_bytes(b"test original")
            cfg["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(source_path(directory, cfg), path.resolve())
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                source_path(directory, cfg)
            with self.assertRaises(ValueError):
                source_path(directory, dict(cfg, relative_path="../outside.xlsx"))

    def test_builder_protects_existing_generated_files(self):
        fake = {"series": [], "quality": {}}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "market_catalog.json").write_text("existing")
            with patch("scripts.prepare_abs.market_bundle", return_value=(fake, fake)):
                with self.assertRaises(ValueError):
                    build("unused", DATA / "sources.json", out, "2026-10-28")
            self.assertEqual((out / "market_catalog.json").read_text(), "existing")


class ABSPreparedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(DATA / "market_data.json.gz", "rt", encoding="utf-8") as f:
            cls.bundle = json.load(f)
        cls.by_id = {s["series_id"]: s for s in cls.bundle["series"]}

    def test_pinned_snapshot_series_counts(self):
        q = self.bundle["quality"]
        self.assertEqual(q["unique_series"], 1497)
        self.assertEqual(q["series_by_dataset"], {"abs_mhsi": 1323, "abs_business_indicators": 174})
        self.assertEqual(q["duplicate_references_merged"], 9)
        self.assertEqual(q["missing_values"], 22909)
        self.assertEqual(q["observation_period_values"], 245227)

    def test_real_series_ids_and_latest_values(self):
        for sid, period, value in [("A130200584T", "2026-08", 82340.5),
                                   ("A3531380T", "2026-Q2", 47803),
                                   ("A3531378F", "2026-Q2", 147756),
                                   ("A3531381V", "2026-Q2", 7686),
                                   ("A3531379J", "2026-Q2", 15249)]:
            with self.subTest(sid=sid):
                s = self.by_id[sid]
                self.assertEqual(s["periods"][-1], period)
                self.assertEqual(s["values"][-1], value)
        experimental = self.by_id["A130276228K"]
        self.assertTrue(experimental["experimental"])
        self.assertEqual(experimental["values"][-1], 40037.6)

    def test_official_and_derived_growth_are_distinct(self):
        s = self.by_id["A130200584T"]
        computed = growth_rates(s["periods"], s["values"], "monthly")
        self.assertAlmostEqual(s["derived"]["year_change_pct"][-1],
                               computed["year_change_pct"][-1], places=6)
        official = self.by_id["A130200588A"]
        self.assertEqual(official["unit"], "percent")
        self.assertEqual(official["values"][-1], 6.8)
        self.assertNotIn("derived", official)
        self.assertEqual(official["measure"], "official_yearly_growth_pct")

    def test_no_future_and_complete_source_provenance(self):
        for source in self.bundle["sources"].values():
            validate_source(source, self.bundle["as_of"])
            self.assertIn("CC BY 4.0", source["license"])
            self.assertEqual(source["download_date"], "2026-10-27")
        self.assertEqual(self.bundle["sources"]["abs_mhsi_t1"]["release_date"], "2026-09-29")
        self.assertEqual(self.bundle["sources"]["abs_business_indicators_t23"]["release_date"],
                         "2026-08-31")
        self.assertEqual(set(s["dataset_id"] for s in self.bundle["series"]),
                         {"abs_mhsi", "abs_business_indicators"})

    def test_ratio_and_adjustment_values(self):
        official = self.by_id["A3531382W"]
        self.assertEqual(official_inventory_sales_ratio(official)[-1]["value"], 0.32)
        def resolved(sid):
            s = self.by_id[sid]
            return dict(s, source=self.bundle["sources"][s["source_ids"][0]])
        audit = validate_ratio_against_components(
            resolved("A3531382W"), resolved("A3531380T"), resolved("A3531378F"))
        self.assertTrue(audit["consistent"])
        self.assertEqual(audit["checked_periods"], 110)
        self.assertEqual(self.by_id["A3531391X"]["adjustment"], "Seasonally Adjusted")
        self.assertEqual(self.by_id["A3531391X"]["values"][-1], 49033)
        self.assertEqual(self.by_id["A3531380T"]["values"][-1], 47803)

    def test_nulls_and_negative_profits_preserved(self):
        trend = self.by_id["A3531399T"]
        self.assertEqual(trend["values"].count(None), 11)
        self.assertEqual(trend["values"][trend["periods"].index("2020-Q1")], None)
        negative_profit = [s for s in self.bundle["series"]
                           if s["measure"] == "business_gross_operating_profits"
                           and any(v is not None and v < 0 for v in s["values"])]
        self.assertTrue(negative_profit)

    def test_catalog_and_checksums_reconcile(self):
        catalog = json.loads((DATA / "market_catalog.json").read_text())
        self.assertEqual(len(catalog["series"]), len(self.bundle["series"]))
        self.assertFalse(any("values" in s for s in catalog["series"]))
        manifest = json.loads((DATA / "build_all.json").read_text())
        for file in manifest["files"]:
            self.assertEqual(hashlib.sha256((DATA / file["name"]).read_bytes()).hexdigest(),
                             file["sha256"])

    def test_counts_is_a_separate_annual_dataset(self):
        counts = json.loads((DATA / "business_counts.json").read_text())
        self.assertEqual(counts["dataset_id"], "abs_business_counts")
        self.assertIsNone(counts["official_series_ids"])
        self.assertEqual(counts["annual_flows"]["frequency"], "financial_year")
        self.assertEqual(counts["annual_flows"]["observations"][-1]["closing"], 156143)
        self.assertEqual(len(counts["survival_cohorts"]), 2)

    @unittest.skipUnless(RESEARCH.is_dir(), "Downloaded research workbooks are optional at runtime")
    def test_read_actual_xlsx_without_downloading(self):
        registry = load_registry(DATA / "sources.json")
        cfg = next(s for s in registry["sources"] if s["source_id"] == "abs_mhsi_t1")
        actual = read_timeseries_excel(source_path(RESEARCH, cfg), cfg)
        s = next(s for s in actual if s["series_id"] == "A130200584T")
        self.assertEqual(s["values"], self.by_id[s["series_id"]]["values"])


if __name__ == "__main__":
    unittest.main()

