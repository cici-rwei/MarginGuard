"""Server-rendered UI contracts; actual interactions require browser QA too."""
import unittest
from app import create_app


class BusinessUITests(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_two_modes_and_csv_review_controls_exist_on_home(self):
        html = self.client.get('/').get_data(as_text=True)
        for marker in ('Explore Demo', 'Analyse My Business', 'csv-file',
                       'upload-currency', 'upload-time-zone', 'upload-sales-basis',
                       'upload-authorized', 'upload-report', '42 consecutive',
                       'business_context.js', 'business_upload.js'):
            self.assertIn(marker, html)

    def test_financial_page_has_explicit_handoff_and_decision_summary(self):
        html = self.client.get('/scenarios').get_data(as_text=True)
        for marker in ('Use inventory assumptions', 'Use suggested quantity',
                       'Apply reviewed inputs', 'Keep current inputs',
                       'Proposed Order Quantity', 'Purchasing Decision Summary',
                       'scenario-currency', 'historical-references'):
            self.assertIn(marker, html)

    def test_every_business_page_exposes_context_reset_and_deletion_controls(self):
        for path in ('/', '/forecasting', '/inventory', '/scenarios'):
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                for marker in ('draft-status', 'delete-business-data', 'Confirm delete',
                               'business-data-context', 'Input drafts are restored'):
                    self.assertIn(marker, html)

    def test_market_does_not_load_business_drafts_or_upload_controls(self):
        html = self.client.get('/market').get_data(as_text=True)
        for marker in ('business_context.js', 'business_upload.js', 'upload-form', 'csv-file'):
            self.assertNotIn(marker, html)
        self.assertIn('market.js', html)

    def test_public_synthetic_pages_disclose_source_before_javascript(self):
        client = create_app(config={
            'PUBLIC_MODE': True, 'SECRET_KEY': 'synthetic-test-only-key-not-a-secret',
            'ENABLE_M5_DEMO': False, 'ENABLE_SYNTHETIC_DEMO': True,
            'ENABLE_BUSINESS_UPLOAD': False,
        }).test_client()
        for path in ('/', '/forecasting', '/inventory', '/scenarios'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                for marker in ('Business data: Synthetic Demo · AUD',
                               'Fictional business', 'simulated 2024 period',
                               'No currency conversion', 'Explore Demo · Synthetic',
                               'data-demo-mode="synthetic"'):
                    self.assertIn(marker, html)
                for marker in ('Walmart M5 Demo', 'Five genuine M5',
                               'Walmart M5 observations', '14 days · USD'):
                    self.assertNotIn(marker, html)

    def test_explicit_synthetic_mode_does_not_replace_local_m5_default(self):
        client = create_app(config={
            'ENABLE_M5_DEMO': True, 'ENABLE_SYNTHETIC_DEMO': True,
        }).test_client()
        self.assertIn('Business data: Walmart M5 Demo', client.get('/').get_data(as_text=True))
        self.assertIn('Business data: Synthetic Demo · AUD',
                      client.get('/?mode=synthetic').get_data(as_text=True))
        self.assertIn('Synthetic history',
                      client.get('/forecasting?mode=synthetic').get_data(as_text=True))
        self.assertNotIn('Walmart M5 observations',
                         client.get('/?mode=business').get_data(as_text=True))

    def test_synthetic_feature_leaves_market_independent(self):
        client = create_app(config={
            'ENABLE_M5_DEMO': False, 'ENABLE_SYNTHETIC_DEMO': True,
        }).test_client()
        html = client.get('/market').get_data(as_text=True)
        self.assertIn('ABS official statistics · AUD', html)
        self.assertNotIn('Business data: Synthetic Demo', html)
        self.assertNotIn('business_context.js', html)


if __name__ == '__main__':
    unittest.main()
