"""Local capability, request-shape and candidate execution boundaries."""
from http.client import HTTPConnection
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from accretion.codec import canonical, strict_json
from accretion.world import WorldStore
from serve import make_server, owner_key


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='accretion-http-test-')
        cls.store = WorldStore(Path(cls.temp.name)/'world.sqlite3')
        cls.key = owner_key(Path(cls.temp.name))
        cls.server = make_server(cls.store, cls.key, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def request(self, method, path, body=None, token=None, origin=None, raw=None):
        headers = {'Content-Type': 'application/json'}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        if origin is not None:
            headers['Origin'] = origin
        data = raw if raw is not None else canonical(body) if body is not None else None
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def grow_body(self):
        snap = self.store.snapshot()
        return {'tier': 1, 'expected_head': snap['head'], 'expected_tail_hash': snap['tail_hash']}

    def test_viewer_can_read_but_cannot_grow(self):
        before = self.store.snapshot()['head']
        status, _, data = self.request('GET', '/api/world')
        self.assertEqual(status, 200)
        self.assertFalse(strict_json(data.decode())['capabilities']['writer'])
        self.assertEqual(self.request('POST', '/api/grow', self.grow_body())[0], 403)
        self.assertEqual(self.store.snapshot()['head'], before)

    def test_author_capability_is_required_and_never_returned_by_status(self):
        status, _, data = self.request('GET', '/api/status', token=self.key)
        self.assertEqual(status, 200)
        self.assertTrue(strict_json(data.decode())['capabilities']['writer'])
        self.assertNotIn(self.key.encode(), data)
        self.assertEqual(self.request('POST', '/api/grow', self.grow_body(), token='0'*64)[0], 403)

    def test_same_origin_author_can_grow_and_fetch_exact_patch(self):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        status, _, data = self.request('POST', '/api/grow', self.grow_body(), token=self.key, origin=origin)
        self.assertEqual(status, 200)
        value = strict_json(data.decode())
        status, headers, scene = self.request('GET', value['entry']['scene_uri'])
        self.assertEqual(status, 200)
        self.assertIn('model/x3d+xml', headers['Content-Type'])
        self.assertEqual(scene.decode(), self.store.detail(value['entry']['n'])['scene_x3d'])

    def test_foreign_origin_cannot_use_author_capability(self):
        before = self.store.snapshot()['head']
        self.assertEqual(self.request('POST', '/api/grow', self.grow_body(), token=self.key, origin='https://example.com')[0], 403)
        self.assertEqual(self.store.snapshot()['head'], before)

    def test_malformed_origin_is_refused_without_connection_reset(self):
        self.assertIn(self.request('POST', '/api/grow', self.grow_body(), token=self.key, origin='http://localhost:bad')[0], [400,403])

    def test_nonascii_fake_capability_is_refused_without_connection_reset(self):
        self.assertIn(self.request('POST', '/api/grow', self.grow_body(), token='é')[0], [400,403])

    def test_untrusted_script_candidate_is_not_appended(self):
        before = self.store.snapshot()['head']
        body = {**self.grow_body(), 'title': 'Bad script', 'instruction': 'Never execute this.', 'x3d': '<Script/>'}
        status, _, data = self.request('POST', '/api/submit', body, token=self.key)
        self.assertEqual(status, 400)
        self.assertEqual(strict_json(data.decode())['attempt']['status'], 'rejected')
        self.assertEqual(self.store.snapshot()['head'], before)

    def test_unexpected_fields_duplicate_json_and_nonfinite_values_are_refused(self):
        values = [canonical({**self.grow_body(), 'url': 'https://example.com/patch.x3d'}),
                  b'{"tier":1,"tier":2}', b'{"tier":NaN}', b'[]']
        for data in values:
            with self.subTest(data=data):
                self.assertEqual(self.request('POST', '/api/grow', token=self.key, raw=data)[0], 400)

    def test_patch_route_allowlist_does_not_expose_private_files(self):
        for path in ['/patches/../data/owner.key', '/api/entries/../../data/owner.key', '/patches/nope.x3d']:
            with self.subTest(path=path):
                status, _, data = self.request('GET', path)
                self.assertEqual(status, 404)
                self.assertNotIn(self.key.encode(), data)


if __name__ == '__main__':
    unittest.main()
