"""Bounded inventory snapshots, separate from sales and financial calculations.

A snapshot is closing stock on Stock As Of Date. It is not a transaction history,
a record of receipts, or evidence that on-order units have arrived. Blank cells
remain unknown. The batch adapter checks each snapshot against the explicitly
selected sales-history end date before calling the unchanged inventory engine.
"""
import csv
import io
import re
import unicodedata
from datetime import date

from business_csv import BusinessCSVError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 100
MAX_FIELD_CHARS = 1024
MAX_UNITS = 1000000
REQUIRED_FIELDS = ('product', 'store', 'stock_as_of_date', 'current_stock',
                   'lead_time_days', 'safety_stock')
OPTIONAL_FIELDS = ('on_order_units',)
FIELD_ALIASES = {
    'product': 'product', 'store': 'store',
    'stock as of date': 'stock_as_of_date', 'stock_as_of_date': 'stock_as_of_date',
    'current stock': 'current_stock', 'current_stock': 'current_stock',
    'supplier lead time': 'lead_time_days', 'supplier delivery time': 'lead_time_days',
    'lead_time_days': 'lead_time_days',
    'safety stock': 'safety_stock', 'backup stock': 'safety_stock',
    'safety_stock': 'safety_stock',
    'on-order units': 'on_order_units', 'on order units': 'on_order_units',
    'on_order_units': 'on_order_units',
}
FIELD_LABELS = {
    'product': 'Product', 'store': 'Store', 'stock_as_of_date': 'Stock As Of Date',
    'current_stock': 'Current Stock', 'lead_time_days': 'Supplier Delivery Time',
    'safety_stock': 'Backup Stock', 'on_order_units': 'On-order Units',
}


class InventoryCSVError(BusinessCSVError):
    """Use the existing bounded, safe CSV error contract."""


def _issue(code, message, line=None, field=None):
    return dict(code=code, message=message, line=line, field=field)


def _fail(code, message, line=None, field=None):
    raise InventoryCSVError([_issue(code, message, line, field)]) from None


def _blank(cells):
    return not cells or (len(cells) == 1 and not cells[0].strip())


def _value(value, field, as_of_date, line):
    cleaned = value.strip()
    if not cleaned:
        return None
    if field in ('product', 'store'):
        if len(cleaned) > 80:
            _fail('identifier_too_long', 'Use a Product and Store identifier of at most 80 characters.', line, field)
        if any(unicodedata.category(char).startswith('C') for char in value) or cleaned[0] in '=+-@':
            _fail('invalid_identifier', 'Remove control characters and spreadsheet formula prefixes from the identifier.', line, field)
        return cleaned
    if field == 'stock_as_of_date':
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', cleaned):
            _fail('invalid_date', 'Stock As Of Date must use YYYY-MM-DD.', line, field)
        try:
            day = date.fromisoformat(cleaned)
        except ValueError:
            _fail('invalid_date', 'Enter a valid calendar date for Stock As Of Date.', line, field)
        if day >= as_of_date:
            _fail('incomplete_or_future_date', 'Stock As Of Date must be before the declared as-of date, on a completed business day.', line, field)
        return day.isoformat()
    if not re.fullmatch(r'[0-9]+', cleaned):
        _fail('invalid_units', FIELD_LABELS[field] + ' must be a nonnegative whole-number literal; do not use decimals, negative quantities or exponents.', line, field)
    maximum = 365 if field == 'lead_time_days' else MAX_UNITS
    # Bound the literal before integer conversion (also accepts harmless leading zeros).
    significant = cleaned.lstrip('0') or '0'
    if len(significant) > len(str(maximum)) or int(significant) > maximum:
        _fail('units_out_of_range', FIELD_LABELS[field] + ' must not exceed ' + str(maximum) + '.', line, field)
    return int(significant)


def parse_inventory_csv(content: bytes, *, as_of_date: date, max_rows=20):
    """Parse UTF-8/BOM inventory bytes, retaining incomplete rows for review.

    Unsupported/duplicate headers, duplicate product-store snapshots, invalid
    nonblank cells and limits reject the file. Missing cells are issues, not
    invented zeros. Only an explicit downstream assumption may replace a missing
    On-order Units value. The caller supplies the first incomplete business date.
    """
    if type(as_of_date) is not date:
        _fail('invalid_as_of_date', 'Supply a date for the first incomplete business day.')
    if type(max_rows) is not int or not 1 <= max_rows <= MAX_ROWS:
        _fail('invalid_limit', 'The inventory row limit must be a whole number from 1 to 100.')
    if not isinstance(content, bytes):
        _fail('invalid_content', 'Upload CSV bytes encoded as UTF-8.')
    if len(content) > MAX_FILE_BYTES:
        _fail('file_too_large', 'The inventory CSV exceeds the permitted file size.')
    try:
        decoded = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        _fail('invalid_encoding', 'Save the inventory CSV as UTF-8 or UTF-8 with BOM.')
    if '\x00' in decoded:
        _fail('invalid_csv', 'Remove NUL characters from the CSV.')
    reader = csv.reader(io.StringIO(decoded, newline=''), strict=True)
    header = None
    rows, issues, seen = [], [], set()
    missing_counts = {field: 0 for field in REQUIRED_FIELDS + OPTIONAL_FIELDS}
    try:
        for cells in reader:
            line = reader.line_num
            if _blank(cells):
                continue
            if any(len(cell) > MAX_FIELD_CHARS for cell in cells):
                _fail('field_too_long', 'Each inventory CSV field must be at most 1,024 characters.', line)
            if header is None:
                if len(cells) > len(REQUIRED_FIELDS + OPTIONAL_FIELDS):
                    _fail('too_many_columns', 'Use only the six required inventory columns and optional On-order Units.', line)
                header = []
                for cell in cells:
                    field = FIELD_ALIASES.get(cell.strip().lower())
                    if field is None:
                        _fail('unknown_column', 'Remove unsupported or empty inventory column headings.', line)
                    if field in header:
                        _fail('duplicate_column', 'Use only one column for each inventory field.', line, field)
                    header.append(field)
                missing = [field for field in REQUIRED_FIELDS if field not in header]
                if missing:
                    _fail('missing_column', 'Add every required inventory column, including ' + FIELD_LABELS[missing[0]] + '.', line, missing[0])
                continue
            if len(rows) >= max_rows:
                _fail('too_many_rows', 'The inventory CSV exceeds the permitted number of product-store snapshots.', line)
            if len(cells) != len(header):
                _fail('column_count', 'Use the same number of fields as the inventory header on every row.', line)
            raw = dict(zip(header, cells))
            row = {field: _value(raw.get(field, ''), field, as_of_date, line)
                   for field in REQUIRED_FIELDS + OPTIONAL_FIELDS}
            key = row['product'], row['store']
            if None not in key:
                if key in seen:
                    _fail('duplicate_record', 'Keep exactly one stock snapshot for each Product and Store; choose its date explicitly.', line)
                seen.add(key)
            for field, value in row.items():
                if value is None:
                    missing_counts[field] += 1
                    entry = _issue('missing_value', FIELD_LABELS[field] + ' is unknown; supply it before assessment or explicitly declare no on-order units where applicable.', line, field)
                    entry['row_index'] = len(rows)
                    issues.append(entry)
            rows.append(row)
    except csv.Error:
        _fail('invalid_csv', 'Check CSV quoting and delimiters; the file must be comma-separated.', reader.line_num)
    if header is None or not rows:
        _fail('empty_csv', 'Add at least one inventory snapshot below the required headings.')
    return {
        'rows': rows,
        'report': {
            'row_count': len(rows), 'max_rows': max_rows,
            'complete_rows': sum(all(value is not None for value in row.values()) for row in rows),
            'incomplete_rows': sum(any(value is None for value in row.values()) for row in rows),
            'missing_values': missing_counts, 'issues': issues,
            'as_of_date': as_of_date.isoformat(),
            'source': 'User-provided inventory snapshots and planning assumptions; not independently verified.',
            'snapshot_rule': 'Closing stock must match the last day of the explicitly selected sales history.',
            'on_order_policy': 'Missing on-order quantities remain unknown unless the user explicitly declares none. On-order units are not current stock.',
        },
    }
