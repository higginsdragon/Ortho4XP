import unittest
import unittest.mock as mock
import os
import bz2
import xml.etree.ElementTree as ET

import O4_Test
import O4_OSM_Utils as OSM

TESTS_DIR = O4_Test.TESTS_DIR
TEMP_DIR = O4_Test.TEMP_DIR


class TestOSMLayer(unittest.TestCase):

    def test_OSMLayer_init(self):
        """Sanity check"""
        layer = OSM.OSM_layer()

        self.assertEqual({}, layer.dicosmn)
        self.assertEqual({}, layer.dicosmn_reverse)
        self.assertEqual({}, layer.dicosmw)
        self.assertEqual(-1, layer.next_node_id)
        self.assertEqual(-1, layer.next_way_id)
        self.assertEqual(-1, layer.next_rel_id)
        self.assertEqual({}, layer.dicosmr)
        self.assertEqual({'n': set(), 'w': set(), 'r': set()}, layer.dicosmfirst)
        self.assertEqual({'n': {}, 'w': {}, 'r': {}}, layer.dicosmtags)
        self.assertEqual([layer.dicosmn,
                          layer.dicosmw,
                          layer.dicosmr,
                          layer.dicosmfirst,
                          layer.dicosmtags],
                         layer.dicosm)

    def test_update_dicosm(self):
        layer = OSM.OSM_layer()
        osm_file = open(os.path.join(TESTS_DIR, 'mocks/osm_get_aeroways.xml'))
        encoded_data = osm_file.read().encode()
        osm_file.close()

        result = layer.update_dicosm(encoded_data)

        self.maxDiff = None

        self.assertEqual(1, result)

        # Do some sampling to make sure data is consistent across tests, which it should be.
        # nodes
        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual((-87.9001194, 41.9539765), layer.dicosmn[-5])
        self.assertEqual((-87.9085817, 41.9838912), layer.dicosmn[-123])
        self.assertEqual((-87.3304211, 41.4583468), layer.dicosmn[-8721])
        # ways
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual([-17, -7203, -1412, -7204, -7135, -7184, -5864, -7040, -7056, -1411, -5859],
                         layer.dicosmw[-10])
        self.assertEqual([-3650, -3451, -3484, -3442], layer.dicosmw[-572])
        self.assertEqual([-6152, -6151, -6146, -6157, -6152], layer.dicosmw[-922])
        # relations
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(50, len(layer.dicosmr[-1]['outer']))
        self.assertEqual([-5138, -5140, -5122, -5121, -5128, -5123, -5117, -5094, -5100, -5097, -5088, -5058,
                          -5061, -5066, -5065, -5057, -5056, -5067, -5068, -5059, -5060, -5021, -5023, -5015,
                          -5014, -5020, -5019, -5031, -5026, -5029, -5032, -5049, -5041, -5046, -5053, -5073,
                          -5085, -5078, -5082, -5087, -5108, -5101, -5105, -5112, -5116, -5124, -5126, -5143,
                          -5142, -5138],
                         layer.dicosmr[-1]['outer'])
        self.assertEqual(26, len(layer.dicosmr[-2]['outer']))
        self.assertEqual([-5138, -5140, -5371, -9611, -506, -5370, -9607, -9606, -9612, -9613, -9608, -9599,
                          -4152, -9600, -9609, -9601, -9602, -4153, -9603, -9604, -9610, -9605, -5148, -5143,
                          -5142, -5138],
                         layer.dicosmr[-2]['outer'])
        # tags
        self.assertEqual(318, len(layer.dicosmtags['n']))
        self.assertEqual({'aeroway': 'gate', 'ref': 'B22'}, layer.dicosmtags['n'][-513])
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual({'aeroway': 'helipad', 'faa': '11IL', 'gnis:feature_id': '427414',
                          'name': "Presence Saint Mary's Hospital - Kankakee Heliport", 'rooftop': 'yes',
                          'surface': 'concrete'}, layer.dicosmtags['w'][-1097])
        self.assertEqual(2, len(layer.dicosmtags['r']))
        self.assertEqual({'aeroway': 'terminal', 'building': 'yes', 'name': 'L Stinger', 'type': 'multipolygon',
                          'wikidata': 'Q56045889'}, layer.dicosmtags['r'][-2])

    def test_update_dicosm_with_uncompressed_file(self):
        layer = OSM.OSM_layer()
        file_path_string = os.path.join(TESTS_DIR, 'mocks/osm_get_aeroways.xml')

        result = layer.update_dicosm(file_path_string)

        # Quicker test because we did a more thorough one above.
        self.assertEqual(1, result)
        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(318, len(layer.dicosmtags['n']))
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

    def test_update_dicosm_with_bz2_file(self):
        layer = OSM.OSM_layer()
        file_path_string = os.path.join(TESTS_DIR, 'mocks/osm_get_aeroways.xml.bz2')

        result = layer.update_dicosm(file_path_string)

        # Quicker test because we did a more thorough one above.
        self.assertEqual(1, result)
        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(318, len(layer.dicosmtags['n']))
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

    @mock.patch('O4_UI_Utils.vprint')
    def test_malformed_xml_data(self, vprint_mock):
        """Test for a clean exit if the XML is malformed."""

        # We don't want exception error text gumming up test output.
        vprint_mock.vprint = None

        layer = OSM.OSM_layer()
        file_path_string = os.path.join(TESTS_DIR, 'mocks/osm_malformed.xml')

        result = layer.update_dicosm(file_path_string)

        self.assertEqual(0, result)

    def test_write_to_file(self):
        layer = OSM.OSM_layer()
        file_path_string = os.path.join(TESTS_DIR, 'mocks/osm_get_aeroways.xml')
        temp_file_path = os.path.join(TEMP_DIR, "write_test.osm")

        layer.update_dicosm(file_path_string)

        layer.write_to_file(temp_file_path)

        self.assertTrue(os.path.isfile(temp_file_path))

        temp_file = open(temp_file_path, 'r', encoding='utf-8')
        file_read = temp_file.read()
        temp_file.close()
        file_array = file_read.split('\n')

        # Simple checks to make sure file text header is proper
        # Can likely remove this in the future if parsing errors disappear
        self.assertEqual("<?xml version='1.0' encoding='UTF-8'?>", file_array[0])
        self.assertEqual('<osm generator="Ortho4XP" version="0.6">', file_array[1])
        self.assertTrue('</osm>' in file_array)

        file_parsed = ET.fromstring(file_read)

        self.assertEqual(10208, len(file_parsed.findall('node')))
        self.assertEqual(1216, len(file_parsed.findall('way')))
        self.assertEqual(2, len(file_parsed.findall('relation')))

        # cleanup
        os.remove(temp_file_path)

    def test_write_to_bz2_file(self):
        layer = OSM.OSM_layer()
        file_path_string = os.path.join(TESTS_DIR, 'mocks/osm_get_aeroways.xml')
        temp_file_path = os.path.join(TEMP_DIR, "write_test.osm.bz2")

        layer.update_dicosm(file_path_string)

        layer.write_to_file(temp_file_path)

        self.assertTrue(os.path.isfile(temp_file_path))

        temp_file = bz2.open(temp_file_path, 'rt', encoding='utf-8')
        file_read = temp_file.read()
        temp_file.close()
        file_array = file_read.split('\n')

        # Simple checks to make sure file text header is proper
        # Can likely remove this in the future if parsing errors disappear
        self.assertEqual("<?xml version='1.0' encoding='UTF-8'?>", file_array[0])
        self.assertEqual('<osm generator="Ortho4XP" version="0.6">', file_array[1])
        self.assertTrue('</osm>' in file_array)

        file_parsed = ET.fromstring(file_read)

        self.assertEqual(10208, len(file_parsed.findall('node')))
        self.assertEqual(1216, len(file_parsed.findall('way')))
        self.assertEqual(2, len(file_parsed.findall('relation')))

        # cleanup
        os.remove(temp_file_path)


class TestGetOverpassData(unittest.TestCase):
    @mock.patch('O4_OSM_Utils.requests.Session.get')
    def test_get_overpass_data_with_string(self, session_mock):
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(TESTS_DIR, 'mocks/osm_get_motorway.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        raw_xml = OSM.get_overpass_data('way["highway"="motorway"]', (41, -88, 42, -87), None)
        osm_parsed = ET.fromstring(raw_xml)

        self.assertEqual('osm', osm_parsed.tag.lower())
        self.assertEqual(session_mock.return_value.content, raw_xml)

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    def test_get_overpass_data_with_tuple(self, session_mock):
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(TESTS_DIR, 'mocks/osm_get_aeroways.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        raw_xml = OSM.get_overpass_data(('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]'),
                                        (41, -88, 42, -87),
                                        None)
        osm_parsed = ET.fromstring(raw_xml)

        self.assertEqual('osm', osm_parsed.tag.lower())
        self.assertEqual(session_mock.return_value.content, raw_xml)


if __name__ == '__main__':
    unittest.main()
