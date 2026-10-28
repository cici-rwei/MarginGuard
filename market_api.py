"""Strict, read-only Flask adapters for the independent ABS market snapshot."""
from threading import Lock

from flask import Blueprint, jsonify, request

from market_service import MarketDataUnavailable, MarketService


def create_market_blueprint(abs_dir):
    """Use a trusted application-configured directory, never a query-string path."""
    blueprint = Blueprint("market_api", __name__, url_prefix="/api/market")
    cached = None
    lock = Lock()

    def service():
        nonlocal cached
        if cached is None:
            with lock:
                if cached is None:
                    cached = MarketService(abs_dir)
        return cached

    def parameters(required=(), optional=()):
        allowed = set(required) | set(optional)
        if set(request.args) - allowed:
            raise ValueError("Unknown query parameter. Use only documented market filters.")
        if any(len(request.args.getlist(key)) != 1 for key in request.args):
            raise ValueError("Query parameters cannot be repeated.")
        result = request.args.to_dict()
        if any(key not in result for key in required):
            raise ValueError("Required query parameters: " + ", ".join(required))
        if any(not value.strip() or len(value) > 200 for value in result.values()):
            raise ValueError("Query parameters must be nonempty and at most 200 characters.")
        return result

    @blueprint.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @blueprint.errorhandler(MarketDataUnavailable)
    def unavailable(error):
        return jsonify(error=str(error)), 503

    @blueprint.get("/catalog")
    def catalog():
        parameters()
        return jsonify(service().catalog())

    @blueprint.get("/series")
    def series():
        params = parameters(("dataset_id", "series_id"), ("start", "end"))
        return jsonify(service().series(**params))

    @blueprint.get("/compare")
    def compare():
        params = parameters(("dataset_id", "table_id", "measure", "adjustment", "period", "growth", "group"),
                            ("category", "geography"))
        return jsonify(service().compare(**params))

    @blueprint.get("/overview")
    def overview():
        parameters()
        return jsonify(service().overview())

    @blueprint.get("/business-counts")
    def business_counts():
        params = parameters(optional=("financial_year",))
        return jsonify(service().business_counts(**params))

    @blueprint.get("/sources")
    def sources():
        parameters()
        return jsonify(service().sources())

    return blueprint
