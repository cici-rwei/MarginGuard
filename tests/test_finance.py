import unittest
from decimal import Decimal
from finance import procurement, gross_profit, lost_sales, ProcurementConstraintError


class FinanceTests(unittest.TestCase):
    def test_landed_cost_and_cash(self):
        r = procurement('2', 100, 20, 30, 100)
        self.assertEqual(r['unit_landed_cost'], Decimal('2.5'))
        self.assertEqual(r['procurement_cash_outlay'], 250)

    def test_profit_and_margin(self):
        r = gross_profit(10, 3, 4, 2, 5)
        self.assertEqual((r['revenue'], r['cogs'], r['gross_profit'], r['gross_margin']), (50,22,28,56))

    def test_cash_is_not_all_cogs(self):
        purchase = procurement(2, 100, 100)
        r = gross_profit(5, 10, 1, 10, purchase['unit_landed_cost'])
        self.assertEqual(purchase['procurement_cash_outlay'], 300)
        self.assertEqual((r['existing_cogs'],r['new_cogs'],r['gross_profit']), (10,30,60))

    def test_moq_and_zero_order(self):
        with self.assertRaises(ProcurementConstraintError):
            procurement(2,9,moq=10)
        r = procurement(2,0,moq=10)
        self.assertEqual(r['procurement_cash_outlay'],0)
        self.assertIsNone(r['unit_landed_cost'])
        with self.assertRaises(ProcurementConstraintError):
            procurement(2,0,freight=1)

    def test_zero_revenue(self):
        r = gross_profit(0,10,2)
        self.assertIsNone(r['gross_margin'])
        self.assertEqual(r['gross_profit'],-20)

    def test_lost_sales_values(self):
        r = lost_sales(4,10,6)
        self.assertEqual((r['potential_lost_revenue'],r['potential_lost_gross_profit']), (40,16))
        self.assertEqual(lost_sales(4,1,2)['potential_lost_gross_profit'],-4)

    def test_invalid_inputs_and_missing_new_cost(self):
        for value in (-1,'NaN','Infinity',True,'bad'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                procurement(value,10)
        with self.assertRaises(ValueError):
            gross_profit(5,1,2,new_units_sold=1)
        with self.assertRaises(ValueError):
            procurement(2,1.5)
