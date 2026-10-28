"""AUD/USD contracts using synthetic assumptions only, never FX equivalence."""
import unittest
from decimal import Decimal

from currency import validate_currency
from finance import ProcurementConstraintError, gross_profit, lost_sales, procurement
from scenario import compare_strategies, simulate


def without_currency(value):
    """Compare arithmetic separately from the declared unit of account."""
    if isinstance(value, dict):
        return {key: without_currency(item) for key, item in value.items() if key != 'currency'}
    if isinstance(value, list):
        return [without_currency(item) for item in value]
    return value


class CurrencyTests(unittest.TestCase):
    def compare(self, **patch):
        values = dict(daily_demand=[10] * 14, current_stock=20,
                      selling_price='5.00', existing_unit_cost='1.00',
                      cash_budget=300, order_quantity=100, unit_purchase_cost='2.00',
                      freight=0, other_costs=0, moq=10, lead_time_days=7,
                      discount_percent=10, demand_uplift_percent=20)
        values.update(patch)
        return compare_strategies(**values)

    def test_declared_currency_is_strict_not_inferred(self):
        for value in ('AUD', 'USD'):
            self.assertEqual(validate_currency(value), value)
        for value in ('EUR', 'usd', ' AUD', '$', '', None, True, 1, [], {}, ['AUD']):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_currency(value)

    def test_currency_is_keyword_only_and_old_usd_calls_remain_valid(self):
        self.assertEqual(procurement(2, 100), procurement(2, 100, currency='USD'))
        self.assertEqual(gross_profit(5, 4, 2), gross_profit(5, 4, 2, currency='USD'))
        self.assertEqual(self.compare(), self.compare(currency='USD'))
        with self.assertRaises(TypeError):
            procurement(2, 100, 0, 0, 0, 'AUD')

    def test_procurement_both_currencies_preserve_decimal_cash_and_landed_cost(self):
        usd = procurement('2.10', 100, '10.25', '9.75', 100, currency='USD')
        aud = procurement('2.10', 100, '10.25', '9.75', 100, currency='AUD')
        self.assertEqual(without_currency(usd), without_currency(aud))
        self.assertEqual(aud['currency'], 'AUD')
        self.assertEqual(aud['procurement_cash_outlay'], Decimal('230.00'))
        self.assertEqual(aud['unit_landed_cost'], Decimal('2.30'))

    def test_profit_both_currencies_keep_old_and_new_inventory_cost_separate(self):
        usd = gross_profit(10, 3, 4, 2, 5, currency='USD')
        aud = gross_profit(10, 3, 4, 2, 5, currency='AUD')
        self.assertEqual(without_currency(usd), without_currency(aud))
        self.assertEqual((aud['existing_cogs'], aud['new_cogs'], aud['gross_profit'],
                          aud['gross_margin']), (12, 10, 28, 56))

    def test_full_strategy_comparison_changes_only_currency_metadata(self):
        usd, aud = self.compare(currency='USD'), self.compare(currency='AUD')
        self.assertEqual(without_currency(usd), without_currency(aud))
        self.assertEqual(aud['currency'], 'AUD')
        self.assertTrue(all(result['currency'] == 'AUD' for result in aud['strategies']))
        self.assertEqual(aud['recommendation'], 'Reorder')

    def test_simulation_default_usd_and_explicit_aud_are_numerically_identical(self):
        values = dict(daily_demand=[1] * 14, current_stock=2, selling_price=5,
                      existing_unit_cost=1, order_quantity=10, unit_purchase_cost=2,
                      freight=10, lead_time_days=2)
        usd = simulate('Reorder', **values)
        aud = simulate('Reorder', **values, currency='AUD')
        self.assertEqual(usd['currency'], 'USD')
        self.assertEqual(aud['currency'], 'AUD')
        self.assertEqual(without_currency(usd), without_currency(aud))
        self.assertEqual((aud['cogs'], aud['procurement_cash_outlay'], aud['gross_profit']),
                         (32, 30, 28))

    def test_invalid_currency_is_rejected_at_every_public_entry_point(self):
        calls = [lambda c: procurement(2, 10, currency=c),
                 lambda c: gross_profit(5, 1, 2, currency=c),
                 lambda c: simulate('Wait', [1] * 14, 5, 10, 2, currency=c),
                 lambda c: self.compare(currency=c)]
        for value in ('EUR', None, True, {}, ['USD']):
            for index, call in enumerate(calls):
                with self.subTest(value=value, entry=index), self.assertRaises(ValueError):
                    call(value)

    def test_missing_amounts_are_not_created_by_currency_support(self):
        for currency in ('AUD', 'USD'):
            with self.subTest(currency=currency):
                with self.assertRaises(ValueError):
                    procurement(None, 5, currency=currency)
                with self.assertRaises(ValueError):
                    gross_profit(5, 2, None, currency=currency)
                with self.assertRaises(ValueError):
                    self.compare(currency=currency, cash_budget='')

    def test_moq_infeasible_result_keeps_currency_and_null_amounts(self):
        for currency in ('AUD', 'USD'):
            result = self.compare(currency=currency, order_quantity=5, moq=10)
            reorder = result['strategies'][1]
            self.assertEqual(reorder['currency'], currency)
            self.assertFalse(reorder['feasible'])
            self.assertFalse(reorder['moq_satisfied'])
            self.assertIsNone(reorder['revenue'])
            self.assertIsNone(reorder['gross_profit'])
            self.assertIsNone(reorder['procurement_cash_outlay'])
            self.assertIsNone(reorder['budget_satisfied'])
            self.assertNotEqual(result['recommendation'], 'Reorder')

    def test_budget_constraint_and_recommendation_are_currency_consistent(self):
        usd = self.compare(currency='USD', cash_budget=10)
        aud = self.compare(currency='AUD', cash_budget=10)
        self.assertEqual(without_currency(usd), without_currency(aud))
        self.assertFalse(aud['strategies'][1]['feasible'])
        self.assertFalse(aud['strategies'][1]['budget_satisfied'])
        self.assertTrue(aud['strategies'][1]['moq_satisfied'])
        self.assertTrue(aud['strategies'][0]['budget_satisfied'])
        self.assertTrue(aud['strategies'][2]['budget_satisfied'])
        self.assertNotEqual(aud['recommendation'], 'Reorder')
        exact_budget = self.compare(currency='AUD', cash_budget=aud['strategies'][1]['procurement_cash_outlay'])
        self.assertTrue(exact_budget['strategies'][1]['budget_satisfied'])

    def test_zero_order_moq_and_invalid_charges_keep_the_existing_rules(self):
        for currency in ('AUD', 'USD'):
            zero = procurement(2, 0, moq=100, currency=currency)
            self.assertEqual(zero['currency'], currency)
            self.assertEqual(zero['procurement_cash_outlay'], 0)
            self.assertIsNone(zero['unit_landed_cost'])
            with self.assertRaises(ProcurementConstraintError):
                procurement(2, 0, freight=1, currency=currency)

    def test_zero_revenue_and_zero_demand_remain_defined_as_before(self):
        for currency in ('AUD', 'USD'):
            profit = gross_profit(0, 10, 2, currency=currency)
            self.assertIsNone(profit['gross_margin'])
            self.assertEqual(profit['gross_profit'], -20)
            comparison = self.compare(currency=currency, daily_demand=[0] * 14,
                                      order_quantity=0)
            self.assertEqual(comparison['recommendation'], 'Wait')
            self.assertTrue(all(item['gross_margin'] is None for item in comparison['strategies']))

    def test_delivery_and_fifo_arithmetic_do_not_depend_on_currency(self):
        for lead in (0, 7, 14, 20):
            usd = self.compare(currency='USD', current_stock=0, lead_time_days=lead)
            aud = self.compare(currency='AUD', current_stock=0, lead_time_days=lead)
            self.assertEqual(without_currency(usd), without_currency(aud))
            reorder = aud['strategies'][1]
            if lead == 7:
                self.assertTrue(all(day['units_sold'] == 0 for day in reorder['daily'][:7]))
            if lead >= 14:
                self.assertEqual(reorder['units_sold'], 0)
                self.assertEqual(reorder['cogs'], 0)
                self.assertEqual(reorder['procurement_cash_outlay'], 200)

    def test_lost_sales_remains_context_inherited_without_new_exchange_logic(self):
        self.assertEqual(lost_sales(4, 10, 6),
                         {'potential_lost_revenue': Decimal(40),
                          'potential_lost_gross_profit': Decimal(16),
                          'lost_profit_reference_unit_cost': Decimal(6)})


if __name__ == '__main__':
    unittest.main()
