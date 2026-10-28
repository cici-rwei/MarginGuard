"""Strict loader for processed M5 daily observations; missing prices stay missing."""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from forecast import validate_history

FIELDS = ("date", "item_id", "store_id", "category_id", "department_id",
          "units_sold", "sell_price_usd")


def load_series(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError("Missing processed data: %s. Run scripts/prepare_m5.py first." % path)
    groups = {}
    seen = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("Invalid processed CSV columns; expected: " + ", ".join(FIELDS))
        for line, row in enumerate(reader, 2):
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Malformed CSV row")
                if not all(row[k].strip() for k in FIELDS[1:5]):
                    raise ValueError("Missing series identifiers")
                day = date.fromisoformat(row["date"])
                units = int(row["units_sold"])
                if units < 0:
                    raise ValueError("Negative units")
                price = Decimal(row["sell_price_usd"]) if row["sell_price_usd"] else None
                if price is not None and (not price.is_finite() or price < 0):
                    raise ValueError("Price must be finite and nonnegative or blank")
                key = (row["item_id"], row["store_id"])
                if (key, day) in seen:
                    raise ValueError("Duplicate series/date")
                seen.add((key, day))
                groups.setdefault(key, []).append(dict(row, date=day, units_sold=units,
                                                       sell_price_usd=price))
            except (ValueError, InvalidOperation) as error:
                raise ValueError("Invalid CSV at line %d: %s" % (line, error)) from error
    if not groups:
        raise ValueError("Processed CSV has no observations.")
    for rows in groups.values():
        rows.sort(key=lambda row: row["date"])
        validate_history(rows, minimum=120)
        if len({(r["category_id"], r["department_id"]) for r in rows}) != 1:
            raise ValueError("Inconsistent category/department within a series.")
    return groups
