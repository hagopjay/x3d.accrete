"""These tests run the vendored upstream XSD and semantic instruments."""
import hashlib
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from accretion import mcp_adapter as mcp


def scene(fragment):
    return '<X3D version="4.0" profile="Immersive"><Scene>' + fragment + '</Scene></X3D>'


class MCPAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import lxml, jsonschema  # explicit test requirements: do not skip an unavailable actual instrument

    def test_actual_xsd_and_semantics_pass_valid_candidate(self):
        xml = scene('<Viewpoint/><Shape><Appearance><Material diffuseColor="0.2 0.5 0.8"/></Appearance><Box size="1 2 1"/></Shape>')
        value = mcp.validate_scene(xml)
        self.assertEqual(value['status'], 'pass', value)
        self.assertEqual(value['xsd']['status'], 'pass')
        self.assertEqual(value['semantic']['status'], 'pass')
        self.assertEqual(value['candidate_sha256'], hashlib.sha256(xml.encode()).hexdigest())

    def test_actual_xsd_refuses_unknown_field(self):
        value = mcp.validate_scene(scene('<Shape><Box imaginaryField="2"/></Shape>'))
        self.assertEqual(value['xsd']['status'], 'fail', value)
        self.assertTrue(value['xsd']['findings'])

    def test_actual_semantics_refuse_dangling_route(self):
        value = mcp.validate_scene(scene('<TimeSensor DEF="Clock"/><ROUTE fromNode="Clock" fromField="fraction_changed" toNode="Absent" toField="set_fraction"/>'))
        self.assertEqual(value['semantic']['status'], 'fail', value)
        self.assertTrue(any('Absent' in x['message'] for x in value['semantic']['findings']))

    def test_actual_semantics_refuse_short_elevation_grid(self):
        value = mcp.validate_scene(scene('<Shape><ElevationGrid xDimension="2" zDimension="2" height="0 0 0"/></Shape>'))
        self.assertEqual(value['semantic']['status'], 'fail', value)
        self.assertTrue(any('height' in x['message'] for x in value['semantic']['findings']))

    def test_actual_semantics_refuse_route_field_type_mismatch(self):
        value = mcp.validate_scene(scene('<TimeSensor DEF="Clock"/><Transform DEF="Part"><Shape><Box/></Shape></Transform><ROUTE fromNode="Clock" fromField="fraction_changed" toNode="Part" toField="set_translation"/>'))
        self.assertEqual(value['semantic']['status'], 'fail', value)

    def test_warnings_are_preserved_without_claiming_visibility(self):
        value = mcp.validate_scene(scene('<Shape><Box/></Shape>'))
        self.assertEqual(value['status'], 'pass', value)
        self.assertTrue(any(x['check'] == 'no-viewpoint' for x in value['semantic']['findings']))
        self.assertTrue(any('visibility' in text for text in value['limitations']))

    def test_identity_carries_full_source_and_schema_digests(self):
        identity = mcp.instrument_identity()
        self.assertEqual(identity['commit'], mcp.COMMIT)
        self.assertEqual(len(identity['code_sha256']), 64)
        self.assertEqual(len(identity['files_sha256']), 19)
        self.assertTrue(all(len(value) == 64 for value in identity['files_sha256'].values()))
        self.assertTrue(identity['runtime']['lxml'])
        self.assertTrue(identity['runtime']['libxml2'])

    def test_missing_dependencies_are_explicit_not_run(self):
        with patch.object(mcp, '_load_vendor', side_effect=ModuleNotFoundError("No module named 'lxml'", name='lxml')):
            value = mcp.validate_scene(scene('<Shape><Box/></Shape>'))
        self.assertEqual(value['status'], 'not_run')
        self.assertEqual(value['xsd']['status'], 'not_run')
        self.assertIn('lxml', value['dependency_error'])

    def test_source_drift_does_not_publish_pass(self):
        with patch.object(mcp, 'instrument_identity', side_effect=mcp.InstrumentError('MCP_FILE_DRIFT: fixture')):
            value = mcp.validate_scene(scene('<Shape><Box/></Shape>'))
        self.assertEqual(value['status'], 'error')
        self.assertEqual(value['xsd']['status'], 'not_run')

    def test_doctype_is_refused_before_upstream_parser(self):
        with patch.object(mcp, '_load_vendor', side_effect=AssertionError('must not execute')):
            value = mcp.validate_scene('<!DOCTYPE X3D SYSTEM "https://example.com/evil.dtd">' + scene('<Shape><Box/></Shape>'))
        self.assertEqual(value['status'], 'fail')
        self.assertEqual(value['xsd']['findings'][0]['check'], 'MCP_XML_DECLARATION')

    def test_oversized_scene_cannot_become_checked(self):
        value = mcp.validate_scene(scene(' ' * mcp.MAX_XML_BYTES))
        self.assertEqual(value['status'], 'not_run')
        self.assertEqual(value['semantic']['status'], 'not_run')

    def test_malformed_xml_is_input_failure_not_green(self):
        value = mcp.validate_scene('<X3D><Scene>')
        self.assertEqual(value['status'], 'fail', value)

    def test_foreign_loaded_validation_package_cannot_be_misattributed(self):
        with patch.dict(sys.modules, {'validation': SimpleNamespace(__file__='/tmp/foreign/validation/__init__.py')}):
            value = mcp.validate_scene(scene('<Shape><Box/></Shape>'))
        self.assertEqual(value['status'], 'error')
        self.assertIn('MCP_NAMESPACE_CONFLICT', value['instrument_error'])

    def test_unpaired_surrogate_is_input_failure(self):
        value = mcp.validate_scene('<X3D>\ud800</X3D>')
        self.assertEqual(value['status'], 'fail')

    def test_origin_manifest_drift_refuses_cached_execution(self):
        with patch.object(mcp, '_ORIGIN_SHA_AT_IMPORT', '0' * 64):
            value = mcp.validate_scene(scene('<Shape><Box/></Shape>'))
        self.assertEqual(value['status'], 'error')
        self.assertIn('MCP_ORIGIN_DRIFT', value['instrument_error'])


if __name__ == '__main__':
    unittest.main()
