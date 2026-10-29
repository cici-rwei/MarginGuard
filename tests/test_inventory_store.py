"""Inventory attachment storage tests use artificial JSON, never business data."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import tempfile
import unittest

from business_store import BusinessError, BusinessStore, owner_key


class InventoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000000.0
        self.store = BusinessStore(self.temp.name, clock=lambda: self.now)
        token, _, _ = self.store.create_session()
        self.owner = owner_key(token)
        self.sales = {
            'meta': {'currency': 'AUD', 'fixture': 'SYNTHETIC'},
            'report': {'series': [{'product': 'SYNTHETIC_A', 'store': 'SYNTHETIC_STORE'}]},
            'series': [{'series_id': 'synthetic-id', 'item_id': 'SYNTHETIC_A',
                        'store_id': 'SYNTHETIC_STORE', 'result': {'forecast': [2] * 14}}],
            'catalog_series': [{'series_id': 'unassessed-id', 'status': 'Not assessed'}],
        }
        self.dataset, pending_revision = self.store.save_pending(self.owner, self.sales)
        self.revision = self.store.confirm(self.owner, self.dataset, pending_revision, self.sales)
        self.inventory = {'inventory': {
            'rows': [{'product': 'SYNTHETIC_A', 'store': 'SYNTHETIC_STORE', 'current_stock': 0}],
            'excess_cover_days': 30, 'assume_no_on_order': False,
            'report': {'fixture': 'SYNTHETIC'},
            'overview': [{'series_id': 'unassessed-id', 'status': 'Not assessed'}],
        }}

    def stage(self, payload=None):
        return self.store.save_inventory_pending(self.owner, self.dataset, self.revision,
                                                 self.inventory if payload is None else payload)

    def confirm(self, upload_id, upload_revision, revision=None):
        return self.store.confirm_inventory(self.owner, self.dataset,
                                            self.revision if revision is None else revision,
                                            upload_id, upload_revision)

    def assert_error(self, status, action):
        with self.assertRaises(BusinessError) as caught:
            action()
        self.assertEqual(caught.exception.status, status)
        return caught.exception

    def rows(self):
        with self.store._connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM datasets ORDER BY id')]

    def test_stage_binds_target_and_preserves_ready_and_pending_sales(self):
        sales_draft, _ = self.store.save_pending(self.owner, {'fixture': 'SYNTHETIC sales draft'})
        before = self.store.load(self.owner, self.dataset)
        supplied = dict(self.inventory, target_dataset_id='untrusted', base_dataset_revision='untrusted',
                        meta={'currency': 'USD'}, series=[])
        upload_id, upload_revision = self.stage(supplied)
        staged = self.store.load(self.owner, upload_id, state='inventory_pending', revision=upload_revision)
        self.assertEqual(staged['payload'], {'target_dataset_id': self.dataset,
                                           'base_dataset_revision': self.revision,
                                           'inventory': self.inventory['inventory']})
        self.assertEqual(staged['expires'], self.now + self.store.pending_ttl)
        self.assertEqual(self.store.load(self.owner, self.dataset), before)
        self.assertEqual(self.store.load(self.owner, sales_draft)['state'], 'pending')
        self.assertEqual(self.store.active(self.owner)['dataset_id'], self.dataset)

    def test_replacement_affects_only_own_inventory_draft(self):
        sales_draft, _ = self.store.save_pending(self.owner, {'fixture': 'SYNTHETIC sales draft'})
        first, _ = self.stage()
        second, _ = self.stage({'inventory': {'rows': [], 'fixture': 'SYNTHETIC replacement'}})
        self.assert_error(404, lambda: self.store.load(self.owner, first))
        self.assertEqual(self.store.load(self.owner, second)['state'], 'inventory_pending')
        self.assertEqual(self.store.load(self.owner, sales_draft)['state'], 'pending')
        self.assertEqual(self.store.load(self.owner, self.dataset)['payload'], self.sales)

    def test_confirmation_rotates_revision_and_changes_only_inventory(self):
        original_input = copy.deepcopy(self.inventory)
        upload_id, upload_revision = self.stage()
        sales_draft, _ = self.store.save_pending(self.owner, {'fixture': 'SYNTHETIC sales draft'})
        before = self.store.load(self.owner, self.dataset)
        result = self.confirm(upload_id, upload_revision)
        self.assertEqual(result, self.store.load(self.owner, self.dataset))
        self.assertEqual(result['id'], self.dataset)
        self.assertNotEqual(result['revision'], self.revision)
        self.assertEqual(result['expires'], before['expires'])
        self.assertEqual(result['state'], 'ready')
        self.assertEqual(result['payload'], dict(self.sales, inventory=self.inventory['inventory']))
        self.assertEqual(self.inventory, original_input)
        self.assertEqual(result['payload']['catalog_series'][0]['status'], 'Not assessed')
        self.assert_error(409, lambda: self.store.load(self.owner, self.dataset, revision=self.revision))
        self.assert_error(404, lambda: self.store.load(self.owner, upload_id))
        self.assertEqual(self.store.load(self.owner, sales_draft)['state'], 'pending')

    def test_new_snapshot_replaces_old_inventory_without_merging_stale_rows(self):
        first, rev = self.stage()
        self.revision = self.confirm(first, rev)['revision']
        replacement = {'inventory': {'rows': [], 'fixture': 'SYNTHETIC no matching inventory'}}
        second, rev = self.stage(replacement)
        result = self.confirm(second, rev)
        self.assertEqual(result['payload']['inventory'], replacement['inventory'])
        self.assertEqual({k: v for k, v in result['payload'].items() if k != 'inventory'}, self.sales)

    def test_cross_owner_stage_confirm_and_delete_are_unavailable(self):
        upload_id, upload_revision = self.stage()
        other_token, _, _ = self.store.create_session()
        other = owner_key(other_token)
        for action in (
            lambda: self.store.save_inventory_pending(other, self.dataset, self.revision, self.inventory),
            lambda: self.store.confirm_inventory(other, self.dataset, self.revision, upload_id, upload_revision),
            lambda: self.store.delete_inventory_pending(other, self.dataset, upload_id),
        ):
            self.assert_error(404, action)
        self.assertEqual(self.store.load(self.owner, upload_id)['state'], 'inventory_pending')

    def test_foreign_inventory_cannot_attach_to_own_ready_dataset(self):
        upload_id, upload_revision = self.stage()
        token, _, _ = self.store.create_session()
        other = owner_key(token)
        identifier, revision = self.store.save_pending(other, self.sales)
        revision = self.store.confirm(other, identifier, revision, self.sales)
        self.assert_error(404, lambda: self.store.confirm_inventory(
            other, identifier, revision, upload_id, upload_revision))
        self.assertEqual(self.store.load(other, identifier)['payload'], self.sales)

    def test_stale_stage_does_not_replace_valid_inventory_draft(self):
        self.stage()
        before = self.rows()
        self.assert_error(409, lambda: self.store.save_inventory_pending(
            self.owner, self.dataset, 'wrong-revision', self.inventory))
        self.assertEqual(self.rows(), before)

    def test_confirmation_checks_both_revisions_without_mutation(self):
        upload_id, upload_revision = self.stage()
        before = self.rows()
        self.assert_error(409, lambda: self.confirm(upload_id, upload_revision, 'wrong-sales-revision'))
        self.assert_error(409, lambda: self.confirm(upload_id, 'wrong-upload-revision'))
        self.assertEqual(self.rows(), before)

    def test_base_revision_is_checked_even_when_caller_has_current_revision(self):
        upload_id, upload_revision = self.stage()
        with self.store._connect() as db:
            db.execute('UPDATE datasets SET revision=? WHERE id=?', ('new-sales-revision', self.dataset))
        before = self.rows()
        self.assert_error(409, lambda: self.confirm(upload_id, upload_revision, 'new-sales-revision'))
        self.assertEqual(self.rows(), before)

    def test_wrong_target_cannot_delete_a_bound_inventory_draft(self):
        upload_id, _ = self.stage()
        self.assert_error(404, lambda: self.store.delete_inventory_pending(self.owner, 'another-dataset', upload_id))
        self.assert_error(404, lambda: self.store.delete_inventory_pending(self.owner, self.dataset, self.dataset))
        self.assertEqual(self.store.load(self.owner, upload_id)['state'], 'inventory_pending')

    def test_delete_inventory_leaves_sales_and_other_pending_data_unchanged(self):
        upload_id, _ = self.stage()
        sales_draft, _ = self.store.save_pending(self.owner, {'fixture': 'SYNTHETIC sales draft'})
        before = self.store.load(self.owner, self.dataset)
        self.assertIsNone(self.store.delete_inventory_pending(self.owner, self.dataset, upload_id))
        self.assert_error(404, lambda: self.store.load(self.owner, upload_id))
        self.assertEqual(self.store.load(self.owner, self.dataset), before)
        self.assertEqual(self.store.load(self.owner, sales_draft)['state'], 'pending')

    def test_pending_expiry_rejects_confirmation_without_needing_cleanup(self):
        upload_id, upload_revision = self.stage()
        self.now += self.store.pending_ttl + 1
        before = self.rows()
        self.assert_error(410, lambda: self.confirm(upload_id, upload_revision))
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.store.load(self.owner, self.dataset)['payload'], self.sales)

    def test_target_expiry_rejects_stage_and_confirmation(self):
        upload_id, upload_revision = self.stage()
        with self.store._connect() as db:
            db.execute('UPDATE datasets SET expires=? WHERE id=?', (self.now, self.dataset))
        before = self.rows()
        self.assert_error(410, lambda: self.stage())
        self.assert_error(410, lambda: self.confirm(upload_id, upload_revision))
        self.assertEqual(self.rows(), before)

    def test_pending_expiry_cannot_outlive_session_absolute_limit(self):
        with self.store._connect() as db:
            db.execute('UPDATE sessions SET expires=? WHERE owner=?', (self.now + 20, self.owner))
        upload_id, _ = self.stage()
        self.assertEqual(self.store.load(self.owner, upload_id)['expires'], self.now + 20)

    def test_expired_owner_cannot_stage_confirm_or_delete(self):
        upload_id, upload_revision = self.stage()
        self.now += self.store.idle_ttl + 1
        for action in (lambda: self.stage(), lambda: self.confirm(upload_id, upload_revision),
                       lambda: self.store.delete_inventory_pending(self.owner, self.dataset, upload_id)):
            self.assert_error(401, action)

    def test_missing_target_cannot_be_recreated_by_inventory_confirmation(self):
        upload_id, upload_revision = self.stage()
        self.store.delete(self.owner, self.dataset)
        self.assert_error(404, lambda: self.confirm(upload_id, upload_revision))
        self.assertIsNone(self.store.active(self.owner))
        self.assert_error(404, lambda: self.store.load(self.owner, upload_id))

    def test_sales_deletion_cascades_only_bound_draft_and_keeps_capacity_lease(self):
        upload_id, _ = self.stage()
        sales_draft, _ = self.store.save_pending(self.owner, {'fixture': 'SYNTHETIC sales draft'})
        token, _, _ = self.store.create_session()
        other = owner_key(token)
        other_id, other_revision = self.store.save_pending(other, self.sales)
        other_revision = self.store.confirm(other, other_id, other_revision, self.sales)
        other_upload, _ = self.store.save_inventory_pending(other, other_id, other_revision, self.inventory)
        other_before = self.store.load(other, other_upload)
        job = self.store.acquire_job(self.owner, 30)
        try:
            self.store.delete(self.owner, self.dataset, state='ready')
            self.assert_error(404, lambda: self.store.load(self.owner, upload_id))
            self.assertEqual(self.store.load(self.owner, sales_draft)['state'], 'pending')
            self.assertEqual(self.store.load(other, other_upload), other_before)
            self.assertEqual(self.store.load(other, other_id)['state'], 'ready')
            with self.store._connect() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs WHERE id=?', (job,)).fetchone()[0], 1)
        finally:
            self.store.release_job(job)

    def test_foreign_sales_deletion_cannot_remove_inventory_draft(self):
        upload_id, _ = self.stage()
        token, _, _ = self.store.create_session()
        other = owner_key(token)
        before = self.rows()
        self.assert_error(404, lambda: self.store.delete(other, self.dataset, state='ready'))
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.store.load(self.owner, upload_id)['state'], 'inventory_pending')

    def test_sales_replacement_invalidates_inventory_pending(self):
        upload_id, upload_revision = self.stage()
        replacement, rev = self.store.save_pending(self.owner, {'fixture': 'SYNTHETIC replacement'})
        self.store.confirm(self.owner, replacement, rev, {'fixture': 'SYNTHETIC replacement'})
        self.assert_error(404, lambda: self.confirm(upload_id, upload_revision))
        self.assert_error(404, lambda: self.store.load(self.owner, upload_id))
        self.assertEqual(self.store.active(self.owner)['dataset_id'], replacement)

    def test_failed_stage_quota_checks_preserve_existing_drafts(self):
        self.stage()
        self.store.save_pending(self.owner, {'fixture': 'SYNTHETIC sales draft'})
        before = self.rows()
        self.store.max_dataset_bytes = 1
        self.assert_error(413, lambda: self.stage())
        self.store.max_dataset_bytes = 100000
        self.store.max_bytes = 1
        self.assert_error(429, lambda: self.stage())
        self.assertEqual(self.rows(), before)

    def test_failed_combined_dataset_limit_rolls_back_both_records(self):
        upload_id, upload_revision = self.stage()
        before = self.rows()
        self.store.max_dataset_bytes = 1
        self.assert_error(413, lambda: self.confirm(upload_id, upload_revision))
        self.assertEqual(self.rows(), before)

    def test_failed_global_capacity_rolls_back_both_records(self):
        upload_id, upload_revision = self.stage()
        before = self.rows()
        self.store.max_bytes = 1
        self.assert_error(429, lambda: self.confirm(upload_id, upload_revision))
        self.assertEqual(self.rows(), before)

    def test_capacity_counts_replacement_not_both_old_and_new_payloads(self):
        upload_id, upload_revision = self.stage()
        sales_draft, _ = self.store.save_pending(self.owner, {'fixture': 'SYNTHETIC retained pending'})
        merged = dict(self.sales, inventory=self.inventory['inventory'])
        final_size = len(json.dumps(merged, separators=(',', ':'), allow_nan=False).encode('utf-8'))
        remaining_size = self.store.load(self.owner, sales_draft)['bytes']
        self.store.max_bytes = final_size + remaining_size
        result = self.confirm(upload_id, upload_revision)
        self.assertEqual(result['bytes'], final_size)
        self.assertEqual(sum(row['bytes'] for row in self.rows()), self.store.max_bytes)

    def test_concurrent_confirmation_has_one_winner_and_one_conflict(self):
        upload_id, upload_revision = self.stage()
        def attempt(_):
            try:
                return self.confirm(upload_id, upload_revision)['state']
            except BusinessError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(attempt, range(2))), ['ready', 409])
        self.assertEqual(self.store.load(self.owner, self.dataset)['payload']['inventory'], self.inventory['inventory'])

    def test_unconfirmed_sales_cannot_accept_inventory(self):
        pending, revision = self.store.save_pending(self.owner, {'fixture': 'SYNTHETIC pending'})
        self.assert_error(409, lambda: self.store.save_inventory_pending(self.owner, pending, revision, self.inventory))

    def test_cleanup_removes_expired_inventory_and_keeps_live_sales(self):
        upload_id, _ = self.stage()
        self.now += self.store.pending_ttl + 1
        self.store.cleanup()
        self.assert_error(404, lambda: self.store.load(self.owner, upload_id))
        self.assertEqual(self.store.load(self.owner, self.dataset)['payload'], self.sales)

    def test_invalid_inventory_payload_cannot_replace_sales(self):
        before = self.rows()
        for payload in ({}, {'inventory': None}, {'inventory': []}, 'SYNTHETIC'):
            self.assert_error(400, lambda payload=payload: self.stage(payload))
        self.assertEqual(self.rows(), before)


if __name__ == '__main__':
    unittest.main()
