"""Explainable inventory rules using hypothetical stock, not Walmart inventory."""
from decimal import Decimal, ROUND_CEILING
from phase2_inputs import demand_values, number, units


def inventory_risk(item_id, daily_demand, current_stock, lead_time_days,
                   safety_stock=0, on_order_units=0, excess_cover_days=30):
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError('A nonempty item_id is required.')
    demand = demand_values(daily_demand)
    stock = units(current_stock, 'current_stock')
    lead = units(lead_time_days, 'lead_time_days', 365)
    safety = units(safety_stock, 'safety_stock')
    on_order = units(on_order_units, 'on_order_units')
    threshold = number(excess_cover_days, 'excess_cover_days', 3650)
    if threshold == 0:
        raise ValueError('excess_cover_days must be greater than zero.')
    average = sum(demand) / 14
    cover = Decimal(stock) / average if average else None
    lead_demand = sum(demand[:lead]) if lead <= 14 else sum(demand) + (lead - 14) * average
    target = lead_demand + safety
    position = stock + on_order
    reorder = int(max(Decimal(0), target - position).to_integral_value(rounding=ROUND_CEILING))
    stockout = Decimal(stock) < lead_demand
    excess = cover > threshold if cover is not None else stock > 0
    if stockout:
        status, explanation = 'Stockout Risk', 'Current stock is below demand before the assumed replenishment arrival.'
    elif position < target:
        status, explanation = 'Reorder Attention', 'Stock covers lead-time demand but inventory position is below the safety-stock target.'
    elif excess:
        status, explanation = 'Excess Inventory Attention', 'Stock exceeds the configured days-of-cover threshold, or stock exists with zero forecast demand.'
    else:
        status, explanation = 'Sufficient Inventory', 'Inventory position meets the lead-time demand plus safety-stock target.'
    return {'item_id': item_id, 'input_source': 'Hypothetical inventory assumptions',
            'average_daily_demand': average, 'days_of_cover': cover,
            'demand_status': 'No forecast demand' if not average else 'Positive forecast demand',
            'lead_time_demand': lead_demand, 'extrapolated': lead > 14,
            'extension_rule': 'After day 14, use the 14-day average daily demand.',
            'inventory_position': position, 'target_inventory_position': target,
            'suggested_reorder_quantity': reorder, 'stockout_risk': stockout,
            'excess_inventory_warning': excess, 'excess_cover_days': threshold,
            'status': status, 'explanation': explanation,
            'on_order_policy': 'On-order units reduce the target gap but cannot cover pre-arrival demand; arrival dates are unknown.'}
