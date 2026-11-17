"""Static export and browser-verifier parity tests (Python + optional Node)."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from accretion.codec import canonical, strict_json
from accretion.world import WorldStore, verify_archive
import export_static

EXAMPLE = ROOT / 'examples' / 'world.json'


class StaticExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = strict_json(EXAMPLE.read_text(encoding='utf-8'))
        cls.files = export_static.build(cls.archive)

    def test_world_json_equals_live_store_view(self):
        # The static api/world.json must be byte-identical to what WorldStore.world() would serve
        # for the same rows, so the viewer cannot drift from the server.
        with tempfile.TemporaryDirectory() as tmp:
            store = WorldStore(Path(tmp) / 'w.sqlite3')
            import sqlite3
            with store.connect() as db:
                for item in self.archive['entries']:
                    row = export_static._row(item)
                    db.execute('PRAGMA foreign_keys=OFF')
                    cols = [r[1] for r in db.execute('PRAGMA table_info(entries)')]
                    values = {'n': item['n'], 'hash': item['hash'], 'prev_hash': item['prev_hash'], 'created_utc': item['created_utc'],
                              'payload': row['payload'], 'raw': item['raw_x3d'], 'canonical': item['canonical_x3d'], 'scene': item['scene_x3d']}
                    db.execute(f"INSERT INTO entries({','.join(c for c in cols if c in values)}) VALUES({','.join('?' for c in cols if c in values)})",
                               [values[c] for c in cols if c in values])
            live = store.world(512)
        self.assertEqual(canonical(live), self.files['api/world.json'])

    def test_detail_and_patch_files_match_archive(self):
        for item in self.archive['entries']:
            detail = json.loads(self.files[f"api/entries/{item['n']}.json"])
            self.assertEqual(detail['scene_x3d'], item['scene_x3d'])
            self.assertEqual(self.files[f"patches/{item['n']:06d}.x3d"].decode(), item['scene_x3d'])
            self.assertEqual(detail['entry']['scene_uri'], f"/patches/{item['n']:06d}.x3d")

    def test_manifest_inventory_and_determinism(self):
        manifest = json.loads(self.files['manifest.json'])
        self.assertEqual(manifest['checkpoint'], self.archive['checkpoint'])
        self.assertEqual(set(manifest['files']), set(self.files) - {'manifest.json'})
        self.assertEqual(export_static.build(self.archive), self.files)

    def test_refuses_unverifiable_archive(self):
        bad = copy.deepcopy(self.archive)
        bad['entries'][3]['payload']['title'] += '!'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.json'
            path.write_text(json.dumps(bad), encoding='utf-8')
            self.assertEqual(export_static.main(['--archive', str(path), '--out', str(Path(tmp) / 'o')]), 2)
            self.assertFalse((Path(tmp) / 'o').exists())

    def test_check_mode_detects_stale_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'o'
            export_static.write(self.files, out)
            self.assertEqual(export_static.check(self.files, out), [])
            (out / 'patches' / '000001.x3d').write_text('x')
            self.assertEqual(export_static.check(self.files, out), ['differs patches/000001.x3d'])


@unittest.skipUnless(shutil.which('node'), 'node not installed')
class BrowserVerifierParity(unittest.TestCase):
    """The JS verifier must agree with verify_archive on valid and tampered archives."""
    def run_node(self, archive):
        script = ("const V=require(process.argv[1]);let s='';process.stdin.on('data',d=>s+=d).on('end',async()=>{"
                  "const a=JSON.parse(s);const r=await V.verifyArchive(a,a.checkpoint);console.log(JSON.stringify({valid:r.valid,checked:r.checked,codes:r.errors.map(e=>e.code+':'+(e.message||''))}))})")
        out = subprocess.run(['node', '-e', script, str(ROOT / 'web' / 'verify-archive.js')], input=json.dumps(archive), capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def py(self, archive):
        r = verify_archive(archive, checkpoint=archive.get('checkpoint'))
        return {'valid': r['valid'], 'checked': r['checked'], 'codes': [e['code'] + ':' + e.get('message', '') for e in r['errors']]}

    def test_cases_agree(self):
        base = strict_json(EXAMPLE.read_text(encoding='utf-8'))
        cases = {'valid': base}
        a = copy.deepcopy(base); a['entries'][5]['payload']['title'] += 'x'; cases['title'] = a
        a = copy.deepcopy(base); a['entries'][7]['canonical_x3d'] += ' '; cases['bytes'] = a
        a = copy.deepcopy(base); a['entries'][2]['payload']['plan']['cell'] = [9, 9]; cases['plan'] = a
        a = copy.deepcopy(base); a['entries'].pop(); cases['truncated'] = a
        a = copy.deepcopy(base); a['entries'][1], a['entries'][2] = a['entries'][2], a['entries'][1]; cases['reorder'] = a
        a = copy.deepcopy(base); a['checkpoint']['hash'] = '0' * 64; cases['checkpoint'] = a
        a = copy.deepcopy(base); a['genesis'] = '1' * 64; cases['genesis'] = a
        for name, archive in cases.items():
            with self.subTest(name):
                self.assertEqual(self.run_node(archive), self.py(archive))
        self.assertTrue(self.run_node(base)['valid'])
        self.assertFalse(self.run_node(cases['title'])['valid'])

    def test_float_repr_matches_python(self):
        script = "const V=require(process.argv[1]);console.log(JSON.stringify([1e-5,1.5e-7,0.0001,0.00012,0.1,19.799999999999997,123456.789,2.5e-10].map(V.pyFloat)))"
        out = subprocess.run(['node', '-e', script, str(ROOT / 'web' / 'verify-archive.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(out.stdout), [repr(x) for x in [1e-5, 1.5e-7, 0.0001, 0.00012, 0.1, 19.799999999999997, 123456.789, 2.5e-10]])


if __name__ == '__main__':
    unittest.main()
