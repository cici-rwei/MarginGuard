"""Business-only portfolio UI contracts; all app configuration is synthetic."""
import unittest
from app import create_app
from tests.test_product_navigation import Document


class BusinessRiskTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app(config={
            'TESTING': True, 'PUBLIC_MODE': True,
            'SECRET_KEY': 'synthetic-business-risk-ui-test-only',
            'ENABLE_M5_DEMO': False, 'ENABLE_SYNTHETIC_DEMO': True,
            'ENABLE_BUSINESS_UPLOAD': True,
        }).test_client()

    def html(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_risk_overview_only_appears_on_uploaded_business_home(self):
        self.assertIn('id="business-risk-overview"', self.html('/?mode=business'))
        for path in ('/', '/?mode=synthetic', '/market', '/inventory?mode=business', '/scenarios?mode=business'):
            with self.subTest(path=path):
                self.assertNotIn('id="business-risk-overview"', self.html(path))

    def test_risk_list_precedes_single_product_selectors_and_results(self):
        html = self.html('/?mode=business')
        self.assertLess(html.index('id="business-risk-overview"'), html.index('id="series-selection"'))
        self.assertLess(html.index('id="priority-risk-list"'), html.index('id="overview-kpis"'))
        self.assertIn('Selected product details', html)

    def test_optional_inventory_upload_has_explicit_policy_and_unchecked_zero_declaration(self):
        doc = Document(self.html('/?mode=business'))
        declaration = next(node for node in doc.root.elements() if node.attrs.get('id') == 'inventory-no-on-order')
        self.assertNotIn('checked', declaration.attrs)
        panel = next(node for node in doc.root.elements() if node.attrs.get('id') == 'inventory-upload-panel')
        self.assertNotIn('open', panel.attrs)
        for text in ('optional CSV', 'closing stock', 'unknown', 'does not replace sales history', '30-day starting assumption'):
            self.assertIn(text, panel.text())

    def test_filters_offer_only_supported_python_choices(self):
        doc = Document(self.html('/?mode=business'))
        risk = next(node for node in doc.root.elements('select') if node.attrs.get('id') == 'risk-filter')
        self.assertEqual([node.attrs['value'] for node in risk.elements('option')],
                         ['all', 'stockout', 'reorder_attention', 'excess', 'sufficient', 'not_assessed'])
        sort = next(node for node in doc.root.elements('select') if node.attrs.get('id') == 'risk-sort')
        self.assertEqual([node.attrs['value'] for node in sort.elements('option')],
                         ['priority', 'product', 'stock_asc', 'demand_desc'])

    def test_business_script_is_absent_from_demo_and_market(self):
        for path in ('/', '/?mode=synthetic', '/market', '/market?mode=business'):
            self.assertNotIn('js/business_risk.js', self.html(path))
        for path in ('/?mode=business', '/forecasting?mode=business', '/inventory?mode=business', '/scenarios?mode=business'):
            self.assertIn('js/business_risk.js', self.html(path))

    def test_no_duplicate_ids_or_new_page_route(self):
        doc = Document(self.html('/?mode=business'))
        ids = [node.attrs['id'] for node in doc.root.elements() if 'id' in node.attrs]
        self.assertEqual(len(ids), len(set(ids)))
        for path in ('/', '/forecasting', '/inventory', '/scenarios', '/market'):
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_missing_information_and_scope_are_not_presented_as_low_risk(self):
        html = self.html('/?mode=business')
        for text in ('not a low-risk result', 'not necessarily all 14 forecast days',
                     'different forecast dates', 'not a combined cash budget',
                     'KPI totals always cover the complete confirmed dataset'):
            self.assertIn(text, html)
