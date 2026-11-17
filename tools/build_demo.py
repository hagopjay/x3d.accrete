#!/usr/bin/env python3
"""Build public Accretion examples using the actual admission pipeline.

The SQLite database exists only in TemporaryDirectory. No author capability,
owner secret or mutable database is written to the example directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from accretion.codec import sha
from accretion.mcp_adapter import MAX_XML_BYTES, validate_scene
from accretion.world import POLICY, POLICY_SHA, WorldStore, verify_archive


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def build_demo(count: int, output: Path, tier: int = 3) -> dict:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 512:
        raise ValueError('Demo count must be an integer from 1 to 512')
    if isinstance(tier, bool) or not isinstance(tier, int) or not 1 <= tier <= 5:
        raise ValueError('Demo tier must be an integer from 1 to 5')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='accretion-demo-') as temporary:
        store = WorldStore(Path(temporary) / 'demo.sqlite3')
        for _ in range(count):
            snapshot = store.snapshot()
            store.append(tier=tier, expected_head=snapshot['head'], expected_tail_hash=snapshot['tail_hash'])

        archive = store.archive()
        checkpoint = dict(archive['checkpoint'])
        verification = verify_archive(archive, checkpoint=checkpoint)
        if not verification['valid'] or verification['checked'] != count:
            raise ValueError('Freshly built archive did not verify against its checkpoint')
        world_xml = store.export_x3d()
        merged_validation = validate_scene(world_xml)
        world_bytes = world_xml.encode('utf-8')
        if merged_validation['candidate_sha256'] != sha(world_bytes):
            raise ValueError('Merged-world validator did not bind the exported scene bytes')

        entries = archive['entries']
        admission_rows = []
        for entry in entries:
            body = entry['payload']
            witnesses = body['witnesses']
            if any(next(w for w in witnesses if w['id'] == name)['status'] != 'pass' for name in POLICY['required']):
                raise ValueError('A demo entry is missing a required passing admission witness')
            admission_rows.append({
                'n': entry['n'], 'entry_hash': entry['hash'], 'previous_hash': entry['prev_hash'],
                'title': body['title'], 'family': body['generation'].get('family'),
                'biome': body['plan']['biome'], 'cell': body['plan']['cell'], 'level': body['plan']['level'],
                'candidate': body['candidate'], 'fit': body['fit'],
                'source_nodes': body['metrics']['nodes'], 'witnesses': witnesses,
            })
        summary = store.world(limit=512)['world']
        pipeline = {'code_sha256': store.code_sha256, 'files': store.code_files}

    # Publish only immutable/public examples after all entry admissions and
    # archive replay checks have completed. The temporary database is gone.
    world_path = output / 'world.json'
    scene_path = output / 'world.x3d'
    checkpoint_path = output / 'checkpoint.json'
    write_json(world_path, archive)
    scene_path.write_bytes(world_bytes)
    write_json(checkpoint_path, checkpoint)
    artifact_rows = {
        path.name: {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
        for path in (world_path, scene_path, checkpoint_path)
    }
    report = {
        'schema': 'accretion.demo-build/1',
        'built_utc': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
        'world': summary, 'count': count, 'tier': tier, 'model_calls': 0,
        'generation': {'kind': 'authored_procedural', 'scope': 'Fresh local sculptures, not model output.'},
        'tool': {'id': 'tools/build_demo.py', 'python': platform.python_version(),
                 'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        'pipeline': pipeline,
        'policy': {'definition': POLICY, 'sha256': POLICY_SHA},
        'archive_verification': verification,
        'checkpoint': checkpoint,
        'artifacts': artifact_rows,
        'merged_scene_validation': merged_validation,
        'merged_scene_input_cap_bytes': MAX_XML_BYTES,
        'admissions': admission_rows,
        'limitations': [
            'The world is authored procedural content. No model or hosted API was called.',
            'The checkpoint was produced in this build; it is not an independent signature or trust root.',
            'Every entry passed the actual local fragment gate and pinned XSD/semantic adapter before append.',
            'Merged-scene validation is recorded separately and may remain not_run if an enlarged export exceeds the adapter cap.',
            'No renderer or visual-performance witness ran in this command.',
            'UUIDs and recorded admission timestamps make fresh builds different histories; each saved history remains replay-verifiable.',
            'No SQLite database, owner key or author capability is included in these four example files.',
        ],
    }
    report['report_sha256'] = sha(report)
    write_json(output / 'admission-summary.json', report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=24, help='Fresh procedural entries, 1..512 (default: 24)')
    parser.add_argument('--output', type=Path, default=ROOT / 'examples', help='Directory for the four public example files')
    parser.add_argument('--tier', type=int, choices=range(1, 6), default=3, help='Authored structural tier, default 3')
    args = parser.parse_args(argv)
    try:
        report = build_demo(args.count, args.output, args.tier)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        'schema': report['schema'], 'count': report['count'], 'tier': report['tier'],
        'archive_valid': report['archive_verification']['valid'],
        'merged_scene_status': report['merged_scene_validation']['status'],
        'merged_scene_bytes': report['artifacts']['world.x3d']['bytes'],
        'checkpoint': report['checkpoint'], 'files': sorted([*report['artifacts'], 'admission-summary.json']),
        'model_calls': 0,
    }, indent=2, sort_keys=True))
    return 0 if report['merged_scene_validation']['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
