"""Procedural fixtures must stay bounded, reproducible and honestly attributed."""
import hashlib
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from accretion.generator import FAMILIES, generate


def plan(word='orrery', seed='a' * 64):
    return {'n': 3, 'mode': 'generate', 'cell': [1, -1], 'level': 0, 'seed': seed, 'seed_word': word, 'biome': 'basalt-brass', 'era': 0}


def parsed(value):
    return ET.fromstring('<Scene>' + value['x3d'] + '</Scene>')


class GeneratorTests(unittest.TestCase):
    def test_turntable_is_a_full_turn(self):
        # Slerp takes the shortest arc, so a key step of pi or more plays out and back.
        import math
        for word in FAMILIES:
            root = parsed(generate(plan(word), 4))
            for node in root.iter('OrientationInterpolator'):
                values = [float(x) for x in node.get('keyValue').split()]
                angles = values[3::4]
                self.assertGreaterEqual(len(angles), 4)
                self.assertTrue(all(abs(b - a) < math.pi for a, b in zip(angles, angles[1:])))
                self.assertAlmostEqual(angles[-1] - angles[0], 2 * math.pi, places=6)

    def test_repeatability(self):
        self.assertEqual(generate(plan(), 5), generate(plan(), 5))

    def test_seed_changes_content(self):
        self.assertNotEqual(generate(plan(seed='a' * 64), 3)['x3d'], generate(plan(seed='b' * 64), 3)['x3d'])

    def test_all_families_and_tiers_meet_basic_budgets(self):
        for family in FAMILIES:
            for tier in range(1, 6):
                with self.subTest(family=family, tier=tier):
                    value = generate(plan(family), tier)
                    root = parsed(value)
                    self.assertLessEqual(len(list(root.iter())) - 1, 80)
                    self.assertLessEqual(len(value['x3d'].encode()), 12_000)
                    self.assertEqual(value['generator']['family'], family)
                    self.assertEqual(value['generator']['kind'], 'procedural')
                    self.assertEqual(value['model_calls'], 0)

    def test_higher_tier_adds_structure_without_a_quality_claim(self):
        a = generate(plan(), 1)
        b = generate(plan(), 5)
        self.assertLess(len(list(parsed(a).iter())), len(list(parsed(b).iter())))
        self.assertIn('not a measured quality grade', b['generator']['scope'])

    def test_animations_are_local_and_bounded(self):
        for family in FAMILIES:
            root = parsed(generate(plan(family), 5))
            defs = {node.get('DEF'): node for node in root.iter() if node.get('DEF')}
            self.assertEqual(len(list(root.iter('TimeSensor'))), 1)
            self.assertGreaterEqual(float(next(root.iter('TimeSensor')).get('cycleInterval')), .5)
            for route in root.iter('ROUTE'):
                self.assertIn(route.get('fromNode'), defs)
                self.assertIn(route.get('toNode'), defs)
            for node in root.iter():
                if node.get('USE'):
                    self.assertIn(node.get('USE'), defs)

    def test_no_external_code_or_world_authority(self):
        forbidden = {'Script', 'Inline', 'Anchor', 'Viewpoint', 'NavigationInfo', 'Background', 'Fog', 'LOD', 'ProtoDeclare', 'ExternProtoDeclare'}
        for family in FAMILIES:
            root = parsed(generate(plan(family), 5))
            for node in root.iter():
                self.assertNotIn(node.tag, forbidden)
                self.assertNotIn('url', node.attrib)

    def test_world_placement_does_not_change_the_local_sculpture(self):
        a = plan()
        b = dict(a, cell=[900, -500], level=5, mode='augment', n=900)
        self.assertEqual(generate(a, 4)['x3d'], generate(b, 4)['x3d'])

    def test_untrusted_or_invalid_generation_parameters_are_refused(self):
        for tier in [0, 6, True, '3', .5]:
            with self.assertRaises(ValueError):
                generate(plan(), tier)
        for seed in ['', 'a' * 63, 'g' * 64, None, 100]:
            with self.assertRaises(ValueError):
                generate(plan(seed=seed))
        for word in ['<Script>', 'ignore\nthis', 'a' * 37, '']:
            with self.assertRaises(ValueError):
                generate(dict(plan(), seed_word=word))

    def test_custom_rings_have_valid_outward_quad_topology(self):
        root = parsed(generate(plan('gyroscope'), 5))
        meshes = list(root.iter('IndexedFaceSet'))
        self.assertEqual(len(meshes), 3)
        for mesh in meshes:
            values = [int(v) for v in mesh.get('coordIndex').split()]
            self.assertEqual(values.count(-1), 64)
            self.assertTrue(all(v == -1 or 0 <= v < 64 for v in values))
            self.assertEqual(len(mesh.find('Coordinate').get('point').split()), 192)

    def test_route_statements_remain_top_level_fragment_siblings(self):
        root = parsed(generate(plan('gyroscope'), 5))
        self.assertEqual(len(list(root.iter('ROUTE'))), len(root.findall('ROUTE')))

    def test_default_tier_has_a_real_animation_target_in_every_family(self):
        for family in FAMILIES:
            root = parsed(generate(plan(family), 3))
            self.assertEqual(len(list(root.iter('TimeSensor'))), 1)
            self.assertEqual(len([n for n in root.iter('Transform') if n.get('DEF') == 'Rotor']), 1)

    def test_all_families_tiers_and_control_seeds_pass_the_local_gate(self):
        from accretion.gate import gate_fragment
        checked = 0
        for family in FAMILIES:
            for tier in range(1, 6):
                for character in ['a', 'b', 'c']:
                    result = gate_fragment(generate(plan(family, character * 64), tier)['x3d'], prefix='G' + str(checked))
                    self.assertEqual(result['status'], 'pass', (family, tier, result['errors']))
                    self.assertLessEqual(result['bounds']['radius'], 3)
                    checked += 1
        self.assertEqual(checked, 90)

    def test_each_family_and_tier_passes_the_pinned_xsd_and_semantic_oracles(self):
        from accretion.gate import gate_fragment
        from accretion.mcp_adapter import validate_scene
        for family in FAMILIES:
            for tier in range(1, 6):
                gate = gate_fragment(generate(plan(family), tier)['x3d'], prefix='M')
                source = '<X3D profile="Immersive" version="4.0"><Scene>' + gate['canonical_x3d'] + '</Scene></X3D>'
                result = validate_scene(source)
                if result['status'] == 'not_run':
                    self.skipTest('Pinned validator dependencies are unavailable')
                self.assertEqual(result['status'], 'pass', (family, tier, result))


if __name__ == '__main__':
    unittest.main()
