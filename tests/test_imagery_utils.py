import unittest
import unittest.mock as mock
import os

import O4_Test
import O4_Imagery_Utils as O4Imagery
import O4_Config_Utils as O4Config
import O4_File_Names

TESTS_DIR = O4_Test.TESTS_DIR
TEMP_DIR = O4_Test.TEMP_DIR
MOCKS_DIR = O4_Test.MOCKS_DIR


class TestInitialization(unittest.TestCase):

    @mock.patch('O4_UI_Utils.lvprint')
    def test_initialize_extents_dict(self, lvprint_mock):
        lvprint_mock.lvprint = None
        O4_File_Names.Extent_dir = os.path.join(MOCKS_DIR, 'Extents/')

        O4Imagery.initialize_extents_dict()

        extents_dict = O4Imagery.extents_dict

        self.assertEqual(5, len(extents_dict))
        self.assertIsNone(extents_dict['global'].directory)
        self.assertEqual('Austria', extents_dict['Tirol'].directory)
        self.assertEqual([10.06, 46.62, 13.0, 47.78], extents_dict['Tirol'].mask_bounds)
        self.assertFalse(extents_dict['Tirol'].low_res)
        self.assertTrue(extents_dict['Sweden'].low_res)

    @mock.patch('O4_UI_Utils.lvprint')
    def test_initialize_color_filters_dict(self, lvprint_mock):
        lvprint_mock.lvprint = None
        O4_File_Names.Filter_dir = os.path.join(MOCKS_DIR, 'Filters/')

        O4Imagery.initialize_color_filters_dict()

        filters_dict = O4Imagery.color_filters_dict
        self.assertEqual(3, len(filters_dict))
        self.assertEqual([], filters_dict['none'])
        self.assertEqual(2, len(filters_dict['GeoPunt2012']))
        self.assertEqual([['brightness-contrast', -30.0, 10.0]], filters_dict['SEA'])

    @mock.patch('O4_UI_Utils.lvprint')
    def test_initialize_providers_dict(self, lvprint_mock):
        lvprint_mock.lvprint = None
        O4_File_Names.Provider_dir = os.path.join(MOCKS_DIR, 'Providers/')

        O4Imagery.initialize_providers_dict()

        providers_dict = O4Imagery.providers_dict
        self.assertEqual(3, len(providers_dict))
        self.assertEqual('wms', providers_dict['SE2'].request_type)
        self.assertTrue(providers_dict['SE2'].in_gui)
        self.assertEqual('nltilingschema', providers_dict['PDOK15'].tilematrixset['identifier'])
        self.assertEqual(15, len(providers_dict['PDOK15'].tilematrixset['tilematrices']))

    @mock.patch('O4_UI_Utils.lvprint')
    def test_initialize_combined_providers_dict(self, lvprint_mock):
        lvprint_mock.lvprint = None
        O4_File_Names.Provider_dir = os.path.join(MOCKS_DIR, 'Providers/')
        O4_File_Names.Filter_dir = os.path.join(MOCKS_DIR, 'Filters/')
        O4_File_Names.Extent_dir = os.path.join(MOCKS_DIR, 'Extents/')

        O4Imagery.initialize_extents_dict()
        O4Imagery.initialize_color_filters_dict()
        O4Imagery.initialize_providers_dict()
        O4Imagery.initialize_combined_providers_dict()

        combined_dict = O4Imagery.combined_providers_dict
        self.assertEqual(2, len(combined_dict))
        test_dict = combined_dict['TEST']
        self.assertEqual(2, len(test_dict))
        # Small sampling
        self.assertEqual('SE2', test_dict[0].layer_code)
        self.assertEqual('high', test_dict[0].priority)
        self.assertEqual('NIB', test_dict[1].layer_code)
        self.assertEqual('Norway', test_dict[1].extent_code)

    @mock.patch('os.path.exists')
    @mock.patch('O4_UI_Utils.vprint')
    @mock.patch('O4_UI_Utils.lvprint')
    def test_initialize_local_combined_providers_dict(self, lvprint_mock, vprint_mock, path_mock):
        vprint_mock.vprint = None
        lvprint_mock.lvprint = None
        path_mock.exists = True
        O4_File_Names.Provider_dir = os.path.join(MOCKS_DIR, 'Providers/')
        O4_File_Names.Filter_dir = os.path.join(MOCKS_DIR, 'Filters/')
        O4_File_Names.Extent_dir = os.path.join(MOCKS_DIR, 'Extents/')

        O4Imagery.initialize_extents_dict()
        O4Imagery.initialize_color_filters_dict()
        O4Imagery.initialize_providers_dict()
        O4Imagery.initialize_combined_providers_dict()

        tile = O4Config.Tile(60, 12, '')
        tile.default_website = 'TEST'

        result = O4Imagery.initialize_local_combined_providers_dict(tile)
        local_dict = O4Imagery.local_combined_providers_dict

        self.assertTrue(result)
        self.assertEqual(1, len(local_dict))
        self.assertEqual(2, len(local_dict['TEST']))
        self.assertEqual('SE2', local_dict['TEST'][0].layer_code)
        self.assertEqual('NIB', local_dict['TEST'][1].layer_code)

    @mock.patch('O4_UI_Utils.vprint')
    @mock.patch('O4_UI_Utils.lvprint')
    def test_has_data(self, lvprint_mock, vprint_mock):
        vprint_mock.vprint = None
        lvprint_mock.lvprint = None
        O4_File_Names.Provider_dir = os.path.join(MOCKS_DIR, 'Providers/')
        O4_File_Names.Filter_dir = os.path.join(MOCKS_DIR, 'Filters/')
        O4_File_Names.Extent_dir = os.path.join(MOCKS_DIR, 'Extents/')

        O4Imagery.initialize_extents_dict()
        O4Imagery.initialize_color_filters_dict()
        O4Imagery.initialize_providers_dict()
        O4Imagery.initialize_combined_providers_dict()

        tile = O4Config.Tile(60, 12, '')
        tile.default_website = 'TEST'
        bbox = (tile.lon, tile.lat + 1, tile.lon + 1, tile.lat)
        entry = O4Imagery.combined_providers_dict['TEST'][1]
        result = O4Imagery.has_data(bbox, entry.extent_code, is_mask_layer=False)

        self.assertTrue(result)

        # create a failing condition
        tile.lon = 13
        bbox = (tile.lon, tile.lat + 1, tile.lon + 1, tile.lat)
        result = O4Imagery.has_data(bbox, entry.extent_code, is_mask_layer=False)

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
