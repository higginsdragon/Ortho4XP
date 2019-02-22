import unittest
import unittest.mock as mock
import os
import sys
from xml.etree import ElementTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src/'))
import O4_OSM_Utils as OSM

class TestBuildCurvTolWeightMap(unittest.TestCase):

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    def test_get_overpass_data_with_string(self, session_mock):
        session_mock.return_value.status_code = 200
        osm_data = open(os.path.join(os.path.dirname(__file__), 'mocks/osm_get_motorway.xml'))
        session_mock.return_value.content = osm_data.read().encode()
        osm_data.close()

        raw_xml = OSM.get_overpass_data('way["highway"="motorway"]', (41, -88, 42, -87), None)
        osm_parsed = ElementTree.fromstring(raw_xml)

        self.assertEqual('osm', osm_parsed.tag.lower())
        self.assertEqual(session_mock.return_value.content, raw_xml)

    @mock.patch('O4_OSM_Utils.requests.Session.get')
    def test_get_overpass_data_with_tuple(self, session_mock):
        session_mock.return_value.status_code = 200
        osm_data = open(os.path.join(os.path.dirname(__file__), 'mocks/osm_get_aeroways.xml'))
        session_mock.return_value.content = osm_data.read().encode()
        osm_data.close()

        raw_xml = OSM.get_overpass_data(('node["aeroway"]','way["aeroway"]','rel["aeroway"]'), (41, -88, 42, -87), None)
        osm_parsed = ElementTree.fromstring(raw_xml)

        self.assertEqual('osm', osm_parsed.tag.lower())
        self.assertEqual(session_mock.return_value.content, raw_xml)


if __name__ == '__main__':
    unittest.main()
