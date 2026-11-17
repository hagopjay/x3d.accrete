"""Direct offline witnesses from a pinned, unmodified x3d_mcp subset.

The adapter calls the repository's actual XML-schema validator and structured
semantic diagnostics. It is not a network MCP client and never mints a Loom
acceptance record. Missing dependencies are explicit ``not_run`` outcomes.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import importlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor' / 'x3d_mcp'
VENDOR_SRC = VENDOR / 'src'
REPOSITORY = 'https://github.com/hagopjay/x3d_mcp'
COMMIT = 'b5c9956917714747fe1d034c729612e99b0f09c9'
MAX_XML_BYTES = 128 * 1024
_DISALLOWED_DECLARATION = re.compile(r'<!\s*(?:DOCTYPE|ENTITY)\b', re.IGNORECASE)
_LOCK = threading.RLock()
_ADAPTER_SHA_AT_IMPORT = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
try:
    _ORIGIN_SHA_AT_IMPORT = hashlib.sha256((VENDOR / 'ORIGIN.json').read_bytes()).hexdigest()
except OSError:
    _ORIGIN_SHA_AT_IMPORT = None


class InstrumentError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def instrument_identity() -> dict:
    """Verify the vendored source/schema bytes before describing the instrument.

    Hashes bind a local record to these bytes. They do not authenticate a
    publisher or prove independence from the author controlling this folder.
    """
    if _sha(Path(__file__).read_bytes()) != _ADAPTER_SHA_AT_IMPORT:
        raise InstrumentError('MCP_ADAPTER_DRIFT: restart after adapter source changes')
    try:
        origin_bytes = (VENDOR / 'ORIGIN.json').read_bytes()
        if _sha(origin_bytes) != _ORIGIN_SHA_AT_IMPORT:
            raise InstrumentError('MCP_ORIGIN_DRIFT: restart after the vendored origin manifest changes')
        manifest = json.loads(origin_bytes)
    except (OSError, ValueError) as error:
        raise InstrumentError('MCP_ORIGIN_UNAVAILABLE: vendored origin manifest is unavailable') from error
    if manifest.get('repository') != REPOSITORY or manifest.get('commit') != COMMIT:
        raise InstrumentError('MCP_ORIGIN_MISMATCH: the adapter requires its pinned repository revision')
    expected = manifest.get('files_sha256')
    if not isinstance(expected, dict) or not expected:
        raise InstrumentError('MCP_ORIGIN_INVALID: a nonempty file-hash map is required')
    actual = {}
    for name, checksum in expected.items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
            raise InstrumentError('MCP_ORIGIN_INVALID: unsafe path or malformed digest')
        try:
            data = (VENDOR / path).read_bytes()
        except OSError as error:
            raise InstrumentError(f'MCP_FILE_UNAVAILABLE: {name}') from error
        actual[name] = _sha(data)
        if actual[name] != checksum:
            raise InstrumentError(f'MCP_FILE_DRIFT: {name}')
    identity = {'repository': REPOSITORY, 'commit': COMMIT, 'files_sha256': actual,
                'adapter_sha256': _ADAPTER_SHA_AT_IMPORT,
                'invocation': ['validation.validate.validate_xml(version="4.0")', 'validation.semantic.semantic_diagnostics'],
                'schema_version': '4.0', 'semantic_vocabulary_version': '4.1'}
    from lxml import etree
    identity['runtime'] = {'python': platform.python_version(), 'lxml': '.'.join(map(str, etree.LXML_VERSION)),
                           'libxml2': '.'.join(map(str, etree.LIBXML_VERSION)), 'jsonschema': metadata.version('jsonschema')}
    identity['code_sha256'] = _sha(_canonical(identity))
    return identity


def _load_vendor():
    # These upstream modules use absolute package names. Refuse an already
    # loaded foreign package instead of quietly measuring with another copy.
    for name in ('validation', 'x3d_utils'):
        loaded = sys.modules.get(name)
        origin = getattr(loaded, '__file__', None)
        if loaded is not None and (not origin or not Path(origin).resolve().is_relative_to(VENDOR_SRC)):
            raise InstrumentError(f'MCP_NAMESPACE_CONFLICT: {name} is already loaded from another source tree')
    if str(VENDOR_SRC) not in sys.path:
        sys.path.insert(0, str(VENDOR_SRC))
    validation = importlib.import_module('validation.validate')
    semantic = importlib.import_module('validation.semantic')
    for module in (validation, semantic):
        if not Path(module.__file__).resolve().is_relative_to(VENDOR_SRC):
            raise InstrumentError('MCP_MODULE_ORIGIN: imported validator does not match the vendored tree')
    return validation, semantic


def _finding(check: str, message: str, level: str = 'error') -> dict:
    return {'level': level, 'check': check, 'message': message}


def validate_scene(xml: str) -> dict:
    """Return independently scoped XSD and semantic results for exact XML bytes.

    A pass means XSD 4.0 validation completed and the pinned semantic checks
    emitted no error-level diagnostics. Warnings/infos remain visible. The
    upstream semantic module uses its default bundled 4.1 UOM vocabulary.
    No renderer, performance instrument or overall Loom accept gate runs here.
    """
    encoding_error = False
    try:
        raw = xml.encode('utf-8') if isinstance(xml, str) else b''
    except UnicodeEncodeError:
        raw = b''
        encoding_error = True
    base = {'status': 'not_run', 'candidate_sha256': _sha(raw),
            'xsd': {'status': 'not_run', 'findings': []},
            'semantic': {'status': 'not_run', 'findings': []},
            'instrument': {'repository': REPOSITORY, 'commit': COMMIT},
            'limitations': [
                'Direct calls to the pinned repository code; no network MCP server or hosted model was called.',
                'XSD is pinned to 4.0; upstream semantic checks use their default bundled 4.1 UOM/profile tables.',
                'Semantic pass means no error-level diagnostics; warnings and infos remain recorded.',
                'These checks do not establish visibility, rendering cost, aesthetic quality or Loom acceptance.',
                'File digests establish local byte identity, not publisher authentication or an independent trust root.',
            ]}
    if encoding_error or not isinstance(xml, str) or not xml.strip():
        base['status'] = 'fail'
        base['xsd'] = {'status': 'fail', 'findings': [_finding('MCP_INPUT', 'A nonempty, valid UTF-8 XML string is required.')]}
        return base
    if len(raw) > MAX_XML_BYTES:
        base['xsd']['findings'] = [_finding('MCP_INPUT_CAP', f'Per-candidate wrapper exceeds {MAX_XML_BYTES} bytes.')]
        return base
    if _DISALLOWED_DECLARATION.search(xml):
        base['status'] = 'fail'
        base['xsd'] = {'status': 'fail', 'findings': [_finding('MCP_XML_DECLARATION', 'DTD and entity declarations are refused before upstream parsing.')]}
        return base
    with _LOCK:
        try:
            base['instrument'] = instrument_identity()
            validator, semantic = _load_vendor()
        except ModuleNotFoundError as error:
            base['dependency_error'] = f'Missing dependency {error.name!r}; install the application requirements.'
            return base
        except ImportError as error:
            base['dependency_error'] = f'Validator dependency could not load: {type(error).__name__}'
            return base
        except InstrumentError as error:
            base['status'] = 'error'
            base['instrument_error'] = str(error)
            return base
        try:
            result = validator.validate_xml(xml, version='4.0')
            status = 'not_run' if result.get('checked') is False else 'pass' if result.get('valid') is True else 'fail'
            base['xsd'] = {'status': status, 'schema_version': result.get('schema_version', '4.0'),
                           'findings': [_finding('xsd', message) for message in result.get('errors', [])],
                           'notes': list(result.get('notes', []))}
            if result.get('verdict'):
                base['xsd']['verdict'] = result['verdict']
        except Exception as error:
            base['xsd'] = {'status': 'error', 'findings': [_finding('MCP_XSD_ERROR', f'{type(error).__name__}: {error}')]}
        try:
            findings = [asdict(diagnostic) for diagnostic in semantic.semantic_diagnostics(xml)]
            base['semantic'] = {'status': 'fail' if any(f['level'] == 'error' for f in findings) else 'pass', 'findings': findings}
        except (semantic.NoSceneError, ValueError) as error:
            base['semantic'] = {'status': 'fail', 'findings': [_finding('semantic-parse', str(error))]}
        except Exception as error:
            # lxml XMLSyntaxError is input failure; all other exceptions remain
            # instrument errors rather than fabricated invalid-scene findings.
            is_parse = type(error).__name__ == 'XMLSyntaxError'
            base['semantic'] = {'status': 'fail' if is_parse else 'error',
                                'findings': [_finding('semantic-parse' if is_parse else 'MCP_SEMANTIC_ERROR', f'{type(error).__name__}: {error}')]}
        statuses = [base['xsd']['status'], base['semantic']['status']]
        base['status'] = 'error' if 'error' in statuses else 'fail' if 'fail' in statuses else 'pass' if all(s == 'pass' for s in statuses) else 'not_run'
        return base
