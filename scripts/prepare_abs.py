"""Build independent ABS data files from the already downloaded official XLSX."""
import argparse
from collections import Counter
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from abs_data import load_registry, load_market_series, validate_source, source_path
from abs_indicators import growth_rates, validate_ratio_against_components
from abs_counts import read_business_counts

NOTES = [
    "ABS aggregate market data does not change Walmart product forecasts.",
    "Household spending and business sales are different statistical populations.",
    "MHSI Table 19 is experimental; do not splice it to historical Retail Trade.",
    "Business gross operating profits are not product gross profit (revenue minus COGS).",
    "Inventory-to-sales ratio is quarter-end inventory / quarterly sales, not days of cover.",
    "Current prices are nominal; no chain-volume measures are included in this snapshot.",
    "Missing observations remain null; growth is null if its prior base is missing or <= 0.",
    "Published percentage series are retained separately and are not growth-transformed.",
]


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def market_bundle(research_dir, registry, as_of):
    series, sources, duplicate_count = load_market_series(research_dir, registry, as_of)
    source_map = {s["source_id"]: s for s in sources}
    for s in series:
        if s["unit"] == "AUD million":
            computed = growth_rates(s["periods"], s["values"], s["frequency"])
            s["derived"] = {k: [None if v is None else round(v, 6) for v in values]
                            for k, values in computed.items()}
            s["derived_note"] = "Calculated from published rounded levels; percent growth, 6 decimals."
    def lookup(measure, category):
        found = [s for s in series if s["dataset_id"] == "abs_business_indicators"
                 and s["measure"] == measure and s["category"] == category
                 and s["adjustment"] == "Original"]
        if len(found) != 1:
            raise ValueError("Expected one compatible ratio component: " + category)
        s = found[0]
        return dict(s, source=source_map[s["source_ids"][0]])
    ratio_checks = {}
    for s in series:
        if s["measure"] == "inventory_to_sales_ratio":
            category = s["category"]
            check = validate_ratio_against_components(
                dict(s, source=source_map[s["source_ids"][0]]),
                lookup("inventories", category), lookup("business_sales", category))
            if not check["consistent"]:
                raise ValueError("Official ratio reconciliation failed: " + category)
            ratio_checks[category] = check
    quality = {
        "input_series_columns": len(series) + duplicate_count,
        "unique_series": len(series), "duplicate_references_merged": duplicate_count,
        "series_by_dataset": dict(Counter(s["dataset_id"] for s in series)),
        "observation_period_values": sum(len(s["periods"]) for s in series),
        "missing_values": sum(v is None for s in series for v in s["values"]),
        "level_series_with_computed_growth": sum("derived" in s for s in series),
        "official_percentage_series": sum(s["unit"] == "percent" for s in series),
        "official_ratio_series": sum(s["unit"] == "ratio" for s in series),
        "negative_published_values": sum(v is not None and v < 0 for s in series
                                         for v in s["values"]),
        "negative_level_values": sum(v is not None and v < 0 for s in series
                                      if s["unit"] == "AUD million" for v in s["values"]),
        "by_dataset": {dataset: {
            "series": sum(s["dataset_id"] == dataset for s in series),
            "period_values": sum(len(s["periods"]) for s in series if s["dataset_id"] == dataset),
            "missing_values": sum(v is None for s in series if s["dataset_id"] == dataset
                                  for v in s["values"]),
        } for dataset in sorted({s["dataset_id"] for s in series})},
        "ratio_checks": ratio_checks,
    }
    payload = {"schema_version": 1, "as_of": as_of, "sources": source_map,
               "series": series, "quality": quality, "notes": NOTES}
    catalog = dict(payload, series=[{k: v for k, v in s.items()
                                    if k not in {"periods", "values", "status", "derived"}}
                                   | {"start_period": s["periods"][0],
                                      "end_period": s["periods"][-1],
                                      "observations": len(s["periods"]),
                                      "missing_values": s["values"].count(None)}
                                   for s in series])
    return payload, catalog


def build(research_dir, registry_path, output_dir, as_of, dataset="market", overwrite=False):
    date.fromisoformat(as_of)
    registry = load_registry(registry_path)
    outputs = {}
    if dataset in {"market", "all"}:
        market, catalog = market_bundle(research_dir, registry, as_of)
        outputs["market_data.json.gz"] = gzip.compress(_bytes(market), mtime=0)
        outputs["market_catalog.json"] = _bytes(catalog)
        outputs["market_quality.json"] = _bytes(market["quality"])
    if dataset in {"counts", "all"}:
        source = next(s for s in registry["sources"] if s["dataset_id"] == "abs_business_counts")
        validate_source(source, as_of)
        counts = read_business_counts(source_path(research_dir, source), source)
        counts["as_of"] = as_of
        outputs["business_counts.json"] = _bytes(counts)
    if not outputs:
        raise ValueError("Select market, counts or all")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_name = "build_" + dataset + ".json"
    targets = list(outputs) + [manifest_name]
    if not overwrite and any((output_dir / name).exists() for name in targets):
        raise ValueError("ABS output exists. Use --overwrite only to rebuild these generated ABS files.")
    manifest = {"schema_version": 1, "as_of": as_of, "dataset_selection": dataset,
                "source_registry_sha256": hashlib.sha256(Path(registry_path).read_bytes()).hexdigest(),
                "files": [{"name": name, "bytes": len(content),
                           "sha256": hashlib.sha256(content).hexdigest()}
                          for name, content in outputs.items()]}
    outputs[manifest_name] = _bytes(manifest)
    # All parsing/calculations succeed before writing. Each generated file replaces atomically.
    for name, content in outputs.items():
        path = output_dir / name
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-dir", type=Path,
                        default=ROOT.parents[1] / "research" / "datasets")
    parser.add_argument("--sources", type=Path, default=ROOT / "data/abs/sources.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/abs")
    parser.add_argument("--as-of", default="2026-10-28",
                        help="Data availability cutoff; reproducible pinned build defaults to 2026-10-28.")
    parser.add_argument("--dataset", choices=("market", "counts", "all"), default="market")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = build(args.research_dir, args.sources, args.output_dir, args.as_of,
                   args.dataset, args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))

