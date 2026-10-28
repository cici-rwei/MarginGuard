"""Stateless public demo using one bundled, explicitly synthetic CSV.

This adapter never reads a client-selected file or stores submitted assumptions.
Forecasting, inventory and financial calculations remain in the existing engines.
The bundled fixture is intentionally repetitive; its MAE is not evidence about
real trading performance. AUD is an explicit demo assumption, with no conversion.
"""
import hashlib
import json
import re
from copy import deepcopy
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from business_csv import parse_business_csv
from business_forecast import analyse_business_series
from inventory import inventory_risk
from phase2_inputs import units
from scenario import compare_strategies

SAMPLE_FILE = Path(__file__).resolve().parent / 'examples/business_csv/synthetic_84_days.csv'
ITEM_ID = 'SYNTHETIC_SKU_001'
STORE_ID = 'SYNTHETIC_STORE_A'
DATASET_ID = 'synthetic-84-day-demo'
CURRENCY = 'AUD'
SOURCE_LABEL = 'Synthetic demonstration data · Not real business transactions'
MAX_BODY_BYTES = 16384
INVENTORY_FIELDS = ('current_stock', 'lead_time_days', 'safety_stock',
                    'on_order_units', 'excess_cover_days')
SCENARIO_FIELDS = ('current_stock', 'selling_price', 'existing_unit_cost',
                   'cash_budget', 'order_quantity', 'unit_purchase_cost',
                   'freight', 'other_costs', 'moq', 'lead_time_days',
                   'discount_percent', 'demand_uplift_percent')
# These are independent demo assumptions, never loaded from M5 defaults.
DEFAULTS = {
    'current_stock': 30, 'lead_time_days': 3, 'safety_stock': 10,
    'on_order_units': 0, 'excess_cover_days': 30, 'selling_price': '14.50',
    'existing_unit_cost': '8.20', 'unit_purchase_cost': '7.50',
    'order_quantity': 60, 'freight': '12', 'other_costs': '0', 'moq': 20,
    'cash_budget': '500', 'discount_percent': 10,
    'demand_uplift_percent': 20, 'max_unmet_units': None,
}


class DemoError(ValueError):
    def __init__(self, message, code='invalid_input', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def serial(value):
    if isinstance(value, (Decimal, date)):
        return str(value)
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    return value


@lru_cache(maxsize=1)
def _trusted_analysis():
    """Parse the small, fixed deployment asset once per worker, not per request."""
    try:
        content = SAMPLE_FILE.read_bytes()
        dataset = parse_business_csv(content, CURRENCY, sales_basis='gross_units',
                                     as_of_date=date(2024, 3, 25))
        if set(dataset['groups']) != {(ITEM_ID, STORE_ID)}:
            raise ValueError('Unexpected bundled series.')
        adapted = analyse_business_series(dataset, ITEM_ID, STORE_ID)
        if len(adapted['history']) != 84:
            raise ValueError('Unexpected bundled history length.')
        result = adapted['analysis']
        revision_material = content + json.dumps(DEFAULTS, sort_keys=True).encode('utf-8') + b'|AUD|synthetic-demo-v1'
        revision = hashlib.sha256(revision_material).hexdigest()[:24]
        context = {'source_kind': 'synthetic_demo', 'dataset_id': DATASET_ID,
                   'revision': revision, 'series_id': ITEM_ID + '/' + STORE_ID,
                   'forecast_origin': result['history_end'], 'currency': CURRENCY}
        forecast = [row['prediction'] for row in result['future']]
        risk = inventory_risk(ITEM_ID, forecast, **{k: DEFAULTS[k] for k in INVENTORY_FIELDS})
        history = [{'date': row['date'], 'units': row['units_sold']} for row in adapted['history']]
        historical_units = sum(row['units'] for row in history)
        references = deepcopy(adapted['references'])
        for reference in references.values():
            if reference:
                reference['source'] = 'Bundled synthetic reference; AUD is an explicit demo assumption.'
        return {'item_id': ITEM_ID, 'store_id': STORE_ID, 'context': context,
                'source_kind': 'synthetic_demo', 'source_label': SOURCE_LABEL,
                'is_synthetic': True, 'currency': CURRENCY,
                'history': history, 'historical_units': historical_units,
                'analysis': result, 'defaults': deepcopy(DEFAULTS),
                'inventory': risk, 'quality': adapted['quality'],
                'overview': [{'item_id': ITEM_ID, 'store_id': STORE_ID,
                              'category': 'Synthetic demonstration',
                              'historical_units': historical_units,
                              'forecast_total': result['total_forecast_demand'],
                              'method': result['selected_method'],
                              'mae': result['backtest'][result['selected_method']]['mae']}],
                'price_reference': references['unit_price'],
                'cost_reference': references['unit_cost'],
                'price_date': references['unit_price']['date'],
                'price': references['unit_price']['value'],
                'assumptions_notice': 'All stock, prices, costs, lead times and strategy inputs are synthetic demonstration assumptions in AUD. No currency conversion.',
                'limitations': 'Synthetic 84-day repeating history. Forecast dates are a historical simulation; a low MAE is not evidence of real-world accuracy.'}
    except (OSError, ValueError, KeyError, TypeError):
        raise DemoError('The bundled synthetic demo is unavailable. Please try again later.',
                        'demo_unavailable', 503) from None


def _unknown_fields(params, allowed):
    if set(params) - set(allowed):
        raise DemoError('Unsupported request fields.')


def _query(allowed):
    if any(len(request.args.getlist(key)) != 1 for key in request.args):
        raise DemoError('Repeated query parameters are not supported.')
    _unknown_fields(request.args, allowed)
    return request.args


def _select(params, require_revision=False):
    if params.get('item_id') != ITEM_ID or params.get('store_id') != STORE_ID:
        raise DemoError('Select the bundled synthetic product and store.', 'unknown_series')
    selected = _trusted_analysis()
    if require_revision and params.get('revision') != selected['context']['revision']:
        raise DemoError('The demo version changed. Reload the page before calculating.', 'revision_conflict', 409)
    return selected


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DemoError('Repeated JSON fields are not supported.')
        result[key] = value
    return result


def _body(required, optional=()):
    if not request.is_json:
        raise DemoError('Submit a JSON object.', 'invalid_content_type', 415)
    if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
        raise DemoError('The demo request exceeds 16 KiB.', 'request_too_large', 413)
    # Bounded stream read also covers requests without a Content-Length header.
    raw = request.stream.read(MAX_BODY_BYTES + 1)
    if len(raw) > MAX_BODY_BYTES:
        raise DemoError('The demo request exceeds 16 KiB.', 'request_too_large', 413)
    try:
        params = json.loads(raw, object_pairs_hook=_unique_object,
                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise DemoError('Submit a valid JSON object with unique fields and finite values.') from None
    if not isinstance(params, dict):
        raise DemoError('Submit a JSON object.')
    identity = ('item_id', 'store_id', 'revision', 'currency')
    metadata = ('hypothetical_stock_at_origin', 'stock_as_of')
    _unknown_fields(params, identity + metadata + tuple(required) + tuple(optional))
    if any(key not in params or params[key] is None or params[key] == '' for key in identity + tuple(required)):
        raise DemoError('Supply all required identity and calculation inputs.')
    if params['currency'] != CURRENCY:
        raise DemoError('The synthetic demo uses explicitly assumed AUD. Currency conversion is not supported.', 'currency_mismatch')
    for key in required + tuple(optional):
        value = params.get(key)
        if key == 'acknowledge_excluded_on_order':
            if value is not None and type(value) is not bool:
                raise DemoError('The on-order acknowledgement must be true or false.')
        elif value is not None:
            if key == 'max_unmet_units' and value == '':
                continue
            # The public adapter bounds precision before Decimal arithmetic.
            # Exponents such as 1e-999999 can otherwise overflow margin division
            # despite being finite and below the core engine's upper bound.
            if (type(value) not in (str, int, float) or len(str(value)) > 32
                    or re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]{1,6})?', str(value)) is None):
                raise DemoError('Use ordinary numeric values with at most six decimal places; scientific notation is unsupported in this demo.')
    if params.get('hypothetical_stock_at_origin', True) is not True:
        raise DemoError('This demo requires hypothetical stock at the historical forecast origin.')
    selected = _select(params, require_revision=True)
    if params.get('stock_as_of') not in (None, '', str(selected['context']['forecast_origin'])):
        raise DemoError('Demo stock assumptions refer to the historical forecast origin.')
    return params, selected


def _metadata(result, selected):
    result.update(source_kind='synthetic_demo', source_label=SOURCE_LABEL,
                  is_synthetic=True, currency=CURRENCY, context=deepcopy(selected['context']))
    return result


def create_synthetic_blueprint():
    bp = Blueprint('synthetic_demo', __name__, url_prefix='/api/demo')

    @bp.before_request
    def gate():
        if not current_app.config.get('ENABLE_SYNTHETIC_DEMO', False):
            raise DemoError('Synthetic demonstration mode is disabled.', 'demo_disabled', 503)
        if request.method == 'POST':
            origin = request.headers.get('Origin')
            if (origin is not None and origin.rstrip('/') != request.host_url.rstrip('/')) or request.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise DemoError('Use this demo from the same website.', 'cross_origin', 403)

    @bp.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'no-store'
        return response

    @bp.errorhandler(DemoError)
    def demo_error(error):
        return jsonify(error=str(error), code=error.code), error.status

    @bp.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error), code='invalid_input'), 400

    @bp.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error='The demo request could not be processed.', code='invalid_request'), error.code

    @bp.get('/catalog')
    def catalog():
        _query(())
        selected = _trusted_analysis()
        return jsonify(source_kind='synthetic_demo', source_label=SOURCE_LABEL,
                       currency=CURRENCY, dataset_id=DATASET_ID,
                       revision=selected['context']['revision'],
                       series=[{'item_id': ITEM_ID, 'store_id': STORE_ID,
                                'series_id': ITEM_ID + '/' + STORE_ID,
                                'category': 'Synthetic demonstration'}])

    @bp.get('/analysis')
    def analysis():
        selected = _select(_query(('item_id', 'store_id')))
        return jsonify(serial(selected))

    @bp.post('/inventory')
    def inventory():
        params, selected = _body(INVENTORY_FIELDS)
        demand = [row['prediction'] for row in selected['analysis']['future']]
        result = inventory_risk(ITEM_ID, demand, **{key: params[key] for key in INVENTORY_FIELDS})
        return jsonify(serial(_metadata(result, selected)))

    @bp.post('/scenarios')
    def scenarios():
        params, selected = _body(SCENARIO_FIELDS, ('max_unmet_units', 'on_order_units', 'acknowledge_excluded_on_order'))
        on_order = units(params.get('on_order_units', 0), 'on_order_units')
        if on_order and params.get('acknowledge_excluded_on_order') is not True:
            raise DemoError('Existing on-order units are unsupported in scenarios. Explicitly acknowledge a separate scenario excluding them.')
        inputs = {key: params[key] for key in SCENARIO_FIELDS}
        inputs['max_unmet_units'] = None if params.get('max_unmet_units') in (None, '') else params['max_unmet_units']
        demand = [row['prediction'] for row in selected['analysis']['future']]
        result = compare_strategies(demand, **inputs, currency=CURRENCY)
        result['excluded_on_order_units'] = on_order
        if on_order:
            result['limitations'] += ' Existing on-order units are explicitly excluded from this separate scenario.'
        return jsonify(serial(_metadata(result, selected)))

    return bp
