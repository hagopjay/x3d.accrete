#!/usr/bin/env python3
"""Export a verified Accretion archive as a static, server-less, read-only site payload.

Writes web/static-world/ (default) so that web/index.html can be hosted on GitHub Pages
or any static file host.  The archive is verified with the Python verifier first; an
archive that does not verify (or does not match --checkpoint) is refused.

    python3 tools/export_static.py --archive examples/world.json
    python3 tools/export_static.py --archive examples/world.json --check   # CI: output must be current

No model calls, no network.  Output is deterministic: the same archive gives the same bytes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from accretion.codec import canonical, sha, strict_json
from accretion.world import POLICY, WorldStore, export_x3d_from_archive, verify_archive

DEFAULT_OUT = ROOT / 'web' / 'static-world'


def _row(item: dict) -> dict:
    return {'n': item['n'], 'hash': item['hash'], 'prev_hash': item['prev_hash'],
            'created_utc': item['created_utc'], 'payload': canonical(item['payload']).decode()}


def _summary(rows: list[dict], genesis: str) -> dict:
    plans = [strict_json(r['payload'])['plan'] for r in rows]
    return {'id': 'accretion-observatory-v1', 'head': len(rows), 'entries_count': len(rows),
            'tail_hash': rows[-1]['hash'] if rows else genesis, 'cell_count': len({tuple(p['cell']) for p in plans}),
            'max_level': max((p['level'] for p in plans), default=0),
            'last_append_utc': rows[-1]['created_utc'] if rows else None}


def build(archive: dict, window: int = 512) -> dict[str, bytes]:
    """Return {relative path: bytes} for the static payload."""
    rows = [_row(item) for item in archive['entries']]
    visible = rows[-window:]
    public = WorldStore.public_entry  # uses only the row mapping and module constants
    world = {'schema': 'accretion.world/v1', 'mode': 'local_reference', 'generator': 'procedural', 'model_calls': 0,
             'world': _summary(rows, archive['genesis']), 'entries': [public(None, r) for r in visible],
             'truncated': len(rows) > window, 'visible_start': visible[0]['n'] if visible else 0,
             'max_entries': 10_000, 'policy': {'profile_id': POLICY['schema'], **POLICY},
             'presence': {'sessions': [], 'count': 0, 'verified_people': False}}
    files: dict[str, bytes] = {'api/world.json': canonical(world)}
    for item, row in zip(archive['entries'], rows):
        n = item['n']
        detail = {'entry': public(None, row), 'payload': item['payload'], 'raw_x3d': item['raw_x3d'],
                  'canonical_x3d': item['canonical_x3d'], 'scene_x3d': item['scene_x3d']}
        files[f'api/entries/{n}.json'] = canonical(detail)
        files[f'patches/{n:06d}.x3d'] = item['scene_x3d'].encode('utf-8')
    files['api/export.json'] = canonical(archive)
    files['api/export.x3d'] = export_x3d_from_archive(archive).encode('utf-8')
    verification = verify_archive(archive, checkpoint=archive['checkpoint'])
    files['api/verify-python.json'] = canonical(verification)
    inventory = {path: {'bytes': len(data), 'sha256': sha(data)} for path, data in sorted(files.items())}
    manifest = {'schema': 'accretion.static-world/1', 'world_id': archive['world_id'], 'hash_profile': archive['hash_profile'],
                'checkpoint': archive['checkpoint'], 'entries': len(rows),
                'archive_sha256': sha(files['api/export.json']),
                'scope': 'Read-only copy of a locally verified archive. Hosting it adds no trust: re-verify in the page or with tools/verify_export.py.',
                'files': inventory}
    files['manifest.json'] = canonical(manifest)
    return files


def write(files: dict[str, bytes], out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    for rel, data in files.items():
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def check(files: dict[str, bytes], out: Path) -> list[str]:
    problems = []
    existing = {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()} if out.exists() else set()
    for rel in sorted(set(files) | existing):
        if rel not in files:
            problems.append('unexpected ' + rel)
        elif rel not in existing:
            problems.append('missing ' + rel)
        elif (out / rel).read_bytes() != files[rel]:
            problems.append('differs ' + rel)
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--archive', required=True, type=Path)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--checkpoint', type=Path, help='trusted checkpoint JSON {head, hash}; defaults to the archive header')
    ap.add_argument('--window', type=int, default=512, help='entries listed by api/world.json (viewer cap is 512)')
    ap.add_argument('--check', action='store_true', help='do not write; fail if the output directory is not current')
    args = ap.parse_args(argv)
    archive = strict_json(args.archive.read_text(encoding='utf-8'))
    trusted = strict_json(args.checkpoint.read_text(encoding='utf-8')) if args.checkpoint else archive.get('checkpoint')
    result = verify_archive(archive, checkpoint=trusted)
    if not result['valid']:
        print('REFUSED: archive does not verify:', json.dumps(result['errors'])[:400], file=sys.stderr)
        return 2
    files = build(archive, args.window)
    if args.check:
        problems = check(files, args.out)
        print('static payload current' if not problems else 'static payload STALE: ' + '; '.join(problems[:8]))
        return 1 if problems else 0
    write(files, args.out)
    total = sum(len(d) for d in files.values())
    print(f"wrote {len(files)} files, {total:,} bytes to {args.out}; head {archive['checkpoint']['head']} hash {archive['checkpoint']['hash']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
