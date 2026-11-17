"""Regression tests for defects found by the independent review of 17 Nov 2026 (see docs/REVIEW-2026-11-17.md)."""
from http.client import HTTPConnection
from pathlib import Path
import sys, tempfile, threading, unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from accretion.gate import gate_fragment
from accretion.world import WorldStore
from serve import make_server, owner_key


def status(xml):
    r = gate_fragment(xml, prefix='A000001')
    return r['status'], [e.get('code') for e in r.get('errors', [])]


class GateFixes(unittest.TestCase):
    def test_sub_float32_values_refused(self):  # G1
        self.assertEqual(status('<Group><Shape><Box size="1e-320 1e-320 1e-320"/></Shape><Shape><Sphere/></Shape></Group>')[0], 'fail')
        self.assertEqual(status('<Transform scale="1e-40 1 1"><Shape><Sphere/></Shape></Transform>')[0], 'fail')
        self.assertEqual(status('<Transform scale="1e-30 1 1"><Shape><Sphere/></Shape></Transform>')[0], 'pass')

    def test_unicode_digits_and_spaces_refused(self):  # G4
        self.assertEqual(status('<Transform translation="١ ٢ ٣"><Shape><Sphere/></Shape></Transform>')[0], 'fail')
        self.assertEqual(status('<Transform translation="1 2 3"><Shape><Sphere/></Shape></Transform>')[0], 'fail')
        self.assertEqual(status('<Transform translation="1 2 3"><Shape><Sphere/></Shape></Transform>')[0], 'pass')

    def test_spotlight_default_beamwidth_matches_schema(self):  # G3 (X3D 4.0 UOM default beamWidth 0.589049)
        xml = '<Group><SpotLight cutOffAngle="0.7"/><Shape><Sphere/></Shape></Group>'
        self.assertEqual(status(xml)[0], 'pass')


class HTTPFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.server = make_server(WorldStore(Path(cls.temp.name) / 'w.sqlite3'), owner_key(Path(cls.temp.name)), port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(5); cls.temp.cleanup()

    def get(self, path, method='GET', host=None):
        c = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            c.putrequest(method, path, skip_host=True)
            c.putheader('Host', host or f'127.0.0.1:{self.server.server_port}'); c.endheaders()
            r = c.getresponse(); return r.status, dict(r.getheaders())
        finally:
            c.close()

    def test_dns_rebinding_host_refused(self):  # H2
        self.assertEqual(self.get('/api/world', host='evil.example:8820')[0], 403)
        self.assertEqual(self.get('/api/world', host=f'localhost:{self.server.server_port}')[0], 200)

    def test_head_and_frame_headers(self):  # H6, H3
        status_, headers = self.get('/api/world', 'HEAD')
        self.assertEqual(status_, 200)
        self.assertEqual(headers.get('X-Frame-Options'), 'DENY')
        self.assertIn('frame-ancestors', headers.get('Content-Security-Policy', ''))

    def test_no_directory_listing(self):  # H3
        self.assertEqual(self.get('/vendor/')[0], 404)

    def test_socket_timeout_set(self):  # H1
        from serve import Handler
        self.assertLessEqual(Handler.timeout, 30)


if __name__ == '__main__':
    unittest.main()
