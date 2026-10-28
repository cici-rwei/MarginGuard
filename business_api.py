"""Private anonymous CSV endpoints; no arbitrary server paths or raw downloads."""
import hmac
import json
from pathlib import Path
import re
import time

from flask import Blueprint, current_app, g, jsonify, request, send_file, session
from werkzeug.exceptions import HTTPException

from business_csv import MAX_FILE_BYTES
from business_store import BusinessError, BusinessStore, owner_key
import business_service as service


def get_business_store():
    if 'business_store' not in current_app.extensions:
        config = current_app.config
        root = config.get('BUSINESS_STORAGE_ROOT')
        if not root:
            raise BusinessError('storage_unconfigured', 'Private upload storage is not configured.', 503)
        store = BusinessStore(root, clock=config.get('BUSINESS_CLOCK', time.time),
                              pending_ttl=config.get('BUSINESS_PENDING_TTL', 900),
                              idle_ttl=config.get('BUSINESS_IDLE_TTL', 1800),
                              absolute_ttl=config.get('BUSINESS_ABSOLUTE_TTL', 7200),
                              max_bytes=config.get('BUSINESS_MAX_STORAGE_BYTES', 500 * 1024 * 1024),
                              max_dataset_bytes=config.get('BUSINESS_MAX_DATASET_BYTES', 20 * 1024 * 1024),
                              max_jobs=config.get('BUSINESS_MAX_JOBS', 2),
                              max_sessions=config.get('BUSINESS_MAX_SESSIONS', 100))
        current_app.extensions['business_store'] = store
        if not current_app.testing:
            store.start_cleanup(config.get('BUSINESS_CLEANUP_INTERVAL', 300))
    return current_app.extensions['business_store']


def _query(required=(), optional=()):
    if any(len(request.args.getlist(key)) != 1 for key in request.args):
        raise BusinessError('duplicate_parameter', 'Repeated query parameters are not supported.')
    values = request.args.to_dict()
    service.checked_fields(values, required, optional)
    if any(len(value) > 128 for value in values.values()):
        raise BusinessError('invalid_parameter', 'Query parameter exceeds its limit.')
    return values


def _body():
    _query()
    if not request.is_json:
        raise BusinessError('json_required', 'Submit parameters as a JSON object.', 415)
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('Invalid JSON number')
    try:
        result = json.loads(request.get_data(), object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError):
        raise BusinessError('invalid_json', 'JSON must be valid, finite and contain no duplicate keys.') from None
    if not isinstance(result, dict):
        raise BusinessError('invalid_json', 'Submit a JSON object.')
    return result


def _timeout():
    return current_app.config.get('BUSINESS_WORKER_TIMEOUT', 5)


def create_business_blueprint():
    bp = Blueprint('business', __name__, url_prefix='/api/business')

    @bp.before_request
    def guard():
        # Limits are set before accessing form/json streams, not after parsing.
        request.max_content_length = 6 * 1024 * 1024 if request.endpoint == 'business.upload_csv' else 32768
        # MultipartDecoder also buffers file chunks (normally 64 KiB). Keep its
        # buffer above that size, then enforce our smaller metadata budget below.
        request.max_form_memory_size = 128 * 1024
        request.max_form_parts = 8
        if request.endpoint == 'business.template_csv':
            return None
        if not current_app.config.get('ENABLE_BUSINESS_UPLOAD', False):
            raise BusinessError('uploads_disabled', 'Business uploads are disabled in this environment.', 503)
        if not current_app.secret_key:
            raise BusinessError('session_unconfigured', 'Private sessions are not configured.', 503)
        origin = request.headers.get('Origin')
        if origin and origin != request.host_url.rstrip('/'):
            raise BusinessError('origin_rejected', 'Only same-origin business requests are accepted.', 403)
        if request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
            raise BusinessError('origin_rejected', 'Only same-origin business requests are accepted.', 403)
        store = get_business_store()
        store.cleanup()
        g.business_store = store
        token = session.get('business_owner')
        valid_token = isinstance(token, str) and re.fullmatch(r'[a-f0-9]{64}', token)
        # Session bootstrap alone may create a new identity after expiry.
        if request.endpoint == 'business.browser_session' and request.method == 'GET':
            return None
        if not valid_token:
            raise BusinessError('session_required', 'Start a private upload session first.', 401)
        g.business_owner = owner_key(token)
        info = store.authenticate(g.business_owner)
        if request.method in ('POST', 'DELETE', 'PUT', 'PATCH'):
            submitted = request.headers.get('X-CSRF-Token', '')
            if not re.fullmatch(r'[a-f0-9]{64}', submitted) or not hmac.compare_digest(submitted, info['csrf']):
                raise BusinessError('csrf_rejected', 'Your request token is missing or expired. Reload the upload panel.', 403)
        store.rate(g.business_owner, 'requests', 120, 60)

    @bp.after_request
    def private_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @bp.errorhandler(BusinessError)
    def business_error(error):
        result = {'error': str(error), 'code': error.code}
        if error.issues is not None:
            result['issues'] = error.issues
        return jsonify(result), error.status

    @bp.errorhandler(HTTPException)
    def http_error(error):
        message = 'Request exceeds its upload limit.' if error.code == 413 else 'The request could not be processed.'
        return jsonify(error=message, code='http_%s' % error.code), error.code

    @bp.errorhandler(ValueError)
    def validation_error(error):
        # Known field validation errors are safe; unexpected storage config is not.
        return jsonify(error='Check the submitted parameters and business declarations.', code='invalid_parameters'), 422

    @bp.errorhandler(Exception)
    def unavailable(error):
        # Never log or return private payloads, paths, SQL or tracebacks.
        return jsonify(error='Private processing is temporarily unavailable.', code='service_unavailable'), 503

    @bp.get('/template.csv')
    def template_csv():
        _query()
        path = Path(__file__).resolve().parent / 'examples' / 'business_csv' / 'template.csv'
        return send_file(path, mimetype='text/csv; charset=utf-8', as_attachment=True,
                         download_name='MarginGuard_daily_sales_template.csv')

    @bp.get('/session')
    def browser_session():
        _query()
        store = g.business_store
        token = session.get('business_owner')
        info = None
        if isinstance(token, str) and re.fullmatch(r'[a-f0-9]{64}', token):
            try:
                info = store.authenticate(owner_key(token))
            except BusinessError:
                pass
        if info is None:
            token, csrf, expires = store.create_session()
            session.clear()
            session['business_owner'] = token
            session.permanent = True
            info = store.authenticate(owner_key(token))
        return jsonify(csrf_token=info['csrf'],
                       expires_at=min(store.clock() + store.idle_ttl, info['expires']),
                       absolute_expires_at=info['expires'], active_dataset=store.active(owner_key(token)),
                       limits={'file_bytes': MAX_FILE_BYTES, 'rows': 50000, 'series': 100,
                               'minimum_history_days': 42, 'recommended_history_days': 84,
                               'pending_seconds': store.pending_ttl, 'idle_seconds': store.idle_ttl,
                               'absolute_seconds': store.absolute_ttl})

    @bp.post('/uploads')
    def upload_csv():
        _query()
        if request.mimetype != 'multipart/form-data':
            raise BusinessError('multipart_required', 'Submit one CSV using multipart/form-data.', 415)
        if set(request.files) != {'file'} or len(request.files.getlist('file')) != 1:
            raise BusinessError('file_required', 'Choose exactly one CSV file.')
        if any(len(request.form.getlist(key)) != 1 for key in request.form):
            raise BusinessError('duplicate_parameter', 'Repeated form parameters are not supported.')
        if sum(len(key.encode('utf-8')) + len(value.encode('utf-8'))
               for key, value in request.form.items()) > 16 * 1024:
            raise BusinessError('form_too_large', 'Upload declarations exceed their 16 KiB limit.', 413)
        file = request.files['file']
        filename = file.filename or ''
        if len(filename) > 255 or '\x00' in filename or filename.rsplit('.', 1)[-1].lower() != 'csv':
            raise BusinessError('unsupported_file_type', 'Choose a .csv file.', 415)
        try:
            content = file.stream.read(MAX_FILE_BYTES + 1)
        finally:
            file.close()
        result = service.upload(g.business_store, g.business_owner, content, request.form.to_dict(), _timeout())
        return jsonify(result), 201

    @bp.post('/uploads/<identifier>/confirm')
    def confirm_upload(identifier):
        result = service.confirm(g.business_store, g.business_owner, identifier, _body(), _timeout())
        return jsonify(result), 201

    @bp.delete('/uploads/<identifier>')
    def delete_upload(identifier):
        _query()
        g.business_store.delete(g.business_owner, identifier, state='pending')
        return '', 204

    @bp.get('/datasets/<identifier>/catalog')
    def business_catalog(identifier):
        _query()
        record = g.business_store.load(g.business_owner, identifier, state='ready')
        return jsonify(service.catalog(record))

    @bp.get('/datasets/<identifier>/analysis')
    def business_analysis(identifier):
        return jsonify(service.analysis(g.business_store, g.business_owner, identifier,
                                        _query(('series_id', 'revision'))))

    @bp.post('/datasets/<identifier>/inventory')
    def inventory_calculation(identifier):
        return jsonify(service.calculate(g.business_store, g.business_owner, identifier,
                                         'inventory', _body(), _timeout()))

    @bp.post('/datasets/<identifier>/scenarios')
    def scenario_calculation(identifier):
        return jsonify(service.calculate(g.business_store, g.business_owner, identifier,
                                         'scenarios', _body(), _timeout()))

    @bp.delete('/datasets/<identifier>')
    def delete_dataset(identifier):
        _query()
        g.business_store.delete(g.business_owner, identifier, state='ready')
        return '', 204

    @bp.delete('/session')
    def delete_session():
        _query()
        g.business_store.delete_session(g.business_owner)
        session.clear()
        return '', 204

    return bp
