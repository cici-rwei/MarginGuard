import json
import tempfile
import unittest
from decimal import Decimal
from datetime import date, timedelta
from pathlib import Path
from scenario import simulate, compare_strategies
from run_phase2 import load_forecast, run_demo, ROOT


class ScenarioTests(unittest.TestCase):
    def simulate(self, strategy='Wait', **kwargs):
        p=dict(daily_demand=[10]*14,current_stock=20,selling_price=5,existing_unit_cost=1)
        p.update(kwargs)
        return simulate(strategy, **p)

    def compare(self, **kwargs):
        p=dict(daily_demand=[10]*14,current_stock=20,selling_price=5,existing_unit_cost=1,
               cash_budget=300,order_quantity=100,unit_purchase_cost=2,lead_time_days=7)
        p.update(kwargs)
        return compare_strategies(**p)

    def test_wait_caps_sales(self):
        r=self.simulate()
        self.assertEqual((r['units_sold'],r['unmet_demand'],r['revenue'],r['gross_profit'],r['ending_inventory']), (20,120,100,80,0))

    def test_delayed_stock_and_before_after_sales(self):
        r=self.simulate('Reorder',current_stock=0,order_quantity=100,unit_purchase_cost=2,lead_time_days=7)
        self.assertTrue(all(d['units_sold']==0 for d in r['daily'][:7]))
        self.assertEqual(r['daily'][7]['received_units'],100)
        self.assertEqual((r['sales_before_receipt'],r['sales_after_receipt'],r['ending_inventory'],r['unmet_demand']), (0,70,30,70))

    def test_arrival_day_one_and_after_horizon(self):
        immediate=self.simulate('Reorder',current_stock=0,order_quantity=100,lead_time_days=0)
        self.assertEqual(immediate['daily'][0]['units_sold'],10)
        for lead in (14,20):
            r=self.simulate('Reorder',current_stock=0,order_quantity=100,unit_purchase_cost=2,lead_time_days=lead)
            self.assertEqual((r['units_sold'],r['cogs'],r['ending_inventory'],r['in_transit_units'],r['procurement_cash_outlay']), (0,0,0,100,200))

    def test_fifo_cash_cogs_and_ending_stock(self):
        r=self.simulate('Reorder',daily_demand=[1]*14,current_stock=2,order_quantity=10,
                        unit_purchase_cost=2,freight=10,lead_time_days=2)
        self.assertEqual((r['existing_units_sold'],r['new_units_sold'],r['cogs'],r['procurement_cash_outlay'],r['gross_profit']), (2,10,32,30,28))

    def test_discount_uplift_and_stock_cap(self):
        r=self.simulate('Discount',discount_percent=15,demand_uplift_percent=20)
        self.assertEqual(r['effective_selling_price'],Decimal('4.25'))
        self.assertEqual((r['expected_demand'],r['units_sold'],r['revenue'],r['gross_profit']), (168,20,85,65))

    def test_full_discount_zero_margin(self):
        r=self.simulate('Discount',discount_percent=100)
        self.assertIsNone(r['gross_margin'])
        self.assertEqual(r['gross_profit'],-20)

    def test_zero_demand_and_zero_order(self):
        r=self.simulate('Reorder',daily_demand=[0]*14,order_quantity=0,moq=100)
        self.assertEqual((r['revenue'],r['ending_inventory'],r['procurement_cash_outlay']), (0,20,0))
        self.assertIsNone(r['receipt_day'])

    def test_budget_and_moq_exclude_reorder(self):
        for patch in ({'cash_budget':10}, {'order_quantity':5,'moq':10}):
            r=self.compare(**patch)
            self.assertFalse(r['strategies'][1]['feasible'])
            self.assertNotEqual(r['recommendation'],'Reorder')

    def test_no_feasible_strategy(self):
        r=self.compare(current_stock=0,order_quantity=0,max_unmet_units=0)
        self.assertIsNone(r['recommendation'])
        self.assertTrue(all(not s['feasible'] for s in r['strategies']))

    def test_profit_recommendation_and_tie(self):
        r=self.compare()
        self.assertEqual(r['recommendation'],'Reorder')
        self.assertEqual(self.compare(order_quantity=0)['recommendation'],'Wait')

    def test_conservation_and_comparison_consistency(self):
        r=self.compare(discount_percent=10,demand_uplift_percent=30)
        for s in r['strategies']:
            self.assertEqual(s['units_sold']+s['unmet_demand'],s['expected_demand'])
            self.assertEqual(20+sum(d['received_units'] for d in s['daily']),s['units_sold']+s['ending_inventory'])
            self.assertEqual(s['revenue']-s['cogs'],s['gross_profit'])
            self.assertEqual(sum(d['units_sold'] for d in s['daily']),s['units_sold'])

    def test_bad_assumptions_rejected(self):
        for patch in ({'discount_percent':101},{'demand_uplift_percent':-1},{'current_stock':-1},
                      {'freight':-1},{'selling_price':'NaN'},{'lead_time_days':1.5},
                      {'cash_budget':-1},{'existing_unit_cost':-1}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.compare(**patch)

    def test_maximum_uplift_no_overflow(self):
        r=self.simulate('Discount',daily_demand=[1000000]*14,current_stock=0,demand_uplift_percent=500)
        self.assertEqual(r['unmet_demand'],84000000)


class Phase2RealDataTests(unittest.TestCase):
    def test_real_phase1_to_phase2(self):
        if not (ROOT/'data/processed_sales.csv').exists():
            self.skipTest('Local M5 processed data required.')
        params=json.loads((ROOT/'data/scenario_defaults.json').read_text())
        r=run_demo(params)
        self.assertEqual(r['item_id'],'FOODS_3_252')
        self.assertEqual(r['forecast_total'],Decimal('525.5'))
        self.assertEqual(r['historical_price_usd'],Decimal('1.58'))
        self.assertEqual(r['comparison']['recommendation'],'Reorder')
        self.assertEqual(r['comparison']['strategies'][0]['revenue'],316)
        self.assertEqual(r['comparison']['strategies'][1]['unmet_demand'],Decimal('62.75'))

    def test_invalid_forecast_dates_and_total(self):
        record={'item_id':'TEST','store_id':'STORE','history_end':'2020-01-01',
                'future':[{'date':'2020-01-02','prediction':1}]*14,'total_forecast_demand':14}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'forecast.json'
            path.write_text(json.dumps([record]))
            with self.assertRaisesRegex(ValueError,'consecutive'):
                load_forecast(path,'TEST','STORE')
            with self.assertRaisesRegex(ValueError,'Unknown'):
                load_forecast(path,'WRONG','STORE')
            record['future'] = [{'date': str(date(2020,1,2)+timedelta(days=i)), 'prediction':1} for i in range(14)]
            record['total_forecast_demand'] = 15
            path.write_text(json.dumps([record]))
            with self.assertRaisesRegex(ValueError,'total disagrees'):
                load_forecast(path,'TEST','STORE')
            record['total_forecast_demand'] = 14
            path.write_text(json.dumps([record,record]))
            with self.assertRaisesRegex(ValueError,'duplicate'):
                load_forecast(path,'TEST','STORE')
            path.write_text('not json')
            with self.assertRaises(ValueError):
                load_forecast(path,'TEST','STORE')
