"""Admission-store controls: real validators, atomic append and bounded replay."""
from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from accretion import world as w
from accretion.codec import canonical, sha


FRAGMENT = '<Shape><Appearance><Material diffuseColor="0.2 0.7 0.6"/></Appearance><Box size="1 1 1"/></Shape>'


def candidate(fragment=FRAGMENT):
    return {'title': 'Controlled patch', 'instruction': 'Keep the next patch distinct.', 'x3d': fragment,
            'generator': {'id': 'unittest-control', 'kind': 'manual', 'version': '1'}}


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='accretion-world-test-')
        self.store = w.WorldStore(Path(self.temp.name)/'world.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def append(self, candidate_value=None, **extra):
        snapshot = self.store.snapshot()
        values = {'expected_head': snapshot['head'], 'expected_tail_hash': snapshot['tail_hash'], 'tier': 2,
                  'candidate': candidate() if candidate_value is None else candidate_value}
        values.update(extra)
        return self.store.append(**values)

    def archive_one(self):
        self.append()
        return self.store.archive()

    def rehash(self, archive):
        # Deliberately repair the outer chain so consistency tests must inspect
        # the embedded candidate, policy and witness bindings rather than only a digest.
        previous = archive['genesis']
        for item in archive['entries']:
            item['prev_hash'] = item['payload']['prev_hash'] = previous
            item['hash'] = sha(item['payload'])
            previous = item['hash']
        archive['checkpoint'] = {'head': len(archive['entries']), 'hash': previous}

    def rejected(self, archive, checkpoint=None):
        try:
            result = w.verify_archive(archive, checkpoint)
        except ValueError:
            return
        self.assertFalse(result['valid'])

    def test_real_local_admission_and_exact_candidate_bindings(self):
        result = self.append()
        self.assertEqual(result['entry']['n'], 1)
        detail = self.store.detail(1)
        body = detail['payload']
        self.assertEqual(body['admission']['fragment']['status'], 'pass')
        self.assertEqual(body['admission']['mcp']['xsd']['status'], 'pass')
        self.assertEqual(body['admission']['mcp']['semantic']['status'], 'pass')
        self.assertEqual(body['candidate']['scene_sha256'], sha(detail['scene_x3d'].encode()))
        self.assertEqual(body['admission']['mcp']['candidate_sha256'], body['candidate']['scene_sha256'])
        self.assertEqual(body['admission']['render']['status'], 'not_run')
        self.assertTrue(self.store.verify()['valid'])

    def test_procedural_generation_runs_through_actual_admission(self):
        snapshot = self.store.snapshot()
        result = self.store.append(expected_head=0, expected_tail_hash=snapshot['tail_hash'], tier=3)
        self.assertEqual(result['attempt']['model_calls'], 0)
        self.assertEqual(result['entry']['generator'], 'procedural')
        self.assertTrue(self.store.verify()['valid'])

    def test_stale_head_or_tail_cannot_append(self):
        original = self.store.snapshot()
        self.append()
        with self.assertRaises(w.Conflict):
            self.store.append(expected_head=original['head'], expected_tail_hash=original['tail_hash'], candidate=candidate())
        with self.assertRaises(w.Conflict):
            self.store.append(expected_head=1, expected_tail_hash='0'*64, candidate=candidate())
        self.assertEqual(self.store.snapshot()['head'], 1)

    def test_two_prepared_writers_have_exactly_one_transaction_winner(self):
        second = w.WorldStore(self.store.path)
        initial = self.store.snapshot()
        barrier = threading.Barrier(2)
        original = w.WorldStore._prepare
        def synchronized(store, *args, **kwargs):
            prepared = original(store, *args, **kwargs)
            barrier.wait(timeout=10)
            return prepared
        def write(store):
            try:
                return store.append(expected_head=0, expected_tail_hash=initial['tail_hash'], candidate=candidate())
            except w.Conflict as error:
                return error
        with patch.object(w.WorldStore, '_prepare', synchronized), ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(write, [self.store, second]))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, w.Conflict) for result in results), 1)
        self.assertEqual(self.store.snapshot()['head'], 1)
        self.assertEqual(sorted(a['status'] for a in self.store.recent_attempts()), ['committed', 'conflict'])
        self.assertTrue(self.store.verify()['valid'])

    def test_attempt_insert_failure_rolls_back_the_entry(self):
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER test_attempt_failure BEFORE INSERT ON attempts BEGIN SELECT RAISE(ABORT,'injected attempt failure'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'injected attempt failure'):
            self.append()
        self.assertEqual(self.store.snapshot()['head'], 0)
        self.assertEqual(self.store.recent_attempts(), [])
        self.assertTrue(self.store.verify()['valid'])

    def test_database_triggers_refuse_update_and_delete(self):
        self.append()
        for sql in ["UPDATE entries SET created_utc='changed'", 'DELETE FROM entries',
                    "UPDATE attempts SET payload='{}'", 'DELETE FROM attempts']:
            with self.subTest(sql=sql), self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
                with self.store.connect() as db:
                    db.execute(sql)
        self.assertEqual(self.store.snapshot()['head'], 1)
        self.assertTrue(self.store.verify()['valid'])

    def test_rejected_script_is_audited_without_an_entry(self):
        with self.assertRaises(w.AdmissionRefused) as context:
            self.append(candidate('<Script/>'))
        self.assertEqual(self.store.snapshot()['head'], 0)
        self.assertEqual(context.exception.attempt['status'], 'rejected')
        self.assertEqual(self.store.recent_attempts()[0]['stages'][0]['status'], 'fail')

    def test_missing_required_validator_cannot_append(self):
        unavailable = {'status': 'not_run', 'xsd': {'status': 'not_run', 'findings': []},
                       'semantic': {'status': 'not_run', 'findings': []}}
        with patch.object(w, 'validate_scene', return_value=unavailable):
            with self.assertRaises(w.AdmissionRefused):
                self.append()
        self.assertEqual(self.store.snapshot()['head'], 0)
        self.assertEqual(self.store.recent_attempts()[0]['status'], 'rejected')

    def test_source_drift_refuses_before_append(self):
        with patch.object(w, 'source_identity', return_value={'changed.py': '0'*64}):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                self.append()
        self.assertEqual(self.store.snapshot()['head'], 0)

    def test_spiral_and_tower_constraints_replay(self):
        self.assertEqual([w.spiral(i) for i in range(9)], [[0,0],[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1],[0,-1],[1,-1]])
        self.append(force_mode='generate')
        for _ in range(5):
            self.append(force_mode='augment')
        with self.assertRaisesRegex(ValueError, 'No cell'):
            self.append(force_mode='augment')
        self.assertEqual([e['level'] for e in self.store.world()['entries']], list(range(6)))
        self.assertTrue(self.store.verify()['valid'])

    def test_bounded_view_window_does_not_delete_history(self):
        for _ in range(3):
            self.append(force_mode='generate')
        view = self.store.world(limit=2)
        self.assertEqual([e['n'] for e in view['entries']], [2,3])
        self.assertTrue(view['truncated'])
        self.assertEqual(view['visible_start'], 2)
        self.assertEqual(len(self.store.archive()['entries']), 3)

    def test_timestamps_raw_canonical_and_scene_bytes_are_bound(self):
        original = self.archive_one()
        for field in ['created_utc', 'raw_x3d', 'canonical_x3d', 'scene_x3d']:
            changed = copy.deepcopy(original)
            changed['entries'][0][field] += ' '
            with self.subTest(field=field):
                self.rejected(changed)

    def test_rehashed_wrong_placement_is_rejected(self):
        archive = self.archive_one()
        archive['entries'][0]['payload']['plan']['translation'][0] += 8
        self.rehash(archive)
        self.rejected(archive)

    def test_rehashed_witness_summary_or_binding_is_rejected(self):
        original = self.archive_one()
        changed = copy.deepcopy(original)
        changed['entries'][0]['payload']['witnesses'][0]['status'] = 'fail'
        self.rehash(changed)
        self.rejected(changed)
        changed = copy.deepcopy(original)
        changed['entries'][0]['payload']['admission']['mcp']['candidate_sha256'] = '0'*64
        self.rehash(changed)
        self.rejected(changed)

    def test_rehashed_changed_policy_or_measurement_is_rejected(self):
        original = self.archive_one()
        changed = copy.deepcopy(original)
        admission = changed['entries'][0]['payload']['admission']
        admission['policy']['required'] = []
        admission['policy_sha256'] = sha(admission['policy'])
        self.rehash(changed)
        self.rejected(changed)
        changed = copy.deepcopy(original)
        changed['entries'][0]['payload']['metrics']['nodes'] += 1
        self.rehash(changed)
        self.rejected(changed)

    def test_self_consistent_rewrite_needs_a_trusted_checkpoint(self):
        archive = self.archive_one()
        checkpoint = copy.deepcopy(archive['checkpoint'])
        archive['entries'][0]['payload']['title'] = 'Rewritten by the database owner'
        self.rehash(archive)
        # A hash chain alone cannot identify the genuine history.
        self.assertTrue(w.verify_archive(archive)['valid'])
        self.rejected(archive, checkpoint)

    def test_browser_integral_float_normalization_preserves_verification(self):
        archive = self.archive_one()
        reparsed = w.strict_json(canonical(archive).decode())
        self.assertTrue(w.verify_archive(reparsed)['valid'])

    def test_malformed_archive_shapes_are_cleanly_refused(self):
        original = self.archive_one()
        for entries in [[None], [3], ['bad']]:
            changed = copy.deepcopy(original)
            changed['entries'] = entries
            with self.subTest(entries=entries):
                self.rejected(changed)
        changed = copy.deepcopy(original)
        changed['checkpoint'] = None
        self.rejected(changed)

    def test_explicit_malformed_trusted_checkpoint_is_not_treated_as_absent(self):
        archive = self.archive_one()
        for value in [{}, False, '', {'head': True, 'hash': archive['checkpoint']['hash']}]:
            with self.subTest(checkpoint=value):
                self.rejected(archive, value)

    def test_boolean_entry_number_is_not_the_integer_one(self):
        archive = self.archive_one()
        archive['entries'][0]['n'] = True
        self.rejected(archive)


if __name__ == '__main__':
    unittest.main()
