"""Validate local, daily business CSVs without altering M5 or ABS data.

This module neither fills missing days nor calculates financial outcomes. The
caller must declare gross positive sales and AUD or USD. That declaration is
retained, not independently verified. ``as_of_date`` is the first incomplete
date: only earlier dates are accepted. Its default is the local calendar date;
callers with a business timezone should supply that timezone's date explicitly.
No timezone conversion is performed on the CSV's date-only observations.
"""
import csv
import io
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


SUPPORTED_CURRENCIES = ("AUD", "USD")
MIN_HISTORY_DAYS = 42
RECOMMENDED_HISTORY_DAYS = 84
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50000
MAX_SERIES = 100
MAX_FIELD_CHARS = 1024
MAX_IDENTIFIER_CHARS = 80
MAX_SPAN_DAYS = 1096
MAX_UNITS = 1000000
MAX_AMOUNT = Decimal("1000000000")
MAX_REPORTED_ERRORS = 50

REQUIRED_FIELDS = ("date", "product", "store", "units_sold")
OPTIONAL_FIELDS = ("unit_price", "unit_cost")
FIELD_ALIASES = {
    "date": "date", "product": "product", "store": "store",
    "units sold": "units_sold", "units_sold": "units_sold",
    "unit price": "unit_price", "unit_price": "unit_price",
    "unit cost": "unit_cost", "unit_cost": "unit_cost",
}


class BusinessCSVError(ValueError):
    """Bounded, structured issues; messages never echo raw business values."""

    def __init__(self, errors, error_count=None):
        self.errors = list(errors)[:MAX_REPORTED_ERRORS]
        self.error_count = len(errors) if error_count is None else error_count
        self.code = self.errors[0]["code"] if self.errors else "invalid_csv"
        first = self.errors[0]["message"] if self.errors else "CSV validation failed."
        super().__init__("%s (%d validation issue(s).)" % (first, self.error_count))


class _Issues:
    def __init__(self):
        self.errors = []
        self.count = 0

    def add(self, code, message, line=None, field=None):
        self.count += 1
        if len(self.errors) < MAX_REPORTED_ERRORS:
            self.errors.append(dict(code=code, message=message, line=line, field=field))

    def raise_if_any(self):
        if self.count:
            raise BusinessCSVError(self.errors, self.count)


class _InvalidField(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message, line=None, field=None):
    raise BusinessCSVError([dict(code=code, message=message, line=line, field=field)]) from None


def _parse_date(value, as_of_date):
    value = value.strip()
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise _InvalidField("invalid_date", "Date must use YYYY-MM-DD.")
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise _InvalidField("invalid_date", "Date is not a valid calendar date.") from None
    if day >= as_of_date:
        raise _InvalidField("incomplete_or_future_date", "Date must precede the declared as-of date.")
    return day


def _parse_identifier(value):
    cleaned = value.strip()
    if not cleaned:
        raise _InvalidField("missing_identifier", "Product and Store must not be blank.")
    if len(cleaned) > MAX_IDENTIFIER_CHARS:
        raise _InvalidField("identifier_too_long", "Identifier exceeds 80 characters.")
    if any(unicodedata.category(c).startswith("C") for c in value):
        raise _InvalidField("invalid_identifier", "Identifier contains a control or formatting character.")
    if cleaned[0] in "=+-@":
        raise _InvalidField("invalid_identifier", "Identifier must not start with a spreadsheet formula prefix.")
    return cleaned


def _parse_units(value):
    value = value.strip()
    if not value:
        return None
    if value.startswith("-"):
        raise _InvalidField("negative_units", "Negative or return quantities are not positive sales.")
    if not re.fullmatch(r"[0-9]+", value):
        raise _InvalidField("invalid_units", "Units Sold must be a whole-number literal or blank; no decimals or exponents.")
    units = int(value)
    if units > MAX_UNITS:
        raise _InvalidField("units_out_of_range", "Units Sold exceeds 1,000,000 per day.")
    return units


def _parse_amount(value):
    value = value.strip()
    if not value:
        return None
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,6})?", value):
        raise _InvalidField("invalid_amount", "Amount must be nonnegative decimal notation with at most six decimal places.")
    amount = Decimal(value)
    if not amount.is_finite() or amount > MAX_AMOUNT:
        raise _InvalidField("amount_out_of_range", "Amount exceeds 1,000,000,000.")
    return amount


def _blank_line(cells):
    # A comma-filled row is not a blank line: its required fields are missing.
    return not cells or (len(cells) == 1 and not cells[0].strip())


def _read_header(cells, line):
    if len(cells) > len(REQUIRED_FIELDS) + len(OPTIONAL_FIELDS):
        _fail("too_many_columns", "CSV may contain only the four required and two optional columns.", line)
    issues = _Issues()
    columns = []
    for cell in cells:
        if len(cell) > MAX_FIELD_CHARS:
            issues.add("field_too_long", "CSV field exceeds 1,024 characters.", line)
        canonical = FIELD_ALIASES.get(cell.strip().lower())
        if canonical is None:
            issues.add("unknown_column", "CSV has an unsupported or empty column heading.", line)
        elif canonical in columns:
            issues.add("duplicate_column", "Two headings map to the same field.", line, canonical)
        columns.append(canonical)
    for field in REQUIRED_FIELDS:
        if field not in columns:
            issues.add("missing_column", "A required CSV column is missing.", line, field)
    issues.raise_if_any()
    return columns


def _continuous_ranges(rows):
    ranges = []
    start = previous = None
    count = 0
    for row in rows:
        day = row["date"]
        if row["units_sold"] is None:
            if start is not None:
                ranges.append(dict(start_date=start.isoformat(), end_date=previous.isoformat(), days=count))
            start = previous = None
            count = 0
        elif start is None or day != previous + timedelta(days=1):
            if start is not None:
                ranges.append(dict(start_date=start.isoformat(), end_date=previous.isoformat(), days=count))
            start = previous = day
            count = 1
        else:
            previous = day
            count += 1
    if start is not None:
        ranges.append(dict(start_date=start.isoformat(), end_date=previous.isoformat(), days=count))
    return ranges


def _last_reference(rows, field):
    for row in reversed(rows):
        if row[field] is not None:
            return {"date": row["date"].isoformat(), "value": str(row[field])}
    return None


def _series_report(product, store, rows):
    start, end = rows[0]["date"], rows[-1]["date"]
    span = (end - start).days + 1
    recorded = {row["date"] for row in rows}
    missing = [(start + timedelta(days=i)).isoformat() for i in range(span)
               if start + timedelta(days=i) not in recorded]
    unknown = [row["date"].isoformat() for row in rows if row["units_sold"] is None]
    ranges = _continuous_ranges(rows)
    known_count = len(rows) - len(unknown)
    zero_count = sum(row["units_sold"] == 0 for row in rows)
    price_missing = sum(row["unit_price"] is None for row in rows)
    cost_missing = sum(row["unit_cost"] is None for row in rows)
    complete = not missing and not unknown
    eligible = complete and len(rows) >= MIN_HISTORY_DAYS
    warnings = []
    if missing:
        warnings.append("missing_dates_are_unknown")
    if unknown:
        warnings.append("blank_units_are_unknown")
    if len(rows) < RECOMMENDED_HISTORY_DAYS:
        warnings.append("less_than_84_recorded_days")
    if known_count and known_count == zero_count:
        warnings.append("no_positive_sales_evidence")
    return {
        "product": product, "store": store,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "calendar_days": span, "recorded_days": len(rows),
        "known_sales_days": known_count, "zero_sales_days": zero_count,
        "positive_sales_days": known_count - zero_count,
        "missing_dates": missing, "unknown_sales_dates": unknown,
        "unknown_days": len(missing) + len(unknown),
        "unknown_ratio": (len(missing) + len(unknown)) / span,
        "continuous_ranges": ranges,
        "longest_continuous_days": max((part["days"] for part in ranges), default=0),
        "forecast_eligible": eligible,
        "recommended_history": complete and len(rows) >= RECOMMENDED_HISTORY_DAYS,
        # Price/cost missing counts refer to recorded rows, not invented gap rows.
        "price_missing_days": price_missing,
        "cost_missing_days": cost_missing,
        "price_coverage_ratio": (len(rows) - price_missing) / len(rows),
        "cost_coverage_ratio": (len(rows) - cost_missing) / len(rows),
        "last_price_reference": _last_reference(rows, "unit_price"),
        "last_cost_reference": _last_reference(rows, "unit_cost"),
        "warnings": warnings,
    }


def parse_business_csv(content, currency, *, sales_basis, as_of_date=None):
    """Parse bytes into sorted series and a JSON-safe audit report.

    Any hard validation error rejects the entire batch. Blank sales and absent
    dates are auditable unknowns, not hard format errors and never zero-filled.
    ``groups[(product, store)]`` uses date/Decimal objects; ``report`` uses ISO
    dates and decimal strings. The caller explicitly declares ``gross_units``;
    this parser cannot prove a positive input was not originally net of returns.
    """
    if not isinstance(currency, str) or currency not in SUPPORTED_CURRENCIES:
        _fail("invalid_currency", "Select AUD or USD explicitly.", field="currency")
    if sales_basis != "gross_units":
        _fail("unsupported_sales_basis", "Declare gross_units; net sales and returns are not supported.", field="sales_basis")
    if as_of_date is None:
        as_of_date = date.today()
    if type(as_of_date) is not date:
        _fail("invalid_as_of_date", "as_of_date must be a Python date.", field="as_of_date")
    if not isinstance(content, bytes):
        _fail("invalid_content_type", "CSV content must be UTF-8 bytes.")
    if len(content) > MAX_FILE_BYTES:
        _fail("file_too_large", "CSV exceeds the 5 MiB limit.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        _fail("invalid_encoding", "CSV must use UTF-8 or UTF-8 BOM encoding.")
    if "\x00" in text:
        _fail("invalid_csv", "NUL or binary content is not supported.")

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    columns = None
    groups, seen = {}, set()
    issues = _Issues()
    row_count = blank_lines = trimmed_identifiers = 0
    while True:
        line = reader.line_num + 1
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error:
            issues.add("invalid_csv", "CSV quoting, structure or field size is invalid.", line)
            break
        if _blank_line(cells):
            blank_lines += 1
            continue
        if columns is None:
            columns = _read_header(cells, line)
            continue
        row_count += 1
        if row_count > MAX_ROWS:
            issues.add("too_many_rows", "CSV exceeds 50,000 data rows.", line)
            break
        if len(cells) != len(columns):
            issues.add("column_count_mismatch", "CSV row has a different field count from its header.", line)
            continue
        before = issues.count
        for field, cell in zip(columns, cells):
            if len(cell) > MAX_FIELD_CHARS:
                issues.add("field_too_long", "CSV field exceeds 1,024 characters.", line, field)
        if issues.count != before:
            continue
        raw = dict(zip(columns, cells))
        checks = {
            "date": lambda value: _parse_date(value, as_of_date),
            "product": _parse_identifier, "store": _parse_identifier,
            "units_sold": _parse_units,
            "unit_price": _parse_amount, "unit_cost": _parse_amount,
        }
        values = {}
        for field, check in checks.items():
            value = raw.get(field, "")
            try:
                values[field] = check(value)
                if field in ("product", "store") and value != values[field]:
                    trimmed_identifiers += 1
            except _InvalidField as error:
                issues.add(error.code, str(error), line, field)
        if all(field in values for field in ("date", "product", "store")):
            key = (values["product"], values["store"])
            daily_key = key + (values["date"],)
            if daily_key in seen:
                issues.add("duplicate_record", "Product, Store and Date must identify one daily row.", line)
            seen.add(daily_key)
        if issues.count != before:
            continue
        if key not in groups and len(groups) >= MAX_SERIES:
            issues.add("too_many_series", "CSV exceeds 100 product-store combinations.", line)
            break
        groups.setdefault(key, []).append({
            "date": values["date"], "units_sold": values["units_sold"],
            "unit_price": values["unit_price"], "unit_cost": values["unit_cost"],
            "source_line": line,
        })

    if columns is None:
        issues.add("empty_file", "CSV has no header or observations.")
    elif row_count == 0:
        issues.add("no_observations", "CSV has a header but no observations.")
    issues.raise_if_any()
    for rows in groups.values():
        rows.sort(key=lambda row: row["date"])
        if (rows[-1]["date"] - rows[0]["date"]).days + 1 > MAX_SPAN_DAYS:
            issues.add("date_span_exceeded", "A series exceeds the 1,096-day calendar span limit.",
                       rows[-1]["source_line"], "date")
    # Never expand a potentially enormous date range before enforcing the cap.
    issues.raise_if_any()
    reports = [_series_report(product, store, rows)
               for (product, store), rows in sorted(groups.items())]
    report = {
        "source_kind": "user_csv", "source_verified": False,
        "currency": currency, "sales_basis": sales_basis,
        "as_of_date": as_of_date.isoformat(),
        "minimum_history_days": MIN_HISTORY_DAYS,
        "recommended_history_days": RECOMMENDED_HISTORY_DAYS,
        "missing_date_policy": "unknown; no automatic zero filling",
        "summary": {
            "series_count": len(groups), "product_count": len({key[0] for key in groups}),
            "store_count": len({key[1] for key in groups}), "row_count": row_count,
            "eligible_series_count": sum(part["forecast_eligible"] for part in reports),
            "series_with_eligible_range_count": sum(part["longest_continuous_days"] >= MIN_HISTORY_DAYS
                                                    for part in reports),
            "blank_lines_skipped": blank_lines,
            "trimmed_identifier_count": trimmed_identifiers,
        },
        "series": reports,
    }
    return {
        "schema_version": 1, "source_kind": "user_csv", "source_verified": False,
        "currency": currency, "sales_basis": sales_basis, "as_of_date": as_of_date,
        "groups": groups, "report": report,
    }


def load_business_csv(path, currency, *, sales_basis, as_of_date=None):
    """Read a caller-chosen local CSV with a bounded read; never write files."""
    try:
        path = Path(path)
    except TypeError:
        _fail("invalid_path", "Provide a local CSV file path.")
    if path.suffix.lower() != ".csv":
        _fail("unsupported_file_type", "Only local .csv files are supported.")
    try:
        with path.open("rb") as handle:
            content = handle.read(MAX_FILE_BYTES + 1)
    except (OSError, ValueError):
        _fail("file_unavailable", "The local CSV file could not be read.")
    return parse_business_csv(content, currency, sales_basis=sales_basis, as_of_date=as_of_date)
