"""Public-release configuration tests; sessions contain SYNTHETIC identity only.

These verify local Flask behaviour, not a deployed HTTPS service or M5 licence.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import ROOT, create_app


class ReleaseConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def public_app(self, **overrides):
        settings = {
            'PUBLIC_MODE': True, 'SECRET_KEY': 'SYNTHETIC-test-secret-' * 3,
            'TESTING': True, 'ENABLE_M5_DEMO': False, 'ENABLE_BUSINESS_UPLOAD': False,
            'BUSINESS_STORAGE_ROOT': self.temp.name, 'TRUSTED_HOSTS': ['preview.example'],
        }
        settings.update(overrides)
        return create_app(config=settings)

    def test_public_mode_rejects_missing_or_short_secret(self):
        for secret in (None, '', 'short', 123):
            with self.subTest(secret=secret):
                with self.assertRaisesRegex(ValueError, 'SECRET_KEY'):
                    self.public_app(SECRET_KEY=secret)

    def test_public_environment_defaults_both_release_gates_to_false(self):
        with patch.dict(os.environ, {'MARGINGUARD_PUBLIC': 'true',
                                      'MARGINGUARD_SECRET_KEY': 'SYNTHETIC-test-secret-' * 3}):
            application = create_app(config={'TESTING': True})
        self.assertTrue(application.config['PUBLIC_MODE'])
        self.assertFalse(application.config['ENABLE_BUSINESS_UPLOAD'])
        self.assertFalse(application.config['ENABLE_M5_DEMO'])

    def test_public_config_override_also_uses_safe_gate_defaults(self):
        application = create_app(config={'PUBLIC_MODE': True, 'TESTING': True,
                                         'SECRET_KEY': 'SYNTHETIC-test-secret-' * 3})
        self.assertFalse(application.config['ENABLE_BUSINESS_UPLOAD'])
        self.assertFalse(application.config['ENABLE_M5_DEMO'])

    def test_m5_gate_requires_separate_confirmed_permission(self):
        with self.assertRaisesRegex(ValueError, 'verified rights'):
            self.public_app(ENABLE_M5_DEMO=True, M5_PUBLIC_LICENSE_CONFIRMED=False)
        application = self.public_app(ENABLE_M5_DEMO=True, M5_PUBLIC_LICENSE_CONFIRMED=True)
        self.assertTrue(application.config['ENABLE_M5_DEMO'])
        self.assertFalse(application.config['ENABLE_BUSINESS_UPLOAD'])

    def test_disabled_gates_return_clear_503_without_private_store(self):
        application = self.public_app()
        client = application.test_client()
        for url in ('/api/catalog', '/api/analysis?item_id=ANY&store_id=ANY', '/api/business/session'):
            with self.subTest(url=url):
                response = client.get(url, base_url='https://preview.example')
                self.assertEqual(response.status_code, 503)
                self.assertIn('disabled', response.get_json()['error'].lower())
        self.assertFalse(any(Path(self.temp.name).iterdir()))
        self.assertEqual(client.get('/api/features', base_url='https://preview.example').get_json(),
                         {'demo_enabled': False, 'synthetic_demo_enabled': False,
                          'upload_enabled': False, 'public_mode': True})

    def test_public_session_cookie_flags_and_no_store_headers(self):
        application = self.public_app(ENABLE_BUSINESS_UPLOAD=True)
        response = application.test_client().get('/api/business/session', base_url='https://preview.example')
        self.assertEqual(response.status_code, 200, response.get_json())
        cookie = response.headers['Set-Cookie']
        for attribute in ('Secure', 'HttpOnly', 'SameSite=Lax'):
            self.assertIn(attribute, cookie)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertIn("connect-src 'self'", response.headers['Content-Security-Policy'])
        self.assertIn('max-age=', response.headers['Strict-Transport-Security'])
        self.assertFalse(application.config['DEBUG'])

    def test_trusted_host_rejects_forged_host(self):
        client = self.public_app().test_client()
        self.assertEqual(client.get('/api/features', base_url='https://preview.example').status_code, 200)
        self.assertEqual(client.get('/api/features', base_url='https://attacker.invalid').status_code, 400)
        self.assertEqual(client.get('/api/features', base_url='https://attacker.invalid',
                                    headers={'X-Forwarded-Host': 'preview.example'}).status_code, 400)

    def test_unexpected_private_error_returns_no_detail_and_is_not_logged(self):
        application = self.public_app(ENABLE_BUSINESS_UPLOAD=True)
        marker = 'SYNTHETIC-private-business-value-123'
        with patch('business_api.get_business_store', side_effect=RuntimeError(marker)):
            # Logger.handle observes actual emitted records on Python 3.9 too.
            with patch.object(application.logger, 'handle') as handle:
                response = application.test_client().get('/api/business/session', base_url='https://preview.example')
            handle.assert_not_called()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['code'], 'service_unavailable')
        self.assertNotIn(marker, response.get_data(as_text=True))
        self.assertNotIn('Traceback', response.get_data(as_text=True))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_reverse_proxy_does_not_trust_forwarded_host(self):
        client = self.public_app(TRUST_REVERSE_PROXY=True).test_client()
        response = client.get('/api/features', base_url='http://preview.example',
                              headers={'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'attacker.invalid'})
        self.assertEqual(response.status_code, 200)
        response = client.get('/api/features', base_url='http://attacker.invalid',
                              headers={'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'preview.example'})
        self.assertEqual(response.status_code, 400)

    def test_local_default_keeps_demo_available_without_public_secret(self):
        application = create_app(config={'TESTING': True})
        self.assertFalse(application.config['PUBLIC_MODE'])
        self.assertTrue(application.config['ENABLE_M5_DEMO'])
        self.assertFalse(application.config['SESSION_COOKIE_SECURE'])
        response = application.test_client().get('/api/catalog')
        if (ROOT / 'data/processed_sales.csv').exists():
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()['series'])
        else:
            self.assertEqual(response.status_code, 503)
            self.assertIn('Restore', response.get_json()['error'])

    def test_public_mode_retains_all_pages_and_abs_catalog(self):
        client = self.public_app().test_client()
        for url in ('/', '/forecasting', '/inventory', '/scenarios', '/market'):
            with self.subTest(url=url):
                self.assertEqual(client.get(url, base_url='https://preview.example').status_code, 200)
        response = client.get('/api/market/catalog', base_url='https://preview.example')
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
