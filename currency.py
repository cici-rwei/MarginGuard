"""Single-currency contracts; no exchange rates or currency conversion."""

SUPPORTED_CURRENCIES = ('AUD', 'USD')


def validate_currency(value):
    """Require an explicit ISO code, without silently relabelling amounts."""
    if not isinstance(value, str) or value not in SUPPORTED_CURRENCIES:
        raise ValueError('Currency must be AUD or USD.')
    return value
