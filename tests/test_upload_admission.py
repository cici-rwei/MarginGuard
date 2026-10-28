"""Public admission integration using SYNTHETIC sessions and disposable storage."""
import io
import tempfile
import unittest
from unittest.mock import patch

from flask.wrappers import Request
from app import create_app
from business_api import get_business_store
from business_store import BusinessError


class UploadAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000001.0
        self.app = create_app(config={
            'TESTING': True, 'PUBLIC_MODE': True,
            'SECRET_KEY': 'SYNTHETIC-upload-admission-key-' * 3,
            'ENABLE_BUSINESS_UPLOAD': True, 'ENABLE_M5_DEMO': False,
            'ENABLE_SYNTHETIC_DEMO': True,
            'BUSINESS_STORAGE_ROOT': self.temp.name,
            'BUSINESS_CLOCK': lambda: self.now,
            'TRUSTED_HOSTS': ['review.example'],
        })
        self.client = self.app.test_client()
        self.base = 'https://review.example'
        self.csrf = self.client.get('/api/business/session', base_url=self.base).get_json()['csrf_token']
        with self.app.app_context():
            self.store = get_business_store()

    def test_public_limits_are_exposed_without_changing_session_shape(self):
        result = self.client.get('/api/business/session', base_url=self.base).get_json()
        self.assertEqual(result['limits']['file_bytes'], 1024 * 1024)
        self.assertEqual(result['limits']['rows'], 10000)
        self.assertEqual(result['limits']['series'], 20)
        self.assertNotIn('storage_path', result)

    def test_global_upload_limit_rejects_before_multipart_parsing(self):
        for _ in range(12):
            self.store.global_rate('uploads', 12, 60)
        with patch.object(Request, '_load_form_data', side_effect=AssertionError('Body must not be parsed')):
            result = self.client.post('/api/business/uploads', base_url=self.base,
                                      headers={'X-CSRF-Token': self.csrf},
                                      data={'file': (io.BytesIO(b'SYNTHETIC,fixture'), 'synthetic.csv')})
        self.assertEqual(result.status_code, 429)
        self.assertEqual(result.get_json()['code'], 'global_rate_limit')
        result.request.environ['wsgi.input'].close()

    def test_new_browser_cookies_cannot_reset_global_session_limit(self):
        # First setUp bootstrap already consumed one global slot.
        for _ in range(19):
            fresh = self.app.test_client()
            self.assertEqual(fresh.get('/api/business/session', base_url=self.base).status_code, 200)
        fresh = self.app.test_client()
        rejected = fresh.get('/api/business/session', base_url=self.base)
        self.assertEqual(rejected.status_code, 429)
        self.assertEqual(rejected.get_json()['code'], 'global_rate_limit')
        self.store.cleanup()
        self.assertEqual(fresh.get('/api/business/session', base_url=self.base).status_code, 429)

    def test_capacity_rejection_does_not_block_public_demo_or_market(self):
        for _ in range(240):
            try:
                self.store.global_rate('requests', 240, 60)
            except BusinessError:
                break
        blocked = self.client.get('/api/business/session', base_url=self.base)
        self.assertEqual(blocked.status_code, 429)
        for path in ('/api/features', '/api/demo/catalog', '/api/market/overview'):
            self.assertEqual(self.client.get(path, base_url=self.base).status_code, 200, path)
        # A new time window recovers admission without replacing an owner.
        self.now += 60
        self.assertEqual(self.client.get('/api/business/session', base_url=self.base).status_code, 200)


if __name__ == '__main__':
    unittest.main()
