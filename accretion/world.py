"""Candidate-bound local admission and an atomic, append-only SQLite world.

The database enforces app-level immutability. Hashes are integrity checks,
not signatures or independent authentication. No model transport is present.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import time
import unicodedata
import uuid

from .codec import canonical, sha, strict_json
from .gate import gate_fragment
from .generator import generate
from .mcp_adapter import validate_scene

ROOT = Path(__file__).resolve().parents[1]
POLICY = {'schema': 'accretion.local-admission/v1', 'required': ['fragment', 'xsd', 'semantic'],
          'render_required': False, 'scope': 'Restricted local content admission, not a formal Loom release receipt.'}
POLICY_SHA = sha(POLICY)
WORDS = ('orrery', 'mycelium', 'ziggurat', 'tide', 'beacon', 'lattice', 'coral', 'helix', 'turbine', 'lotus', 'astrolabe', 'reef',
         'spindle', 'crystal', 'canopy', 'resonance', 'cairn', 'gyroscope', 'seed', 'aurora', 'vessel', 'ripple', 'spire', 'orbit')
BIOMES = [('basalt-brass', [.81,.57,.24]), ('coral-glass', [.21,.77,.70]), ('verdant', [.23,.57,.71]), ('noctilucent', [.62,.39,.79])]


class Conflict(ValueError):
    """Another append won, or the supplied snapshot was not current."""


class AdmissionRefused(ValueError):
    def __init__(self, message, attempt):
        super().__init__(message)
        self.attempt = attempt


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def text(value, cap):
    if not isinstance(value, str):
        raise ValueError('Titles and instructions must be strings')
    cleaned = ''.join(c for c in value if not unicodedata.category(c).startswith('C'))
    cleaned = ' '.join(cleaned.split())[:cap]
    if not cleaned:
        raise ValueError('Titles and instructions cannot be empty')
    return cleaned


def integer(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{label} must be an integer in {low}..{high}')
    return value


def spiral(index):
    integer(index, 'spiral index', 0, 10_000_000)
    if index == 0:
        return [0, 0]
    ring = math.ceil((math.sqrt(index + 1) - 1) / 2)
    side, top = 2 * ring, (2 * ring + 1) ** 2 - 1
    if index >= top - side:
        return [ring - (top - index), -ring]
    if index >= top - 2 * side:
        return [-ring, -ring + (top - side - index)]
    if index >= top - 3 * side:
        return [-ring + (top - 2 * side - index), ring]
    return [ring, ring - (top - 3 * side - index)]


def plan_next(placements, previous_hash, force_mode=None):
    if force_mode not in (None, 'auto', 'generate', 'augment'):
        raise ValueError('Unknown growth mode')
    n = len(placements) + 1
    seed = sha((previous_hash + ':' + str(n)).encode())
    tops = {}
    for row in placements:
        tops[tuple(row['cell'])] = max(tops.get(tuple(row['cell']), -1), row['level'])
    recent = []
    for row in reversed(placements[-32:]):
        cell = tuple(row['cell'])
        if tops[cell] < 5 and cell not in recent:
            recent.append(cell)
    augment = bool(recent) and int(seed[:8], 16) % 100 < 42
    if force_mode in ('generate', 'augment'):
        augment = force_mode == 'augment'
    if augment and not recent:
        raise ValueError('No cell can be augmented yet; generate a new cell first')
    if augment:
        cell = list(recent[int(seed[8:16], 16) % len(recent)])
        level = tops[tuple(cell)] + 1
    else:
        cell = spiral(sum(row['mode'] == 'generate' for row in placements))
        level = 0
    ring = max(abs(cell[0]), abs(cell[1]))
    biome, color = BIOMES[(ring // 2) % len(BIOMES)]
    return {'n': n, 'mode': 'augment' if augment else 'generate', 'requested_mode': force_mode or 'auto',
            'cell': cell, 'level': level, 'seed': seed, 'seed_word': WORDS[int(seed[16:24], 16) % len(WORDS)],
            'biome': biome, 'era': (n-1)//32, 'color': color,
            'translation': [cell[0]*8, level*6.6, cell[1]*8]}


def wrap_scene(fragment):
    return '<?xml version="1.0" encoding="UTF-8"?>\n<X3D profile="Immersive" version="4.0"><Scene>' + fragment + '</Scene></X3D>\n'


def source_identity():
    paths = sorted((ROOT/'accretion').glob('*.py')) + [ROOT/'serve.py']
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in paths if p.is_file()}


class WorldStore:
    def __init__(self, path, max_entries=10_000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.code_files = source_identity()
        self.code_sha256 = sha(self.code_files)
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS entries(
                n INTEGER PRIMARY KEY,hash TEXT UNIQUE NOT NULL,prev_hash TEXT NOT NULL,
                payload TEXT NOT NULL,raw TEXT NOT NULL,canonical TEXT NOT NULL,scene TEXT NOT NULL,created_utc TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
              CREATE TRIGGER IF NOT EXISTS entries_no_update BEFORE UPDATE ON entries BEGIN SELECT RAISE(ABORT,'entries are append-only'); END;
              CREATE TRIGGER IF NOT EXISTS entries_no_delete BEFORE DELETE ON entries BEGIN SELECT RAISE(ABORT,'entries are append-only'); END;
              CREATE TRIGGER IF NOT EXISTS attempts_no_update BEFORE UPDATE ON attempts BEGIN SELECT RAISE(ABORT,'attempts are append-only'); END;
              CREATE TRIGGER IF NOT EXISTS attempts_no_delete BEFORE DELETE ON attempts BEGIN SELECT RAISE(ABORT,'attempts are append-only'); END;
            ''')
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('world_id', 'accretion-observatory-v1'))
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('schema', 'accretion.store/1'))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            yield db
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    @property
    def genesis(self):
        return sha(b'accretion-observatory-v1:genesis:accretion-c14n/1')

    def _rows(self, db):
        return list(db.execute('SELECT n,hash,prev_hash,payload,created_utc FROM entries ORDER BY n'))

    def _placements(self, rows):
        return [strict_json(row['payload'])['plan'] for row in rows]

    def snapshot(self):
        with self.connect() as db:
            rows = self._rows(db)
        return {'head': len(rows), 'tail_hash': rows[-1]['hash'] if rows else self.genesis,
                'placements': self._placements(rows)}

    def summary(self, rows):
        plans = self._placements(rows)
        return {'id': 'accretion-observatory-v1', 'head': len(rows), 'entries_count': len(rows),
                'tail_hash': rows[-1]['hash'] if rows else self.genesis, 'cell_count': len({tuple(p['cell']) for p in plans}),
                'max_level': max((p['level'] for p in plans), default=0),
                'last_append_utc': rows[-1]['created_utc'] if rows else None}

    def public_entry(self, row):
        body = strict_json(row['payload'])
        p = body['plan']
        return {'n': row['n'], 'hash': row['hash'], 'prev_hash': row['prev_hash'],
                'title': body['title'], 'instruction': body['instruction'], 'mode': p['mode'], 'cell': p['cell'],
                'level': p['level'], 'translation': p['translation'], 'biome': p['biome'], 'era': p['era'], 'color': p['color'],
                'bounds': body['bounds'], 'fit': body['fit'], 'metrics': body['metrics'],
                'scene_sha256': body['candidate']['scene_sha256'], 'canonical_sha256': body['candidate']['canonical_sha256'],
                'scene_uri': f"/patches/{row['n']:06d}.x3d", 'admission': {'status': 'pass', 'profile_id': POLICY['schema']},
                'created_utc': row['created_utc'], 'generator': body['generation']['kind']}

    def world(self, limit=512):
        limit = integer(limit, 'entry window', 1, 512)
        with self.connect() as db:
            rows = self._rows(db)
        visible = rows[-limit:]
        return {'schema': 'accretion.world/v1', 'mode': 'local_reference', 'generator': 'procedural', 'model_calls': 0,
                'world': self.summary(rows), 'entries': [self.public_entry(row) for row in visible],
                'truncated': len(rows) > limit, 'visible_start': visible[0]['n'] if visible else 0,
                'max_entries': self.max_entries, 'policy': {'profile_id': POLICY['schema'], **POLICY},
                'presence': {'sessions': [], 'count': 0, 'verified_people': False}}

    def detail(self, n):
        with self.connect() as db:
            row = db.execute('SELECT * FROM entries WHERE n=?', (n,)).fetchone()
        if row is None:
            raise KeyError('No such patch')
        return {'entry': self.public_entry(row), 'payload': strict_json(row['payload']),
                'raw_x3d': row['raw'], 'canonical_x3d': row['canonical'], 'scene_x3d': row['scene']}

    def _attempt(self, attempt):
        with self.connect() as db:
            db.execute('INSERT INTO attempts VALUES(?,?)', (attempt['id'], canonical(attempt).decode()))

    def recent_attempts(self, limit=20):
        with self.connect() as db:
            rows = list(db.execute('SELECT payload FROM attempts ORDER BY rowid DESC LIMIT ?', (limit,)))
        return [strict_json(row['payload']) for row in rows]

    def _prepare(self, plan, candidate, tier, attempt_id):
        if source_identity() != self.code_files:
            raise ValueError('Instrument source changed; restart the local server before admitting content')
        started = time.perf_counter()
        title, instruction = text(candidate.get('title'), 120), text(candidate.get('instruction'), 280)
        raw = candidate.get('x3d')
        if not isinstance(raw, str):
            raise ValueError('A candidate needs an X3D fragment string')
        attempt = {'schema': 'accretion.attempt/1', 'id': attempt_id, 'created_utc': utc(), 'status': 'rejected',
                   'generator': candidate.get('generator', {}).get('kind', 'manual'), 'model_calls': 0, 'stages': []}
        gate = gate_fragment(raw, prefix=f"A{plan['n']:06d}")
        attempt['stages'].append({'id': 'fragment', 'status': gate['status'], 'detail': gate.get('errors', [])})
        if gate['status'] != 'pass':
            attempt['errors'] = gate.get('errors', [])
            attempt['raw_excerpt'] = raw[:400]
            self._attempt(attempt)
            raise AdmissionRefused('The restricted fragment gate refused this candidate', attempt)
        fragment = gate['canonical_x3d']
        scene = wrap_scene(fragment)
        validated = validate_scene(scene)
        for name in ('xsd', 'semantic'):
            result = validated.get(name, {})
            attempt['stages'].append({'id': name, 'status': result.get('status', 'not_run'), 'detail': result.get('findings', [])})
        if validated.get('status') != 'pass' or any(validated.get(name, {}).get('status') != 'pass' for name in ('xsd', 'semantic')):
            attempt['errors'] = validated
            self._attempt(attempt)
            raise AdmissionRefused('A required pinned validator did not pass; candidate was not appended', attempt)
        candidate_hashes = {'raw_sha256': sha(raw.encode()), 'canonical_sha256': sha(fragment.encode()), 'scene_sha256': sha(scene.encode())}
        if validated.get('candidate_sha256') != candidate_hashes['scene_sha256']:
            raise ValueError('Validator candidate identity does not match the exact scene bytes')
        if gate.get('canonical_sha256') != candidate_hashes['canonical_sha256'] or gate.get('raw_sha256') != candidate_hashes['raw_sha256']:
            raise ValueError('Fragment gate candidate identity mismatch')
        gate_record = {key: value for key, value in gate.items() if key != 'canonical_x3d'}
        body = {'schema': 'accretion.entry/1', 'hash_profile': 'accretion-c14n/1', 'n': plan['n'], 'plan': plan,
                'title': title, 'instruction': instruction, 'candidate': candidate_hashes,
                'bounds': gate['bounds'], 'fit': gate['fit'], 'metrics': gate['metrics'],
                'generation': candidate.get('generator', {'kind': 'manual', 'id': 'local-editor', 'version': '1'}),
                'admission': {'schema': POLICY['schema'], 'policy': POLICY, 'policy_sha256': POLICY_SHA,
                              'fragment': gate_record, 'mcp': validated,
                              'render': {'status': 'not_run', 'required': False, 'scope': 'Preview is not a candidate-bound render witness.'}},
                'pipeline': {'code_sha256': self.code_sha256, 'files': self.code_files}, 'attempt_id': attempt_id}
        attempt['duration_ms'] = round((time.perf_counter()-started)*1000, 3)
        return body, raw, fragment, scene, attempt

    def append(self, *, tier=3, expected_head, expected_tail_hash, force_mode=None, candidate=None):
        tier = integer(tier, 'tier', 1, 5)
        expected_head = integer(expected_head, 'expected head', 0, self.max_entries)
        snap = self.snapshot()
        if expected_head != snap['head'] or expected_tail_hash != snap['tail_hash']:
            raise Conflict('The world changed; refresh its head and try again')
        if snap['head'] >= self.max_entries:
            raise ValueError('This local reference world has reached its configured entry cap')
        plan = plan_next(snap['placements'], snap['tail_hash'], force_mode)
        if candidate is None:
            candidate = generate(plan, tier)
        attempt_id = uuid.uuid4().hex
        body, raw, fragment, scene, attempt = self._prepare(plan, candidate, tier, attempt_id)
        body['prev_hash'] = snap['tail_hash']
        body['tier'] = tier
        created = utc()
        body['created_utc'] = created
        a = body['admission']
        body['witnesses'] = witness_rows(a)
        entry_hash = sha(body)
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                latest = db.execute('SELECT n,hash FROM entries ORDER BY n DESC LIMIT 1').fetchone()
                head, tail = (latest['n'], latest['hash']) if latest else (0, self.genesis)
                if head != expected_head or tail != expected_tail_hash:
                    raise Conflict('Another author append won; the prepared candidate was not committed')
                if sha(scene.encode()) != body['candidate']['scene_sha256'] or sha(fragment.encode()) != body['candidate']['canonical_sha256']:
                    raise ValueError('Candidate changed before commit')
                db.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,?,?)', (plan['n'], entry_hash, tail, canonical(body).decode(), raw, fragment, scene, created))
                attempt.update({'status': 'committed', 'entry_n': plan['n'], 'entry_hash': entry_hash})
                attempt['stages'].append({'id': 'commit', 'status': 'pass', 'detail': 'SQLite transaction and current-head comparison committed the append.'})
                db.execute('INSERT INTO attempts VALUES(?,?)', (attempt_id, canonical(attempt).decode()))
                db.execute('COMMIT')
        except Conflict:
            attempt['status'] = 'conflict'
            self._attempt(attempt)
            raise
        return {'entry': self.detail(plan['n'])['entry'], 'world': self.world()['world'], 'attempt': attempt}

    def archive(self):
        with self.connect() as db:
            rows = list(db.execute('SELECT * FROM entries ORDER BY n'))
        items = [{'n': row['n'], 'hash': row['hash'], 'prev_hash': row['prev_hash'], 'created_utc': row['created_utc'],
                  'payload': strict_json(row['payload']), 'raw_x3d': row['raw'], 'canonical_x3d': row['canonical'], 'scene_x3d': row['scene']} for row in rows]
        return {'schema': 'accretion.archive/1', 'hash_profile': 'accretion-c14n/1', 'world_id': 'accretion-observatory-v1',
                'genesis': self.genesis, 'entries': items, 'checkpoint': {'head': len(items), 'hash': items[-1]['hash'] if items else self.genesis},
                'scope': 'Local append history and recorded admission evidence; not a signed Loom release receipt.'}

    def verify(self):
        return verify_archive(self.archive())

    def export_x3d(self):
        archive = self.archive()
        children = []
        for row in archive['entries']:
            pos = row['payload']['plan']['translation']
            children.append('<Transform translation="'+' '.join(str(v) for v in pos)+'">'+row['canonical_x3d']+'</Transform>')
        return '<?xml version="1.0" encoding="UTF-8"?>\n<X3D profile="Immersive" version="4.0"><head><meta name="title" content="Accretion Observatory snapshot"/></head><Scene><WorldInfo title="Local procedural accretion snapshot"/><Background skyColor="0.012 0.025 0.04"/><Viewpoint position="40 36 65" orientation="-0.7 0.7 0.1 0.65"/><DirectionalLight direction="-0.4 -1 -0.6" intensity="0.9"/>'+''.join(children)+'</Scene></X3D>\n'


def verify_archive(archive, checkpoint=None):
    errors = []
    if not isinstance(archive, dict) or archive.get('schema') != 'accretion.archive/1' or archive.get('hash_profile') != 'accretion-c14n/1':
        raise ValueError('Not a supported Accretion archive')
    previous = sha(b'accretion-observatory-v1:genesis:accretion-c14n/1')
    if archive.get('genesis') != previous:
        errors.append({'code': 'GENESIS_MISMATCH'})
    if archive.get('world_id') != 'accretion-observatory-v1':
        errors.append({'code': 'WORLD_ID_MISMATCH'})
    placements = []
    entries = archive.get('entries')
    if not isinstance(entries, list):
        raise ValueError('Archive entries must be an array')
    for index, item in enumerate(entries, 1):
        try:
            body = item['payload']
            if item['created_utc'] != body['created_utc']:
                raise ValueError('entry timestamp binding mismatch')
            if type(item['n']) is not int or type(body['n']) is not int or item['n'] != index or body['n'] != index or item['prev_hash'] != previous or body['prev_hash'] != previous:
                raise ValueError('sequence or previous hash mismatch')
            if sha(body) != item['hash']:
                raise ValueError('entry payload digest mismatch')
            p = body['plan']
            if canonical(plan_next(placements, previous, p['requested_mode'])) != canonical(p):
                raise ValueError('deterministic placement replay mismatch')
            candidate = body['candidate']
            if any(candidate[key] != sha(item[field].encode()) for key, field in [('raw_sha256','raw_x3d'),('canonical_sha256','canonical_x3d'),('scene_sha256','scene_x3d')]):
                raise ValueError('candidate bytes mismatch')
            if item['scene_x3d'] != wrap_scene(item['canonical_x3d']):
                raise ValueError('stored scene is not the exact wrapped fragment')
            a = body['admission']
            if body['witnesses'] != witness_rows(a):
                raise ValueError('displayed witness summary mismatch')
            if any(body[key] != a['fragment'][key] for key in ('bounds', 'fit', 'metrics')):
                raise ValueError('displayed fragment measurements mismatch')
            if a['policy_sha256'] != sha(a['policy']) or a['policy'] != POLICY:
                raise ValueError('admission policy mismatch')
            gate, mcp = a['fragment'], a['mcp']
            if gate['status'] != 'pass' or gate['raw_sha256'] != candidate['raw_sha256'] or gate['canonical_sha256'] != candidate['canonical_sha256']:
                raise ValueError('fragment witness binding mismatch')
            if mcp['status'] != 'pass' or mcp['candidate_sha256'] != candidate['scene_sha256'] or any(mcp[name]['status'] != 'pass' for name in ('xsd','semantic')):
                raise ValueError('pinned validator witness binding mismatch')
            if body['pipeline']['code_sha256'] != sha(body['pipeline']['files']):
                raise ValueError('pipeline identity digest mismatch')
            placements.append(p)
            previous = item['hash']
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            errors.append({'n': index, 'code': 'ENTRY_MISMATCH', 'message': str(error)})
            break
    claimed = archive.get('checkpoint', {})
    last_hash = entries[-1].get('hash') if entries and isinstance(entries[-1], dict) else archive.get('genesis') if not entries else None
    if not isinstance(claimed, dict) or type(claimed.get('head')) is not int or claimed.get('head') != len(entries) or claimed.get('hash') != last_hash:
        errors.append({'code': 'CHECKPOINT_HEADER_MISMATCH'})
    if checkpoint is not None:
        n = checkpoint.get('head') if isinstance(checkpoint, dict) else None
        digest = checkpoint.get('hash') if isinstance(checkpoint, dict) else None
        record = entries[n-1] if type(n) is int and 0 < n <= len(entries) else None
        observed = record.get('hash') if isinstance(record, dict) else archive.get('genesis') if n == 0 else None
        if type(n) is not int or n < 0 or n > len(entries) or observed != digest:
            errors.append({'code': 'TRUSTED_CHECKPOINT_MISMATCH'})
    return {'valid': not errors, 'head': len(entries), 'checked': len(placements), 'tail_hash': previous,
            'errors': errors, 'scope': 'Hash chain, placement replay, policy and candidate/witness binding; not signatures, authorship or a fresh validator/render run.'}


def witness_rows(admission):
    instrument = admission['mcp'].get('instrument', {})
    brief = {key: instrument[key] for key in ('repository', 'commit', 'code_sha256') if key in instrument}
    return [
        {'id': 'fragment', 'status': admission['fragment']['status'], 'instrument': admission['fragment'].get('instrument', {}), 'scope': 'Restricted local fragment checks and conservative containment.'},
        {'id': 'xsd', 'status': admission['mcp']['xsd']['status'], 'instrument': brief, 'scope': 'Pinned upstream XSD 4.0 on exact wrapped scene bytes.'},
        {'id': 'semantic', 'status': admission['mcp']['semantic']['status'], 'instrument': brief, 'scope': 'Pinned upstream semantics using its default 4.1 UOM tables.'},
        {'id': 'render', 'status': admission['render']['status'], 'required': False, 'scope': admission['render']['scope']},
    ]
