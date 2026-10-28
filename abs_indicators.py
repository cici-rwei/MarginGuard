"""Transparent ABS calculations, independent of product demand and finance engines.

Values stay in their published units unless the caller explicitly converts them.
Missing observations are None, never zero. Percentage growth is unavailable when
the previous observation is missing, zero or negative; negative profit bases
otherwise produce percentages that are easy to misinterpret.
"""
import math
import re
from decimal import Decimal
from numbers import Real


_MONEY_SCALES = {'AUD': 1, 'AUD million': 1_000_000, 'AUD billion': 1_000_000_000}
_UNITS = set(_MONEY_SCALES) | {'percent', 'ratio', 'businesses'}
_FREQUENCIES = {'monthly': (12, r'(\d{4})-(0[1-9]|1[0-2])'),
                'quarterly': (4, r'(\d{4})-Q([1-4])')}


def _number(value):
    """Accept finite numeric observations while preserving missing values."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        raise ValueError('ABS values must be numbers or None.')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('ABS values must be finite; use None for missing data.')
    return result


def _validated_values(periods, values, frequency):
    if frequency not in _FREQUENCIES:
        raise ValueError('Frequency must be monthly or quarterly.')
    if not isinstance(periods, (list, tuple)) or not isinstance(values, (list, tuple)):
        raise ValueError('Periods and values must be lists or tuples.')
    if len(periods) != len(values):
        raise ValueError('Periods and values must have the same length.')
    steps, pattern = _FREQUENCIES[frequency]
    previous = None
    for period in periods:
        match = re.fullmatch(pattern, period) if isinstance(period, str) else None
        if match is None or int(match[1]) == 0:
            raise ValueError('Invalid %s period: %r.' % (frequency, period))
        position = int(match[1]) * steps + int(match[2]) - 1
        if previous is not None and position != previous + 1:
            raise ValueError('Periods must be unique, chronological and consecutive; '
                             'retain missing periods with None values.')
        previous = position
    return [_number(value) for value in values]


def _growth(current, previous):
    if current is None or previous is None or previous <= 0:
        return None
    result = (current / previous - 1) * 100
    if not math.isfinite(result):
        raise ValueError('Growth result exceeds the supported numeric range.')
    return result


def growth_rates(periods, values, frequency):
    """Return period and annual percentage changes on one consistent series.

    Monthly: previous month and the same month one year earlier.
    Quarterly: previous quarter and the same quarter one year earlier.
    The function does not interpolate, annualise quarterly growth, seasonally
    adjust a series, or change its current-price/volume basis. Apply it to level
    values, not to ABS-published percentage-growth or ratio series.
    """
    numbers = _validated_values(periods, values, frequency)
    year_lag = _FREQUENCIES[frequency][0]
    return {
        'period_change_pct': [None if n == 0 else _growth(value, numbers[n - 1])
                              for n, value in enumerate(numbers)],
        'year_change_pct': [None if n < year_lag else _growth(value, numbers[n - year_lag])
                            for n, value in enumerate(numbers)],
    }


def convert_value(value, from_unit, to_unit):
    """Explicit AUD magnitude conversion; ratios and percentages stay distinct.

    Conversion changes the magnitude label only. It is not a currency exchange,
    a deflator, an annualisation or an adjustment of the statistical basis.
    """
    if from_unit not in _UNITS or to_unit not in _UNITS:
        raise ValueError('Unsupported ABS unit.')
    if from_unit != to_unit and not (from_unit in _MONEY_SCALES and to_unit in _MONEY_SCALES):
        raise ValueError('Only AUD magnitude conversions are supported.')
    number = _number(value)
    if number is None or from_unit == to_unit:
        return number
    result = number * (_MONEY_SCALES[from_unit] / _MONEY_SCALES[to_unit])
    if not math.isfinite(result):
        raise ValueError('Converted value exceeds the supported numeric range.')
    return result


def _check_series(series, table, measure, observation_type, unit=None):
    expected = {'dataset_id': 'abs_business_indicators', 'frequency': 'quarterly',
                'adjustment': 'Original', 'price_basis': 'current_prices',
                'classification': 'ANZSIC', 'measure': measure,
                'observation_type': observation_type,
                'business_scope': 'TOTAL (SCP_SCOPE)'}
    if not isinstance(series, dict):
        raise ValueError('Expected an ABS series dictionary.')
    for field, wanted in expected.items():
        if series.get(field) != wanted:
            raise ValueError('Expected %s=%r for the official inventory/sales comparison.'
                             % (field, wanted))
    if table not in series.get('table_ids', []):
        raise ValueError('Expected ABS Business Indicators Table %d.' % table)
    if not series.get('category') or not series.get('geography'):
        raise ValueError('Category and geography must be explicit.')
    if unit is not None and series.get('unit') != unit:
        raise ValueError('Expected unit %r.' % unit)
    if unit is None and series.get('unit') not in _MONEY_SCALES:
        raise ValueError('Inventory and sales components require an AUD amount unit.')
    return _validated_values(series.get('periods'), series.get('values'), 'quarterly')


def official_inventory_sales_ratio(series):
    """Read published Table 23 values without replacing them with a calculation.

    This stock-at-quarter-end / quarterly-sales ratio is not inventory days,
    days of cover, a COGS turnover ratio or a product-level risk score.
    """
    values = _check_series(series, 23, 'inventory_to_sales_ratio', 'RATIO', 'ratio')
    return [{'period': period, 'value': value}
            for period, value in zip(series['periods'], values)]


def validate_ratio_against_components(ratio_series, inventory_series, sales_series):
    """Audit the official ratio against compatible current-price components.

    Only common periods are checked, because ABS tables begin at different
    dates. Official ratios have two decimal places; tolerance is 0.005 plus a
    small floating-point allowance. Missing or nonpositive-sales periods are
    reported separately and never imputed. Official values remain authoritative.
    """
    published = official_inventory_sales_ratio(ratio_series)
    inventories = _check_series(inventory_series, 3, 'inventories', 'STOCK_CLOSE')
    sales = _check_series(sales_series, 6, 'business_sales', 'FLOW')
    release = ratio_series.get('source', {}).get('release_date')
    if not release:
        raise ValueError('A release date is required for a revision-consistent audit.')
    for other in (inventory_series, sales_series):
        if any(other.get(field) != ratio_series.get(field)
               for field in ('category', 'geography')):
            raise ValueError('Inventory, sales and ratio must cover the same category/geography.')
        if other.get('source', {}).get('release_date') != release:
            raise ValueError('Inventory, sales and ratio must use the same release vintage.')
    inv = {period: convert_value(value, inventory_series['unit'], 'AUD million')
           for period, value in zip(inventory_series['periods'], inventories)}
    sale = {period: convert_value(value, sales_series['unit'], 'AUD million')
            for period, value in zip(sales_series['periods'], sales)}
    common = [row for row in published if row['period'] in inv and row['period'] in sale]
    if not common:
        raise ValueError('No common quarterly observations to compare.')
    checked = missing = undefined = 0
    differences, mismatches = [], []
    for row in common:
        period, official = row['period'], row['value']
        stock, revenue = inv[period], sale[period]
        if official is None or stock is None or revenue is None:
            missing += 1
            continue
        if revenue <= 0:
            undefined += 1
            continue
        calculated = stock / revenue
        difference = abs(calculated - official)
        differences.append(difference)
        checked += 1
        if difference > 0.005000001:
            mismatches.append({'period': period, 'official': official,
                               'calculated': calculated, 'absolute_difference': difference})
    return {'common_periods': len(common), 'checked_periods': checked,
            'missing_periods': missing, 'nonpositive_sales_periods': undefined,
            'max_absolute_difference': max(differences) if differences else None,
            'mismatches': mismatches, 'consistent': checked > 0 and not mismatches}
