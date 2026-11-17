#!/usr/bin/env python3
"""Measure real local admission, SQLite append, replay and snapshot exports.

One empty temporary world grows through 10, 100 and, if the measured projection
permits, 1,000 entries. Every append runs the real local gate and pinned MCP
validators. This is not a GPU, browser, cloud, network or presence benchmark.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from accretion.codec import canonical, sha
from accretion.world import WorldStore


def cpu_name():
    name = platform.processor()
    info = Path('/proc/cpuinfo')
    if not name and info.is_file():
        for line in info.read_text(errors='replace').splitlines():
            if line.startswith('model name'):
                name = line.split(':', 1)[1].strip()
                break
    return name or 'not reported'


def cpu_quota():
    path = Path('/sys/fs/cgroup/cpu.max')
    if not path.is_file():
        return None
    quota, period = path.read_text().split()[:2]
    return None if quota == 'max' else int(quota)/int(period)


def db_sizes(path):
    values = {}
    for suffix, key in [('', 'database'), ('-wal', 'wal'), ('-shm', 'shared_memory')]:
        candidate = Path(str(path)+suffix)
        values[key] = candidate.stat().st_size if candidate.exists() else 0
    values['total'] = sum(values.values())
    return values


def timed(fn):
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter()-start


def rounded(seconds):
    return round(seconds, 6)


def p95(values):
    return sorted(values)[max(0, (95*len(values)+99)//100-1)]


def projection_1000(append_seconds, observed_overhead):
    """A simple nonnegative linear per-append trend from two measured windows.

    Last-20 average is compared with the early warm 2..10 average. The fitted
    slope is integrated over appends 101..1000. Verification/export overhead
    is conservatively scaled 10x from the measured 100-entry checkpoint.
    This is a stop rule, not a performance result for an unexecuted workload.
    """
    early = statistics.mean(append_seconds[1:10])
    late = statistics.mean(append_seconds[80:100])
    slope = max(0.0, (late-early)/(90.5-6.0))
    intercept = max(0.0, early-slope*6.0)
    remaining = 900*intercept + slope*sum(range(101, 1001))
    projected = sum(append_seconds) + remaining + observed_overhead*10
    return {'projected_total_seconds': rounded(projected),
            'method': 'Nonnegative linear per-append trend, early warm entries 2..10 versus entries 81..100; integrate 101..1000; add 10x measured 100-entry verify/export overhead.',
            'early_warm_mean_seconds': rounded(early), 'late_mean_seconds': rounded(late),
            'per_entry_slope_seconds': round(slope, 9), 'intercept_seconds': rounded(intercept),
            'status': 'estimate_only_not_a_1000_entry_measurement'}


def run(output, max_projected_seconds=90.0):
    started_utc = datetime.now(timezone.utc).isoformat(timespec='seconds')
    overall_start = time.perf_counter()
    report = {'schema': 'accretion.store-scaling/1', 'recorded_utc': started_utc,
              'scope': 'Single-writer local backend: actual fragment admission, pinned XSD/semantics, SQLite transactions, archive replay and JSON/X3D serialization.',
              'not_measured': ['GPU or browser performance', 'concurrent-author throughput', 'cloud storage', 'network delivery', 'authenticated human presence', 'model latency or spend'],
              'rig': {'python': platform.python_version(), 'implementation': platform.python_implementation(),
                      'platform': platform.platform(), 'machine': platform.machine(), 'cpu': cpu_name(),
                      'logical_cpus_reported': os.cpu_count(), 'cgroup_cpu_quota': cpu_quota(),
                      'note': 'One shared runtime, one process and one writer. Filesystem cache and runtime scheduling were not isolated.'},
              'workload': {'requested_checkpoints': [10, 100, 1000], 'tier': 3,
                           'source': 'New empty temporary SQLite database; authored procedural patches, zero model calls.',
                           'admission_bypasses': False,
                           'cold_warm': 'First append includes lazy schema/validator initialization in this process. Later appends reuse upstream parser/schema caches. Imports before run() are outside append timing.',
                           'stop_rule_seconds': max_projected_seconds},
              'checkpoints': [], 'corpus': [], 'skipped': []}
    append_times = []
    validation_ms = []
    stage_start_index = 0
    max_storage = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='accretion-scaling-') as directory:
        db_path = Path(directory)/'world.sqlite3'
        store = WorldStore(db_path)
        report['instrument'] = {'script': 'tools/benchmark_store.py',
                                'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                'pipeline_code_sha256': store.code_sha256, 'pipeline_files': store.code_files}
        target = 1000
        index = 0
        while index < target:
            index += 1
            snapshot = store.snapshot()
            result, elapsed = timed(lambda: store.append(tier=3, expected_head=snapshot['head'], expected_tail_hash=snapshot['tail_hash']))
            append_times.append(elapsed)
            validation_ms.append(result['attempt']['duration_ms'])
            sizes = db_sizes(db_path)
            max_storage = max(max_storage, sizes['total'])
            detail = store.detail(index)
            body = detail['payload']
            if index == 1:
                report['instrument']['mcp'] = body['admission']['mcp']['instrument']
            report['corpus'].append({'n': index, 'hash': result['entry']['hash'], 'prev_hash': result['entry']['prev_hash'],
                                     'plan': body['plan'], 'tier': body['tier'], 'candidate': body['candidate'],
                                     'family': body['generation'].get('family'), 'nodes': body['metrics']['nodes'],
                                     'raw_bytes': len(detail['raw_x3d'].encode('utf-8'))})
            if index % 50 == 0:
                print(json.dumps({'progress_entries': index, 'append_wall_seconds': rounded(sum(append_times)),
                                  'last_append_ms': round(elapsed*1000, 3)}), flush=True)
            if index not in (10, 100, 1000):
                continue
            verified, verify_elapsed = timed(store.verify)
            archive, archive_elapsed = timed(store.archive)
            archive_bytes, json_elapsed = timed(lambda: canonical(archive))
            scene, scene_elapsed = timed(store.export_x3d)
            current = append_times[stage_start_index:index]
            checkpoint = {'entries': index, 'append_wall_seconds_cumulative': rounded(sum(append_times)),
                          'append_wall_seconds_stage': rounded(sum(current)),
                          'append_mean_ms_stage': round(statistics.mean(current)*1000, 3),
                          'append_median_ms_stage': round(statistics.median(current)*1000, 3),
                          'append_p95_ms_stage': round(p95(current)*1000, 3),
                          'first_append_ms_including_cold_validation': round(append_times[0]*1000, 3),
                          'prepare_gate_and_validator_ms_cumulative': round(sum(validation_ms), 3),
                          'verify_wall_seconds': rounded(verify_elapsed), 'verify_valid': verified['valid'],
                          'verify_checked_entries': verified['checked'],
                          'archive_read_wall_seconds': rounded(archive_elapsed),
                          'json_serialize_wall_seconds': rounded(json_elapsed), 'json_bytes': len(archive_bytes),
                          'x3d_export_wall_seconds': rounded(scene_elapsed), 'x3d_bytes': len(scene.encode('utf-8')),
                          'storage_bytes': sizes, 'max_storage_bytes_observed': max_storage,
                          'checkpoint': archive['checkpoint']}
            report['checkpoints'].append(checkpoint)
            stage_start_index = index
            print(json.dumps({'checkpoint': index, 'append_seconds': checkpoint['append_wall_seconds_cumulative'],
                              'verify_valid': verified['valid'], 'json_bytes': len(archive_bytes)}), flush=True)
            if not verified['valid'] or verified['checked'] != index:
                raise ValueError('Actual world replay verification failed during the benchmark')
            if index == 100:
                overhead = verify_elapsed + archive_elapsed + json_elapsed + scene_elapsed
                projected = projection_1000(append_times, overhead)
                report['projection_at_100'] = projected
                if projected['projected_total_seconds'] > max_projected_seconds:
                    report['skipped'].append({'entries': 1000, 'reason': 'Measured 100-entry trend projected above the configured run budget.',
                                              'projected_total_seconds': projected['projected_total_seconds'],
                                              'limit_seconds': max_projected_seconds, 'status': 'not_run'})
                    break
        report['measured_entries'] = index
        report['families'] = dict(sorted(Counter(row['family'] for row in report['corpus']).items()))
        report['raw_patch_bytes'] = {'min': min(row['raw_bytes'] for row in report['corpus']),
                                     'max': max(row['raw_bytes'] for row in report['corpus']),
                                     'mean': round(statistics.mean(row['raw_bytes'] for row in report['corpus']), 3)}
        report['observed_total_wall_seconds'] = rounded(time.perf_counter()-overall_start)
        report['temporary_database_removed_after_run'] = True
        report['limitations'] = [
            'Each append performs full actual local admission; no mock witnesses or prevalidated admission bypass were used.',
            'The record includes every procedural plan and candidate digest so the exact generated fragments can be reconstructed from pinned generator code.',
            'Append wall time includes the application method, whose return value reads the current world. It excludes the caller snapshot/detail read and checkpoint exports.',
            'Source timestamps and attempt identities influence the history chain; independent runs need not traverse the same procedural plans.',
            'The 1,000-entry projection, if used to stop, is an explicit estimate and never a measurement.',
            'These serialized sizes and local timings do not establish million-patch capacity, GPU frame rate or cloud throughput.',
        ]
    report['report_sha256'] = sha(report)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'saved': output.name, 'measured_entries': report['measured_entries'],
                      'wall_seconds': report['observed_total_wall_seconds'], 'skipped': report['skipped']}), flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/store-scaling.json')
    parser.add_argument('--max-projected-seconds', type=float, default=90)
    args = parser.parse_args(argv)
    if args.max_projected_seconds <= 0:
        parser.error('Projection budget must be positive')
    run(args.output, args.max_projected_seconds)


if __name__ == '__main__':
    main()
