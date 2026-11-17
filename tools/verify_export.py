#!/usr/bin/env python3
"""Verify an exported archive; optional HEAD:HASH is an independently kept checkpoint."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from accretion.codec import strict_json
from accretion.world import verify_archive
import json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive', type=Path)
parser.add_argument('--checkpoint', help='HEAD:SHA256 from a previously retained copy')
args = parser.parse_args()
try:
    checkpoint = None
    if args.checkpoint:
        head, digest = args.checkpoint.split(':', 1)
        checkpoint = {'head': int(head), 'hash': digest}
    result = verify_archive(strict_json(args.archive.read_text(encoding='utf-8')), checkpoint)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['valid'] else 1)
except (ValueError, OSError) as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(2)
