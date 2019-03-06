import unittest
import unittest.mock as mock
import os
import O4_Test
import O4_Imagery_Utils as O4Imagery
import O4_Config_Utils as O4Config
import O4_File_Names
from PIL import Image

TESTS_DIR = O4_Test.TESTS_DIR
TEMP_DIR = O4_Test.TEMP_DIR
MOCKS_DIR = O4_Test.MOCKS_DIR


@mock.patch('O4_UI_Utils.vprint')
@mock.patch('O4_UI_Utils.lvprint')
class TestInitialization(unittest.TestCase):

    def test_initialize_extents_dict(self, lvprint_mock, vprint_mock):
        lvprint_mock.lvprint = None
        vprint_mock.lvprint = None
        O4_File_Names.Extent_dir = os.path.join(MOCKS_DIR, 'Extents/')

        O4Imagery.initialize_extents_dict()

        extents_dict = O4Imagery.extents_dict

        self.assertEqual(5, len(extents_dict))
        self.assertIsNone(extents_dict['global'].directory)
        self.assertEqual('Austria', extents_dict['Tirol'].directory)
        self.assertEqual([10.06, 46.62, 13.0, 47.78], extents_dict['Tirol'].mask_bounds)
        self.assertFalse(extents_dict['Tirol'].low_res)
        self.assertTrue(extents_dict['Sweden'].low_res)

    def test_initialize_color_filters_dict(self, lvprint_mock, vprint_mock):
        lvprint_mock.lvprint = None
        vprint_mock.lvprint = None
        O4_File_Names.Filter_dir = os.path.join(MOCKS_DIR, 'Filters/')

        O4Imagery.initialize_color_filters_dict()

        filters_dict = O4Imagery.color_filters_dict
        self.assertEqual(3, len(filters_dict))
        self.assertEqual([], filters_dict['none'])
        self.assertEqual(2, len(filters_dict['GeoPunt2012']))
        self.assertEqual([['brightness-contrast', -30.0, 10.0]], filters_dict['SEA'])

    def test_initialize_providers_dict(self, lvprint_mock, vprint_mock):
        lvprint_mock.lvprint = None
        vprint_mock.lvprint = None
        O4_File_Names.Provider_dir = os.path.join(MOCKS_DIR, 'Providers/')

        O4Imagery.initialize_providers_dict()

        providers_dict = O4Imagery.providers_dict
        self.assertEqual(3, len(providers_dict))
        self.assertEqual('wms', providers_dict['SE2'].request_type)
        self.assertTrue(providers_dict['SE2'].in_gui)
        self.assertEqual('nltilingschema', providers_dict['PDOK15'].tilematrixset['identifier'])
        self.assertEqual(15, len(providers_dict['PDOK15'].tilematrixset['tilematrices']))

    def test_initialize_combined_providers_dict(self, lvprint_mock, vprint_mock):
        lvprint_mock.lvprint = None
        vprint_mock.lvprint = None
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
    def test_initialize_local_combined_providers_dict(self, path_mock, lvprint_mock, vprint_mock):
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


@mock.patch('O4_UI_Utils.vprint')
class TestImageRequests(unittest.TestCase):

    def test_http_request_to_image(self, vprint_mock):
        vprint_mock.vprint = None
        image_path = os.path.join(MOCKS_DIR, '48N114W_22560_12064_NAIP16.jpg')
        image_file = open(image_path, 'br')
        image_data = image_file.read()
        image_file.close()

        request = O4_Test.MockSession()
        request.status_code = 200
        request.headers['Content-Length'] = os.path.getsize(image_path)

        request.content = image_data

        url = 'http://image-test.none'
        (result, remote_image) = O4Imagery.http_request_to_image(url, None, request)

        self.assertTrue(result)

        local_image = Image.open(image_path)
        self.assertEqual(local_image, remote_image)
        local_image.close()

    def test_http_request_to_image_not_found(self, vprint_mock):
        vprint_mock.vprint = None
        request = O4_Test.MockSession()
        request.status_code = 404

        url = 'http://image-test.none'
        (result, result_status) = O4Imagery.http_request_to_image(url, None, request)

        self.assertFalse(result)
        self.assertEqual(404, result_status)

    def test_http_request_to_image_forbidden(self, vprint_mock):
        vprint_mock.vprint = None
        request = O4_Test.MockSession()
        request.status_code = 403

        url = 'http://image-test.none'
        (result, result_status) = O4Imagery.http_request_to_image(url, None, request)

        self.assertFalse(result)
        self.assertEqual(403, result_status)

    @mock.patch('O4_Imagery_Utils.time.sleep')
    def test_http_request_to_image_internal_error(self, sleep_mock, vprint_mock):
        vprint_mock.vprint = None
        sleep_mock.sleep = mock.MagicMock()
        request = O4_Test.MockSession()
        request.status_code = 500

        url = 'http://image-test.none'
        (result, result_status) = O4Imagery.http_request_to_image(url, None, request)

        self.assertFalse(result)
        self.assertEqual(500, result_status)

    def test_http_request_to_image_wrong_content_type(self, vprint_mock):
        vprint_mock.vprint = None
        request = O4_Test.MockSession()
        request.status_code = 200
        request.headers = {'Content-Type': 'text/text'}

        url = 'http://image-test.none'
        (result, result_status) = O4Imagery.http_request_to_image(url, None, request)

        self.assertFalse(result)
        self.assertEqual(200, result_status)

    @mock.patch('O4_Imagery_Utils.UI')
    @mock.patch('O4_Imagery_Utils.time.sleep')
    def test_http_request_to_image_red_flag(self, sleep_mock, ui_mock, vprint_mock):
        vprint_mock.vprint = None
        ui_mock.red_flag = True
        sleep_mock.sleep = mock.MagicMock()
        request = O4_Test.MockSession()
        request.status_code = 500

        url = 'http://image-test.none'
        (result, result_status) = O4Imagery.http_request_to_image(url, None, request)

        self.assertFalse(result)
        self.assertEqual('Stopped', result_status)


if __name__ == '__main__':
    unittest.main()
