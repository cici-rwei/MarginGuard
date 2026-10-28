"""Single-currency arithmetic; Decimal amounts stay unrounded until display."""
from decimal import Decimal
from phase2_inputs import number, units
from currency import validate_currency


class ProcurementConstraintError(ValueError):
    """A well-formed order fails a business constraint such as MOQ."""


def procurement(unit_purchase_cost, order_quantity, freight=0, other_costs=0, moq=0,
                *, currency='USD'):
    currency = validate_currency(currency)
    cost = number(unit_purchase_cost, 'unit_purchase_cost')
    quantity = units(order_quantity, 'order_quantity')
    freight = number(freight, 'freight')
    other = number(other_costs, 'other_costs')
    minimum = units(moq, 'moq')
    if quantity == 0:
        if freight or other:
            raise ProcurementConstraintError('A zero-quantity order cannot have procurement charges.')
        total, landed = Decimal(0), None
    else:
        if quantity < minimum:
            raise ProcurementConstraintError('Order quantity is below MOQ.')
        total = cost * quantity + freight + other
        landed = total / quantity
    return {'currency': currency, 'order_quantity': quantity,
            'total_procurement_cost': total, 'unit_landed_cost': landed,
            'procurement_cash_outlay': total}


def gross_profit(selling_price, existing_units_sold, existing_unit_cost,
                 new_units_sold=0, new_unit_landed_cost=None, *, currency='USD'):
    currency = validate_currency(currency)
    price = number(selling_price, 'selling_price')
    old_units = number(existing_units_sold, 'existing_units_sold', 14000000)
    new_units = number(new_units_sold, 'new_units_sold', 14000000)
    old_cost = number(existing_unit_cost, 'existing_unit_cost')
    if new_units and new_unit_landed_cost is None:
        raise ValueError('New sales require a new-unit landed cost.')
    new_cost = number(new_unit_landed_cost, 'new_unit_landed_cost', '1000000000000000') if new_unit_landed_cost is not None else Decimal(0)
    revenue = (old_units + new_units) * price
    old_cogs, new_cogs = old_units * old_cost, new_units * new_cost
    cogs = old_cogs + new_cogs
    profit = revenue - cogs
    return {'currency': currency, 'revenue': revenue, 'existing_cogs': old_cogs,
            'new_cogs': new_cogs, 'cogs': cogs, 'gross_profit': profit,
            'gross_margin': profit / revenue * 100 if revenue else None,
            'margin_status': 'Undefined: zero revenue' if not revenue else 'Defined'}


def lost_sales(unmet_demand, selling_price, reference_unit_cost):
    unmet = number(unmet_demand, 'unmet_demand', 84000000)
    price = number(selling_price, 'selling_price')
    cost = number(reference_unit_cost, 'reference_unit_cost', '1000000000000000')
    return {'potential_lost_revenue': unmet * price,
            'potential_lost_gross_profit': unmet * (price - cost),
            'lost_profit_reference_unit_cost': cost}
