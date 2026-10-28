"""Read-only views of prepared ABS data, with transparent Python insights.

This layer reads fixed Phase 4A JSON files, never Excel or user-supplied paths.
It does not change product forecasts or financial scenario calculations.
"""
import copy
import gzip
import json
from pathlib import Path
import re


class MarketDataUnavailable(Exception):
    """The prepared local ABS snapshot cannot safely be served."""


def _metadata(series):
    result = {k: v for k, v in series.items()
              if k not in {"periods", "values", "status", "derived"}}
    result.update(start_period=series["periods"][0], end_period=series["periods"][-1],
                  observations=len(series["periods"]), missing_values=series["values"].count(None))
    return result


def _period(value, frequency):
    pattern = r"[1-9][0-9]{3}-(?:0[1-9]|1[0-2])" if frequency == "monthly" else r"[1-9][0-9]{3}-Q[1-4]"
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError("Use YYYY-MM for months or YYYY-Q1 through YYYY-Q4 for quarters.")
    return value


def _direction(value):
    return "increased" if value > 0 else "decreased" if value < 0 else "was unchanged"


class MarketService:
    """One validated snapshot loaded once for a Flask application's lifetime."""

    def __init__(self, abs_dir):
        root = Path(abs_dir)
        try:
            with gzip.open(root / "market_data.json.gz", "rt", encoding="utf-8") as stream:
                self.market = json.load(stream)
            self.counts = json.loads((root / "business_counts.json").read_text(encoding="utf-8"))
            if self.market["schema_version"] != 1 or self.counts["schema_version"] != 1:
                raise ValueError("Unexpected schema version")
            self.index = {}
            for series in self.market["series"]:
                key = (series["dataset_id"], series["series_id"])
                if key in self.index or not series["periods"]:
                    raise ValueError("Duplicate or empty series")
                if not (len(series["periods"]) == len(series["values"]) == len(series["status"])):
                    raise ValueError("Mismatched series arrays")
                if any(len(values) != len(series["periods"]) for values in series.get("derived", {}).values()):
                    raise ValueError("Mismatched growth arrays")
                if any(source_id not in self.market["sources"] for source_id in series["source_ids"]):
                    raise ValueError("Missing source reference")
                self.index[key] = series
            self.financial_years = [row["period"] for row in self.counts["annual_flows"]["observations"]]
            if not self.index or not self.financial_years:
                raise ValueError("Empty ABS snapshot")
            self.as_of = self.market["as_of"]
        except (OSError, ValueError, KeyError, TypeError, EOFError) as error:
            raise MarketDataUnavailable("ABS market data is unavailable. Restore the prepared Phase 4A files and restart the server.") from error

    def _sources(self, series_list):
        ids = sorted({source_id for series in series_list for source_id in series["source_ids"]})
        return [self.market["sources"][source_id] for source_id in ids]

    def catalog(self):
        return {"schema_version": 1, "as_of": self.as_of,
                "series": [_metadata(series) for series in self.index.values()],
                "counts": {"financial_years": self.financial_years}}

    def sources(self):
        return {"as_of": self.as_of,
                "sources": list(self.market["sources"].values()) + [self.counts["source"]],
                "notes": self.market["notes"] + self.counts["notes"]}

    def _get(self, dataset_id, series_id):
        try:
            return self.index[(dataset_id, series_id)]
        except KeyError as error:
            raise ValueError("Unknown ABS dataset and Series ID combination.") from error

    @staticmethod
    def _latest(series, position):
        derived = series.get("derived", {})
        def growth(key):
            return derived[key][position] if key in derived else None
        current = series["values"][position]
        previous = series["values"][position - 1] if position else None
        delta = round(current - previous, 6) if current is not None and previous is not None else None
        return {"period": series["periods"][position], "value": current,
                "status": series["status"][position],
                "period_change_pct": growth("period_change_pct"),
                "year_change_pct": growth("year_change_pct"), "period_delta": delta}

    @staticmethod
    def _insights(series, latest):
        period, value = latest["period"], latest["value"]
        if value is None:
            return ["The selected series has no published value for %s. Its direction cannot be assessed; missing values are not zero." % period]
        if series["measure"] == "inventory_to_sales_ratio":
            delta = latest["period_delta"]
            insight = ("The official inventory-to-sales ratio %s by %.2f from the previous quarter in %s."
                       % (_direction(delta), abs(delta), period)) if delta is not None else (
                           "The previous quarter is unavailable; the ratio's change cannot be assessed.")
            return [insight, "Quarter-end inventory is compared with quarterly sales. This is not inventory days or an individual firm's risk rating."]
        insights = []
        for key, label in (("period_change_pct", "month-on-month" if series["frequency"] == "monthly" else "quarter-on-quarter"),
                           ("year_change_pct", "year-on-year")):
            growth = latest[key]
            if growth is None:
                insights.append("%s change for %s cannot be assessed from the available positive-base observations." % (label.capitalize(), period))
            elif growth == 0:
                insights.append("The selected measure was unchanged %s in %s." % (label, period))
            else:
                insights.append("The selected measure %s by %.2f%% %s in %s." % (_direction(growth), abs(growth), label, period))
        if "derived" in series:
            insights.append("Changes are calculated from published current-price levels; they describe nominal movement, not its causes.")
        return insights

    def series(self, dataset_id, series_id, start=None, end=None):
        series = self._get(dataset_id, series_id)
        periods = series["periods"]
        start = periods[0] if start is None else _period(start, series["frequency"])
        end = periods[-1] if end is None else _period(end, series["frequency"])
        if start not in periods or end not in periods or start > end:
            raise ValueError("Select an ordered date range within this series' published history.")
        first, last = periods.index(start), periods.index(end)
        result = _metadata(series)
        result.update({key: series[key][first:last + 1] for key in ("periods", "values", "status")})
        if "derived" in series:
            result["derived"] = {key: values[first:last + 1] for key, values in series["derived"].items()}
        latest = self._latest(series, last)
        return {"series": result, "latest": latest, "insights": self._insights(series, latest),
                "sources": self._sources([series]), "as_of": self.as_of}

    def overview(self):
        definitions = [
            ("Household Spending", "abs_mhsi", "A130200584T"),
            ("Experimental Retail Turnover", "abs_mhsi", "A130276228K"),
            ("Retail Inventories", "abs_business_indicators", "A3531380T"),
            ("Inventory-to-Sales Ratio", "abs_business_indicators", "A3531382W"),
        ]
        kpis, selected = [], []
        for label, dataset_id, series_id in definitions:
            series = self._get(dataset_id, series_id)
            selected.append(series)
            latest = self._latest(series, len(series["periods"]) - 1)
            kpis.append(dict(latest, label=label, dataset_id=dataset_id, series_id=series_id,
                             unit=series["unit"], frequency=series["frequency"],
                             adjustment=series["adjustment"], experimental=series["experimental"],
                             price_basis=series["price_basis"], source_ids=series["source_ids"]))
        return {"kpis": kpis, "sources": self._sources(selected), "as_of": self.as_of,
                "notes": ["Reference periods differ by release: monthly household spending and retail turnover, quarterly business indicators.",
                          "ABS aggregate market indicators are independent of Walmart product forecasts and scenarios."]}

    def compare(self, dataset_id, table_id, measure, adjustment, period, growth, group,
                category=None, geography=None):
        if dataset_id != "abs_mhsi" or table_id not in {"2", "19", "states"}:
            raise ValueError("Comparisons support MHSI Table 2, Table 19 or state Tables 3–10.")
        if growth not in {"year", "period"} or adjustment not in {"Original", "Seasonally Adjusted", "Trend"}:
            raise ValueError("Select year/period growth and a supported adjustment.")
        expected_measure = "retail_turnover" if table_id == "19" else "household_spending"
        if measure != expected_measure:
            raise ValueError("The selected measure does not belong to this table.")
        if (table_id == "states" and (group != "geography" or not category)) or (
                table_id != "states" and (group != "category" or not geography)):
            raise ValueError("State comparisons require a category; category comparisons require a geography.")
        _period(period, "monthly")
        def matches(series):
            tables = series["table_ids"]
            table_match = any(table in tables for table in range(3, 11)) if table_id == "states" else int(table_id) in tables
            return (series["dataset_id"] == dataset_id and table_match
                    and series["measure"] == measure and series["adjustment"] == adjustment
                    and (category is None or series["category"] == category)
                    and (geography is None or series["geography"] == geography)
                    and (table_id != "2" or series["classification"] == "COICOP")
                    and (table_id != "19" or series["category"] != "Total (Industry)"))
        selected = [series for series in self.index.values() if matches(series)]
        if not selected or any(period not in series["periods"] for series in selected):
            raise ValueError("No matching published comparison for these filters and month.")
        if len({series[group] for series in selected}) != len(selected):
            raise ValueError("Comparison filters must identify one series per category or state.")
        growth_key = "year_change_pct" if growth == "year" else "period_change_pct"
        rows = []
        for series in selected:
            position = series["periods"].index(period)
            rows.append({"name": series[group], "period": period, "value": series["values"][position],
                         "growth_pct": series["derived"][growth_key][position],
                         "series_id": series["series_id"], "category": series["category"],
                         "geography": series["geography"], "source_ids": series["source_ids"]})
        rows.sort(key=lambda row: (row["growth_pct"] is None,
                                  -(row["growth_pct"] or 0), row["name"]))
        available = [row for row in rows if row["growth_pct"] is not None]
        label = "Year-on-year" if growth == "year" else "Month-on-month"
        if available:
            highest = available[0]["growth_pct"]
            leaders = [row["name"] for row in available if row["growth_pct"] == highest]
            insights = ["%s had the highest available %s change (%.2f%%) in %s among the %d displayed comparisons."
                        % (", ".join(leaders), label.lower(), highest, period, len(available))]
        else:
            insights = ["No comparable growth rates are available for this selection; a ranking cannot be assessed."]
        missing = len(rows) - len(available)
        if missing:
            insights.append("%d comparison(s) have unavailable growth and are excluded from ranking." % missing)
        insights.append("Ranking uses percentage growth, not spending size. These figures do not establish causes or predict future performance.")
        return {"rows": rows, "unit": "AUD million", "growth_label": label,
                "insights": insights, "sources": self._sources(selected),
                "experimental": table_id == "19", "adjustment": adjustment,
                "period": period, "classification": selected[0]["classification"],
                "frequency": "monthly", "price_basis": "current_prices", "as_of": self.as_of}

    def business_counts(self, financial_year=None):
        if financial_year is not None and financial_year not in self.financial_years:
            raise ValueError("Select a published financial year from the business-counts catalog.")
        result = copy.deepcopy(self.counts)
        if financial_year is not None:
            result["annual_flows"]["observations"] = [row for row in result["annual_flows"]["observations"]
                                                       if row["period"] == financial_year]
        latest = result["annual_flows"]["observations"][-1]
        net = latest["derived_net_change"]
        if net is None:
            insights = ["The net change in businesses cannot be assessed for this financial year."]
        else:
            insights = ["Retail trade businesses %s by %s in %s (entries less exits)."
                        % (_direction(net), format(abs(net), ","), latest["period"])]
        for cohort in result["survival_cohorts"]:
            observation = cohort["observations"][-1]
            rate = observation["official_survival_rate_pct"]
            label = "Existing businesses" if cohort["cohort_type"] == "existing_businesses" else "Entrants"
            insights.append(("%s in the %s cohort had a published survival rate of %.1f%% at %s."
                             % (label, cohort["cohort_period"], rate, observation["period"])) if rate is not None
                            else "%s survival cannot be assessed for the latest cohort observation." % label)
        insights.append("Business counts are not store counts. Exits are not a bankruptcy measure; the survival cohorts have different fixed denominators.")
        result["insights"] = insights
        return result
