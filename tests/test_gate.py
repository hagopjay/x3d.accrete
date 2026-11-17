"""Negative controls for the deliberately bounded fragment instrument."""
import hashlib
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from accretion.gate import gate_fragment, MAX_NODES

BOX = '<Shape><Appearance><Material diffuseColor=".2 .5 .6"/></Appearance><Box size="1 1 1"/></Shape>'


def anim(target='set_rotation', kind='OrientationInterpolator', key='0 1', values='0 1 0 0 0 1 0 3.14'):
    return '<Transform DEF="Rig">' + BOX + '</Transform><TimeSensor DEF="Clock" cycleInterval="4" loop="true"/>' + \
        f'<{kind} DEF="Turn" key="{key}" keyValue="{values}"/>' + \
        '<ROUTE fromNode="Clock" fromField="fraction_changed" toNode="Turn" toField="set_fraction"/>' + \
        f'<ROUTE fromNode="Turn" fromField="value_changed" toNode="Rig" toField="{target}"/>'


class GateTests(unittest.TestCase):
    def accept(self, xml, **kwargs):
        result = gate_fragment(xml, **kwargs)
        self.assertEqual(result['status'], 'pass', result['errors'])
        self.assertFalse(result['errors'])
        self.assertEqual(len(result['canonical_sha256']), 64)
        self.assertEqual(hashlib.sha256(result['canonical_x3d'].encode()).hexdigest(), result['canonical_sha256'])
        return result

    def reject(self, xml, code=None, **kwargs):
        result = gate_fragment(xml, **kwargs)
        self.assertEqual(result['status'], 'fail', result)
        self.assertTrue(result['errors'])
        self.assertIsNone(result['canonical_x3d'])
        if code:
            self.assertEqual(result['errors'][0]['code'], 'GATE_' + code, result['errors'])
        return result

    def test_stable_normalized_xml_and_bound_identity(self):
        a = self.accept(BOX)
        b = self.accept(BOX.replace('.2 .5 .6', '0.20 0.500 0.600').replace('size="1 1 1"', 'size="1.0,1,1"'))
        self.assertEqual(a['canonical_x3d'], b['canonical_x3d'])
        self.assertNotEqual(a['raw_sha256'], b['raw_sha256'])
        self.assertIn('code_sha256', a['instrument'])

    def test_scene_and_x3d_wrappers(self):
        expected = self.accept(BOX)['canonical_x3d']
        for source in ['<Scene>' + BOX + '</Scene>', '<?xml version="1.0"?><X3D version="4.0" profile="Immersive"><Scene>' + BOX + '</Scene></X3D>']:
            self.assertEqual(self.accept(source)['canonical_x3d'], expected)
        self.reject('<X3D version="4.1"><Scene>' + BOX + '</Scene></X3D>', 'WRAPPER')
        self.reject('<X3D><head/><Scene>' + BOX + '</Scene></X3D>', 'WRAPPER')

    def test_all_text_and_wrapper_text_are_refused(self):
        for source in ['hi' + BOX, BOX + 'hi', '<X3D>hidden<Scene>' + BOX + '</Scene></X3D>', '<Scene>hidden' + BOX + '</Scene>', '<Shape>hi<Box/></Shape>']:
            self.reject(source, 'TEXT_CONTENT')

    def test_dtd_entity_cdata_comments_and_processing_instructions(self):
        for text, code in [('<!DOCTYPE X3D>' + BOX, 'DTD_ENTITY'), ('<!ENTITY x "a">' + BOX, 'DTD_ENTITY'), ('<![CDATA[hi]]>' + BOX, 'CDATA'), ('<!--inert but outside policy-->' + BOX, 'XML_DECLARATION'), ('<?do something?>' + BOX, 'XML_DECLARATION'), ('<Group DEF="&#65;">' + BOX + '</Group>', 'ENTITY_REFERENCE')]:
            self.reject(text, code)
        self.reject('<Group DEF="A&amp;B">' + BOX + '</Group>', 'DEF_NAME')

    def test_forbidden_nodes_and_fields(self):
        for tag in ['Script', 'Inline', 'Anchor', 'Text', 'FontStyle', 'Viewpoint', 'Background', 'Fog', 'NavigationInfo', 'LOD', 'ProtoDeclare', 'ExternProtoDeclare', 'ComposedShader', 'ImageTexture']:
            self.reject('<' + tag + '/>' + BOX, 'NODE_FORBIDDEN')
        self.reject('<Transform url="https://example.com">' + BOX + '</Transform>', 'FIELD_FORBIDDEN')

    def test_containment_and_explicit_container_field(self):
        self.reject('<Shape><Material/><Box/></Shape>', 'CONTAINMENT')
        self.reject('<Shape><Box/><Sphere/></Shape>', 'SHAPE_GEOMETRY')
        self.reject('<Shape><Appearance/></Shape>', 'SHAPE_GEOMETRY')
        self.reject('<Shape><Box containerField="children"/></Shape>', 'CONTAINER_FIELD')
        self.accept('<Shape><Box containerField="geometry"/></Shape>')

    def test_finite_typed_numbers_and_dimensions(self):
        for value in ['NaN', 'INF', '-Inf', '1e309', '1e7', 'oops']:
            self.reject('<Shape><Sphere radius="' + value + '"/></Shape>')
        for value in ['0', '-1']:
            self.reject('<Shape><Sphere radius="' + value + '"/></Shape>', 'FIELD_POSITIVE')
        self.reject('<Transform translation="1 2">' + BOX + '</Transform>', 'FIELD_LENGTH')
        self.reject('<Transform scale="1 0 1">' + BOX + '</Transform>', 'ZERO_SCALE')
        self.reject('<Shape><Cylinder side="yes"/></Shape>', 'FIELD_BOOLEAN')
        self.reject('<Shape><Appearance><Material diffuseColor="1.1 0 0"/></Appearance><Box/></Shape>', 'FIELD_RANGE')

    def test_zero_rotation_axis_only_for_identity(self):
        self.accept('<Transform rotation="0 0 0 0">' + BOX + '</Transform>')
        self.reject('<Transform rotation="0 0 0 1">' + BOX + '</Transform>', 'ROTATION_AXIS')

    def test_limits_bytes_depth_nodes_and_expansion(self):
        self.reject(BOX + ' ' * (12 * 1024), 'BYTES')
        self.reject('<Group>' * 17 + BOX + '</Group>' * 17, 'DEPTH')
        self.reject('<Group/>' * MAX_NODES + BOX, 'NODES')
        # A compact source DAG can still request exponential rendered instances.
        xml = '<Group DEF="A">' + BOX + '</Group>'
        for index, previous in enumerate(['A', 'B', 'C', 'D', 'E'], 1):
            current = chr(ord('A') + index)
            xml += '<Group DEF="' + current + '">' + ('<Group USE="' + previous + '"/>') * 4 + '</Group>'
        self.reject(xml, 'EXPANDED_SHAPES')

    def test_def_use_type_order_unique_and_cycle(self):
        self.accept('<Group DEF="Part">' + BOX + '</Group><Group USE="Part"/>')
        self.reject('<Group USE="Part"/><Group DEF="Part">' + BOX + '</Group>', 'USE_FORWARD')
        self.reject('<Group DEF="Part">' + BOX + '</Group><Shape USE="Part"/>', 'USE_TYPE')
        self.reject('<Group DEF="Part">' + BOX + '</Group><Group DEF="Part"/>', 'DEF_DUPLICATE')
        self.reject('<Group DEF="Part"><Group USE="Part"/></Group>', 'USE_CYCLE')
        self.reject('<Group DEF="Part">' + BOX + '</Group><Group USE="Part" DEF="Other"/>', 'USE_SHAPE')

    def test_namespaces_are_deterministic_and_prefix_is_bounded(self):
        source = '<Group DEF="Part">' + BOX + '</Group><Group USE="Part"/>'
        a, b = self.accept(source, prefix='P1'), self.accept(source, prefix='P2')
        self.assertIn('DEF="P1_Part"', a['canonical_x3d'])
        self.assertIn('USE="P1_Part"', a['canonical_x3d'])
        self.assertNotEqual(a['canonical_sha256'], b['canonical_sha256'])
        for prefix in ['with space', 'a' * 41, '<bad>', 3]:
            self.reject(source, 'PREFIX', prefix=prefix)

    def test_gentle_typed_animation_and_namespaced_routes(self):
        result = self.accept(anim(), prefix='P7')
        self.assertEqual(result['metrics']['routes'], 2)
        self.assertEqual(result['metrics']['timers'], 1)
        self.assertIn('fromNode="P7_Clock"', result['canonical_x3d'])
        self.reject(anim(target='set_translation'), 'ROUTE_TYPE')
        self.reject(anim().replace('toNode="Rig"', 'toNode="Foreign"'), 'ROUTE_LOCAL')

    def test_animation_graph_cannot_feed_itself_or_controls(self):
        self.reject(anim().replace('toNode="Rig" toField="set_rotation"', 'toNode="Turn" toField="set_fraction"'), 'ROUTE_TYPE')
        self.reject(anim().replace('fromField="fraction_changed"', 'fromField="time"'), 'ROUTE_GRAPH')
        self.reject('<Group>' + anim() + '</Group>', 'CONTAINMENT')

    def test_key_range_order_cardinality_and_clock_caps(self):
        for key in ['0 0', '1 0', '-.1 1', '0 1.1', '0']:
            self.reject(anim(key=key))
        self.reject(anim(values='0 1 0 0'), 'KEY_VALUE_COUNT')
        self.reject(anim().replace('cycleInterval="4"', 'cycleInterval="0.1"'), 'FIELD_RANGE')
        self.reject(BOX + '<TimeSensor/><TimeSensor/><TimeSensor/>', 'TIMERS_CAP')
        self.reject(anim(key=' '.join(str(i/32) for i in range(33))), 'FIELD_LENGTH')

    def test_local_light_is_forced_and_light_count_capped(self):
        result = self.accept(BOX + '<PointLight global="true" location="0 2 0" intensity=".8"/>')
        self.assertIn('global="false"', result['canonical_x3d'])
        self.reject(BOX + '<PointLight/><DirectionalLight/>', 'LIGHTS_CAP')
        self.reject(BOX + '<SpotLight beamWidth="1" cutOffAngle=".5"/>', 'SPOT_CONE')
        self.reject(BOX + '<DirectionalLight direction="0 0 0"/>', 'DIRECTION_ZERO')

    def test_animated_light_range_is_checked(self):
        source = BOX + '<PointLight DEF="L"/><TimeSensor DEF="T"/><ScalarInterpolator DEF="I" key="0 1" keyValue="0 2"/><ROUTE fromNode="T" fromField="fraction_changed" toNode="I" toField="set_fraction"/><ROUTE fromNode="I" fromField="value_changed" toNode="L" toField="set_intensity"/>'
        self.reject(source, 'ANIMATED_RANGE')
        self.accept(source.replace('keyValue="0 2"', 'keyValue="0 .8"'))

    def test_use_cannot_amplify_the_one_light_budget(self):
        self.reject('<Group DEF="Lit">' + BOX + '<PointLight/></Group><Group USE="Lit"/>', 'LIGHTS_CAP')
        self.reject(BOX + '<PointLight DEF="L"/><PointLight USE="L"/>', 'LIGHTS_CAP')

    def test_indexed_mesh_and_line_counts(self):
        face = '<Shape><IndexedFaceSet coordIndex="0 1 2 -1" creaseAngle="1.2"><Coordinate point="0 0 0 1 0 0 0 1 0"/></IndexedFaceSet></Shape>'
        result = self.accept(face)
        self.assertEqual(result['metrics']['custom_triangle_estimate'], 1)
        self.reject(face.replace('0 1 2 -1', '0 1 3 -1'), 'INDEX_RANGE')
        self.reject(face.replace('0 1 2 -1', '0 1 -1'), 'INDEX_CARDINALITY')
        self.reject(face.replace('0 1 2 -1', '0 1 2.5 -1'), 'FIELD_NUMBER')
        self.reject(face.replace('0 1 2 -1', '0 1 2 -1 -1'), 'INDEX_EMPTY')
        self.accept('<Shape><IndexedLineSet coordIndex="0 1 -1"><Coordinate point="0 0 0 1 1 1"/></IndexedLineSet></Shape>')

    def test_missing_coordinates_and_short_colors(self):
        self.reject('<Shape><IndexedFaceSet coordIndex="0 1 2 -1"/></Shape>', 'COORDINATE_REQUIRED')
        self.reject('<Shape><IndexedFaceSet coordIndex="0 1 2 -1"><Coordinate point="0 0 0 1 0 0 0 1 0"/><Color color="1 0 0"/></IndexedFaceSet></Shape>', 'COLOR_COUNT')

    def test_grid_height_crash_control(self):
        source = '<Shape><ElevationGrid xDimension="2" zDimension="2" height="0 0 0 0"/></Shape>'
        self.accept(source)
        self.reject(source.replace('height="0 0 0 0"', 'height="0 0 0"'), 'GRID_HEIGHT_COUNT')
        self.reject(source.replace('xDimension="2"', 'xDimension="2.5"'), 'FIELD_NUMBER')
        self.reject(source.replace('xDimension="2"', 'xDimension="65"'), 'FIELD_RANGE')

    def test_extrusion_spine_scale_and_orientation_counts(self):
        self.accept('<Shape><Extrusion/></Shape>')
        self.reject('<Shape><Extrusion spine="0 0 0"/></Shape>', 'EXTRUSION_COUNT')
        self.reject('<Shape><Extrusion scale="1 1 2 2 3 3"/></Shape>', 'EXTRUSION_COUNT')
        self.reject('<Shape><Extrusion orientation="0 0 0 1"/></Shape>', 'ROTATION_AXIS')

    def test_static_fit_is_stored_and_nonsense_is_rejected(self):
        result = self.accept('<Transform translation="8 0 0">' + BOX + '</Transform>')
        self.assertGreater(result['raw_bounds']['radius'], 8)
        self.assertLessEqual(result['bounds']['radius'], 3)
        self.assertLess(result['fit']['scale'], 1)
        wrapper = ET.fromstring(result['canonical_x3d'])
        self.assertEqual([float(x) for x in wrapper.get('scale').split()], [result['fit']['scale']] * 3)
        self.reject('<Transform translation="121 0 0">' + BOX + '</Transform>', 'BOUNDS_LIMIT')

    def test_animation_translation_and_scale_are_in_the_fit_envelope(self):
        translation = self.accept(anim(target='set_translation', kind='PositionInterpolator', values='0 0 0 20 0 0'))
        self.assertGreater(translation['raw_bounds']['radius'], 20)
        self.assertLessEqual(translation['bounds']['radius'], 3)
        scale = self.accept(anim(target='set_scale', kind='PositionInterpolator', values='1 1 1 12 2 3'))
        self.assertAlmostEqual(scale['raw_bounds']['radius'], math.sqrt(3)/2 * 12)

    def test_rotating_offset_geometry_is_not_given_a_static_tight_box(self):
        source = anim().replace('<Transform DEF="Rig">', '<Transform DEF="Rig"><Transform translation="2 0 0">').replace('</Shape></Transform>', '</Shape></Transform></Transform>', 1)
        result = self.accept(source)
        radius = 2 + math.sqrt(3)/2
        self.assertAlmostEqual(result['raw_bounds']['radius'], radius)
        # Offset geometry sweeps into every horizontal quadrant.
        for angle in [i * math.tau / 17 for i in range(18)]:
            for x, y, z in [(2.5, .5, .5), (1.5, -.5, -.5)]:
                rotated = (x*math.cos(angle)+z*math.sin(angle), y, -x*math.sin(angle)+z*math.cos(angle))
                self.assertLessEqual(math.hypot(*rotated), radius)

    def test_degenerate_or_empty_geometry_refused(self):
        self.reject('<Group/>', 'NO_EXTENT')
        self.reject('', 'EMPTY')
        self.reject('<Shape><IndexedLineSet coordIndex="0 1 -1"><Coordinate point="0 0 0 0 0 0"/></IndexedLineSet></Shape>', 'NO_EXTENT')

    def test_bad_unicode_and_input_types(self):
        self.reject(None, 'INPUT_TYPE')
        self.reject('\ud800', 'UTF8')

    def test_real_generator_families_fit_the_actual_subset(self):
        from accretion.generator import generate, FAMILIES
        for word in FAMILIES:
            for tier in range(1, 6):
                with self.subTest(word=word, tier=tier):
                    result = self.accept(generate({'seed': 'a'*64, 'seed_word': word}, tier)['x3d'])
                    self.assertLessEqual(result['metrics']['nodes'], 80)
                    self.assertLessEqual(result['bounds']['radius'], 3)

    def test_instrument_drift_is_refused_instead_of_mislabelled(self):
        with patch('accretion.gate.Path.read_bytes', return_value=b'different implementation'):
            self.reject(BOX, 'INSTRUMENT_DRIFT')


if __name__ == '__main__':
    unittest.main()
