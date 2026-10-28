"""Adapt validated business CSV histories to the unchanged Phase 1 engine.

No web, storage, inventory or finance actions happen here. Currency is metadata;
preserving AUD does not make the existing USD finance engine AUD-compatible.
"""
import re
from datetime import date, timedelta

import forecast
from business_csv import (
    MIN_HISTORY_DAYS, RECOMMENDED_HISTORY_DAYS, SUPPORTED_CURRENCIES,
)


class BusinessForecastError(ValueError):
    """An unusable selection, with a stable code for a future interface."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _date_bound(value):
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise BusinessForecastError('invalid_range', 'Use YYYY-MM-DD dates for both range boundaries.')


def _history(dataset, product, store):
    if not isinstance(dataset, dict) or dataset.get('source_kind') != 'user_csv':
        raise BusinessForecastError('invalid_dataset', 'Use a validated business CSV dataset.')
    if dataset.get('currency') not in SUPPORTED_CURRENCIES:
        raise BusinessForecastError('invalid_currency', 'The dataset currency must be AUD or USD.')
    if dataset.get('sales_basis') != 'gross_units':
        raise BusinessForecastError('invalid_sales_basis', 'Only gross sold units are supported; returns are separate.')
    if not isinstance(product, str) or not isinstance(store, str):
        raise BusinessForecastError('invalid_selection', 'Select an exact product and store from the dataset.')
    groups = dataset.get('groups')
    if not isinstance(groups, dict) or (product, store) not in groups:
        raise BusinessForecastError('unknown_series', 'The selected product-store series is not in this dataset.')
    rows = groups[(product, store)]
    if not isinstance(rows, list) or not rows:
        raise BusinessForecastError('invalid_dataset', 'The selected series has no validated records.')
    previous = None
    for row in rows:
        if not isinstance(row, dict) or type(row.get('date')) is not date:
            raise BusinessForecastError('invalid_dataset', 'History must contain validated calendar dates.')
        if previous is not None and row['date'] <= previous:
            raise BusinessForecastError('invalid_dataset', 'History must have sorted, unique dates.')
        previous = row['date']
    return rows


def _reference(rows, field):
    for row in reversed(rows):
        if row.get(field) is not None:
            return {'date': row['date'], 'value': row[field],
                    'source': 'User-provided historical reference; not independently verified.'}
    return None


def analyse_business_series(dataset, product, store, *, start_date=None, end_date=None):
    """Analyse one complete series, or an explicitly selected continuous window.

    Missing days/unknown sales are never filled or silently removed. Both range
    boundaries must be supplied together and must be observed dates. The caller
    can review ``dataset['report']`` before choosing a window. Output keeps the
    engine's Python dates and numerical values without rounding or relabelling.
    """
    original = _history(dataset, product, store)
    explicit = start_date is not None or end_date is not None
    if explicit:
        if start_date is None or end_date is None:
            raise BusinessForecastError('invalid_range', 'Supply both start_date and end_date.')
        start, end = _date_bound(start_date), _date_bound(end_date)
        observed_dates = {row['date'] for row in original}
        if start > end or start not in observed_dates or end not in observed_dates:
            raise BusinessForecastError('invalid_range', 'Choose ordered boundaries present in the selected series.')
        selected = [row for row in original if start <= row['date'] <= end]
    else:
        selected = original

    # Do not send None, fractional units or a fabricated zero to forecast.py.
    rows = []
    for row in selected:
        units = row.get('units_sold')
        if units is None:
            raise BusinessForecastError('unknown_sales', 'Unknown daily sales remain unknown; choose a complete window.')
        if type(units) is not int or not 0 <= units <= 1000000:
            raise BusinessForecastError('invalid_units', 'Daily sales must be validated nonnegative whole units.')
        if rows and row['date'] != rows[-1]['date'] + timedelta(days=1):
            raise BusinessForecastError('missing_dates', 'The selected history has missing dates; no zero filling is applied.')
        rows.append({'date': row['date'], 'units_sold': units})
    if len(rows) < MIN_HISTORY_DAYS:
        raise BusinessForecastError('insufficient_history',
                                    'At least 42 consecutive known daily observations are required (28 training + 14 validation).')
    if rows[-1]['date'] > date.max - timedelta(days=14):
        raise BusinessForecastError('date_out_of_range', 'The 14-day forecast would exceed supported calendar dates.')

    # Preserve the original method comparison, exact-tie preference and refit.
    analysis = forecast.analyse(rows)
    zero_days = sum(row['units_sold'] == 0 for row in rows)
    warnings = []
    if len(rows) < RECOMMENDED_HISTORY_DAYS:
        warnings.append({'code': 'short_history',
                         'message': '42 days meet the minimum; at least 84 days are recommended, not a reliability guarantee.'})
    if zero_days == len(rows):
        warnings.append({'code': 'all_zero_sales',
                         'message': 'No positive sales are observed. A zero MAE is not evidence of high forecasting confidence.'})
    excluded = len(original) - len(rows)
    if excluded:
        warnings.append({'code': 'explicit_history_window',
                         'message': 'Only the explicitly selected history is analysed; other records are excluded.'})
    if rows[-1]['date'] != original[-1]['date']:
        warnings.append({'code': 'historical_simulation',
                         'message': 'This window ends before the last uploaded record; its future dates are a historical simulation.'})

    return {
        'source_kind': 'user_csv',
        'source_verified': False,
        'currency': dataset['currency'],
        'sales_basis': dataset['sales_basis'],
        'product': product,
        'store': store,
        'history': rows,
        'quality': {
            'observations': len(rows),
            'recommended_history': len(rows) >= RECOMMENDED_HISTORY_DAYS,
            'zero_sales_days': zero_days,
            'positive_sales_days': len(rows) - zero_days,
            'excluded_record_count': excluded,
            'range_explicit': explicit,
            'warnings': warnings,
        },
        'references': {'unit_price': _reference(selected, 'unit_price'),
                       'unit_cost': _reference(selected, 'unit_cost')},
        'analysis': analysis,
        'forecast_start': analysis['future'][0]['date'],
        'forecast_end': analysis['future'][-1]['date'],
        'financial_analysis_available': False,
        'financial_status': 'Phase 5A provides forecasts and currency metadata only.',
    }
