"""Stream user-supplied original M5 CSV files into a compact, validated subset."""
import argparse
import csv
import hashlib
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_loader import FIELDS, load_series


def read_rows(path, required):
    if not path.is_file():
        raise ValueError("Missing original M5 file: %s" % path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not set(required).issubset(reader.fieldnames or []):
            raise ValueError("Invalid columns in %s; required: %s" % (path.name, required))
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Malformed row in " + path.name)
            yield row


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def prepare(raw_dir, output, items, stores, days=180):
    if not 120 <= days <= 1913:
        raise ValueError("Select between 120 and 1913 consecutive days.")
    raw_dir, output = Path(raw_dir), Path(output)
    paths = {name: raw_dir / (name + ".csv") for name in
             ("sales_train_validation", "calendar", "sell_prices")}
    day_ids = ["d_%d" % n for n in range(1914 - days, 1914)]
    calendar = {}
    for row in read_rows(paths["calendar"], ("d", "date", "wm_yr_wk")):
        if row["d"] in calendar:
            raise ValueError("Duplicate calendar day")
        date.fromisoformat(row["date"])
        calendar[row["d"]] = row
    if not set(day_ids).issubset(calendar):
        raise ValueError("Calendar does not cover selected sales days.")
    selected = {}
    required = ["id", "item_id", "store_id", "cat_id", "dept_id", "state_id"] + day_ids
    for row in read_rows(paths["sales_train_validation"], required):
        key = (row["item_id"], row["store_id"])
        if key[0] in items and key[1] in stores:
            if key in selected:
                raise ValueError("Duplicate product-store sales row")
            selected[key] = row
    expected = {(item, store) for item in items for store in stores}
    if set(selected) != expected:
        raise ValueError("Missing requested product-store pairs: %s" % sorted(expected - set(selected)))
    prices = {}
    weeks = {calendar[d]["wm_yr_wk"] for d in day_ids}
    for row in read_rows(paths["sell_prices"], ("store_id", "item_id", "wm_yr_wk", "sell_price")):
        pair = (row["item_id"], row["store_id"])
        if pair in selected and row["wm_yr_wk"] in weeks:
            key = pair + (row["wm_yr_wk"],)
            if key in prices:
                raise ValueError("Duplicate item/store/week price")
            price = Decimal(row["sell_price"]) if row["sell_price"] else None
            if price is not None and (not price.is_finite() or price < 0):
                raise ValueError("Invalid selling price")
            prices[key] = "" if price is None else str(price)
    records = []
    for pair, sales in sorted(selected.items()):
        for day_id in day_ids:
            cal = calendar[day_id]
            records.append(dict(zip(FIELDS, (cal["date"], pair[0], pair[1], sales["cat_id"],
                                            sales["dept_id"], sales[day_id],
                                            prices.get(pair + (cal["wm_yr_wk"],), "")))))
    records.sort(key=lambda r: (r["date"], r["item_id"], r["store_id"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".pending.csv")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(records)
        groups = load_series(temporary)
        summary = []
        for pair, rows in groups.items():
            nonzero = sum(r["units_sold"] > 0 for r in rows)
            summary.append({"item_id": pair[0], "store_id": pair[1], "days": len(rows),
                            "start": str(rows[0]["date"]), "end": str(rows[-1]["date"]),
                            "nonzero_days": nonzero, "zero_sales_days": len(rows) - nonzero,
                            "missing_price_days": sum(r["sell_price_usd"] is None for r in rows),
                            "zero_price_days": sum(r["sell_price_usd"] == 0 for r in rows),
                            "sparsity_warning": nonzero / len(rows) < 0.2})
            if not nonzero:
                raise ValueError("All-zero series rejected: %s" % (pair,))
        report = {"source": "User-supplied M5 files; verify provenance and usage rights separately",
                  "sha256": {name: digest(path) for name, path in paths.items()},
                  "series": summary, "duplicates": 0, "missing_sales": 0}
        temporary.replace(output)
        output.with_suffix(".validation.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--output", default="data/processed_sales.csv")
    parser.add_argument("--items", nargs="+", required=True)
    parser.add_argument("--stores", nargs="+", required=True)
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.raw_dir, args.output, args.items, args.stores, args.days), indent=2))
    except (ValueError, OSError, InvalidOperation, csv.Error) as error:
        parser.exit(2, "Data preparation failed: %s\n" % error)


if __name__ == "__main__":
    main()
