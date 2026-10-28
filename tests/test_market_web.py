"""Read-only ABS API regression tests against the delivered Phase 4A snapshot."""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import ROOT, create_app


class MarketWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(ROOT / 'data/abs/market_data.json.gz', 'rt', encoding='utf-8') as stream:
            cls.snapshot = json.load(stream)
        cls.by_id = {s['series_id']: s for s in cls.snapshot['series']}
        cls.counts = json.loads((ROOT / 'data/abs/business_counts.json').read_text())
        cls.client = create_app().test_client()

    def get_json(self, path, params=None):
        response = self.client.get('/api/market/' + path, query_string=params)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def get_series(self, series_id, **params):
        s = self.by_id[series_id]
        return self.get_json('series', dict(dataset_id=s['dataset_id'], series_id=series_id, **params))

    def comparison_params(self, **patch):
        return dict(dict(dataset_id='abs_mhsi', table_id='2', measure='household_spending',
                         adjustment='Seasonally Adjusted', period='2026-08', growth='year',
                         group='category', geography='Australia'), **patch)

    def assert_bad_request(self, path, params):
        response = self.client.get('/api/market/' + path, query_string=params)
        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        self.assertIsInstance(response.get_json().get('error'), str)

    def test_five_pages_and_market_assets(self):
        for path in ('/', '/forecasting', '/inventory', '/scenarios', '/market',
                     '/static/js/market.js', '/static/css/market.css'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                if not path.startswith('/static/'):
                    self.assertIn('Market Intelligence', response.get_data(as_text=True))
                response.close()
        page = self.client.get('/market').get_data(as_text=True)
        self.assertIn('Australian Retail Market Overview', page)
        self.assertIn('Experimental', page)
        self.assertNotIn('id="product"', page)

    def test_catalog_preserves_series_dimensions_without_values(self):
        result = self.get_json('catalog')
        self.assertEqual(len(result['series']), len(self.by_id))
        self.assertEqual(result['as_of'], self.snapshot['as_of'])
        for s in result['series']:
            expected = self.by_id[s['series_id']]
            for field in ('dataset_id', 'frequency', 'adjustment', 'unit', 'classification',
                          'price_basis', 'experimental', 'table_ids', 'source_ids'):
                self.assertEqual(s[field], expected[field])
            self.assertNotIn('values', s)
        self.assertEqual(result['counts']['financial_years'],
                         [r['period'] for r in self.counts['annual_flows']['observations']])

    def test_overview_kpis_match_exact_snapshot_and_reference_periods(self):
        result = self.get_json('overview')
        self.assertEqual(len(result['kpis']), 4)
        actual = {k['series_id']: k for k in result['kpis']}
        self.assertIn('A130200584T', actual)
        self.assertIn('A130276228K', actual)
        self.assertIn('A3531382W', actual)
        for sid, kpi in actual.items():
            source = self.by_id[sid]
            self.assertEqual(kpi['period'], source['periods'][-1])
            self.assertEqual(kpi['value'], source['values'][-1])
            for field in ('unit', 'adjustment', 'experimental', 'source_ids'):
                self.assertEqual(kpi[field], source[field])
        self.assertEqual(actual['A130200584T']['period'], '2026-08')
        self.assertEqual(actual['A3531382W']['period'], '2026-Q2')
        self.assertTrue(actual['A130276228K']['experimental'])

    def test_selected_month_changes_values_and_growth(self):
        previous = self.get_series('A130200584T', start='2026-07', end='2026-07')
        current = self.get_series('A130200584T', start='2026-08', end='2026-08')
        self.assertNotEqual(previous['latest']['value'], current['latest']['value'])
        for result, month in ((previous, '2026-07'), (current, '2026-08')):
            expected = self.by_id['A130200584T']
            i = expected['periods'].index(month)
            self.assertEqual(result['series']['periods'], [month])
            self.assertEqual(result['latest']['value'], expected['values'][i])
            for field in ('period_change_pct', 'year_change_pct'):
                self.assertEqual(result['latest'][field], expected['derived'][field][i])
            # A one-month view still uses the full prior history, not the display range.
            self.assertIsNotNone(result['latest']['year_change_pct'])

    def test_growth_is_percentage_not_percentage_point_change(self):
        result = self.get_series('A130200584T', start='2026-08', end='2026-08')
        values = self.by_id['A130200584T']['values']
        self.assertAlmostEqual(result['latest']['period_change_pct'],
                               (values[-1] / values[-2] - 1) * 100, places=6)
        self.assertAlmostEqual(result['latest']['year_change_pct'],
                               (values[-1] / values[-13] - 1) * 100, places=6)

    def test_original_and_seasonally_adjusted_are_separate(self):
        original = self.get_series('A130207496V')['series']
        adjusted = self.get_series('A130200584T')['series']
        self.assertEqual(original['adjustment'], 'Original')
        self.assertEqual(adjusted['adjustment'], 'Seasonally Adjusted')
        self.assertNotEqual(original['series_id'], adjusted['series_id'])
        self.assertNotEqual(original['values'][-1], adjusted['values'][-1])

    def test_missing_values_and_last_period_never_backfilled(self):
        expected = self.by_id['A3531399T']
        missing = next(p for p, v in zip(expected['periods'], expected['values']) if v is None)
        result = self.get_series('A3531399T', start=missing, end=missing)
        self.assertEqual(result['series']['periods'], [missing])
        self.assertEqual(result['series']['values'], [None])
        self.assertEqual(result['latest']['period'], missing)
        self.assertIsNone(result['latest']['value'])
        self.assertIsNone(result['latest']['year_change_pct'])
        self.assertTrue(result['insights'])
        self.assertRegex(' '.join(result['insights']).lower(), r'unavailable|insufficient|cannot|missing')

    def test_categories_compare_only_coicop_and_python_sorted_growth(self):
        result = self.get_json('compare', self.comparison_params())
        self.assertEqual(len(result['rows']), 9)
        self.assertFalse(result['experimental'])
        rates = []
        for row in result['rows']:
            expected = self.by_id[row['series_id']]
            self.assertEqual(expected['classification'], 'COICOP')
            self.assertIn(2, expected['table_ids'])
            i = expected['periods'].index('2026-08')
            self.assertEqual(row['value'], expected['values'][i])
            self.assertEqual(row['growth_pct'], expected['derived']['year_change_pct'][i])
            rates.append(row['growth_pct'])
        self.assertEqual(rates, sorted(rates, reverse=True))
        self.assertIn(result['rows'][0]['name'], ' '.join(result['insights']))

    def test_month_and_growth_switch_change_comparison_results(self):
        yearly = self.get_json('compare', self.comparison_params())
        monthly = self.get_json('compare', self.comparison_params(growth='period'))
        earlier = self.get_json('compare', self.comparison_params(period='2026-07'))
        by_id = lambda result: {r['series_id']: r['growth_pct'] for r in result['rows']}
        self.assertNotEqual(by_id(yearly), by_id(monthly))
        self.assertNotEqual(by_id(yearly), by_id(earlier))
        for row in monthly['rows']:
            self.assertEqual(row['growth_pct'], self.by_id[row['series_id']]['derived']['period_change_pct'][-1])

    def test_experimental_retail_industry_is_distinct_from_coicop(self):
        result = self.get_json('compare', self.comparison_params(table_id='19', measure='retail_turnover'))
        self.assertTrue(result['experimental'])
        self.assertTrue(result['rows'])
        for row in result['rows']:
            s = self.by_id[row['series_id']]
            self.assertEqual(s['classification'], 'ANZSIC_retail_groups')
            self.assertNotEqual(s['category'], 'Total (Industry)')
            detail = self.get_series(s['series_id'], start='2026-07', end='2026-08')
            self.assertTrue(detail['series']['experimental'])
        industry_ids = {r['series_id'] for r in result['rows']}
        category_ids = {r['series_id'] for r in self.get_json('compare', self.comparison_params())['rows']}
        self.assertFalse(industry_ids & category_ids)

    def test_selected_industry_changes_actual_series(self):
        selected = [s for s in self.snapshot['series'] if s['dataset_id'] == 'abs_mhsi'
                    and 19 in s['table_ids'] and s['geography'] == 'Australia'
                    and s['adjustment'] == 'Seasonally Adjusted'
                    and s['category'] != 'Total (Industry)'][:2]
        first, second = [self.get_series(s['series_id'], start='2026-08', end='2026-08') for s in selected]
        self.assertNotEqual(first['series']['category'], second['series']['category'])
        self.assertNotEqual(first['latest']['value'], second['latest']['value'])

    def test_states_growth_not_amount_ranking_and_state_switch(self):
        params = self.comparison_params(table_id='states', group='geography',
                                        category='Total (Household Spending Categories)')
        params.pop('geography')
        result = self.get_json('compare', params)
        self.assertEqual({r['name'] for r in result['rows']},
                         {'New South Wales', 'Victoria', 'Queensland', 'South Australia',
                          'Western Australia', 'Tasmania', 'Northern Territory',
                          'Australian Capital Territory'})
        for row in result['rows']:
            self.assertEqual(row['growth_pct'], self.by_id[row['series_id']]['derived']['year_change_pct'][-1])
        rates = [r['growth_pct'] for r in result['rows']]
        self.assertEqual(rates, sorted(rates, reverse=True))
        nsw = self.get_series('A130203272K', end='2026-08')
        vic = self.get_series('A130201352X', end='2026-08')
        self.assertNotEqual(nsw['latest']['value'], vic['latest']['value'])
        self.assertEqual(nsw['series']['geography'], 'New South Wales')
        self.assertEqual(vic['series']['geography'], 'Victoria')

    def test_state_category_switch_matches_corresponding_series(self):
        params = self.comparison_params(table_id='states', group='geography', category='Food')
        params.pop('geography')
        result = self.get_json('compare', params)
        self.assertEqual(len(result['rows']), 8)
        for row in result['rows']:
            self.assertEqual(self.by_id[row['series_id']]['category'], 'Food')

    def test_quarterly_financial_metrics_preserve_definition_and_units(self):
        for sid in ('A3531380T', 'A3531378F', 'A3531381V', 'A3531379J'):
            with self.subTest(series_id=sid):
                result = self.get_series(sid, start='2026-Q1', end='2026-Q2')
                self.assertEqual(result['series']['frequency'], 'quarterly')
                self.assertEqual(result['series']['unit'], 'AUD million')
                self.assertEqual(result['series']['values'], self.by_id[sid]['values'][-2:])
                self.assertEqual(result['latest']['period_change_pct'],
                                 self.by_id[sid]['derived']['period_change_pct'][-1])
        self.assertEqual(self.get_series('A3531381V')['series']['measure'],
                         'business_gross_operating_profits')

    def test_official_inventory_sales_ratio_is_not_a_risk_score(self):
        result = self.get_series('A3531382W', start='2026-Q1', end='2026-Q2')
        self.assertEqual(result['series']['values'], self.by_id['A3531382W']['values'][-2:])
        self.assertEqual(result['series']['unit'], 'ratio')
        self.assertEqual(result['latest']['value'], 0.32)
        self.assertNotIn('risk_score', result)
        self.assertNotIn('risk_status', result)
        self.assertTrue(result['insights'])

    def test_business_year_selection_and_fixed_cohorts(self):
        for year in ('2022-23', '2025-26'):
            result = self.get_json('business-counts', {'financial_year': year})
            rows = result['annual_flows']['observations']
            expected = next(r for r in self.counts['annual_flows']['observations'] if r['period'] == year)
            self.assertEqual(rows, [expected])
            self.assertEqual(result['survival_cohorts'], self.counts['survival_cohorts'])
            self.assertEqual(expected['opening'] + expected['entries_total'] - expected['exits_total'],
                             expected['closing'])
        self.assertNotEqual(self.counts['survival_cohorts'][0]['cohort_size'],
                            self.counts['survival_cohorts'][1]['cohort_size'])

    def test_sources_release_dates_and_licence_are_retained(self):
        result = self.get_json('sources')
        sources = {s['source_id']: s for s in result['sources']}
        self.assertEqual(len(sources), 17)
        for source in sources.values():
            self.assertTrue(source['url'].startswith('https://www.abs.gov.au/'))
            self.assertLessEqual(source['release_date'], result['as_of'])
            self.assertLessEqual(source['reference_end_date'], source['release_date'])
            self.assertIn('CC BY 4.0', source['license'])
        series = self.get_series('A130200584T')
        self.assertEqual({s['source_id'] for s in series['sources']},
                         set(series['series']['source_ids']))

    def test_series_rejects_invalid_unknown_repeated_and_file_parameters(self):
        valid = {'dataset_id': 'abs_mhsi', 'series_id': 'A130200584T'}
        cases = [{}, {'dataset_id': 'abs_mhsi'}, dict(valid, series_id='unknown'),
                 dict(valid, dataset_id='abs_business_indicators'), dict(valid, path='/etc/passwd'),
                 dict(valid, series_id='../../data/raw/sales_train_validation.csv'),
                 dict(valid, start='2026-13'), dict(valid, start='2026-08', end='2026-07'),
                 dict(valid, end='2099-12'), dict(valid, start='2026-Q1'), dict(valid, start=''),
                 list(valid.items()) + [('series_id', 'A130200584T')]]
        for case in cases:
            with self.subTest(case=case):
                self.assert_bad_request('series', case)

    def test_compare_rejects_cross_classification_and_invalid_dimensions(self):
        for patch in ({'dataset_id': 'walmart_m5'}, {'table_id': '23'}, {'growth': 'forecast'},
                      {'adjustment': 'Adjusted'}, {'period': '2026-Q2'}, {'period': '2099-01'},
                      {'geography': 'Unknown'}, {'category': 'Not a category'}, {'group': 'file'},
                      {'measure': 'business_sales'}, {'file': '/etc/passwd'}):
            with self.subTest(patch=patch):
                self.assert_bad_request('compare', self.comparison_params(**patch))
        self.assert_bad_request('compare', list(self.comparison_params().items()) + [('period', '2026-07')])

    def test_simple_routes_reject_unrecognized_arguments_and_mutations(self):
        for endpoint in ('catalog', 'overview', 'sources', 'business-counts'):
            with self.subTest(endpoint=endpoint):
                self.assert_bad_request(endpoint, {'filename': '../../anything'})
                response = self.client.post('/api/market/' + endpoint, json={})
                self.assertEqual(response.status_code, 405)
        self.assert_bad_request('business-counts', {'financial_year': '2026-27'})
        self.assert_bad_request('business-counts', [('financial_year', '2025-26'), ('financial_year', '2025-26')])

    def test_missing_abs_files_fail_clearly_without_hiding_market_page(self):
        with tempfile.TemporaryDirectory() as temp:
            client = create_app(temp).test_client()
            self.assertEqual(client.get('/market').status_code, 200)
            for endpoint in ('catalog', 'overview', 'sources', 'business-counts'):
                response = client.get('/api/market/' + endpoint)
                self.assertEqual(response.status_code, 503)
                self.assertIsInstance(response.get_json().get('error'), str)
                self.assertNotIn(temp, response.get_json()['error'])

    def test_market_runtime_does_not_import_excel_processing_dependencies(self):
        code = ('import sys; from app import create_app; '
                'c=create_app().test_client(); '
                'assert c.get("/api/market/overview").status_code==200; '
                'assert "pandas" not in sys.modules; assert "openpyxl" not in sys.modules')
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_prepared_snapshot_is_cached_between_requests(self):
        client = create_app().test_client()
        self.assertEqual(client.get('/api/market/overview').status_code, 200)
        with patch('market_service.gzip.open', side_effect=AssertionError('Unexpected reload')), \
                patch('market_service.Path.read_text', side_effect=AssertionError('Unexpected reload')):
            for endpoint in ('catalog', 'overview', 'sources', 'business-counts'):
                self.assertEqual(client.get('/api/market/' + endpoint).status_code, 200)

    def test_corrupt_prepared_data_returns_safe_service_error(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'abs'
            directory.mkdir()
            (directory / 'market_data.json.gz').write_bytes(b'not a gzip file')
            response = create_app(temp).test_client().get('/api/market/overview')
            self.assertEqual(response.status_code, 503)
            self.assertIn('ABS', response.get_json()['error'])
            self.assertNotIn(temp, response.get_json()['error'])


if __name__ == '__main__':
    unittest.main()
