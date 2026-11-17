"""A bounded, deterministic X3D fragment admission instrument.

This is deliberately narrower than X3D. It neither claims schema conformance
nor establishes visibility, quality, safety of arbitrary X3D, or Loom acceptance.
Only its canonical, fitted output should reach the world renderer.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

VERSION = '2.0.0'
MAX_BYTES = 12 * 1024
MAX_CANONICAL_BYTES = 24 * 1024
MAX_NODES = 80
MAX_DEPTH = 16
MAX_EXPANDED_SHAPES = 160
SLOT_RADIUS = 3.0
REJECT_RADIUS = 120.0
_FLOAT = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z')
_INT = re.compile(r'[+-]?\d+\Z')
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}\Z')
_PREFIX = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')
_ENTITY = re.compile(r'&(?!(?:amp|lt|gt|apos|quot);)')
_IMPORTED_CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class GateError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _fail(code, message):
    raise GateError('GATE_' + code, message)


def _fmt(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (list, tuple)):
        return ' '.join(_fmt(x) for x in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail('NONFINITE', 'Arithmetic produced a nonfinite value')
        return '0' if value == 0 else str(int(value)) if value.is_integer() else repr(value)
    return str(value)


def _nums(text, count=None, low=-1e6, high=1e6, integers=False, multiple=None, max_items=8192):
    parts = text.replace(',', ' ').split()
    if not parts or len(parts) > max_items or count is not None and len(parts) != count:
        _fail('FIELD_LENGTH', f'Numeric field needs {count or "a bounded nonempty list of"} values')
    if multiple and len(parts) % multiple:
        _fail('FIELD_LENGTH', f'Numeric list must have a multiple of {multiple} components')
    pattern = _INT if integers else _FLOAT
    if any(not pattern.fullmatch(v) for v in parts):
        _fail('FIELD_NUMBER', 'Numeric field contains an invalid lexical number')
    values = [int(v) if integers else float(v) for v in parts]
    if any(not math.isfinite(v) or not low <= v <= high for v in values):
        _fail('FIELD_RANGE', f'Numeric field must be finite and within [{low}, {high}]')
    return values


def _boolean(text):
    if text not in ('true', 'false', '1', '0'):
        _fail('FIELD_BOOLEAN', 'Boolean must be true, false, 1 or 0')
    return text in ('true', '1')


def _positive(text, count=1):
    result = _nums(text, count)
    if any(v <= 0 for v in result):
        _fail('FIELD_POSITIVE', 'Dimension must be strictly positive')
    return result[0] if count == 1 else result


def _rotation(text, multi=False):
    values = _nums(text, None if multi else 4, multiple=4 if multi else None)
    out = []
    for i in range(0, len(values), 4):
        x, y, z, angle = values[i:i+4]
        length = math.hypot(x, y, z)
        if length == 0:
            if angle != 0:
                _fail('ROTATION_AXIS', 'A nonzero rotation needs a nonzero axis')
            out.extend([0.0, 0.0, 1.0, 0.0])
        else:
            out.extend([x / length, y / length, z / length, angle])
    return out


def _field(kind, text):
    if kind == 'bool':
        return _boolean(text)
    if kind == 'positive':
        return _positive(text)
    if kind == 'size':
        return _positive(text, 3)
    if kind == 'scale':
        value = _nums(text, 3)
        if any(v == 0 for v in value):
            _fail('ZERO_SCALE', 'Static scale components must be nonzero')
        return value
    if kind == 'vec3':
        return _nums(text, 3)
    if kind == 'direction':
        value = _nums(text, 3)
        length = math.hypot(*value)
        if not length:
            _fail('DIRECTION_ZERO', 'A light direction must be nonzero')
        return [v / length for v in value]
    if kind == 'attenuation':
        value = _nums(text, 3, 0, 1e6)
        if not any(value):
            _fail('ATTENUATION_ZERO', 'Light attenuation cannot be all zero')
        return value
    if kind == 'color':
        return _nums(text, 3, 0, 1)
    if kind == 'unit':
        return _nums(text, 1, 0, 1)[0]
    if kind == 'angle':
        return _nums(text, 1, 0, math.pi)[0]
    if kind == 'spotangle':
        return _nums(text, 1, 0, math.pi/2)[0]
    if kind == 'radius':
        return _nums(text, 1, .001, 30)[0]
    if kind == 'cycle':
        return _nums(text, 1, .5, 3600)[0]
    if kind == 'time':
        return _nums(text, 1, 0, 1e12)[0]
    if kind == 'rotation':
        return _rotation(text)
    if kind == 'rotations':
        return _rotation(text, True)
    if kind == 'dimension':
        return _nums(text, 1, 2, 64, integers=True)[0]
    if kind == 'key':
        value = _nums(text, low=0, high=1, max_items=32)
        if len(value) < 2 or any(a >= b for a, b in zip(value, value[1:])):
            _fail('KEY_ORDER', 'Interpolator needs 2 to 32 strictly increasing keys in [0, 1]')
        return value
    if kind == 'indices':
        return _nums(text, low=-1, high=4095, integers=True, max_items=4096)
    if kind == 'points':
        return _nums(text, multiple=3, max_items=3072)
    if kind == 'colors':
        return _nums(text, low=0, high=1, multiple=3, max_items=3072)
    if kind == 'vec2list':
        return _nums(text, multiple=2, max_items=128)
    if kind == 'vec3list':
        return _nums(text, multiple=3, max_items=192)
    if kind == 'values':
        return _nums(text, max_items=4096)
    _fail('INTERNAL_FIELD', 'Unknown gate field type')


_MATERIAL = {k: 'color' for k in ('diffuseColor', 'emissiveColor', 'specularColor')}
_MATERIAL.update({k: 'unit' for k in ('ambientIntensity', 'shininess', 'transparency')})
_LIGHT = {'ambientIntensity': 'unit', 'color': 'color', 'intensity': 'unit', 'on': 'bool', 'global': 'bool'}
FIELDS = {
    'Group': {},
    'Transform': {'translation': 'vec3', 'rotation': 'rotation', 'scale': 'scale', 'center': 'vec3', 'scaleOrientation': 'rotation'},
    'Shape': {}, 'Appearance': {}, 'Material': _MATERIAL,
    'PhysicalMaterial': {'baseColor': 'color', 'emissiveColor': 'color', 'metallic': 'unit', 'roughness': 'unit', 'transparency': 'unit'},
    'Box': {'size': 'size', 'solid': 'bool'},
    'Sphere': {'radius': 'positive', 'solid': 'bool'},
    'Cylinder': {'radius': 'positive', 'height': 'positive', 'side': 'bool', 'top': 'bool', 'bottom': 'bool', 'solid': 'bool'},
    'Cone': {'bottomRadius': 'positive', 'height': 'positive', 'side': 'bool', 'bottom': 'bool', 'solid': 'bool'},
    'Coordinate': {'point': 'points'}, 'Color': {'color': 'colors'},
    'IndexedFaceSet': {'coordIndex': 'indices', 'ccw': 'bool', 'convex': 'bool', 'solid': 'bool', 'colorPerVertex': 'bool', 'creaseAngle': 'angle'},
    'IndexedLineSet': {'coordIndex': 'indices', 'colorPerVertex': 'bool'},
    'ElevationGrid': {'xDimension': 'dimension', 'zDimension': 'dimension', 'xSpacing': 'positive', 'zSpacing': 'positive', 'height': 'values', 'ccw': 'bool', 'solid': 'bool', 'colorPerVertex': 'bool', 'creaseAngle': 'angle'},
    'Extrusion': {'crossSection': 'vec2list', 'spine': 'vec3list', 'scale': 'vec2list', 'orientation': 'rotations', 'ccw': 'bool', 'convex': 'bool', 'beginCap': 'bool', 'endCap': 'bool', 'solid': 'bool', 'creaseAngle': 'angle'},
    'TimeSensor': {'cycleInterval': 'cycle', 'loop': 'bool', 'enabled': 'bool', 'startTime': 'time', 'stopTime': 'time'},
    'PositionInterpolator': {'key': 'key', 'keyValue': 'values'},
    'OrientationInterpolator': {'key': 'key', 'keyValue': 'rotations'},
    'ColorInterpolator': {'key': 'key', 'keyValue': 'colors'},
    'ScalarInterpolator': {'key': 'key', 'keyValue': 'values'},
    'DirectionalLight': {**_LIGHT, 'direction': 'direction'},
    'PointLight': {**_LIGHT, 'location': 'vec3', 'radius': 'radius', 'attenuation': 'attenuation'},
    'SpotLight': {**_LIGHT, 'location': 'vec3', 'radius': 'radius', 'attenuation': 'attenuation', 'direction': 'direction', 'beamWidth': 'spotangle', 'cutOffAngle': 'spotangle'},
    'ROUTE': {},
}
GEOMETRY = {'Box', 'Sphere', 'Cylinder', 'Cone', 'IndexedFaceSet', 'IndexedLineSet', 'ElevationGrid', 'Extrusion'}
INTERPOLATORS = {'PositionInterpolator': (3, 'SFVec3f'), 'OrientationInterpolator': (4, 'SFRotation'), 'ColorInterpolator': (3, 'SFColor'), 'ScalarInterpolator': (1, 'SFFloat')}
LIGHTS = {'DirectionalLight', 'PointLight', 'SpotLight'}
GROUP_CHILDREN = {'Group', 'Transform', 'Shape', 'TimeSensor', *INTERPOLATORS, *LIGHTS}


def _children(parent, child):
    if parent in ('Fragment', 'Group', 'Transform') and child in GROUP_CHILDREN:
        return 'children'
    if parent == 'Fragment' and child == 'ROUTE':
        return None
    if parent == 'Shape' and child == 'Appearance':
        return 'appearance'
    if parent == 'Shape' and child in GEOMETRY:
        return 'geometry'
    if parent == 'Appearance' and child in ('Material', 'PhysicalMaterial'):
        return 'material'
    if parent in ('IndexedFaceSet', 'IndexedLineSet') and child == 'Coordinate':
        return 'coord'
    if parent in ('IndexedFaceSet', 'IndexedLineSet', 'ElevationGrid') and child == 'Color':
        return 'color'
    _fail('CONTAINMENT', f'{child} is not admitted inside {parent}')


def _parse(xml):
    clean = re.sub(r'^\s*<\?xml\s[^?]*\?>', '', xml, count=1)
    upper = clean.upper()
    if '<!DOCTYPE' in upper or '<!ENTITY' in upper:
        _fail('DTD_ENTITY', 'DTD and entity declarations are forbidden')
    if '<![CDATA[' in upper:
        _fail('CDATA', 'CDATA is forbidden in a patch')
    if '<!--' in clean or '<?' in clean or '<!' in clean:
        _fail('XML_DECLARATION', 'Comments, processing instructions and declarations are outside this patch policy')
    if _ENTITY.search(clean):
        _fail('ENTITY_REFERENCE', 'Only the five standard named XML entities are admitted')
    try:
        root = ET.fromstring('<Fragment>' + clean + '</Fragment>')
    except ET.ParseError as error:
        _fail('XML_PARSE', 'Malformed XML: ' + str(error))
    if any(node.text and node.text.strip() or node.tail and node.tail.strip() for node in root.iter()):
        _fail('TEXT_CONTENT', 'Text content is forbidden, including outside wrapper elements')
    if len(root) == 1 and root[0].tag in ('X3D', 'Scene'):
        wrapper = root[0]
        if wrapper.tag == 'X3D':
            if set(wrapper.attrib) - {'profile', 'version'} or wrapper.get('version', '4.0') != '4.0':
                _fail('WRAPPER', 'X3D wrapper supports only version 4.0 and a profile declaration')
            if len(wrapper) != 1 or wrapper[0].tag != 'Scene':
                _fail('WRAPPER', 'X3D wrapper must contain exactly one Scene and no head/global data')
            wrapper = wrapper[0]
        if wrapper.attrib:
            _fail('WRAPPER', 'Scene wrapper cannot carry attributes')
        if wrapper.text and wrapper.text.strip() or wrapper.tail and wrapper.tail.strip():
            _fail('TEXT_CONTENT', 'Text content is forbidden')
        root = ET.Element('Fragment')
        root.extend(list(wrapper))
    if not len(root):
        _fail('EMPTY', 'A patch must contain geometry')
    return root


def gate_fragment(xml: str, prefix: str = 'P') -> dict:
    instrument = {'id': 'accretion.fragment-gate', 'version': VERSION,
                  'code_sha256': _IMPORTED_CODE_SHA256,
                  'scope': 'Bounded XML subset, typed local references and conservative geometry/animation envelopes; not XSD, visibility, taste or Loom release acceptance.'}
    result = {'status': 'fail', 'errors': [], 'raw_sha256': None, 'canonical_x3d': None,
              'canonical_sha256': None, 'bounds': None, 'raw_bounds': None, 'fit': None,
              'metrics': {}, 'instrument': instrument}
    try:
        try:
            current_code = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        except OSError:
            _fail('INSTRUMENT_DRIFT', 'Gate source cannot be read; restart from a complete installation')
        if current_code != _IMPORTED_CODE_SHA256:
            _fail('INSTRUMENT_DRIFT', 'Gate source changed after import; restart before collecting another verdict')
        if not isinstance(xml, str):
            _fail('INPUT_TYPE', 'Fragment must be a UTF-8 string')
        try:
            raw = xml.encode('utf-8')
        except UnicodeEncodeError:
            _fail('UTF8', 'Fragment contains an invalid Unicode surrogate')
        result['raw_sha256'] = hashlib.sha256(raw).hexdigest()
        if len(raw) > MAX_BYTES:
            _fail('BYTES', f'Patch exceeds the {MAX_BYTES}-byte input cap')
        if not isinstance(prefix, str) or prefix and not _PREFIX.fullmatch(prefix):
            _fail('PREFIX', 'Prefix must be empty or a bounded XML identifier')
        root = _parse(xml)
        defs, values, routes, order = {}, {}, [], []
        counters = {'nodes': 0, 'shapes': 0, 'routes': 0, 'timers': 0, 'lights': 0, 'materials': 0, 'uses': 0, 'interpolators': 0}

        def visit(node, parent='Fragment', depth=1, ancestors=()):
            if depth > MAX_DEPTH:
                _fail('DEPTH', f'Patch nesting exceeds {MAX_DEPTH}')
            if node.tag not in FIELDS:
                _fail('NODE_FORBIDDEN', f'{node.tag} is outside the bounded patch vocabulary')
            field = _children(parent, node.tag)
            counters['nodes'] += 1
            if counters['nodes'] > MAX_NODES:
                _fail('NODES', f'Patch exceeds {MAX_NODES} source nodes')
            if node.text and node.text.strip() or node.tail and node.tail.strip():
                _fail('TEXT_CONTENT', 'Text content is forbidden')
            if node.get('containerField') is not None and node.get('containerField') != field:
                _fail('CONTAINER_FIELD', f'Unexpected containerField on {node.tag}')
            if node.tag == 'ROUTE':
                if set(node.attrib) != {'fromNode', 'fromField', 'toNode', 'toField'} or len(node):
                    _fail('ROUTE_SHAPE', 'ROUTE requires exactly its four endpoint attributes')
                if any(node.get(k) not in defs for k in ('fromNode', 'toNode')):
                    _fail('ROUTE_LOCAL', 'ROUTE endpoints must already be defined inside this patch')
                routes.append(node)
                counters['routes'] += 1
                return
            if 'USE' in node.attrib:
                name = node.get('USE')
                if set(node.attrib) - {'USE', 'containerField'} or len(node):
                    _fail('USE_SHAPE', 'USE must not carry fields, DEF or children')
                if name not in defs:
                    _fail('USE_FORWARD', 'USE must refer to an earlier local DEF')
                if defs[name].tag != node.tag:
                    _fail('USE_TYPE', 'USE node type differs from its DEF')
                if name in ancestors:
                    _fail('USE_CYCLE', 'A grouping node cannot contain itself through USE')
                counters['uses'] += 1
                values[id(node)] = {}
                return
            name = node.get('DEF')
            if name is not None:
                if not _NAME.fullmatch(name):
                    _fail('DEF_NAME', 'DEF must be a bounded XML identifier')
                if name in defs:
                    _fail('DEF_DUPLICATE', 'DEF names must be unique inside a patch')
                defs[name] = node
            attrs = set(node.attrib) - {'DEF', 'containerField'}
            unexpected = attrs - set(FIELDS[node.tag])
            if unexpected:
                _fail('FIELD_FORBIDDEN', f'Unsupported field on {node.tag}: {sorted(unexpected)[0]}')
            parsed = {key: _field(FIELDS[node.tag][key], node.get(key)) for key in attrs}
            if node.tag in LIGHTS:
                parsed['global'] = False
                counters['lights'] += 1
            if node.tag == 'TimeSensor':
                parsed.setdefault('cycleInterval', 1.0)
                counters['timers'] += 1
            if node.tag in INTERPOLATORS:
                counters['interpolators'] += 1
                if 'key' not in parsed or 'keyValue' not in parsed:
                    _fail('KEY_REQUIRED', 'Interpolator requires key and keyValue')
                width = INTERPOLATORS[node.tag][0]
                if len(parsed['keyValue']) != len(parsed['key']) * width:
                    _fail('KEY_VALUE_COUNT', 'Interpolator keyValue count does not match keys')
            if node.tag == 'SpotLight' and parsed.get('beamWidth', math.pi/4) > parsed.get('cutOffAngle', math.pi/2):
                _fail('SPOT_CONE', 'SpotLight beamWidth must not exceed cutOffAngle')
            counters['shapes'] += node.tag == 'Shape'
            counters['materials'] += node.tag in ('Material', 'PhysicalMaterial')
            values[id(node)] = parsed
            order.append(node)
            for child in node:
                visit(child, node.tag, depth + 1, ancestors + ((name,) if name else ()))
            child_types = [child.tag for child in node]
            if node.tag == 'Shape' and (sum(t in GEOMETRY for t in child_types) != 1 or child_types.count('Appearance') > 1):
                _fail('SHAPE_GEOMETRY', 'Shape requires exactly one geometry and at most one Appearance')
            if node.tag == 'Appearance' and len(node) > 1:
                _fail('MATERIAL_COUNT', 'Appearance admits at most one material')

        if root.text and root.text.strip():
            _fail('TEXT_CONTENT', 'Text content is forbidden')
        for node in root:
            visit(node)
        for key, cap in [('routes', 12), ('timers', 2), ('lights', 1), ('interpolators', 8)]:
            if counters[key] > cap:
                _fail(key.upper() + '_CAP', f'Patch exceeds {cap} {key}')

        def actual(node):
            return defs[node.get('USE')] if node.get('USE') else node

        def child_of(node, tag):
            found = [actual(child) for child in node if child.tag == tag]
            if len(found) > 1:
                _fail('CHILD_DUPLICATE', f'{node.tag} admits at most one {tag}')
            return found[0] if found else None

        custom_triangles = 0
        for node in order:
            v = values[id(node)]
            if node.tag in ('IndexedFaceSet', 'IndexedLineSet'):
                coordinate = child_of(node, 'Coordinate')
                if coordinate is None or 'point' not in values[id(coordinate)] or 'coordIndex' not in v:
                    _fail('COORDINATE_REQUIRED', 'Indexed geometry needs Coordinate.point and coordIndex')
                points = len(values[id(coordinate)]['point']) // 3
                segments, segment = [], []
                for index in v['coordIndex']:
                    if index == -1:
                        if not segment:
                            _fail('INDEX_EMPTY', 'Empty indexed face/line is not admitted')
                        segments.append(segment); segment = []
                    else:
                        if index >= points:
                            _fail('INDEX_RANGE', 'Coordinate index is outside its point array')
                        segment.append(index)
                if segment:
                    segments.append(segment)
                minimum = 3 if node.tag == 'IndexedFaceSet' else 2
                if not segments or any(len(part) < minimum for part in segments):
                    _fail('INDEX_CARDINALITY', 'Indexed face/line has too few vertices')
                color = child_of(node, 'Color')
                if color is not None:
                    needed = points if v.get('colorPerVertex', True) else len(segments)
                    if len(values[id(color)].get('color', [])) // 3 < needed:
                        _fail('COLOR_COUNT', 'Color array is shorter than the implicit index mapping')
                if node.tag == 'IndexedFaceSet':
                    custom_triangles += sum(len(part) - 2 for part in segments)
            if node.tag == 'ElevationGrid':
                if not {'xDimension', 'zDimension', 'height'} <= set(v) or len(v['height']) != v['xDimension'] * v['zDimension']:
                    _fail('GRID_HEIGHT_COUNT', 'ElevationGrid height count must equal xDimension times zDimension')
                color = child_of(node, 'Color')
                if color is not None:
                    needed = v['xDimension'] * v['zDimension'] if v.get('colorPerVertex', True) else (v['xDimension']-1) * (v['zDimension']-1)
                    if len(values[id(color)].get('color', [])) // 3 < needed:
                        _fail('COLOR_COUNT', 'ElevationGrid Color array is too short')
                custom_triangles += 2 * (v['xDimension']-1) * (v['zDimension']-1)
            if node.tag == 'Extrusion':
                cross = v.get('crossSection', [1, 1, 1, -1, -1, -1, -1, 1, 1, 1])
                spine = v.get('spine', [0, 0, 0, 0, 1, 0])
                if len(cross) < 6 or len(spine) < 6:
                    _fail('EXTRUSION_COUNT', 'Extrusion needs at least three cross-section points and two spine points')
                n = len(spine) // 3
                if len(v.get('scale', [1, 1])) not in (2, n*2) or len(v.get('orientation', [0, 0, 1, 0])) not in (4, n*4):
                    _fail('EXTRUSION_COUNT', 'Extrusion scale/orientation must have one value or one per spine point')

        animated = {}
        target_types = {'translation': 'SFVec3f', 'center': 'SFVec3f', 'scale': 'SFVec3f', 'rotation': 'SFRotation', 'scaleOrientation': 'SFRotation'}
        for route in routes:
            source, target = defs[route.get('fromNode')], defs[route.get('toNode')]
            source_field, target_field = route.get('fromField'), route.get('toField')
            if source.tag == 'TimeSensor' and source_field == 'fraction_changed' and target.tag in INTERPOLATORS and target_field == 'set_fraction':
                continue
            if source.tag not in INTERPOLATORS or source_field != 'value_changed':
                _fail('ROUTE_GRAPH', 'Only TimeSensor→interpolator→local target animation is admitted')
            target_field = target_field[4:] if target_field.startswith('set_') else target_field
            field_type = None
            if target.tag == 'Transform':
                field_type = target_types.get(target_field)
            elif target.tag in ('Material', 'PhysicalMaterial') and FIELDS[target.tag].get(target_field) == 'color':
                field_type = 'SFColor'
            elif target.tag in LIGHTS and target_field in ('intensity', 'color'):
                field_type = 'SFFloat' if target_field == 'intensity' else 'SFColor'
            if field_type != INTERPOLATORS[source.tag][1]:
                _fail('ROUTE_TYPE', 'ROUTE endpoint types or allowed event fields do not match')
            samples = values[id(source)]['keyValue']
            width = INTERPOLATORS[source.tag][0]
            if target.tag in LIGHTS and target_field == 'intensity' and any(not 0 <= x <= 1 for x in samples):
                _fail('ANIMATED_RANGE', 'Animated light intensity must remain within [0, 1]')
            animated.setdefault((id(target), target_field), []).extend(samples[i:i+width] for i in range(0, len(samples), width))

        cache = {}

        def envelope(raw_node):
            node = actual(raw_node)
            if id(node) in cache:
                return cache[id(node)]
            v, tag = values[id(node)], node.tag
            child_results = [envelope(child) for child in node]
            radius = max([x[0] for x in child_results], default=0.0)
            shapes = sum(x[1] for x in child_results)
            lights = 1 if tag in LIGHTS else sum(x[2] for x in child_results)
            if tag == 'Box':
                radius = math.hypot(*v.get('size', [2, 2, 2])) / 2; shapes = 1
            elif tag == 'Sphere':
                radius = v.get('radius', 1.0); shapes = 1
            elif tag in ('Cylinder', 'Cone'):
                radius = math.hypot(v.get('radius', v.get('bottomRadius', 1.0)), v.get('height', 2.0) / 2); shapes = 1
            elif tag in ('IndexedFaceSet', 'IndexedLineSet'):
                points = values[id(child_of(node, 'Coordinate'))]['point']
                radius = max(math.hypot(*points[i:i+3]) for i in range(0, len(points), 3)); shapes = 1
            elif tag == 'ElevationGrid':
                x = (v['xDimension']-1) * v.get('xSpacing', 1.0)
                z = (v['zDimension']-1) * v.get('zSpacing', 1.0)
                radius = math.hypot(x, max(abs(y) for y in v['height']), z); shapes = 1
            elif tag == 'Extrusion':
                cross = v.get('crossSection', [1, 1, 1, -1, -1, -1, -1, 1, 1, 1])
                spine = v.get('spine', [0, 0, 0, 0, 1, 0])
                scale = v.get('scale', [1, 1])
                radius = max(math.hypot(*spine[i:i+3]) for i in range(0, len(spine), 3)) + max(math.hypot(*cross[i:i+2]) for i in range(0, len(cross), 2)) * max(abs(s) for s in scale)
                shapes = 1
            elif tag == 'Transform':
                translations = [v.get('translation', [0, 0, 0]), *animated.get((id(node), 'translation'), [])]
                centers = [v.get('center', [0, 0, 0]), *animated.get((id(node), 'center'), [])]
                scales = [v.get('scale', [1, 1, 1]), *animated.get((id(node), 'scale'), [])]
                t = max(math.hypot(*a) for a in translations)
                c = max(math.hypot(*a) for a in centers)
                s = max(abs(a) for triple in scales for a in triple)
                radius = t + c + s * (radius + c)
            if not math.isfinite(radius):
                _fail('BOUNDS_NONFINITE', 'Transform composition overflowed')
            if shapes > MAX_EXPANDED_SHAPES:
                _fail('EXPANDED_SHAPES', f'USE expansion exceeds {MAX_EXPANDED_SHAPES} geometry instances')
            if lights > 1:
                _fail('LIGHTS_CAP', 'USE expansion exceeds one local light instance')
            cache[id(node)] = radius, shapes, lights
            return radius, shapes, lights

        all_bounds = [envelope(node) for node in root if node.tag != 'ROUTE']
        raw_radius = max((x[0] for x in all_bounds), default=0.0)
        expanded_shapes = sum(x[1] for x in all_bounds)
        expanded_lights = sum(x[2] for x in all_bounds)
        if expanded_shapes > MAX_EXPANDED_SHAPES:
            _fail('EXPANDED_SHAPES', f'Patch exceeds {MAX_EXPANDED_SHAPES} expanded geometry instances')
        if expanded_lights > 1:
            _fail('LIGHTS_CAP', 'Patch exceeds one expanded local light instance')
        if not expanded_shapes or raw_radius <= 1e-12:
            _fail('NO_EXTENT', 'Patch must have nonzero declared geometry extent')
        if raw_radius > REJECT_RADIUS:
            _fail('BOUNDS_LIMIT', f'Conservative source envelope exceeds {REJECT_RADIUS} metres')
        fit = min(1.0, SLOT_RADIUS * (1-1e-12) / raw_radius)
        final_radius = raw_radius * fit
        mapping = {name: (prefix + '_' + name if prefix else name) for name in defs}

        def serialize(node):
            if node.tag == 'ROUTE':
                attrs = dict(node.attrib)
                attrs['fromNode'] = mapping[attrs['fromNode']]
                attrs['toNode'] = mapping[attrs['toNode']]
            elif node.get('USE'):
                attrs = {'USE': mapping[node.get('USE')]}
            else:
                attrs = {key: _fmt(value) for key, value in values[id(node)].items()}
                if node.get('DEF'):
                    attrs['DEF'] = mapping[node.get('DEF')]
            # containerField is validated but omitted because all supported
            # child relations have the matching X3D default container field.
            attributes = ''.join(' ' + key + '=' + quoteattr(str(value)) for key, value in sorted(attrs.items()))
            children = ''.join(serialize(child) for child in node)
            return '<' + node.tag + attributes + ('>' + children + '</' + node.tag + '>' if children else '/>')

        # ROUTE statements cannot be children of Transform in this output's
        # conservative policy: keep them as top-level siblings of the fit rig.
        children_xml = ''.join(serialize(node) for node in root if node.tag != 'ROUTE')
        canonical = '<Transform scale=' + quoteattr(_fmt([fit]*3)) + '>' + children_xml + '</Transform>' + ''.join(serialize(node) for node in root if node.tag == 'ROUTE')
        canonical_bytes = len(canonical.encode('utf-8'))
        if canonical_bytes > MAX_CANONICAL_BYTES:
            _fail('CANONICAL_BYTES', f'Fitted/namespaced output exceeds {MAX_CANONICAL_BYTES} bytes')
        types = {node.tag for node in order}
        score = 3.5 if counters['nodes'] >= 65 else 3 if counters['nodes'] >= 45 else 2 if counters['nodes'] >= 25 else 1 if counters['nodes'] >= 10 else 0
        score += 1 if len(types) >= 12 else .5 if len(types) >= 8 else 0
        score += 1 if counters['routes'] >= 4 and counters['interpolators'] >= 2 else .5 if counters['routes'] >= 2 else 0
        custom = len(types & {'IndexedFaceSet', 'IndexedLineSet', 'ElevationGrid', 'Extrusion'})
        score += .75 if custom >= 2 else .5 if custom else 0
        score += .25 if counters['uses'] else 0
        counters.update({'expanded_shapes': expanded_shapes, 'expanded_lights': expanded_lights, 'type_variety': len(types), 'custom_triangle_estimate': custom_triangles,
                         'source_bytes': len(raw), 'canonical_bytes': canonical_bytes, 'owned_wrapper_nodes': 1,
                         'complexity': min(5.0, score), 'complexity_scope': 'Structural quantity rubric, not beauty, readability or measured GPU cost.'})
        def box(radius):
            return {'min': [-radius]*3, 'max': [radius]*3, 'radius': radius,
                    'kind': 'conservative origin-centred sphere envelope enclosed by an axis-aligned cube'}
        result.update(status='pass', canonical_x3d=canonical,
                      canonical_sha256=hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
                      bounds=box(final_radius), raw_bounds=box(raw_radius),
                      fit={'scale': fit, 'applied': fit < 1.0, 'slot_radius': SLOT_RADIUS, 'wrapper_in_canonical': True}, metrics=counters)
    except GateError as error:
        result['errors'].append({'code': error.code, 'message': str(error)})
    except (OverflowError, ValueError, RecursionError) as error:
        result['errors'].append({'code': 'GATE_ARITHMETIC', 'message': 'Input could not be safely evaluated: ' + type(error).__name__})
    return result
