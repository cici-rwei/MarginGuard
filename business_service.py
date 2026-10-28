"""Server-only data selection and bounded calls to the existing Python engines."""
import base64
from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from business_store import BusinessError
from phase2_inputs import units

ROOT = Path(__file__).resolve().parent
INVENTORY_FIELDS = ('current_stock', 'lead_time_days', 'safety_stock', 'on_order_units', 'excess_cover_days')
SCENARIO_FIELDS = ('current_stock', 'selling_price', 'existing_unit_cost', 'cash_budget',
                   'order_quantity', 'unit_purchase_cost', 'freight', 'other_costs', 'moq',
                   'lead_time_days', 'discount_percent', 'demand_uplift_percent')


def checked_fields(parameters, required, optional=()):
    if not isinstance(parameters, dict):
        raise BusinessError('invalid_parameters', 'Submit a JSON object.')
    if set(parameters) - set(required) - set(optional):
        raise BusinessError('unknown_parameter', 'An unsupported parameter was supplied.')
    if any(key not in parameters or parameters[key] in ('', None) for key in required):
        raise BusinessError('missing_parameter', 'Provide every required field explicitly; missing values are not zero.')
    return parameters


@contextmanager
def processing_slot(store, owner, timeout):
    # Keep one shared lease while the parent encodes, receives and persists the
    # result too. The expiry recovers capacity after a crashed request process;
    # it exceeds the 20-second Gunicorn request timeout and child CPU deadline.
    job = store.acquire_job(owner, max(timeout + 25, 30))
    try:
        yield job
    finally:
        store.release_job(job)


def run_worker(store, owner, action, payload, timeout=5, job_id=None):
    owns_job = job_id is None
    job = store.acquire_job(owner, max(timeout + 25, 30)) if owns_job else job_id
    process = None
    try:
        limits = {'max_rows': store.max_rows, 'max_series': store.max_series,
                  'max_dataset_bytes': store.max_dataset_bytes}
        encoded = json.dumps({'action': action, 'payload': payload, 'limits': limits},
                             allow_nan=False).encode('utf-8')
        process = subprocess.Popen([sys.executable, str(ROOT / 'business_worker.py')],
                                   cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, start_new_session=True,
                                   env={'PYTHONDONTWRITEBYTECODE': '1',
                                        'MARGINGUARD_WORKER_MEMORY_BYTES': str(store.worker_memory_bytes),
                                        'MARGINGUARD_WORKER_MAX_OUTPUT_BYTES': str(store.max_worker_output_bytes)})
        try:
            output, _ = process.communicate(encoded, timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise BusinessError('processing_timeout', 'Processing exceeded its time limit. Try a smaller dataset.', 503) from None
        if process.returncode or len(output) > store.max_worker_output_bytes:
            raise BusinessError('processing_failed', 'Private processing was stopped or exceeded its limit.', 503)
        try:
            result = json.loads(output)
        except (ValueError, UnicodeError):
            raise BusinessError('processing_failed', 'Private processing returned an invalid response.', 503) from None
        if not result.get('ok'):
            raise BusinessError(result.get('code', 'processing_failed'), result.get('error', 'Processing failed.'),
                                result.get('status', 503), result.get('issues'))
        store.authenticate(owner, touch=False)
        return result['result']
    except OSError:
        raise BusinessError('processing_unavailable', 'Private processing is temporarily unavailable.', 503) from None
    finally:
        try:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
        finally:
            # An early timeout can interrupt communicate before stdin is closed.
            # Explicitly close all pipes after reaping the child on every path.
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass
            if owns_job:
                store.release_job(job)


def upload(store, owner, content, meta, timeout=5):
    checked_fields(meta, ('currency', 'time_zone', 'sales_basis', 'tax_basis', 'authorized'))
    if meta['currency'] not in ('AUD', 'USD') or meta['sales_basis'] != 'gross_units':
        raise BusinessError('invalid_declaration', 'Declare AUD or USD and gross_units sales explicitly.', 422)
    if meta['tax_basis'] not in ('exclusive', 'inclusive') or meta['authorized'] != 'true':
        raise BusinessError('invalid_declaration', 'Confirm permission and a single tax basis.', 422)
    if not isinstance(meta['time_zone'], str) or len(meta['time_zone']) > 80:
        raise BusinessError('invalid_time_zone', 'Choose a valid IANA business time zone.', 422)
    try:
        zone = ZoneInfo(meta['time_zone'])
    except (ZoneInfoNotFoundError, ValueError):
        raise BusinessError('invalid_time_zone', 'Choose a valid IANA business time zone.', 422) from None
    if len(content) > store.max_file_bytes:
        raise BusinessError('file_too_large', 'CSV exceeds the %s MiB limit. Choose a smaller file.'
                            % ('%g' % (store.max_file_bytes / (1024 * 1024))), 413)
    store.rate(owner, 'upload', 3, 600)
    with processing_slot(store, owner, timeout) as job:
        today = datetime.fromtimestamp(store.clock(), timezone.utc).astimezone(zone).date()
        pending = run_worker(store, owner, 'parse', {'content': base64.b64encode(content).decode('ascii'),
                                                   'meta': meta, 'as_of_date': str(today)}, timeout, job_id=job)
        identifier, revision = store.save_pending(owner, pending)
        preview = []
        for group in pending['dataset']['groups']:
            for row in group['rows']:
                if len(preview) >= 20:
                    break
                preview.append(dict(date=row['date'], product=group['item_id'], store=group['store_id'],
                                    units_sold=row['units_sold'], unit_price=row['unit_price'], unit_cost=row['unit_cost']))
            if len(preview) >= 20:
                break
        return {'upload_id': identifier, 'revision': revision, 'report': pending['report'],
                'preview': preview, 'series': pending['series']}


def catalog(record):
    data = record['payload']
    return {'dataset_id': record['id'], 'revision': record['revision'], 'meta': data['meta'],
            'context': {'source_kind': 'user_csv', 'dataset_id': record['id'],
                        'revision': record['revision'], 'currency': data['meta']['currency']},
            'series': [{key: entry[key] for key in ('series_id', 'item_id', 'store_id', 'start_date', 'end_date', 'observations')}
                       for entry in data['series']]}


def confirm(store, owner, identifier, parameters, timeout=5):
    checked_fields(parameters, ('revision', 'selections'))
    if not isinstance(parameters['revision'], str):
        raise BusinessError('invalid_revision', 'Select the upload version returned by validation.')
    with processing_slot(store, owner, timeout) as job:
        pending = store.load(owner, identifier, state='pending', revision=parameters['revision'])
        selections = parameters['selections']
        if not isinstance(selections, list) or not 1 <= len(selections) <= store.max_series:
            raise BusinessError('invalid_selection', 'Select between 1 and %d eligible series.' % store.max_series)
        known = {entry['series_id'] for entry in pending['payload']['series']}
        seen = set()
        for choice in selections:
            checked_fields(choice, ('series_id', 'start_date', 'end_date'))
            if not isinstance(choice['series_id'], str) or choice['series_id'] not in known or choice['series_id'] in seen:
                raise BusinessError('invalid_selection', 'Select each series from this upload at most once.')
            if not isinstance(choice['start_date'], str) or not isinstance(choice['end_date'], str):
                raise BusinessError('invalid_selection', 'Use explicit ISO date boundaries.')
            seen.add(choice['series_id'])
        store.rate(owner, 'compute', 30, 60)
        payload = run_worker(store, owner, 'confirm', {'pending': pending['payload'], 'selections': selections}, timeout, job_id=job)
        revision = store.confirm(owner, identifier, parameters['revision'], payload)
        return catalog(store.load(owner, identifier, state='ready', revision=revision))


def selected(store, owner, identifier, series_id, revision):
    if not isinstance(series_id, str) or not isinstance(revision, str):
        raise BusinessError('invalid_selection', 'Select a dataset version and series.')
    record = store.load(owner, identifier, state='ready', revision=revision)
    entry = next((row for row in record['payload']['series'] if row['series_id'] == series_id), None)
    if entry is None:
        raise BusinessError('unknown_series', 'The selected series is not in this dataset.', 404)
    context = {'source_kind': 'user_csv', 'dataset_id': identifier, 'revision': revision,
               'series_id': series_id, 'forecast_origin': entry['end_date'],
               'currency': record['payload']['meta']['currency']}
    return record, entry, context


def analysis(store, owner, identifier, parameters):
    checked_fields(parameters, ('series_id', 'revision'))
    store.rate(owner, 'compute', 30, 60)
    record, entry, context = selected(store, owner, identifier, **parameters)
    result = entry['result']
    engine = result['analysis']
    price = result['references']['unit_price']
    cost = result['references']['unit_cost']
    defaults = {key: None for key in set(INVENTORY_FIELDS + SCENARIO_FIELDS + ('max_unmet_units',))}
    return {'item_id': entry['item_id'], 'store_id': entry['store_id'], 'context': context,
            'currency': context['currency'], 'meta': record['payload']['meta'],
            'history': [{'date': row['date'], 'units': row['units_sold']} for row in result['history']],
            'historical_units': sum(row['units_sold'] for row in result['history']),
            'analysis': engine, 'quality': result['quality'], 'defaults': defaults, 'inventory': None,
            'price_reference': price, 'cost_reference': cost, 'price': price['value'] if price else None,
            'price_date': price['date'] if price else None,
            'overview': [{'item_id': entry['item_id'], 'store_id': entry['store_id'], 'category': 'Not supplied',
                          'historical_units': sum(row['units_sold'] for row in result['history']),
                          'forecast_total': engine['total_forecast_demand'], 'method': engine['selected_method'],
                          'mae': engine['backtest'][engine['selected_method']]['mae']}],
            'source_label': 'User-uploaded data · Source not independently verified'}


def calculate(store, owner, identifier, operation, parameters, timeout=5):
    fields = INVENTORY_FIELDS if operation == 'inventory' else SCENARIO_FIELDS
    required = ('series_id', 'revision', 'currency') + fields
    optional = ('stock_as_of', 'hypothetical_stock_at_origin')
    if operation == 'scenarios':
        optional += ('max_unmet_units', 'on_order_units', 'acknowledge_excluded_on_order')
    checked_fields(parameters, required, optional)
    with processing_slot(store, owner, timeout) as job:
        record, entry, context = selected(store, owner, identifier, parameters['series_id'], parameters['revision'])
        if parameters['currency'] != context['currency']:
            raise BusinessError('currency_conflict', 'All financial inputs must use the confirmed dataset currency.', 422)
        for field in ('hypothetical_stock_at_origin', 'acknowledge_excluded_on_order'):
            if field in parameters and type(parameters[field]) is not bool:
                raise BusinessError('invalid_declaration', 'Use explicit true or false declarations.', 422)
        stock_date = parameters.get('stock_as_of')
        if stock_date not in (None, ''):
            if not isinstance(stock_date, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', stock_date):
                raise BusinessError('invalid_stock_date', 'Stock as of must be an ISO calendar date.', 422)
            try:
                date.fromisoformat(stock_date)
            except ValueError:
                raise BusinessError('invalid_stock_date', 'Stock as of must be an ISO calendar date.', 422) from None
        if parameters.get('hypothetical_stock_at_origin') is not True and parameters.get('stock_as_of') != entry['end_date']:
            raise BusinessError('stock_date_required', 'Confirm stock as of the forecast origin, or explicitly use hypothetical stock there.', 422)
        store.rate(owner, 'compute', 30, 60)
        inputs = {key: parameters[key] for key in fields}
        excluded = 0
        if operation == 'scenarios':
            limit = parameters.get('max_unmet_units')
            inputs['max_unmet_units'] = None if limit is None or limit == '' else limit
            excluded = units(parameters.get('on_order_units', 0), 'on_order_units')
            if excluded and parameters.get('acknowledge_excluded_on_order') is not True:
                raise BusinessError('on_order_not_supported', 'Existing on-order stock is unsupported in this scenario. Explicitly acknowledge a separate scenario excluding it.', 422)
        result = run_worker(store, owner, operation,
                            {'item_id': entry['item_id'], 'currency': context['currency'], 'inputs': inputs,
                             'daily_demand': [row['prediction'] for row in entry['result']['analysis']['future']]}, timeout, job_id=job)
        # If a concurrent replacement/deletion occurred, do not publish its old result.
        store.load(owner, identifier, state='ready', revision=parameters['revision'])
        result.update(context=context, currency=context['currency'],
                      input_provenance='User-provided assumptions; not independently verified.',
                      stock_as_of=parameters.get('stock_as_of'),
                      hypothetical_stock_at_origin=parameters.get('hypothetical_stock_at_origin') is True)
        if operation == 'scenarios':
            result['forecast_demand'] = entry['result']['analysis']['total_forecast_demand']
            result['excluded_on_order_units'] = excluded
            if excluded:
                result['limitations'] += ' This separate scenario explicitly excludes existing on-order stock and its costs.'
        return result
