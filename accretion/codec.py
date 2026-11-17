"""Bounded JSON hash profile. Integral floats normalize across browser exports.

This is accretion-c14n/1, not RFC 8785/JCS. Verify with this implementation.
"""
import hashlib
import json
import math


def normalized(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Nonfinite JSON number')
        return int(value) if value.is_integer() else value
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized(item) for item in value]
    return value


def canonical(value):
    return json.dumps(normalized(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def strict_json(text):
    def refuse(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise ValueError('Duplicate JSON key: ' + key)
            out[key] = value
        return out
    return json.loads(text, parse_constant=refuse, object_pairs_hook=pairs)
