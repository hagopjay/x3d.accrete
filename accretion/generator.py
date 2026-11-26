"""Authored procedural X3D patches for the offline Accretion reference world.

The world supplies placement and a content seed. This module only supplies a
small local sculpture. It never calls a model and never chooses a world slot.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import random
import re
from typing import Mapping
import xml.etree.ElementTree as ET

VERSION = '1.0.0'
FAMILIES = ('orrery', 'coral', 'ziggurat', 'beacon', 'mycelium', 'gyroscope')
SHAPE_LIMIT = {1: 4, 2: 7, 3: 10, 4: 12, 5: 14}
PALETTES = {
    'basalt-brass': {'label': 'Basalt and brass', 'base': (.055, .075, .085), 'metal': (.75, .48, .19), 'ceramic': (.20, .61, .59), 'glow': (.33, .91, .79)},
    'coral-glass': {'label': 'Coral and copper', 'base': (.065, .08, .13), 'metal': (.86, .55, .34), 'ceramic': (.77, .29, .28), 'glow': (1.0, .61, .31)},
    'verdant': {'label': 'Verdant alloy', 'base': (.05, .085, .065), 'metal': (.43, .60, .29), 'ceramic': (.21, .57, .35), 'glow': (.63, .92, .40)},
    'noctilucent': {'label': 'Noctilucent porcelain', 'base': (.055, .065, .125), 'metal': (.52, .49, .71), 'ceramic': (.34, .44, .78), 'glow': (.58, .78, 1.0)},
}


def _f(value: float) -> str:
    value = 0.0 if abs(value) < 5e-8 else value
    return format(value, '.6g')


def _vec(value) -> str:
    return ' '.join(_f(float(v)) for v in value)


@dataclass(frozen=True)
class Part:
    kind: str
    dimensions: tuple
    position: tuple = (0, 0, 0)
    material: str = 'ceramic'
    rotation: tuple = (0, 1, 0, 0)
    scale: tuple = (1, 1, 1)
    moving: bool = False


def _part(kind, dimensions, position=(0, 0, 0), material='ceramic', rotation=(0, 1, 0, 0), scale=(1, 1, 1), moving=False):
    return Part(kind, tuple(dimensions), tuple(position), material, tuple(rotation), tuple(scale), moving)


def _link(a, b, radius=.055, material='metal', moving=False):
    d = tuple(b[i] - a[i] for i in range(3))
    length = math.hypot(*d)
    if length <= 0:
        raise ValueError('A generated link needs distinct endpoints')
    # Rotate Cylinder's +Y axis onto d. The cross product is (dz, 0, -dx).
    lateral = math.hypot(d[0], d[2])
    if lateral < 1e-12:
        rotation = (1, 0, 0, 0 if d[1] > 0 else math.pi)
    else:
        rotation = (d[2] / lateral, 0, -d[0] / lateral, math.acos(max(-1, min(1, d[1] / length))))
    return _part('Cylinder', (radius, length), tuple((a[i] + b[i]) / 2 for i in range(3)), material, rotation, moving=moving)


def _foundation():
    return _part('Cylinder', (1.28, .14), (0, .07, 0), 'base')


def _orrery(rng):
    pivot = (0, 1.40, 0)
    parts = [_foundation(), _part('Cylinder', (.49, .22), (0, .25, 0), 'metal'),
             _part('Cylinder', (.09, 1.02), (0, .86, 0), 'metal'),
             _part('Sphere', (.34,), pivot, 'glow'),
             _part('Box', (2.10, .065, .09), material='metal', moving=True),
             _part('Box', (.09, .065, 2.10), material='metal', moving=True)]
    for index in range(4):
        angle = index * math.pi / 2
        parts.append(_part('Sphere', (.15 + .025 * (index % 2),), (1.05 * math.cos(angle), 0, 1.05 * math.sin(angle)), 'ceramic', moving=True))
    parts.extend([_part('Cylinder', (.25, .09), (0, 1.05, 0), 'metal'),
                  _part('Cone', (.17, .45), (0, 1.96, 0), 'metal'),
                  _part('Sphere', (.11,), (.60, .35, .60), 'glow', moving=True),
                  _part('Sphere', (.11,), (-.60, -.25, -.60), 'glow', moving=True)])
    return pivot, parts


def _coral(rng):
    pivot = (0, 1.75, 0)
    branches = [(.70, 1.40, .12), (-.60, 1.57, .22), (.16, 1.52, -.68), (-.13, 1.88, .55)]
    parts = [_foundation(), _link((0, .14, 0), (.06, 1.45, 0), .13, 'ceramic'),
             _part('Sphere', (.25,), (.03, 1.53, 0), 'glow'),
             _link((0, .65, 0), branches[0], .075, 'metal')]
    for index, end in enumerate(branches):
        if index:
            parts.append(_link((.02, .65 + index * .12, 0), end, .065, 'metal'))
        parts.append(_part('Sphere', (.21 - index * .014,), end, 'ceramic', scale=(1, .72, 1)))
    for index in range(3):
        angle = index * math.tau / 3 + .25
        parts.append(_part('Sphere', (.105,), (.45 * math.cos(angle), .08 + index * .07, .45 * math.sin(angle)), 'glow', moving=True))
    parts.append(_part('Cylinder', (.31, .055), (0, .24, 0), 'metal'))
    return pivot, parts[:14]


def _ziggurat(rng):
    pivot = (0, 1.89, 0)
    parts = [_part('Box', (2.45, .15, 2.45), (0, .075, 0), 'base'),
             _part('Box', (1.96, .31, 1.96), (0, .31, 0), 'ceramic'),
             _part('Box', (1.48, .34, 1.48), (0, .635, 0), 'metal'),
             _part('Cone', (.37, .55), (0, 1.77, 0), 'glow'),
             _part('Box', (1.03, .36, 1.03), (0, .985, 0), 'ceramic'),
             _part('Box', (.58, .33, .58), (0, 1.33, 0), 'metal')]
    for index in range(4):
        angle = math.pi / 4 + index * math.pi / 2
        parts.append(_part('Box', (.62, .06, .15), (.44 * math.cos(angle), 0, .44 * math.sin(angle)), 'metal', (0, 1, 0, -angle), moving=True))
    for index in range(4):
        x, z = ((-.93, -.93), (.93, -.93), (.93, .93), (-.93, .93))[index]
        parts.append(_part('Sphere', (.09,), (x, .57, z), 'glow'))
    return pivot, parts


def _beacon(rng):
    pivot = (0, 1.62, 0)
    parts = [_foundation(), _part('Cylinder', (.17, 1.16), (0, .72, 0), 'metal'),
             _part('Sphere', (.27,), (0, 1.45, 0), 'glow'),
             _part('Sphere', (.68,), (0, 1.20, 0), 'ceramic', scale=(1, .20, 1)),
             _part('Box', (2.12, .065, .12), material='metal', moving=True),
             _part('Sphere', (.145,), (1.06, 0, 0), 'glow', moving=True),
             _part('Sphere', (.145,), (-1.06, 0, 0), 'glow', moving=True),
             _part('Cone', (.23, .48), (0, 1.94, 0), 'metal')]
    for index in range(4):
        angle = index * math.pi / 2 + math.pi / 4
        parts.append(_part('Cylinder', (.055, .75), (.72 * math.cos(angle), .51, .72 * math.sin(angle)), 'metal'))
    parts.extend([_part('Cylinder', (.46, .06), (0, .26, 0), 'ceramic'),
                  _part('Sphere', (.09,), (0, 2.23, 0), 'glow')])
    return pivot, parts


def _mycelium(rng):
    pivot = (0, 1.70, 0)
    parts = [_part('Sphere', (1.24,), (0, .10, 0), 'base', scale=(1, .12, 1)),
             _part('Cone', (.18, 1.17), (0, .77, 0), 'metal'),
             _part('Sphere', (.62,), (0, 1.38, 0), 'ceramic', scale=(1, .34, 1)),
             _part('Sphere', (.15,), (0, 1.70, 0), 'glow')]
    for index in range(3):
        angle = index * math.tau / 3 + .25
        x, z = .70 * math.cos(angle), .70 * math.sin(angle)
        height = .57 + index * .14
        parts.append(_part('Cylinder', (.055, height), (x, .17 + height / 2, z), 'metal'))
        parts.append(_part('Sphere', (.31,), (x, .20 + height, z), 'ceramic', scale=(1, .32, 1)))
    for index in range(4):
        angle = index * math.pi / 2 + .5
        parts.append(_part('Sphere', (.075,), (.49 * math.cos(angle), .12 + .13 * (index % 2), .49 * math.sin(angle)), 'glow', moving=True))
    return pivot, parts


def _gyroscope(rng):
    pivot = (0, 1.39, 0)
    parts = [_foundation(), _part('Box', (.48, .65, .48), (0, .47, 0), 'metal'),
             _part('Sphere', (.34,), pivot, 'glow'),
             _part('Cylinder', (.10, .50), (0, 1.03, 0), 'metal'),
             _part('Box', (1.88, .06, .10), material='metal', moving=True),
             _part('Box', (.10, .06, 1.88), material='metal', moving=True),
             _part('Box', (.08, 1.88, .08), material='ceramic', moving=True)]
    for axis in range(3):
        for sign in (-1, 1):
            position = [0.0, 0.0, 0.0]
            position[axis] = sign * .94
            parts.append(_part('Sphere', (.12,), position, 'ceramic', moving=True))
    parts.append(_part('Cylinder', (.66, .06), (0, .19, 0), 'ceramic'))
    return pivot, parts


BUILDERS = {'orrery': _orrery, 'coral': _coral, 'ziggurat': _ziggurat, 'beacon': _beacon, 'mycelium': _mycelium, 'gyroscope': _gyroscope}
WORD_FAMILIES = {'orrery': 'orrery', 'orbit': 'orrery', 'tide': 'coral', 'coral': 'coral', 'reef': 'coral',
                 'ziggurat': 'ziggurat', 'temple': 'ziggurat', 'beacon': 'beacon', 'lighthouse': 'beacon',
                 'mycelium': 'mycelium', 'mushroom': 'mycelium', 'forest': 'mycelium', 'gyroscope': 'gyroscope', 'gyro': 'gyroscope'}
INSTRUCTIONS = {
    'orrery': 'Carry the orbital rhythm upward with one quiet moving crown.',
    'coral': 'Answer these branching stems with a different silhouette and the same patient rhythm.',
    'ziggurat': 'Extend the stepped rhythm while leaving a clear interval for light.',
    'beacon': 'Echo the lantern with a lower, wider gesture in the next stratum.',
    'mycelium': 'Let the next canopy branch sideways before it reaches upward.',
    'gyroscope': 'Balance the next mechanism around a visible centre and a single slow clock.',
}


def _material(parent, name, palette, seen):
    appearance = ET.SubElement(parent, 'Appearance')
    if name in seen:
        ET.SubElement(appearance, 'Material', {'USE': 'M_' + name})
        return
    seen.add(name)
    color = palette[name]
    attrs = {'DEF': 'M_' + name, 'diffuseColor': _vec(color),
             'specularColor': _vec((.78, .70, .50) if name == 'metal' else (.28, .38, .39)),
             'shininess': '.72' if name == 'metal' else '.32', 'ambientIntensity': '.22'}
    if name == 'glow':
        attrs['emissiveColor'] = _vec(c * .20 for c in color)
        attrs['shininess'] = '.45'
    ET.SubElement(appearance, 'Material', attrs)


def _emit(parent, part, palette, seen):
    attrs = {'translation': _vec(part.position)}
    if part.rotation[3]:
        attrs['rotation'] = _vec(part.rotation)
    if part.scale != (1, 1, 1):
        attrs['scale'] = _vec(part.scale)
    transform = ET.SubElement(parent, 'Transform', attrs)
    shape = ET.SubElement(transform, 'Shape')
    _material(shape, part.material, palette, seen)
    if part.kind == 'Box':
        geometry = {'size': _vec(part.dimensions)}
    elif part.kind == 'Sphere':
        geometry = {'radius': _f(part.dimensions[0])}
    elif part.kind == 'Cylinder':
        geometry = {'radius': _f(part.dimensions[0]), 'height': _f(part.dimensions[1])}
    elif part.kind == 'Cone':
        geometry = {'bottomRadius': _f(part.dimensions[0]), 'height': _f(part.dimensions[1])}
    elif part.kind == 'Torus':
        # A compact authored IndexedFaceSet, not a nonstandard Torus node.
        # Sixteen major segments and four tube faces keep three rings below the
        # 12 KB patch ceiling while showing a genuine custom-geometry path.
        major, minor = part.dimensions
        points = []
        for i in range(16):
            u = math.tau * i / 16
            for j in range(4):
                v = math.tau * j / 4
                radial = major + minor * math.cos(v)
                points.extend((radial * math.cos(u), minor * math.sin(v), radial * math.sin(u)))
        faces = []
        for i in range(16):
            for j in range(4):
                faces.extend((i * 4 + j, i * 4 + (j + 1) % 4,
                              ((i + 1) % 16) * 4 + (j + 1) % 4, ((i + 1) % 16) * 4 + j, -1))
        mesh = ET.SubElement(shape, 'IndexedFaceSet', {'coordIndex': ' '.join(str(v) for v in faces), 'solid': 'true', 'creaseAngle': '1.8'})
        ET.SubElement(mesh, 'Coordinate', {'point': _vec(points)})
        return
    else:
        raise ValueError('Unimplemented authored geometry')
    ET.SubElement(shape, part.kind, geometry)


def generate(plan: dict, tier: int = 3) -> dict:
    """Return an authored, deterministic local sculpture; never a model result.

    `plan['seed']` is a full SHA-256 hex seed selected by the world. World cell,
    layer and mode remain metadata: no generated transform uses world placement.
    """
    if not isinstance(plan, Mapping):
        raise ValueError('The world must supply a plan mapping')
    if isinstance(tier, bool) or not isinstance(tier, int) or tier not in SHAPE_LIMIT:
        raise ValueError('Tier must be an integer from 1 to 5')
    seed = plan.get('seed')
    if not isinstance(seed, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', seed):
        raise ValueError('The content seed must contain 64 hexadecimal characters')
    seed = seed.lower()
    word = plan.get('seed_word', 'accretion')
    if not isinstance(word, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z -]{0,35}', word):
        raise ValueError('Seed words must be short authored words')
    rng = random.Random(int(seed, 16))
    family = WORD_FAMILIES.get(word.casefold(), FAMILIES[int(seed[:8], 16) % len(FAMILIES)])
    biome = plan.get('biome')
    if not isinstance(biome, str) or biome not in PALETTES:
        biome = tuple(PALETTES)[int(seed[-8:], 16) % len(PALETTES)]
    palette = PALETTES[biome]
    pivot, parts = BUILDERS[family](rng)
    # Small deterministic proportions provide variation even within one family.
    # A common uniform sculpture scale stays local and below the gate's fitting
    # threshold. It is unrelated to world placement.
    variation = .88 + .12 * rng.random()
    if tier >= 4 and family in ('orrery', 'gyroscope'):
        parts[4] = _part('Torus', (1.05, .045), material='metal', rotation=(1, 0, 0, math.pi / 2), moving=True)
        parts[5] = _part('Torus', (.84, .04), material='ceramic', rotation=(0, 0, 1, math.pi / 2), moving=True)
        if family == 'gyroscope':
            parts[6] = _part('Torus', (.72, .035), material='metal', moving=True)
    limit = min(SHAPE_LIMIT[tier], 13) if tier >= 4 and family in ('orrery', 'gyroscope') else SHAPE_LIMIT[tier]
    parts = parts[:limit]
    holder = ET.Element('Scene')
    root = ET.SubElement(holder, 'Group')
    sculpture = ET.SubElement(root, 'Transform', {'scale': _vec((variation, variation, variation))})
    rotor = None
    seen = set()
    for part in parts:
        if part.moving and tier >= 3:
            if rotor is None:
                rotor = ET.SubElement(sculpture, 'Transform', {'DEF': 'Rotor', 'translation': _vec(pivot)})
            parent = rotor
        else:
            parent = sculpture
            if part.moving:
                # Static lower tiers retain the authored pose in the same place.
                part = Part(part.kind, part.dimensions, tuple(part.position[i] + pivot[i] for i in range(3)), part.material, part.rotation, part.scale)
        _emit(parent, part, palette, seen)
    if rotor is None and tier >= 3:
        # Some organic families place their small satellite details late in
        # the richer tiers. The medium tier uses a slow whole-sculpture
        # turntable rather than claiming an animation that has no target.
        sculpture.set('DEF', 'Rotor')
        rotor = sculpture
    if rotor is not None:
        period = 26 + int(seed[8:12], 16) % 29
        ET.SubElement(holder, 'TimeSensor', {'DEF': 'Clock', 'cycleInterval': str(period), 'loop': 'true'})
        # Slerp takes the shortest arc, so each keyframe step must stay under pi:
        # the old 0, pi, 2*pi keys played a half turn out and back. Four keys at
        # 2*pi/3 steps give one full turn.
        ET.SubElement(holder, 'OrientationInterpolator', {'DEF': 'Turn', 'key': '0 .33333333 .66666667 1', 'keyValue': '0 1 0 0 0 1 0 2.0943951 0 1 0 4.1887902 0 1 0 6.2831853'})
        routes = [{'fromNode': 'Clock', 'fromField': 'fraction_changed', 'toNode': 'Turn', 'toField': 'set_fraction'},
                  {'fromNode': 'Turn', 'fromField': 'value_changed', 'toNode': 'Rotor', 'toField': 'set_rotation'}]
        if tier >= 4 and 'glow' in seen:
            glow = palette['glow']
            values = [component * amplitude for amplitude in (.12, .32, .12) for component in glow]
            ET.SubElement(holder, 'ColorInterpolator', {'DEF': 'Breathe', 'key': '0 .5 1', 'keyValue': _vec(values)})
            routes.extend([{'fromNode': 'Clock', 'fromField': 'fraction_changed', 'toNode': 'Breathe', 'toField': 'set_fraction'},
                           {'fromNode': 'Breathe', 'fromField': 'value_changed', 'toNode': 'M_glow', 'toField': 'set_emissiveColor'}])
        for route in routes:
            ET.SubElement(holder, 'ROUTE', route)
    xml = ''.join(ET.tostring(child, encoding='unicode', short_empty_elements=True) for child in holder)
    if len(list(holder.iter())) - 1 > 80 or len(xml.encode('utf-8')) > 12_000:
        raise ValueError('The authored generator exceeded its declared patch budget')
    return {'title': word.title() + ' ' + family.title(), 'instruction': INSTRUCTIONS[family], 'x3d': xml,
            'generator': {'id': 'accretion.authored-procedural', 'version': VERSION, 'seed': seed, 'kind': 'procedural',
                          'family': family, 'palette': biome, 'tier': tier, 'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          'scope': 'Authored synthetic sculpture, not model output. Tier changes structural quantity, not a measured quality grade.'},
            'color': list(palette['ceramic']), 'model_calls': 0}
