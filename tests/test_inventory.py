import unittest
from decimal import Decimal
from inventory import inventory_risk


class InventoryTests(unittest.TestCase):
    def risk(self, **kwargs):
        p = dict(item_id='TEST', daily_demand=[10]*14, current_stock=80,
                 lead_time_days=7, safety_stock=20, on_order_units=0)
        p.update(kwargs)
        return inventory_risk(**p)

    def test_normal_target_and_cover(self):
        r = self.risk()
        self.assertEqual((r['average_daily_demand'], r['days_of_cover'], r['lead_time_demand']), (10, 8, 70))
        self.assertEqual((r['inventory_position'], r['target_inventory_position'], r['suggested_reorder_quantity']), (80, 90, 10))
        self.assertEqual(r['status'], 'Reorder Attention')

    def test_zero_demand(self):
        r = self.risk(daily_demand=[0]*14, safety_stock=0)
        self.assertIsNone(r['days_of_cover'])
        self.assertTrue(r['excess_inventory_warning'])
        self.assertFalse(r['stockout_risk'])
        self.assertEqual(r['suggested_reorder_quantity'], 0)

    def test_stockout_on_order_does_not_arrive_early(self):
        r = self.risk(current_stock=20, on_order_units=100)
        self.assertTrue(r['stockout_risk'])
        self.assertEqual(r['suggested_reorder_quantity'], 0)
        self.assertEqual(r['status'], 'Stockout Risk')

    def test_lead_beyond_horizon(self):
        r = self.risk(daily_demand=list(range(1,15)), lead_time_days=20)
        self.assertEqual(r['lead_time_demand'], 150)
        self.assertTrue(r['extrapolated'])

    def test_ceil_and_safety_on_order(self):
        r = self.risk(daily_demand=[Decimal('1.1')]*14, current_stock=2,
                      lead_time_days=3, safety_stock=1, on_order_units=1)
        self.assertEqual(r['suggested_reorder_quantity'], 2)
        self.assertEqual(self.risk(on_order_units=10)['suggested_reorder_quantity'], 0)
        self.assertEqual(self.risk(safety_stock=0)['suggested_reorder_quantity'], 0)

    def test_excess_threshold_and_zero_lead(self):
        self.assertTrue(self.risk(current_stock=301)['excess_inventory_warning'])
        self.assertFalse(self.risk(current_stock=300)['excess_inventory_warning'])
        self.assertEqual(self.risk(lead_time_days=0)['lead_time_demand'], 0)

    def test_invalid_inputs(self):
        for patch in [{'current_stock':-1}, {'current_stock':1.5}, {'lead_time_days':366},
                      {'safety_stock':-1}, {'on_order_units':-1}, {'excess_cover_days':0},
                      {'daily_demand':[float('nan')]*14}, {'daily_demand':[1]*13}, {'item_id':''}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.risk(**patch)
