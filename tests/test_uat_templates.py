"""Public business UI contracts, using fictional test configuration only.

These checks cover feature-dependent disclosure and semantic controls. Responsive
layout and changing calculations also require browser acceptance checks.
"""
import unittest

from app import create_app
from tests.test_product_navigation import Document


class PostDeploymentTemplateTests(unittest.TestCase):
    def client(self, uploads=False):
        return create_app(config={
            'TESTING': True,
            'PUBLIC_MODE': True,
            'SECRET_KEY': 'synthetic-uat-template-test-key-only',
            'ENABLE_BUSINESS_UPLOAD': uploads,
            'ENABLE_SYNTHETIC_DEMO': True,
            'ENABLE_M5_DEMO': False,
        }).test_client()

    def test_disabled_upload_entry_explains_unavailability_on_all_business_pages(self):
        client = self.client()
        for path in ('/', '/forecasting', '/inventory', '/scenarios'):
            with self.subTest(path=path):
                doc = Document(client.get(path).get_data(as_text=True))
                entry = next(node for node in doc.root.elements('a')
                             if node.attrs.get('id') == 'mode-business')
                self.assertIn('Temporarily unavailable', entry.text())
                self.assertEqual(entry.attrs.get('aria-describedby'), 'upload-availability')
                notice = next(node for node in doc.root.elements()
                              if node.attrs.get('id') == 'upload-availability')
                self.assertIn('Synthetic Demo', notice.text())
                self.assertNotIn('Upload now', doc.root.text())

    def test_enabled_upload_entry_does_not_keep_disabled_copy(self):
        client = self.client(uploads=True)
        for path in ('/', '/?mode=business', '/scenarios?mode=business'):
            with self.subTest(path=path):
                doc = Document(client.get(path).get_data(as_text=True))
                entry = next(node for node in doc.root.elements('a')
                             if node.attrs.get('id') == 'mode-business')
                self.assertEqual(entry.text(), 'Analyse My Business')
                self.assertNotIn('Temporarily unavailable', doc.root.text())
                self.assertNotIn('upload-availability', entry.attrs.values())

    def test_compact_source_details_keep_material_demo_disclosures(self):
        doc = Document(self.client().get('/').get_data(as_text=True))
        context = next(node for node in doc.root.elements()
                       if node.attrs.get('id') == 'business-data-context')
        self.assertIn('Business data: Synthetic Demo', context.text())
        details = context.elements('details')
        self.assertEqual(len(details), 1)
        for phrase in ('No real business account', 'simulated 2024 period',
                       'No currency conversion', 'demonstration assumptions'):
            self.assertIn(phrase, details[0].text())
        self.assertNotIn('open', details[0].attrs)

    def test_zero_error_explanation_is_specific_to_synthetic_demo(self):
        client = self.client()
        phrase = 'A zero validation MAE does not imply perfect accuracy on real business data.'
        for path in ('/', '/forecasting'):
            with self.subTest(path=path):
                self.assertIn(phrase, client.get(path).get_data(as_text=True))
                self.assertNotIn(phrase, client.get(path + '?mode=business').get_data(as_text=True))

    def test_inventory_explains_coverage_scope_without_changing_controls(self):
        doc = Document(self.client().get('/inventory').get_data(as_text=True))
        self.assertIn('does not necessarily mean you have enough stock for the full 14-day forecast', doc.root.text())
        self.assertIn('Supplier Delivery Time (lead time)', doc.root.text())
        self.assertIn('Backup Stock (safety stock)', doc.root.text())
        ids = {node.attrs.get('id') for node in doc.root.elements()}
        self.assertTrue({'inventory-form', 'inventory-fields', 'inventory-results',
                         'inventory-coverage', 'inventory-notes'}.issubset(ids))

    def test_financial_comparison_supports_mobile_cards_and_explicit_confirmation(self):
        doc = Document(self.client().get('/scenarios').get_data(as_text=True))
        ids = {node.attrs.get('id') for node in doc.root.elements()}
        self.assertTrue({'scenario-table', 'scenario-cards', 'handoff-differences',
                         'handoff-preview', 'confirm-handoff', 'cancel-handoff'}.issubset(ids))
        for phrase in ('Use inventory assumptions', 'Keep current inputs',
                       'cost of goods actually sold (COGS)',
                       'not the same as the cost of stock sold'):
            self.assertIn(phrase, doc.root.text())

    def test_upload_explains_early_data_loss_and_explicit_deletion(self):
        doc = Document(self.client(uploads=True).get('/?mode=business').get_data(as_text=True))
        # Part B changes this new Part A contract: the session API now supplies
        # capacity/TTL copy; Node tests verify both public and local TTL values.
        for phrase in ('service restarts or sleeps', 'Closing a tab is not a deletion request',
                       'Use Delete uploaded data', 'session expiry limits will appear'):
            self.assertIn(phrase, doc.root.text())
        ids = {node.attrs.get('id') for node in doc.root.elements()}
        self.assertTrue({'upload-expiry', 'upload-limits'}.issubset(ids))


if __name__ == '__main__':
    unittest.main()
