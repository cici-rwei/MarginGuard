"""Deadline UI contracts; app configuration uses fictional test settings only."""
import unittest
from app import create_app
from tests.test_product_navigation import Document


class InventoryUploadEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app(config={
            'TESTING': True, 'PUBLIC_MODE': True,
            'SECRET_KEY': 'synthetic-deadline-template-test-only',
            'ENABLE_M5_DEMO': False, 'ENABLE_SYNTHETIC_DEMO': True,
            'ENABLE_BUSINESS_UPLOAD': True,
        }).test_client()

    def html(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_inventory_entry_precedes_product_form_and_uses_existing_upload(self):
        html = self.html('/inventory?mode=business')
        self.assertLess(html.index('id="inventory-upload-panel"'), html.index('id="series-selection"'))
        self.assertLess(html.index('id="inventory-upload-panel"'), html.index('id="inventory-form"'))
        self.assertIn('Upload Inventory CSV', html)
        self.assertIn('/api/business/inventory-template.csv', html)
        self.assertNotIn('id="business-risk-overview"', html)
        doc = Document(html)
        panel = next(node for node in doc.root.elements() if node.attrs.get('id') == 'inventory-upload-panel')
        self.assertIn('open', panel.attrs)
        self.assertIn('hidden', panel.attrs)  # Revealed after the owned dataset is loaded.
        self.assertIn('does not replace sales history', panel.text())
        self.assertIn('Inventory: Unknown', panel.text())

    def test_inventory_and_overview_share_one_upload_form_per_page(self):
        for path in ('/inventory?mode=business', '/?mode=business'):
            with self.subTest(path=path):
                html = self.html(path)
                self.assertEqual(html.count('id="inventory-upload-form"'), 1)
                ids = [node.attrs['id'] for node in Document(html).root.elements() if 'id' in node.attrs]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertIn('id="inventory-upload-errors"', html)
                self.assertIn('id="inventory-file-status"', html)

    def test_demo_inventory_and_other_workspaces_keep_their_existing_flow(self):
        for path in ('/inventory', '/inventory?mode=synthetic', '/scenarios?mode=business', '/market'):
            with self.subTest(path=path):
                self.assertNotIn('id="inventory-upload-form"', self.html(path))
        self.assertIn('id="inventory-form"', self.html('/inventory?mode=synthetic'))

    def test_missing_on_order_is_still_explicit_and_never_implicitly_zero(self):
        html = self.html('/inventory?mode=business')
        doc = Document(html)
        declaration = next(node for node in doc.root.elements('input') if node.attrs.get('id') == 'inventory-no-on-order')
        self.assertNotIn('checked', declaration.attrs)
        self.assertIn('Unknown values stay unknown', html)
        self.assertIn('A different date cannot be assessed automatically', html)
