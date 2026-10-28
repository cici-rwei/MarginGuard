"""Small shared validators; all Phase 2 business inputs are explicit assumptions."""
from decimal import Decimal, InvalidOperation


def number(value, name, maximum='1000000000'):
    if isinstance(value, bool):
        raise ValueError(name + ' must be numeric, not boolean.')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(name + ' must be numeric.') from None
    if not result.is_finite() or not 0 <= result <= Decimal(str(maximum)):
        raise ValueError(name + ' must be finite and between 0 and ' + str(maximum) + '.')
    return result


def units(value, name, maximum=1000000):
    result = number(value, name, maximum)
    if result != result.to_integral_value():
        raise ValueError(name + ' must be a whole number.')
    return int(result)


def demand_values(values):
    if not isinstance(values, (list, tuple)) or len(values) != 14:
        raise ValueError('Exactly 14 daily forecast values are required.')
    return [number(v, 'daily demand', 1000000) for v in values]
