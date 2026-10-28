"""Local Flask dashboard: thin HTTP adapters around the existing Python engines."""
import json
import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from data_loader import load_series
from forecast import analyse
from inventory import inventory_risk
from scenario import compare_strategies
from market_api import create_market_blueprint
from runtime_config import configure
from business_api import create_business_blueprint
from synthetic_demo import create_synthetic_blueprint
from upload_review import (configure_upload_review, business_upload_enabled,
                           review_session_authorized, review_window_open)

ROOT = Path(__file__).resolve().parent


def serial(value):
    if isinstance(value, (Decimal, date)):
        return str(value)
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


class DataUnavailable(Exception):
    pass


def create_app(data_dir=None, config=None):
    app = Flask(__name__)
    configure(app, config)
    configure_upload_review(app)
    app.config.update(DATA_DIR=Path(data_dir) if data_dir else ROOT / 'data')
    app.register_blueprint(create_market_blueprint(app.config['DATA_DIR'] / 'abs'))
    app.register_blueprint(create_business_blueprint())
    app.register_blueprint(create_synthetic_blueprint())

    def data():
        if not app.config['ENABLE_M5_DEMO']:
            raise DataUnavailable('Walmart M5 Demo is disabled in this deployment pending data-use permission. Market Intelligence remains available.')
        try:
            groups = load_series(app.config['DATA_DIR'] / 'processed_sales.csv')
            defaults = json.loads((app.config['DATA_DIR'] / 'scenario_defaults.json').read_text())
            return groups, defaults
        except (OSError, ValueError) as error:
            raise DataUnavailable('Historical data unavailable. Restore the local M5 files and run Phase 1 preprocessing.') from None

    def selected(params):
        item, store = params.get('item_id'), params.get('store_id')
        if not isinstance(item, str) or not isinstance(store, str) or not item or not store:
            raise ValueError('Select a valid product and store.')
        groups, defaults = data()
        if (item, store) not in groups:
            raise ValueError('Unknown product-store combination.')
        rows = groups[(item, store)]
        analysis = analyse(rows)  # Existing, unchanged Phase 1 algorithm.
        values = [r['prediction'] for r in analysis['future']]
        return rows, defaults, analysis, values

    def body():
        if not request.is_json:
            raise ValueError('Submit parameters as a JSON object.')
        p = request.get_json()
        if not isinstance(p, dict):
            raise ValueError('Submit parameters as a JSON object.')
        return p

    def fields(p, names):
        missing = [n for n in names if n not in p or p[n] == '']
        if missing:
            raise ValueError('Required inputs: ' + ', '.join(missing))
        return {n: p[n] for n in names}

    @app.errorhandler(DataUnavailable)
    def unavailable(error):
        return jsonify(error=str(error)), 503

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith('/api/'):
            return jsonify(error=error.description), error.code
        return error

    pages = {'/': ('dashboard', 'Business Overview'), '/forecasting': ('forecasting', 'Demand Forecasting'),
             '/inventory': ('inventory', 'Inventory & Risk'), '/scenarios': ('scenarios', 'Financial Decision Lab'),
             '/market': ('market', 'Australian Retail Market Overview')}
    for route, (page, title) in pages.items():
        def view(page=page, title=title):
            return render_template(page + '.html', page=page, title=title,
                                   upload_enabled=business_upload_enabled(),
                                   upload_review_active=review_session_authorized(),
                                   upload_review_entry=(page == 'dashboard' and review_window_open()
                                                        and request.args.get('mode') == 'business'
                                                        and request.args.get('review') == '1'),
                                   demo_enabled=app.config['ENABLE_M5_DEMO'],
                                   synthetic_demo_enabled=app.config['ENABLE_SYNTHETIC_DEMO'],
                                   public_mode=app.config['PUBLIC_MODE'])
        app.add_url_rule(route, page, view)

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = ("default-src 'self'; script-src 'self'; "
                                                     "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                                     "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if app.config['PUBLIC_MODE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if (request.path.startswith('/api/business/') or request.endpoint == 'features'
                or request.endpoint in {'dashboard', 'forecasting', 'inventory', 'scenarios'}):
            response.headers['Cache-Control'] = 'no-store'
            response.vary.add('Cookie')
        return response

    @app.get('/api/features')
    def features():
        return jsonify(demo_enabled=app.config['ENABLE_M5_DEMO'],
                       synthetic_demo_enabled=app.config['ENABLE_SYNTHETIC_DEMO'],
                       upload_enabled=business_upload_enabled(), public_mode=app.config['PUBLIC_MODE'])

    @app.get('/api/catalog')
    def catalog():
        groups, _ = data()
        return jsonify(series=[{'item_id': item, 'store_id': store, 'category': rows[0]['category_id']}
                               for (item, store), rows in sorted(groups.items())])

    @app.get('/api/analysis')
    def analysis_api():
        rows, defaults, result, values = selected(request.args)
        price = rows[-1]['sell_price_usd']
        defaults = dict(defaults, selling_price=price)
        risk = inventory_risk(request.args['item_id'], values, defaults['current_stock'],
                              defaults['lead_time_days'], defaults['safety_stock'],
                              defaults['on_order_units'], defaults['excess_cover_days'])
        groups, _ = data()
        overview = []
        for (item, store), history in sorted(groups.items()):
            a = analyse(history)
            overview.append({'item_id': item, 'store_id': store, 'category': history[0]['category_id'],
                             'historical_units': sum(r['units_sold'] for r in history),
                             'forecast_total': a['total_forecast_demand'], 'method': a['selected_method'],
                             'mae': a['backtest'][a['selected_method']]['mae']})
        revision = hashlib.sha256((app.config['DATA_DIR'] / 'processed_sales.csv').read_bytes()).hexdigest()[:24]
        context = {'source_kind': 'm5_demo', 'dataset_id': 'm5-demo', 'revision': revision,
                   'series_id': request.args['item_id'] + '/' + request.args['store_id'],
                   'forecast_origin': result['history_end'], 'currency': 'USD'}
        return jsonify(serial({'item_id': request.args['item_id'], 'store_id': request.args['store_id'], 'context': context,
                               'history': [{'date': r['date'], 'units': r['units_sold']} for r in rows],
                               'historical_units': sum(r['units_sold'] for r in rows),
                               'analysis': result, 'defaults': defaults, 'inventory': risk, 'overview': overview,
                               'price_date': rows[-1]['date'], 'price': price}))

    @app.post('/api/inventory')
    def inventory_api():
        p = body()
        if p.get('currency', 'USD') != 'USD':
            raise ValueError('Walmart M5 Demo uses USD.')
        _, _, _, values = selected(p)
        inputs = fields(p, ('current_stock','lead_time_days','safety_stock','on_order_units','excess_cover_days'))
        result = inventory_risk(p['item_id'], values, **inputs)
        return jsonify(serial(result))

    @app.post('/api/scenarios')
    def scenario_api():
        p = body()
        if p.get('currency', 'USD') != 'USD':
            raise ValueError('Walmart M5 Demo uses USD.')
        from phase2_inputs import units
        if units(p.get('on_order_units', 0), 'on_order_units') and p.get('acknowledge_excluded_on_order') is not True:
            raise ValueError('Existing on-order units are unsupported in scenarios. Explicitly acknowledge a separate scenario excluding them.')
        _, _, _, values = selected(p)
        inputs = fields(p, ('current_stock','selling_price','existing_unit_cost','cash_budget',
                            'order_quantity','unit_purchase_cost','freight','other_costs','moq',
                            'lead_time_days','discount_percent','demand_uplift_percent'))
        inputs['max_unmet_units'] = None if p.get('max_unmet_units') in (None, '') else p['max_unmet_units']
        return jsonify(serial(compare_strategies(values, **inputs)))

    return app


app = create_app()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5050, debug=False)
