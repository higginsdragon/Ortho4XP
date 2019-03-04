import unittest
import unittest.mock as mock
import os

import O4_Test
import O4_File_Parser as O4Parser
import xml.etree.ElementTree as ET

TESTS_DIR = O4_Test.TESTS_DIR
TEMP_DIR = O4_Test.TEMP_DIR
MOCKS_DIR = O4_Test.MOCKS_DIR


class TestImageProvider(unittest.TestCase):

    def test_image_provider_init(self):
        provider = O4Parser.ImageProvider()

        self.assertEqual('', provider.code)
        self.assertEqual('', provider.directory)
        self.assertEqual('', provider.request_type)
        self.assertEqual('', provider.url)
        self.assertTrue(provider.in_gui)
        self.assertEqual(18, provider.max_zl)
        self.assertEqual('jpeg', provider.image_type)
        self.assertEqual('global', provider.extent)
        self.assertEqual('none', provider.color_filters)
        self.assertEqual('grouped', provider.imagery_dir)
        self.assertEqual('', provider.grid_type)
        self.assertEqual(256, provider.tile_size)
        self.assertTrue(3857, provider.epsg_code)
        self.assertIsNone(provider.scaledenominator)
        self.assertIsNone(provider.top_left_corner)
        self.assertEqual(None, provider.resolutions)
        self.assertEqual(None, provider.tilematrixset)
        self.assertEqual(8, provider.max_threads)
        self.assertEqual({'User-Agent': "Mozilla/5.0 (X11; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0",
                          'Accept': '*/*',
                          'Connection': 'keep-alive',
                          'Accept-Encoding': 'gzip, deflate'},
                         provider.request_headers)
        # WMS tests
        self.assertIsNone(provider.wms_version)
        self.assertEqual(256, provider.wms_size)
        self.assertEqual('', provider.layers)

    def test_image_provider_parse_from_file(self):
        lay_file = os.path.join(MOCKS_DIR, 'Providers/Test/SE2.lay')
        provider = O4Parser.ImageProvider()
        result = provider.parse_from_file(lay_file)

        self.assertTrue(result)
        self.assertEqual('SE2', provider.code)
        self.assertEqual('Test', provider.directory)
        self.assertEqual('wms', provider.request_type)
        self.assertEqual('http://mapy.geoportal.gov.pl/wss/service/img/guest/ORTO/MapServer/WMSServer?', provider.url)
        self.assertEqual('Raster', provider.layers)
        self.assertEqual(None, provider.tilematrixset)
        self.assertTrue(provider.in_gui)
        self.assertEqual('1.1.1', provider.wms_version)
        self.assertEqual(512, provider.wms_size)
        self.assertEqual(3857, provider.epsg_code)
        self.assertEqual({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
                          'Accept': '*/*',
                          'Connection': 'keep-alive',
                          'Accept-Encoding': 'gzip, deflate, br',
                          'Referer': 'https://map.geo.admin.ch',
                          'Origin': 'https://map.geo.admin.ch'},
                         provider.request_headers)

    @mock.patch('O4_UI_Utils.lvprint')
    def test_image_provider_parse_from_file_bad_key(self, lvprint_mock):
        lvprint_mock.lvprint = None
        lay_file = os.path.join(MOCKS_DIR, 'Providers/Test/BAD.lay')
        provider = O4Parser.ImageProvider()
        result = provider.parse_from_file(lay_file)

        self.assertFalse(result)


class TestCombinedProvider(unittest.TestCase):

    def test_combined_entry_init(self):
        combined_entry = O4Parser.CombinedEntry()

        self.assertEqual('', combined_entry.layer_code)
        self.assertEqual('', combined_entry.extent_code)
        self.assertEqual('none', combined_entry.color_code)
        self.assertEqual('medium', combined_entry.priority)

    def test_combined_provider_init(self):
        combined_provider = O4Parser.CombinedProvider()

        self.assertEqual('', combined_provider.code)
        self.assertEqual([], combined_provider.combined_list)

    def test_combined_provider_parse_from_file(self):
        combined_file = os.path.join(MOCKS_DIR, 'Providers/TEST.comb')
        combined_provider = O4Parser.CombinedProvider()
        result = combined_provider.parse_from_file(combined_file)

        self.assertTrue(result)
        # Small sampling
        self.assertEqual(2, len(combined_provider.combined_list))
        self.assertEqual('SE2', combined_provider.combined_list[0].layer_code)
        self.assertEqual('high', combined_provider.combined_list[0].priority)
        self.assertEqual('PDOK15', combined_provider.combined_list[1].layer_code)
        self.assertEqual('Tirol', combined_provider.combined_list[1].extent_code)

    @mock.patch('O4_UI_Utils.lvprint')
    def test_combined_provider_parse_from_file_bad_priority(self, lvprint_mock):
        lvprint_mock.lvprint = None
        combined_file = os.path.join(MOCKS_DIR, 'Providers/BADPRIO.comb')
        combined_provider = O4Parser.CombinedProvider()
        result = combined_provider.parse_from_file(combined_file)

        self.assertTrue(result)
        self.assertEqual(1, len(combined_provider.combined_list))

    @mock.patch('O4_UI_Utils.lvprint')
    def test_combined_provider_parse_from_file_bad_entry(self, lvprint_mock):
        lvprint_mock.lvprint = None
        combined_file = os.path.join(MOCKS_DIR, 'Providers/BADENTRY.comb')
        combined_provider = O4Parser.CombinedProvider()
        result = combined_provider.parse_from_file(combined_file)

        self.assertFalse(result)


class TestImageExtent(unittest.TestCase):

    def test_image_extent_init(self):
        extent = O4Parser.ImageExtent()

        self.assertEqual('', extent.code)
        self.assertEqual(None, extent.directory)
        self.assertEqual(None, extent.epsg_code)
        self.assertEqual(None, extent.mask_bounds)
        self.assertEqual(None, extent.mask_width)
        self.assertEqual(None, extent.buffer_width)
        self.assertFalse(extent.low_res)

        extent = O4Parser.ImageExtent('global')

        self.assertEqual('global', extent.code)

    def test_image_extent_parse_from_file(self):
        extent_file = os.path.join(MOCKS_DIR, 'Extents/Austria/Tirol.ext')
        extent = O4Parser.ImageExtent()
        result = extent.parse_from_file(extent_file)

        self.assertTrue(result)
        self.assertEqual('Tirol', extent.code)
        self.assertEqual('Austria', extent.directory)
        self.assertEqual([10.06, 46.62, 13.0, 47.78], extent.mask_bounds)
        self.assertIsNone(extent.epsg_code)
        self.assertIsNone(extent.mask_width)
        self.assertIsNone(extent.buffer_width)
        self.assertFalse(extent.low_res)

        extent_file = os.path.join(MOCKS_DIR, 'Extents/LowRes/Sweden.ext')
        extent = O4Parser.ImageExtent()
        result = extent.parse_from_file(extent_file)

        self.assertTrue(result)
        self.assertEqual('Sweden', extent.code)
        self.assertTrue(extent.low_res)

    @mock.patch('O4_UI_Utils.lvprint')
    def test_image_extent_parse_from_file_bad_key(self, lvprint_mock):
        lvprint_mock.lvprint = None
        extent_file = os.path.join(MOCKS_DIR, 'Extents/LowRes/Bad.ext')
        extent = O4Parser.ImageExtent()
        result = extent.parse_from_file(extent_file)

        self.assertFalse(result)

    def test_image_extent_parse_from_file_with_array(self):
        extent_file = os.path.join(MOCKS_DIR, 'Extents/LowRes/Array.ext')
        extent = O4Parser.ImageExtent()
        result = extent.parse_from_file(extent_file)

        self.assertTrue(result)


class TestColorFilter(unittest.TestCase):

    def test_color_filter_init(self):
        color_filter = O4Parser.ColorFilter()

        self.assertEqual('', color_filter.code)
        self.assertEqual([], color_filter.filters)

    def test_color_filter_parse_from_file(self):
        filter_file = os.path.join(MOCKS_DIR, 'Filters/GeoPunt2012.flt')
        color_filter = O4Parser.ColorFilter()
        result = color_filter.parse_from_file(filter_file)

        self.assertTrue(result)
        self.assertEqual('GeoPunt2012', color_filter.code)
        self.assertEqual(2, len(color_filter.filters))
        self.assertEqual(['brightness-contrast', -25.0, 10.0], color_filter.filters[1])

    @mock.patch('O4_UI_Utils.lvprint')
    def test_color_filter_parse_from_bad_file(self, lvprint_mock):
        lvprint_mock.print = None
        filter_file = os.path.join(MOCKS_DIR, 'Filters/BAD.flt')
        color_filter = O4Parser.ColorFilter()
        result = color_filter.parse_from_file(filter_file)

        self.assertFalse(result)


class TestFileParser(unittest.TestCase):

    def test_read_tile_matrix_sets_from_file(self):
        file_path = os.path.join(MOCKS_DIR, 'Providers/Netherlands/capabilities_PDOK15.xml')
        result = O4Parser.read_tile_matrix_sets_from_file(file_path)

        self.assertEqual(list, type(result))
        self.assertEqual(1, len(result))
        self.assertEqual('nltilingschema', result[0]['identifier'])
        tile_matrices = result[0]['tilematrices']
        self.assertEqual(15, len(tile_matrices))
        self.assertEqual('12288000.0', tile_matrices[0]['ScaleDenominator'])
        self.assertEqual('256', tile_matrices[0]['TileWidth'])

    def test_read_xml_file(self):
        file_path = os.path.join(MOCKS_DIR, 'Providers/Netherlands/capabilities_PDOK15.xml')
        result = O4Parser.read_xml_file(file_path)

        self.assertEqual(ET.Element, type(result))


if __name__ == '__main__':
    unittest.main()
