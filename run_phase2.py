"""Run Phase 2 using saved Phase 1 forecasts; never retrain the forecast model."""
import argparse
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from data_loader import load_series
from inventory import inventory_risk
from phase2_inputs import demand_values, number
from scenario import compare_strategies

ROOT = Path(__file__).resolve().parent


def load_forecast(path, item_id, store_id):
    if not item_id or not store_id:
        raise ValueError('Both item_id and store_id are required.')
    try:
        records = json.loads(Path(path).read_text())
        if not isinstance(records, list):
            raise ValueError('Forecast JSON must contain a list.')
        selected = [r for r in records if r['item_id'] == item_id and r['store_id'] == store_id]
        if len(selected) != 1:
            raise ValueError('Unknown or duplicate product-store forecast.')
        record = selected[0]
        values = demand_values([r['prediction'] for r in record['future']])
        origin = date.fromisoformat(record['history_end'])
        dates = [date.fromisoformat(r['date']) for r in record['future']]
        if dates != [origin + timedelta(days=i) for i in range(1, 15)]:
            raise ValueError('Forecast dates must be the 14 consecutive days after history_end.')
        total = number(record['total_forecast_demand'], 'total_forecast_demand', 14000000)
        if abs(sum(values) - total) > Decimal('0.00000001'):
            raise ValueError('Forecast total disagrees with its daily values.')
        return record, values
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid Phase 1 forecast JSON: ' + str(error)) from error


def run_demo(parameters, forecast_path=None, processed_path=None):
    config = dict(parameters)
    item, store = config['item_id'], config['store_id']
    record, values = load_forecast(forecast_path or ROOT / 'data/forecast_results_future.json', item, store)
    history = load_series(processed_path or ROOT / 'data/processed_sales.csv')
    if (item, store) not in history:
        raise ValueError('Selected product-store is missing from historical data.')
    last = history[(item, store)][-1]
    if str(last['date']) != record['history_end']:
        raise ValueError('Forecast origin and processed historical end date disagree.')
    if last['sell_price_usd'] is None or last['sell_price_usd'] <= 0:
        raise ValueError('The last historical price must be present and positive for this demo.')
    price = last['sell_price_usd']
    inventory = inventory_risk(item, values, config['current_stock'], config['lead_time_days'],
                               config['safety_stock'], config['on_order_units'], config['excess_cover_days'])
    # Arrival dates/costs of existing purchase orders are outside this MVP.
    if config['on_order_units'] != 0:
        raise ValueError('Demo scenarios require on_order_units=0; existing orders have no arrival/cost schedule.')
    names = ('current_stock', 'existing_unit_cost', 'cash_budget', 'order_quantity',
             'unit_purchase_cost', 'freight', 'other_costs', 'moq', 'lead_time_days',
             'discount_percent', 'demand_uplift_percent', 'max_unmet_units')
    comparison = compare_strategies(values, selling_price=price, **{k: config[k] for k in names})
    return {'item_id': item, 'store_id': store, 'forecast_method': record['selected_method'],
            'forecast_start': record['future'][0]['date'], 'forecast_end': record['future'][-1]['date'],
            'forecast_total': sum(values), 'historical_price_date': str(last['date']),
            'historical_price_usd': price,
            'selling_price_assumption': 'Carry the final observed historical price forward unchanged; future price is an assumption.',
            'parameters': config, 'inventory': inventory, 'comparison': comparison}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parameters', default=str(ROOT / 'data/scenario_defaults.json'))
    parser.add_argument('--output', default=str(ROOT / 'data/phase2_demo.json'))
    args = parser.parse_args()
    try:
        parameters = json.loads(Path(args.parameters).read_text())
        result = run_demo(parameters)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, default=str, indent=2) + '\n')
        print(result['item_id'], result['store_id'], result['forecast_start'], 'to', result['forecast_end'])
        for row in result['comparison']['strategies']:
            print(row['strategy'], 'revenue=', row['revenue'], 'gross_profit=', row['gross_profit'],
                  'ending_inventory=', row['ending_inventory'], row['feasibility_status'])
        print('Recommendation:', result['comparison']['recommendation'])
        print('Saved:', output)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, 'Phase 2 failed: %s\n' % error)


if __name__ == '__main__':
    main()
