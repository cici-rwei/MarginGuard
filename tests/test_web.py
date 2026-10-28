"""Flask integration tests compare HTTP responses to the unchanged Python engines."""
import json
import tempfile
import unittest
from pathlib import Path
from app import create_app, serial, ROOT
from data_loader import load_series
from forecast import analyse
from inventory import inventory_risk
from scenario import compare_strategies


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT/'data/processed_sales.csv').exists():
            raise unittest.SkipTest('Local processed M5 data required for Web integration tests.')
        cls.groups=load_series(ROOT/'data/processed_sales.csv')
        cls.defaults=json.loads((ROOT/'data/scenario_defaults.json').read_text())

    def setUp(self):
        self.client=create_app().test_client()
        self.key={'item_id':'FOODS_3_252','store_id':'CA_1'}
        self.values=[r['prediction'] for r in analyse(self.groups[('FOODS_3_252','CA_1')])['future']]

    def params(self):
        d=self.defaults
        names=('current_stock','existing_unit_cost','cash_budget','order_quantity','unit_purchase_cost','freight','other_costs','moq','lead_time_days','discount_percent','demand_uplift_percent','max_unmet_units')
        return dict(self.key,selling_price='1.58',**{k:d[k] for k in names})

    def test_four_pages_and_static_assets(self):
        for path in ('/','/forecasting','/inventory','/scenarios','/static/css/style.css','/static/js/main.js'):
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                response.close()

    def test_catalog_real_series(self):
        r=self.client.get('/api/catalog').get_json()
        self.assertEqual(len(r['series']),5)
        self.assertEqual({(x['item_id'],x['store_id']) for x in r['series']},set(self.groups))

    def test_analysis_matches_engine_and_switches(self):
        totals=[]
        for item,store in self.groups:
            r=self.client.get('/api/analysis',query_string={'item_id':item,'store_id':store})
            self.assertEqual(r.status_code,200)
            expected=analyse(self.groups[(item,store)])
            self.assertEqual(r.get_json()['analysis'],serial(expected))
            totals.append(r.get_json()['analysis']['total_forecast_demand'])
        self.assertEqual(len(set(totals)),5)

    def test_inventory_matches_engine_and_recalculates(self):
        for stock in (0,200,1000):
            p=dict(self.key,current_stock=stock,lead_time_days=20,safety_stock=40,on_order_units=10,excess_cover_days=30)
            r=self.client.post('/api/inventory',json=p)
            expected=inventory_risk(p['item_id'],self.values,stock,20,40,10,30)
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.get_json(),serial(expected))

    def test_scenarios_exact_engine_match(self):
        p=self.params()
        r=self.client.post('/api/scenarios',json=p)
        expected=compare_strategies(self.values,**{k:v for k,v in p.items() if k not in self.key})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.get_json(),serial(expected))

    def test_budget_and_moq_constraints(self):
        for patch in ({'cash_budget':1},{'order_quantity':1,'moq':100}):
            p=dict(self.params(),**patch)
            r=self.client.post('/api/scenarios',json=p).get_json()
            self.assertFalse(r['strategies'][1]['feasible'])
            self.assertNotEqual(r['recommendation'],'Reorder')

    def test_zero_service_limit_not_ignored(self):
        p=dict(self.params(),current_stock=0,order_quantity=0,freight=0,other_costs=0,max_unmet_units=0)
        r=self.client.post('/api/scenarios',json=p).get_json()
        self.assertIsNone(r['recommendation'])
        self.assertTrue(all(not s['feasible'] for s in r['strategies']))

    def test_invalid_parameters(self):
        for patch in ({'current_stock':-1},{'discount_percent':101},{'unit_purchase_cost':'NaN'},
                      {'lead_time_days':1.5},{'cash_budget':'Infinity'},{'current_stock':True},
                      {'selling_price':None},{'selling_price':''}):
            with self.subTest(patch=patch):
                r=self.client.post('/api/scenarios',json=dict(self.params(),**patch))
                self.assertEqual(r.status_code,400)
                self.assertIn('error',r.get_json())

    def test_unknown_missing_selection_and_inputs(self):
        for q in ({},{'item_id':'WRONG','store_id':'CA_1'},{'item_id':'FOODS_3_252'}):
            self.assertEqual(self.client.get('/api/analysis',query_string=q).status_code,400)
        self.assertEqual(self.client.post('/api/inventory',json=self.key).status_code,400)

    def test_malformed_request(self):
        for kwargs in ({'json':[]},{'data':'invalid','content_type':'application/json'},{'data':'abc'}):
            r=self.client.post('/api/scenarios',**kwargs)
            self.assertEqual(r.status_code,400)
            self.assertIn('error',r.get_json())

    def test_missing_and_invalid_dataset_clear_error(self):
        with tempfile.TemporaryDirectory() as temp:
            c=create_app(temp).test_client()
            self.assertEqual(c.get('/').status_code,200)
            r=c.get('/api/catalog')
            self.assertEqual(r.status_code,503)
            self.assertIn('Restore',r.get_json()['error'])
            (Path(temp)/'processed_sales.csv').write_text('wrong\n1\n')
            self.assertEqual(c.get('/api/catalog').status_code,503)

    def test_delayed_arrival_via_api(self):
        p=dict(self.params(),current_stock=0,lead_time_days=7)
        r=self.client.post('/api/scenarios',json=p).get_json()['strategies'][1]
        self.assertTrue(all(d['units_sold']=='0' for d in r['daily'][:7]))
        self.assertEqual(r['daily'][7]['received_units'],350)
