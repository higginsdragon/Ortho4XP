import unittest
import unittest.mock as mock
import os
import bz2
import xml.etree.ElementTree as ET

import O4_Test
import O4_OSM_Utils as OSM

TESTS_DIR = O4_Test.TESTS_DIR
TEMP_DIR = O4_Test.TEMP_DIR
MOCKS_DIR = O4_Test.MOCKS_DIR


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
        self.assertEqual({'n': [], 'w': [], 'r': []}, layer.input_tags)
        self.assertEqual({'n': [], 'w': [], 'r': []}, layer.target_tags)

    def test_update_dicosm(self):
        layer = OSM.OSM_layer()
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'))
        encoded_data = osm_file.read().encode()
        osm_file.close()

        result = layer.update_dicosm(encoded_data)

        self.maxDiff = None

        self.assertTrue(result)

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
        self.assertEqual(50, len(layer.dicosmr[-1]['outer'][0]))
        self.assertEqual([[-5138, -5140, -5122, -5121, -5128, -5123, -5117, -5094, -5100, -5097, -5088, -5058,
                          -5061, -5066, -5065, -5057, -5056, -5067, -5068, -5059, -5060, -5021, -5023, -5015,
                          -5014, -5020, -5019, -5031, -5026, -5029, -5032, -5049, -5041, -5046, -5053, -5073,
                          -5085, -5078, -5082, -5087, -5108, -5101, -5105, -5112, -5116, -5124, -5126, -5143,
                          -5142, -5138]],
                         layer.dicosmr[-1]['outer'])
        self.assertEqual(26, len(layer.dicosmr[-2]['outer'][0]))
        self.assertEqual([[-5138, -5140, -5371, -9611, -506, -5370, -9607, -9606, -9612, -9613, -9608, -9599,
                          -4152, -9600, -9609, -9601, -9602, -4153, -9603, -9604, -9610, -9605, -5148, -5143,
                          -5142, -5138]],
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

    def test_update_dicosm_water(self):
        layer = OSM.OSM_layer()
        file_names = ['water_rel', 'water_way']
        target_tags = {'n': [], 'w': [('natural', 'water'), ('name', '')], 'r': [('natural', 'water'), ('name', '')]}
        input_tags = {'n': [], 'w': [('natural', 'water')], 'r': [('natural', 'water')]}

        for n in file_names:
            osm_file_name = os.path.join(MOCKS_DIR, 'osm_40113W_' + n + '_raw.xml')
            layer.update_dicosm(osm_file_name, input_tags, target_tags)

        self.assertEqual(18, len(layer.dicosmr))
        self.assertEqual(254, len(layer.dicosmr[-1]['outer'][0]))
        self.assertEqual(99, len(layer.dicosmr[-17]['outer'][0]))
        self.assertEqual([-4764, -4765, -4766, -4767, -4768, -4769, -4770, -4771, -4772, -4773, -4774, -4775, -4776,
                          -4777, -4778, -4779, -4780, -4781, -4782, -4783, -4784, -4785, -4786, -4787, -4788, -4789,
                          -4790, -4791, -4792, -4793, -7820, -4764],
                         layer.dicosmr[-16]['outer'][0])
        self.assertEqual([-3403, -3404, -3405, -3406, -3407, -3408, -3409, -3410, -3411, -3412, -3413, -3403],
                         layer.dicosmr[-16]['inner'][0])

    def test_update_dicosm_bad_relation(self):
        layer = OSM.OSM_layer()
        osm_file_name = os.path.join(MOCKS_DIR, 'osm_bad_relation.xml')
        layer.update_dicosm(osm_file_name)

        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual([-1, -2, -3, -4, -1], layer.dicosmr[-1]['outer'][0])
        self.assertEqual([-13, -14, -15, -17, -13], layer.dicosmr[-2]['outer'][0])

    def test_update_dicosm_with_uncompressed_file(self):
        layer = OSM.OSM_layer()
        file_path_string = os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml')

        result = layer.update_dicosm(file_path_string)

        # Smaller test because we did a more thorough one above.
        self.assertTrue(result)
        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(318, len(layer.dicosmtags['n']))
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

    def test_update_dicosm_with_bz2_file(self):
        layer = OSM.OSM_layer()
        file_path_string = os.path.join(MOCKS_DIR, 'cached_aeroways.osm.bz2')

        result = layer.update_dicosm(file_path_string)

        # Quicker test because we did a more thorough one above.
        self.assertTrue(result)
        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(0, len(layer.dicosmtags['n']))     # node tags aren't saved currently
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

    @mock.patch('O4_UI_Utils.vprint')
    def test_malformed_xml_data(self, vprint_mock):
        """Test for a clean exit if the XML is malformed."""

        # We don't want exception error text gumming up test output.
        vprint_mock.vprint = None

        layer = OSM.OSM_layer()
        file_path_string = os.path.join(MOCKS_DIR, 'osm_malformed.xml')

        result = layer.update_dicosm(file_path_string)

        self.assertFalse(result)

    def test_write_to_file(self):
        layer = OSM.OSM_layer()
        file_path_string = os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml')
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

        # These are to make sure it saved the proper amount of data
        self.assertEqual(10208, len(file_parsed.findall('node')))
        self.assertEqual(1216, len(file_parsed.findall('way')))
        self.assertEqual(2, len(file_parsed.findall('relation')))
        members = file_parsed.findall('relation/member')
        self.assertEqual(4, len(members))
        self.assertEqual(-784, int(members[0].get('ref')))
        self.assertEqual(-1117, int(members[1].get('ref')))
        self.assertEqual(-1116, int(members[2].get('ref')))
        self.assertEqual(-1118, int(members[3].get('ref')))

        # cleanup
        os.remove(temp_file_path)

    def test_write_to_file_and_read_back(self):
        save_layer = OSM.OSM_layer()
        file_path_string = os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml')
        temp_file_path = os.path.join(TEMP_DIR, "write_test.osm")

        save_layer.update_dicosm(file_path_string)

        self.assertEqual(10208, len(save_layer.dicosmn))
        self.assertEqual(1216, len(save_layer.dicosmw))
        self.assertEqual(2, len(save_layer.dicosmr))
        self.assertEqual(318, len(save_layer.dicosmtags['n']))
        self.assertEqual(1212, len(save_layer.dicosmtags['w']))
        self.assertEqual(2, len(save_layer.dicosmtags['r']))

        save_layer.write_to_file(temp_file_path)

        layer = OSM.OSM_layer()
        file_path_string = os.path.join(temp_file_path)

        result = layer.update_dicosm(file_path_string)

        # Quicker test because we did a more thorough one above.
        self.assertTrue(result)
        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(0, len(layer.dicosmtags['n']))     # node tags aren't saved currently
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

        # cleanup
        os.remove(temp_file_path)

    def test_write_to_bz2_file(self):
        layer = OSM.OSM_layer()
        file_path_string = os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml')
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

        # These are to make sure it saved the proper amount of data
        self.assertEqual(10208, len(file_parsed.findall('node')))
        self.assertEqual(1216, len(file_parsed.findall('way')))
        self.assertEqual(2, len(file_parsed.findall('relation')))
        self.assertEqual(4, len(file_parsed.findall('relation/member')))

        # cleanup
        os.remove(temp_file_path)


class TestOsmQueriesToOsmLayer(unittest.TestCase):

    @mock.patch('bz2.open')
    @mock.patch('os.path.isfile')
    @mock.patch('O4_File_Names.osm_old_cached')
    @mock.patch('O4_UI_Utils.vprint')
    def test_osm_queries_to_osm_layer_from_file(self, vprint_mock, file_mock, os_mock, bz_mock):
        # This seems complex--it's not too much. Need to trigger a bz2.open, but just need to give it some valid XML.
        vprint_mock.vprint = None
        file_mock.return_value = os.path.join(MOCKS_DIR, 'cached_aeroways.osm.bz2')
        os_mock.return_value = True
        bz_mock.return_value = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'), 'rt', encoding='utf-8')

        queries = [('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]')]
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()

        result = OSM.OSM_queries_to_OSM_layer(queries, layer, 41, -88, tags_of_interest, cached_suffix='airports')

        self.assertTrue(result)

        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

        bz_mock.return_value.close()

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    def test_osm_queries_to_osm_layer_from_server(self, vprint_mock, session_mock):
        vprint_mock.vprint = None
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        queries = [('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]')]
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()

        result = OSM.OSM_queries_to_OSM_layer(queries, layer, 41, -88, tags_of_interest, cached_suffix='airports')

        self.assertTrue(result)

        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

    @mock.patch('bz2.open')
    @mock.patch('os.path.isfile')
    @mock.patch('O4_File_Names.osm_old_cached')
    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    def test_osm_queries_to_osm_layer_file_fail_should_get_from_server(self,
                                                                       vprint_mock,
                                                                       session_mock,
                                                                       file_mock,
                                                                       os_mock,
                                                                       bz_mock):
        vprint_mock.vprint = None
        file_mock.return_value = os.path.join(MOCKS_DIR, 'cached_aeroways.osm.bz2')
        os_mock.return_value = True
        bz_mock.return_value = open(os.path.join(MOCKS_DIR, 'osm_malformed.xml'), 'rt', encoding='utf-8')
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        queries = [('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]')]
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()
        # We don't actually want to attempt to write anything for this test.
        layer.write_to_file = mock.Mock(return_value=1)

        result = OSM.OSM_queries_to_OSM_layer(queries, layer, 41, -88, tags_of_interest, cached_suffix='airports')

        self.assertTrue(result)

        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

        bz_mock.return_value.close()

    @mock.patch('os.path.isfile')
    @mock.patch('O4_OSM_Utils.UI')
    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    def test_osm_queries_to_osm_layer_should_fail_if_ui_red_flag(self, vprint_mock, session_mock, ui_mock, path_mock):
        vprint_mock.vprint = None
        ui_mock.red_flag = True
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()
        path_mock.return_value = False  # We want it to try fetching.

        queries = [('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]')]
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()

        result = OSM.OSM_queries_to_OSM_layer(queries, layer, 41, -88, tags_of_interest, cached_suffix='airports')

        self.assertFalse(result)

    @mock.patch('os.path.isfile')
    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    @mock.patch('O4_UI_Utils.lvprint')
    def test_osm_queries_to_osm_layer_should_fail_if_no_response(self,
                                                                 lvprint_mock,
                                                                 vprint_mock,
                                                                 session_mock,
                                                                 path_mock):
        lvprint_mock.lvprint = None
        vprint_mock.vprint = None
        session_mock.return_value.status_code = 404
        session_mock.return_value.content = ''
        OSM.max_osm_tentatives = 1  # Otherwise this single test will take over 8 minutes
        path_mock.return_value = False  # We want it to try fetching.

        queries = [('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]')]
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()

        result = OSM.OSM_queries_to_OSM_layer(queries, layer, 41, -88, tags_of_interest, cached_suffix='airports')

        self.assertFalse(result)


class TestOsmQueryToOsmLayer(unittest.TestCase):

    @mock.patch('bz2.open')
    @mock.patch('os.path.isfile')
    @mock.patch('O4_File_Names.osm_old_cached')
    @mock.patch('O4_UI_Utils.vprint')
    def test_osm_query_to_osm_layer_from_file(self, vprint_mock, file_mock, os_mock, bz_mock):
        # This seems complex--it's not too much. Need to trigger a bz2.open, but just need to give it some valid XML.
        vprint_mock.vprint = None
        file_path = os.path.join(MOCKS_DIR, 'cached_aeroways.osm.bz2')
        file_mock.return_value = file_path
        os_mock.return_value = True
        bz_mock.return_value = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'), 'rt', encoding='utf-8')

        queries = ['node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]']
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()
        bbox = (41, -88, 42, -87)

        result = OSM.OSM_query_to_OSM_layer(queries, bbox, layer, tags_of_interest, cached_file_name=file_path)

        self.assertTrue(result)

        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

        bz_mock.return_value.close()

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    def test_osm_query_to_osm_layer_from_server(self, vprint_mock, session_mock):
        vprint_mock.vprint = None
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_motorway.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        queries = 'way["highway"="motorway"]'
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()
        bbox = (41, -88, 42, -87)

        result = OSM.OSM_query_to_OSM_layer(queries, bbox, layer, tags_of_interest)

        self.assertTrue(result)

        self.assertEqual(10701, len(layer.dicosmn))
        self.assertEqual(2035, len(layer.dicosmw))
        self.assertEqual(0, len(layer.dicosmr))
        self.assertEqual(2035, len(layer.dicosmtags['w']))
        self.assertEqual(0, len(layer.dicosmtags['r']))

    @mock.patch('bz2.open')
    @mock.patch('os.path.isfile')
    @mock.patch('O4_File_Names.osm_old_cached')
    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    def test_osm_query_to_osm_layer_file_fail_should_get_from_server(self,
                                                                     vprint_mock,
                                                                     session_mock,
                                                                     file_mock,
                                                                     os_mock,
                                                                     bz_mock):
        vprint_mock.vprint = None
        file_mock.return_value = os.path.join(MOCKS_DIR, 'cached_aeroways.osm.bz2')
        os_mock.return_value = True
        bz_mock.return_value = open(os.path.join(MOCKS_DIR, 'osm_malformed.xml'), 'rt', encoding='utf-8')
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        queries = [('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]')]
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()
        # We don't actually want to attempt to write anything for this test.
        layer.write_to_file = mock.Mock(return_value=1)
        bbox = (41, -88, 42, -87)

        result = OSM.OSM_query_to_OSM_layer(queries, bbox, layer, tags_of_interest, cached_file_name='airports')

        self.assertTrue(result)

        self.assertEqual(10208, len(layer.dicosmn))
        self.assertEqual(1216, len(layer.dicosmw))
        self.assertEqual(2, len(layer.dicosmr))
        self.assertEqual(1212, len(layer.dicosmtags['w']))
        self.assertEqual(2, len(layer.dicosmtags['r']))

        bz_mock.return_value.close()

    @mock.patch('O4_OSM_Utils.UI')
    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    def test_osm_query_to_osm_layer_should_fail_if_ui_red_flag(self, vprint_mock, session_mock, ui_mock):
        vprint_mock.vprint = None
        ui_mock.red_flag = True
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        queries = 'way["highway"="motorway"]'
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()
        bbox = (41, -88, 42, -87)

        result = OSM.OSM_query_to_OSM_layer(queries, bbox, layer, tags_of_interest)

        self.assertFalse(result)

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    @mock.patch('O4_UI_Utils.lvprint')
    def test_osm_query_to_osm_layer_should_fail_if_no_response(self, lvprint_mock, vprint_mock, session_mock):
        lvprint_mock.lvprint = None
        vprint_mock.vprint = None
        session_mock.return_value.status_code = 404
        session_mock.return_value.content = ''
        OSM.max_osm_tentatives = 1  # Otherwise this single test will take over 8 minutes

        queries = 'way["highway"="motorway"]'
        tags_of_interest = ['all']
        layer = OSM.OSM_layer()
        bbox = (41, -88, 42, -87)

        result = OSM.OSM_query_to_OSM_layer(queries, bbox, layer, tags_of_interest)

        self.assertFalse(result)


class TestGetOverpassData(unittest.TestCase):

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    def test_get_overpass_data_with_string(self, session_mock):
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_motorway.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        raw_xml = OSM.get_overpass_data('way["highway"="motorway"]', (41, -88, 42, -87), None)
        osm_parsed = ET.fromstring(raw_xml)

        self.assertEqual('osm', osm_parsed.tag.lower())
        self.assertEqual(session_mock.return_value.content, raw_xml)

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    def test_get_overpass_data_with_tuple(self, session_mock):
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        raw_xml = OSM.get_overpass_data(('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]'),
                                        (41, -88, 42, -87),
                                        None)
        osm_parsed = ET.fromstring(raw_xml)

        self.assertEqual('osm', osm_parsed.tag.lower())
        self.assertEqual(session_mock.return_value.content, raw_xml)

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    def test_get_overpass_with_bad_server_code(self, vprint_mock, session_mock):
        vprint_mock.vprint = None
        session_mock.return_value.status_code = 200
        osm_file = open(os.path.join(MOCKS_DIR, 'osm_get_aeroways.xml'))
        session_mock.return_value.content = osm_file.read().encode()
        osm_file.close()

        raw_xml = OSM.get_overpass_data(('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]'),
                                        (41, -88, 42, -87),
                                        '8Xa')
        osm_parsed = ET.fromstring(raw_xml)

        self.assertEqual('osm', osm_parsed.tag.lower())
        self.assertEqual(session_mock.return_value.content, raw_xml)

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    @mock.patch('O4_UI_Utils.vprint')
    def test_get_overpass_with_server_error(self, vprint_mock, session_mock):
        vprint_mock.vprint = None
        session_mock.return_value.status_code = 404
        session_mock.return_value.content = ''
        OSM.max_osm_tentatives = 1  # Otherwise this single test will take over 8 minutes

        raw_xml = OSM.get_overpass_data(('node["aeroway"]', 'way["aeroway"]', 'rel["aeroway"]'),
                                        (41, -88, 42, -87),
                                        None)

        self.assertFalse(raw_xml)


if __name__ == '__main__':
    unittest.main()
