"""Controlled public upload gate tests use SYNTHETIC keys and CSV fixtures only.

They are local integration tests, not a claim that Render has been tested or
that public CSV uploads have been enabled.
"""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from business_api import get_business_store
from business_store import owner_key
from tests.business_fixtures import csv_bytes, synthetic_rows
from tests.test_product_navigation import Document


class UploadReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000000
        self.key = 'b' * 64  # SYNTHETIC test credential, never a deployment key.
        self.key_hash = hashlib.sha256(self.key.encode('ascii')).hexdigest()
        self.config = {
            'TESTING': True, 'PUBLIC_MODE': True,
            'SECRET_KEY': 'synthetic-upload-review-signing-key-only',
            'ENABLE_M5_DEMO': False, 'ENABLE_SYNTHETIC_DEMO': True,
            'ENABLE_BUSINESS_UPLOAD': False,
            'BUSINESS_STORAGE_ROOT': self.temp.name,
            'BUSINESS_CLOCK': lambda: self.now,
            'UPLOAD_REVIEW_CLOCK': lambda: self.now,
            'UPLOAD_REVIEW_ENABLED': True,
            'UPLOAD_REVIEW_KEY_SHA256': self.key_hash,
            'UPLOAD_REVIEW_DEADLINE': self.now + 600,
            'UPLOAD_REVIEW_GRANT_TTL': 120,
        }
        self.app = create_app(config=self.config)
        self.client = self.app.test_client()

    def get(self, path, client=None, **kwargs):
        return (client or self.client).get(path, base_url='https://localhost', **kwargs)

    def bootstrap(self, client=None, key=None, **kwargs):
        return self.get('/api/business/session', client,
                        headers={'X-Upload-Review-Key': self.key if key is None else key, **kwargs})

    def enabled(self, client=None):
        return self.get('/api/features', client).get_json()['upload_enabled']

    def upload(self, client=None, csrf=None, extra_headers=None):
        headers = dict(extra_headers or {})
        if csrf is not None:
            headers['X-CSRF-Token'] = csrf
        return (client or self.client).post('/api/business/uploads', base_url='https://localhost',
            headers=headers, data={
                'currency': 'AUD', 'time_zone': 'Australia/Sydney', 'tax_basis': 'exclusive',
                'sales_basis': 'gross_units', 'authorized': 'true',
                'file': (io.BytesIO(csv_bytes(synthetic_rows(42))), 'SYNTHETIC_REVIEW.csv'),
            })

    def test_default_disabled_review_does_not_change_public_flags_or_create_storage(self):
        app = create_app(config=dict(self.config, UPLOAD_REVIEW_ENABLED=False,
                                     UPLOAD_REVIEW_KEY_SHA256='', UPLOAD_REVIEW_DEADLINE=0))
        client = app.test_client()
        self.assertFalse(self.enabled(client))
        self.assertEqual(self.bootstrap(client).status_code, 503)
        self.assertNotIn('upload-review-form', self.get('/?mode=business&review=1', client).text)
        self.assertNotIn('business_store', app.extensions)

    def test_review_page_is_opt_in_and_never_renders_credentials(self):
        for path in ('/', '/?mode=business', '/scenarios?mode=business&review=1', '/market?review=1'):
            with self.subTest(path=path):
                self.assertNotIn('upload-review-form', self.get(path).text)
        html = self.get('/?mode=business&review=1').text
        self.assertIn('Restricted upload acceptance test', html)
        self.assertIn('Public CSV uploads are still closed', html)
        self.assertNotIn(self.key, html)
        self.assertNotIn(self.key_hash, html)
        doc = Document(html)
        key_input = next(e for e in doc.root.elements('input') if e.attrs.get('id') == 'upload-review-key')
        self.assertEqual(key_input.attrs['type'], 'password')
        self.assertNotIn('name', key_input.attrs)  # Cannot enter a native form URL.
        self.assertNotIn('value', key_input.attrs)
        form = next(e for e in doc.root.elements('form') if e.attrs.get('id') == 'upload-review-form')
        self.assertEqual(form.attrs['method'], 'post')
        self.assertIn('Temporarily unavailable', html)

    def test_key_in_query_or_wrong_header_cannot_bootstrap(self):
        self.assertEqual(self.get('/api/business/session?review_key=' + self.key).status_code, 503)
        for bad in ('x', 'c' * 64, self.key_hash, 'é' * 64):
            with self.subTest(key_type='synthetic invalid'):
                self.assertEqual(self.bootstrap(key=bad).status_code, 403)
        self.assertFalse(self.enabled())
        self.assertNotIn('business_store', self.app.extensions)

    def test_bootstrap_requires_https_and_same_origin(self):
        response = self.client.get('/api/business/session',
                                   headers={'X-Upload-Review-Key': self.key}, base_url='http://localhost')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.bootstrap(Origin='https://other.invalid').status_code, 403)
        self.assertEqual(self.bootstrap(**{'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
        self.assertNotIn('business_store', self.app.extensions)

    def test_bootstrap_enables_only_its_live_owner_and_does_not_return_key(self):
        response = self.bootstrap()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.get_json()), {'csrf_token', 'expires_at', 'absolute_expires_at',
                                                   'active_dataset', 'limits'})
        self.assertNotIn(self.key, response.text)
        self.assertIn('Secure', response.headers['Set-Cookie'])
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertIn('SameSite=Lax', response.headers['Set-Cookie'])
        self.assertTrue(self.enabled())
        other = self.app.test_client()
        self.assertFalse(self.enabled(other))
        self.assertEqual(self.get('/api/business/session', other).status_code, 503)
        self.assertFalse(self.app.config['ENABLE_BUSINESS_UPLOAD'])
        with self.client.session_transaction(base_url='https://localhost') as values:
            grant = values['upload_review']
            self.assertNotIn(self.key, repr(dict(values)))
            self.assertEqual(grant['key_version'], self.key_hash)
            self.assertEqual(grant['owner'], owner_key(values['business_owner']))
            self.assertEqual(grant['expires'], self.now + 120)
        html = self.get('/?mode=business').text
        self.assertIn('Controlled acceptance test only', html)
        self.assertNotIn('Temporarily unavailable', html)
        features = self.get('/api/features')
        self.assertEqual(features.headers['Cache-Control'], 'no-store')
        self.assertIn('Cookie', features.headers['Vary'])
        self.assertEqual(self.get('/?mode=business').headers['Cache-Control'], 'no-store')

    def test_review_key_does_not_bypass_csrf_or_owner_isolation(self):
        csrf = self.bootstrap().get_json()['csrf_token']
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.upload(csrf='f' * 64).status_code, 403)
        # The key is only exchanged at GET /session, never an upload capability.
        self.assertEqual(self.upload(csrf=csrf, extra_headers={'X-Upload-Review-Key': self.key}).status_code, 403)
        upload = self.upload(csrf=csrf)
        self.assertEqual(upload.status_code, 201, upload.text)
        pending = upload.get_json()
        other = self.app.test_client()
        other_csrf = self.bootstrap(other).get_json()['csrf_token']
        response = other.delete('/api/business/uploads/' + pending['upload_id'],
                                base_url='https://localhost', headers={'X-CSRF-Token': other_csrf})
        self.assertEqual(response.status_code, 404)
        response = self.client.delete('/api/business/uploads/' + pending['upload_id'],
                                      base_url='https://localhost', headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 204)

    def test_grant_expiry_does_not_silently_bootstrap_a_new_owner(self):
        self.bootstrap()
        with self.client.session_transaction(base_url='https://localhost') as values:
            original_owner = values['business_owner']
        self.now += 121
        self.assertFalse(self.enabled())
        self.assertEqual(self.get('/api/business/session').status_code, 503)
        with self.client.session_transaction(base_url='https://localhost') as values:
            self.assertEqual(values['business_owner'], original_owner)
        self.assertEqual(self.bootstrap().status_code, 200)
        self.assertTrue(self.enabled())

    def test_deadline_rotation_and_disabling_revoke_existing_grants(self):
        self.bootstrap()
        replacement_key = 'd' * 64
        self.app.config['UPLOAD_REVIEW_KEY_SHA256'] = hashlib.sha256(replacement_key.encode('ascii')).hexdigest()
        self.assertFalse(self.enabled())
        self.assertEqual(self.get('/api/business/session').status_code, 503)
        self.assertEqual(self.bootstrap().status_code, 403)
        self.assertEqual(self.bootstrap(key=replacement_key).status_code, 200)
        self.assertTrue(self.enabled())
        self.app.config['UPLOAD_REVIEW_ENABLED'] = False
        self.assertFalse(self.enabled())
        self.app.config['UPLOAD_REVIEW_ENABLED'] = True
        self.now += 601
        self.assertFalse(self.enabled())
        self.assertEqual(self.bootstrap(key=replacement_key).status_code, 503)
        self.assertNotIn('upload-review-form', self.get('/?mode=business&review=1').text)

    def test_lost_private_owner_revokes_cookie_and_requires_key_again(self):
        self.bootstrap()
        with self.client.session_transaction(base_url='https://localhost') as values:
            owner = values['business_owner']
        with self.app.app_context():
            get_business_store().delete_session(owner_key(owner))
        self.assertFalse(self.enabled())
        self.assertEqual(self.get('/api/business/session').status_code, 503)
        self.assertEqual(self.bootstrap().status_code, 200)
        with self.client.session_transaction(base_url='https://localhost') as values:
            self.assertNotEqual(values['business_owner'], owner)

    def test_owner_expiry_between_gate_and_session_read_cannot_recreate_identity(self):
        self.app.config['BUSINESS_IDLE_TTL'] = 20
        self.bootstrap()
        with self.client.session_transaction(base_url='https://localhost') as values:
            original_identity = dict(values)
        with self.app.app_context():
            store = get_business_store()
        authenticate = store.authenticate
        calls = []
        def expire_after_first_check(*args, **kwargs):
            result = authenticate(*args, **kwargs)
            calls.append(True)
            if len(calls) == 1:
                # The signed review grant passes the initial gate, then the
                # private owner expires before the existing session view runs.
                self.now += 21
            return result
        with patch.object(store, 'authenticate', side_effect=expire_after_first_check), \
                patch.object(store, 'create_session', wraps=store.create_session) as create:
            response = self.get('/api/business/session')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()['code'], 'session_expired')
        create.assert_not_called()
        with self.client.session_transaction(base_url='https://localhost') as values:
            # Flask may refresh a permanent cookie's expiry, but the application
            # must not replace its owner or attach a new review identity.
            self.assertEqual(dict(values), original_identity)
        self.assertFalse(self.enabled())
        with store._connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)

    def test_idle_expiry_does_not_get_extended_by_features_or_page_reads(self):
        self.app.config['BUSINESS_IDLE_TTL'] = 20
        self.bootstrap()
        self.now += 15
        self.assertTrue(self.enabled())
        self.get('/?mode=business')
        self.now += 6
        self.assertFalse(self.enabled())
        self.assertEqual(self.get('/api/business/session').status_code, 503)

    def test_changed_owner_or_invalid_cookie_cannot_reuse_grant(self):
        self.bootstrap()
        with self.client.session_transaction(base_url='https://localhost') as values:
            values['business_owner'] = 'e' * 64
        self.assertFalse(self.enabled())
        self.assertEqual(self.get('/api/business/session').status_code, 503)
        self.client.set_cookie('marginguard_session', 'SYNTHETIC-invalid-signature')
        self.assertFalse(self.enabled())

    def test_delete_session_removes_review_grant(self):
        csrf = self.bootstrap().get_json()['csrf_token']
        response = self.client.delete('/api/business/session', base_url='https://localhost',
                                      headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 204)
        self.assertFalse(self.enabled())
        self.assertEqual(self.get('/api/business/session').status_code, 503)

    def test_public_uploads_are_a_separate_explicit_mode(self):
        with self.assertRaises(ValueError):
            create_app(config=dict(self.config, ENABLE_BUSINESS_UPLOAD=True))
        app = create_app(config=dict(self.config, ENABLE_BUSINESS_UPLOAD=True,
                                     UPLOAD_REVIEW_ENABLED=False))
        client = app.test_client()
        self.assertTrue(self.enabled(client))
        self.assertEqual(self.get('/api/business/session', client).status_code, 200)
        self.assertNotIn('Restricted upload acceptance test', self.get('/?mode=business&review=1', client).text)

    def test_review_deadline_cannot_be_permanent_and_expired_config_stays_closed(self):
        with self.assertRaises(ValueError):
            create_app(config=dict(self.config, UPLOAD_REVIEW_DEADLINE=self.now + 7201))
        app = create_app(config=dict(self.config, UPLOAD_REVIEW_DEADLINE=self.now - 1))
        client = app.test_client()
        self.assertFalse(self.enabled(client))
        self.assertEqual(self.bootstrap(client).status_code, 503)
        self.assertEqual(self.get('/', client).status_code, 200)
        self.assertEqual(self.get('/market', client).status_code, 200)
        self.assertNotIn('upload-review-form', self.get('/?mode=business&review=1', client).text)

    def test_missing_deadline_or_digest_fails_closed(self):
        for change in ({'UPLOAD_REVIEW_DEADLINE': 0}, {'UPLOAD_REVIEW_KEY_SHA256': ''},
                       {'UPLOAD_REVIEW_KEY_SHA256': self.key[:32]}, {'UPLOAD_REVIEW_DEADLINE': 'nan'}):
            with self.subTest(change=tuple(change)):
                with self.assertRaises(ValueError):
                    create_app(config=dict(self.config, **change))


if __name__ == '__main__':
    unittest.main()
