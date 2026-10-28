"""14-day expected-sales simulations with FIFO cost layers and lost sales (no backlog)."""
from decimal import Decimal
from finance import procurement, gross_profit, lost_sales, ProcurementConstraintError
from phase2_inputs import demand_values, number, units
from currency import validate_currency

STRATEGIES = ('Wait', 'Reorder', 'Discount')  # Deterministic tie preference.


def simulate(strategy, daily_demand, current_stock, selling_price, existing_unit_cost,
             order_quantity=0, unit_purchase_cost=0, freight=0, other_costs=0,
             moq=0, lead_time_days=0, discount_percent=0, demand_uplift_percent=0,
             *, currency='USD'):
    currency = validate_currency(currency)
    if strategy not in STRATEGIES:
        raise ValueError('Unknown strategy.')
    demand = demand_values(daily_demand)
    stock = units(current_stock, 'current_stock')
    price = number(selling_price, 'selling_price')
    old_cost = number(existing_unit_cost, 'existing_unit_cost')
    lead = units(lead_time_days, 'lead_time_days', 365)
    discount = number(discount_percent, 'discount_percent', 100)
    uplift = number(demand_uplift_percent, 'demand_uplift_percent', 500)
    # Validate even inactive inputs so bad assumptions never pass silently.
    quantity = units(order_quantity, 'order_quantity')
    purchase_cost = number(unit_purchase_cost, 'unit_purchase_cost')
    freight = number(freight, 'freight')
    other_costs = number(other_costs, 'other_costs')
    minimum = units(moq, 'moq')
    if strategy == 'Reorder':
        purchase = procurement(purchase_cost, quantity, freight, other_costs, minimum,
                               currency=currency)
    else:
        purchase = procurement(0, 0, currency=currency)
        quantity = 0
    if strategy == 'Discount':
        price *= 1 - discount / 100
        demand = [v * (1 + uplift / 100) for v in demand]
    old_remaining, new_remaining = Decimal(stock), Decimal(0)
    old_sold = new_sold = unmet = before_receipt = after_receipt = Decimal(0)
    daily = []
    for index, requested in enumerate(demand):
        # A lead time of 7 means seven full unavailable days; receipt is day 8.
        received = quantity if quantity and index == lead else 0
        new_remaining += received
        sold_old = min(old_remaining, requested)
        sold_new = min(new_remaining, requested - sold_old)
        old_remaining -= sold_old
        new_remaining -= sold_new
        sold = sold_old + sold_new
        missed = requested - sold
        old_sold += sold_old
        new_sold += sold_new
        unmet += missed
        if quantity and index >= lead:
            after_receipt += sold
        else:
            before_receipt += sold
        daily.append({'day': index + 1, 'demand': requested, 'received_units': received,
                      'existing_units_sold': sold_old, 'new_units_sold': sold_new,
                      'units_sold': sold, 'unmet_demand': missed,
                      'ending_inventory': old_remaining + new_remaining})
    landed = purchase['unit_landed_cost']
    result = {'strategy': strategy, 'effective_selling_price': price,
              'expected_demand': sum(demand), 'units_sold': old_sold + new_sold,
              'existing_units_sold': old_sold, 'new_units_sold': new_sold,
              'unmet_demand': unmet, 'ending_inventory': old_remaining + new_remaining,
              'ending_existing_inventory': old_remaining, 'ending_new_inventory': new_remaining,
              'in_transit_units': quantity if lead >= 14 else 0,
              'receipt_day': lead + 1 if quantity else None,
              'sales_before_receipt': before_receipt, 'sales_after_receipt': after_receipt,
              'stock_sufficient': unmet == 0, 'moq_satisfied': True,
              'daily': daily, **purchase,
              **gross_profit(price, old_sold, old_cost, new_sold, landed, currency=currency)}
    # A transparent opportunity-cost estimate, separate from realised COGS.
    reference_cost = landed if landed is not None else old_cost
    result.update(lost_sales(unmet, price, reference_cost))
    return result


def compare_strategies(daily_demand, current_stock, selling_price, existing_unit_cost,
                       cash_budget, order_quantity, unit_purchase_cost, freight=0,
                       other_costs=0, moq=0, lead_time_days=0, discount_percent=0,
                       demand_uplift_percent=0, max_unmet_units=None, *, currency='USD'):
    currency = validate_currency(currency)
    budget = number(cash_budget, 'cash_budget', '1000000000000000')
    max_unmet = number(max_unmet_units, 'max_unmet_units', 84000000) if max_unmet_units is not None else None
    results = []
    for strategy in STRATEGIES:
        try:
            result = simulate(strategy, daily_demand, current_stock, selling_price,
                              existing_unit_cost, order_quantity, unit_purchase_cost,
                              freight, other_costs, moq, lead_time_days, discount_percent,
                              demand_uplift_percent, currency=currency)
        except ProcurementConstraintError as error:
            result = {'currency': currency, 'strategy': strategy, 'feasible': False, 'feasibility_status': 'Infeasible',
                      'reasons': [str(error)], 'moq_satisfied': 'MOQ' not in str(error),
                      'revenue': None, 'gross_profit': None, 'gross_margin': None,
                      'unmet_demand': None, 'ending_inventory': None,
                      'procurement_cash_outlay': None, 'daily': []}
        else:
            reasons = []
            if result['procurement_cash_outlay'] > budget:
                reasons.append('Procurement cash exceeds budget.')
            if max_unmet is not None and result['unmet_demand'] > max_unmet:
                reasons.append('Unmet demand exceeds the user service constraint.')
            result.update(feasible=not reasons, feasibility_status='Infeasible' if reasons else 'Feasible', reasons=reasons)
        cash_outlay = result['procurement_cash_outlay']
        result['budget_satisfied'] = None if cash_outlay is None else cash_outlay <= budget
        results.append(result)
    feasible = [r for r in results if r['feasible']]
    winner = max(feasible, key=lambda r: r['gross_profit']) if feasible else None
    reason = ('Highest forecast gross profit among strategies meeting cash, procurement and any service constraints; exact ties prefer Wait, then Reorder, then Discount.' if winner else 'No strategy meets all configured constraints; no recommendation.')
    return {'currency': currency, 'horizon_days': 14, 'cash_budget': budget,
            'max_unmet_units': max_unmet, 'strategies': results,
            'recommendation': winner['strategy'] if winner else None,
            'recommendation_reason': reason,
            'tradeoffs': [{k: r.get(k) for k in ('strategy', 'gross_profit', 'unmet_demand',
                          'ending_inventory', 'procurement_cash_outlay', 'feasibility_status', 'reasons')} for r in results],
            'limitations': 'Hypothetical assumptions; lost sales are not backlogged. No operating expenses, holding costs or demand uncertainty. A recommendation is not a guaranteed real-world optimum.'}
