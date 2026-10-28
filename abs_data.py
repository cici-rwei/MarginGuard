"""Read pinned ABS workbooks without changing M5 data or forecasting code.

Each series keeps its official ID and statistical dimensions. Missing values stay
None. Published percentage series are retained separately from computed growth.
"""
import hashlib
import json
import math
from datetime import date, datetime
from numbers import Real
from pathlib import Path

import pandas as pd

SCHEMA_VERSION = 1
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
ADJUSTMENTS = {"Original", "Seasonally Adjusted", "Trend"}
UNIT_MAP = {"$ Millions": "AUD million", "Percent": "percent", "Quotient": "ratio"}
AGGREGATES = {"Total (Household Spending Categories)", "Goods", "Services",
              "Discretionary", "Non Discretionary"}
LABELS = ("Unit", "Series Type", "Data Type", "Frequency", "Collection Month",
          "Series Start", "Series End", "No. Obs", "Series ID")
BI_MEASURES = {3: "inventories", 6: "business_sales",
               15: "business_gross_operating_profits", 17: "wages",
               23: "inventory_to_sales_ratio"}


def load_registry(path):
    """Load explicit table provenance; never discover/download new files."""
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported ABS source registry schema")
    ids = [s["source_id"] for s in registry["sources"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate ABS source_id")
    return registry


def validate_source(source, as_of):
    required = ("source_id", "dataset_id", "table_id", "relative_path", "sha256",
                "url", "release_date", "download_date", "reference_end_date",
                "license", "license_url", "frequency")
    if any(not source.get(key) for key in required):
        raise ValueError("Incomplete ABS source provenance")
    cutoff = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    release = date.fromisoformat(source["release_date"])
    download = date.fromisoformat(source["download_date"])
    reference = date.fromisoformat(source["reference_end_date"])
    if release > cutoff or download > cutoff or reference > release or release > download:
        raise ValueError("ABS source was not available at the selected as-of date")
    if not source["url"].startswith("https://www.abs.gov.au/"):
        raise ValueError("Expected an official ABS source URL")


def source_path(research_dir, source):
    root = Path(research_dir).resolve()
    path = (root / source["relative_path"]).resolve()
    if root not in path.parents:
        raise ValueError("ABS source path must remain inside the research directory")
    if not path.is_file():
        raise ValueError("Missing local ABS workbook: " + str(path))
    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("ABS workbook checksum changed: " + path.name)
    return path


def number_or_none(value):
    """Only known missing markers are accepted; unknown text is an error."""
    if value is None or (isinstance(value, str) and value.strip().lower()
                         in {"", "..", "na", "n/a"}):
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("Unexpected nonnumeric ABS observation: " + repr(value))
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("ABS observations must be finite or explicitly missing")
    return value


def period_label(value, frequency):
    if not isinstance(value, (date, datetime, pd.Timestamp)):
        raise ValueError("Expected an Excel date, got " + repr(value))
    if value.day != 1:
        raise ValueError("ABS monthly/quarterly dates must mark the first day")
    if frequency == "monthly":
        return "%04d-%02d" % (value.year, value.month)
    if frequency == "quarterly" and value.month in (3, 6, 9, 12):
        return "%04d-Q%d" % (value.year, value.month // 3)
    raise ValueError("Unexpected ABS frequency or quarter-ending month")


def expected_periods(start, end, frequency):
    freq = {"monthly": "M", "quarterly": "Q-DEC"}[frequency]
    # Pandas PeriodIndex checks calendar continuity, not just row counts.
    return [str(p).replace("Q", "-Q") if frequency == "quarterly" else str(p)
            for p in pd.period_range(start.replace("-Q", "Q"),
                                     end.replace("-Q", "Q"), freq=freq)]


def dimensions(description, source, unit):
    parts = [part.strip() for part in description.split(";") if part.strip()]
    dataset, table = source["dataset_id"], source["table_id"]
    if dataset == "abs_mhsi":
        if len(parts) != 4 or parts[3] != "Current Price":
            raise ValueError("Unrecognized MHSI description: " + description)
        raw_measure, category, geography, _ = parts
        allowed = {"Household spending": "household_spending",
                   "Household spending - Percentage change from previous period":
                       "official_monthly_growth_pct",
                   "Household spending - Through the year percentage change":
                       "official_yearly_growth_pct",
                   "Turnover": "retail_turnover"}
        if raw_measure not in allowed or (table == 19) != (raw_measure == "Turnover"):
            raise ValueError("Unexpected MHSI measure/table")
        measure = allowed[raw_measure]
        expected_unit = "percent" if measure.startswith("official_") else "AUD million"
        if unit != expected_unit:
            raise ValueError("MHSI measure/unit mismatch")
        return dict(measure=measure, category=category, geography=geography,
                    classification=("ANZSIC_retail_groups" if table == 19 else
                                    "spending_aggregate" if category in AGGREGATES
                                    else "COICOP"),
                    domain="experimental_retail_turnover" if table == 19
                           else "household_spending",
                    price_basis="current_prices", experimental=(table == 19))
    if dataset == "abs_business_indicators":
        if (table not in BI_MEASURES or len(parts) != 5
                or parts[1] != "Total (State)" or parts[3] != "Current Price"
                or parts[4] != "TOTAL (SCP_SCOPE)"):
            raise ValueError("Unexpected Business Indicators scope/price basis")
        names = {3: "Inventories", 6: "Sales", 15: "Gross Operating Profits",
                 17: "Wages", 23: "Inventories to sales ratio"}
        if parts[0] != names[table]:
            raise ValueError("Unexpected Business Indicators measure: " + parts[0])
        if unit != ("ratio" if table == 23 else "AUD million"):
            raise ValueError("Business Indicators unit/table mismatch")
        return dict(measure=BI_MEASURES[table], category=parts[2],
                    geography="Australia", classification="ANZSIC",
                    domain="business_operations", price_basis="current_prices",
                    experimental=False, business_scope="TOTAL (SCP_SCOPE)")
    raise ValueError("Unsupported ABS dataset")


def parse_timeseries_frame(frame, source):
    """Parse Data1 by metadata labels, then validate each declared date window."""
    metadata = {}
    for i in range(min(len(frame), 25)):
        label = frame.iat[i, 0]
        if label in LABELS:
            if label in metadata:
                raise ValueError("Duplicate ABS metadata label: " + label)
            metadata[label] = i
    if set(metadata) != set(LABELS):
        raise ValueError("Missing ABS metadata labels")
    description_row = metadata["Unit"] - 1
    first_data_row = max(metadata.values()) + 1
    if description_row < 0 or first_data_row >= len(frame):
        raise ValueError("No ABS observations or descriptions")
    result = []
    for column in range(1, frame.shape[1]):
        def meta(label):
            return frame.iat[metadata[label], column]
        series_id = meta("Series ID")
        description = frame.iat[description_row, column]
        if series_id in (None, "") and description in (None, ""):
            continue
        if not isinstance(series_id, str) or not series_id.startswith("A"):
            raise ValueError("Missing or invalid official Series ID")
        if not isinstance(description, str):
            raise ValueError("Missing ABS series description")
        unit = UNIT_MAP.get(meta("Unit"))
        frequency = {"Month": "monthly", "Quarter": "quarterly"}.get(meta("Frequency"))
        if unit is None or frequency != source["frequency"]:
            raise ValueError("Unsupported unit/frequency")
        adjustment = meta("Series Type")
        observation_type = meta("Data Type")
        if adjustment not in ADJUSTMENTS:
            raise ValueError("Unknown ABS adjustment")
        expected_type = "PERCENT" if unit == "percent" else "RATIO" if unit == "ratio" else (
            "STOCK_CLOSE" if source["table_id"] == 3 and
            source["dataset_id"] == "abs_business_indicators" else "FLOW")
        if observation_type != expected_type:
            raise ValueError("ABS data type does not match measure/unit")
        start = period_label(meta("Series Start"), frequency)
        end = period_label(meta("Series End"), frequency)
        if pd.Timestamp(meta("Series End")).date() > date.fromisoformat(source["reference_end_date"]):
            raise ValueError("Observation extends beyond approved reference period")
        periods, values = [], []
        for row in range(first_data_row, len(frame)):
            day = frame.iat[row, 0]
            label = period_label(day, frequency)
            if start <= label <= end:
                periods.append(label)
                values.append(number_or_none(frame.iat[row, column]))
        if periods != expected_periods(start, end, frequency):
            raise ValueError("Missing, duplicate or unordered ABS dates: " + series_id)
        declared = meta("No. Obs")
        if not isinstance(declared, Real) or declared != len(periods):
            raise ValueError("Declared ABS observation count does not match dates")
        series = dict(dataset_id=source["dataset_id"], series_id=series_id,
                      table_ids=[source["table_id"]], source_ids=[source["source_id"]],
                      description=description, frequency=frequency, unit=unit,
                      currency="AUD" if unit == "AUD million" else None,
                      adjustment=adjustment, observation_type=observation_type,
                      periods=periods, values=values,
                      status=["missing" if v is None else "observed" for v in values])
        series.update(dimensions(description, source, unit))
        if source["table_id"] == 23 and adjustment != "Original":
            raise ValueError("Official inventory/sales ratio must be Original")
        result.append(series)
    if not result:
        raise ValueError("ABS workbook contains no series")
    return result


def read_timeseries_excel(path, source):
    """Pandas + openpyxl reads existing files only; no network or workbook edits."""
    frame = pd.read_excel(path, sheet_name="Data1", header=None, dtype=object,
                          keep_default_na=False, engine="openpyxl")
    return parse_timeseries_frame(frame, source)


def merge_series(series_list):
    """Repeated official IDs are references, not extra observations to sum."""
    unique = {}
    duplicates = 0
    ignored = {"table_ids", "source_ids"}
    for series in series_list:
        key = (series["dataset_id"], series["series_id"])
        if key not in unique:
            unique[key] = series
            continue
        old = unique[key]
        if ({k: v for k, v in old.items() if k not in ignored} !=
                {k: v for k, v in series.items() if k not in ignored}):
            raise ValueError("Conflicting duplicate ABS series: " + repr(key))
        old["table_ids"] = sorted(set(old["table_ids"] + series["table_ids"]))
        old["source_ids"] = sorted(set(old["source_ids"] + series["source_ids"]))
        duplicates += 1
    return sorted(unique.values(), key=lambda s: (s["dataset_id"], s["series_id"])), duplicates


def load_market_series(research_dir, registry, as_of):
    result = []
    sources = [s for s in registry["sources"]
               if s["dataset_id"] in {"abs_mhsi", "abs_business_indicators"}]
    for source in sources:
        validate_source(source, as_of)
        result.extend(read_timeseries_excel(source_path(research_dir, source), source))
    series, duplicates = merge_series(result)
    return series, sources, duplicates

