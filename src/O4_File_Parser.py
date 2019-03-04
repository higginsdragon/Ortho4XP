import os
import numpy
import O4_UI_Utils as UI
import O4_Imagery_Utils as O4Imagery
import xml.etree.ElementTree as ET
import gettext  # for future localization
_ = gettext.gettext

USER_AGENT_GENERIC = 'Mozilla/5.0 (X11; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0'
REQUEST_HEADERS_GENERIC = {
    'User-Agent': USER_AGENT_GENERIC,
    'Accept': '*/*',
    'Connection': 'keep-alive',
    'Accept-Encoding': 'gzip, deflate'
}
VALID_IMAGERY_REQUEST_TYPES = ['wms', 'wmts', 'tms', 'local_tms']
VALID_IMAGERY_DIRS = ['grouped', 'normal', 'code']
VALID_GRID_TYPES = ['webmercator']
VALID_COMBINED_PRIORITIES = ['low', 'medium', 'high', 'mask']


class ImageProvider:

    def __init__(self):
        self.code = ''
        self.directory = ''
        self.request_type = ''
        self.url = ''
        self.in_gui = True
        self.max_zl = 18
        self.image_type = 'jpeg'
        self.extent = 'global'
        self.imagery_dir = 'grouped'
        self.grid_type = ''
        self.color_filters = 'none'
        self.tile_size = 256
        self.epsg_code = 3857
        self.scaledenominator = None
        self.top_left_corner = None
        self.resolutions = None
        self.tilematrixset = None
        self.max_threads = 8
        self.request_headers = REQUEST_HEADERS_GENERIC
        self.wms_version = None
        self.wmts_version = None
        self.wms_size = self.tile_size
        self.layers = ''

        self.url_prefix = ''
        self.url_template = ''
        self.fake_headers = None

    def parse_from_file(self, file_path):
        f = open(file_path)
        lines = f.readlines()
        f.close()

        user_agent_generic = USER_AGENT_GENERIC  # compatibility with existing files for eval statements
        file_dir = os.path.split(file_path)[0]
        self.code = os.path.split(file_path)[1].split('.')[0]
        self.directory = os.path.split(file_dir)[1]
        valid_keys = list(vars(self).keys())

        for line in lines:
            line = line.strip()
            if '#' in line:
                if line[0] == '#':
                    continue
                else:
                    line = line.split('#')[0].strip()

            if '=' not in line:
                continue

            items = line.split('=')
            key = items[0].strip()
            value = '='.join(items[1:]).strip()
            key = key.lower()

            if value[0] in ['[', '{'] or value in ['True', 'False']:
                value = eval(value)
            else:
                try:
                    value = int(value)
                except ValueError:
                    pass

            if key not in valid_keys:
                UI.lvprint(0, _('{key} is not a valid line in provider {provider_code}. Skipping.').
                           format(key=key, provider_code=self.code))
                return 0
            else:
                setattr(self, key, value)

        # structuring data
        unknown_type_text = _('Unknown {var} field for provider {provider_code}: {value}')
        error_reading_text = _('Error in reading {var} for provider {provider_code}')

        if self.grid_type and self.grid_type not in VALID_GRID_TYPES:
            UI.vprint(0, unknown_type_text.format(var='grid_type', provider_code=self.code, value=self.request_type))
            return 0

        if self.url_prefix:
            self.url = self.url_prefix
        if self.url_template:
            self.url = self.url_template
        if not self.url:  # TODO: Add support for custom URLs
            print(error_reading_text.format(var='url', provider_code=self.code))
            return 0

        if self.fake_headers:
            try:
                if type(self.fake_headers) is not dict:
                    print(_('Definition of fake_headers for provider {provider_code} not valid: Not a dictionary').
                          format(provider_code=self.code))
                    return 0
                # just add/change headers rather than replace
                for key in self.fake_headers:
                    self.request_headers[key] = self.fake_headers[key]

            except SyntaxError as e:
                print(_('Definition of fake_headers for provider {provider_code} not valid: {reason}').
                      format(provider_code=self.code, reason=e))
                return 0

        if not isinstance(self.in_gui, bool):
            UI.vprint(0, _('Error in GUI status for provider {provider_code}').format(provider_code=self.code))
            self.in_gui = True

        if self.request_type == 'wms':
            self.tile_size = self.wms_size
        else:
            self.wms_size = self.tile_size

        if self.tile_size < 100 or self.tile_size > 10000:
            print(_('wm(t)s size for provider {provider_code} seems off limits, provider skipped.').
                  format(provider_code=self.code))
            return 0

        for ver in [self.wms_version, self.wmts_version]:
            if ver and len(ver.split('.')) < 2:
                print(unknown_type_text.format(var='wm(t)s_version', provider_code=self.code, value=ver))
                return 0

        if self.top_left_corner:
            try:
                value = str(self.top_left_corner)
                self.top_left_corner = [numpy.array([float(x) for x in value.split()]) for r in range(40)]
            except ValueError:
                print(error_reading_text.format(var='top_left_corner', provider_code=self.code))
                return 0

        if self.scaledenominator:
            try:
                value = str(self.scaledenominator)
                self.scaledenominator = numpy.array([float(x) for x in value.split()])
            except ValueError:
                print(error_reading_text.format(var='scaledenominator', provider_code=self.code))
                return 0

        if self.resolutions:
            try:
                value = str(self.resolutions)
                self.resolutions = numpy.array([float(x) for x in value.split()])
            except ValueError:
                print(error_reading_text.format(var='resolutions', provider_code=self.code))
                return 0

        if self.color_filters != 'none':
            if self.color_filters not in O4Imagery.color_filters_dict:
                print(_('Error in reading color_filter for provider {provider_code}. Assuming none.').
                      format(provider_code=self.code))
                self.color_filters = 'none'

        if self.imagery_dir not in VALID_IMAGERY_DIRS:
            print(_('Error in reading imagery_dir for provider {provider_code}. Assuming grouped.').
                  format(provider_code=self.code))
            self.imagery_dir = 'grouped'

        if self.request_type == 'wmts':
            file_path = os.path.join(file_dir, 'capabilities_' + str(self.code) + '.xml')
            if not os.path.isfile(file_path):
                file_path = os.path.join(file_dir, 'capabilities.xml')
                if not os.path.isfile(file_path):
                    print(_('Cannot find capabilities XML file for {provider_code}. Skipping.').
                          format(provider_code=self.code))
                    return 0

            tile_matrix_sets = read_tile_matrix_sets_from_file(file_path)
            if not tile_matrix_sets:
                print(_('Error parsing capabilities XML file for {provider_code}. Skipping').
                      format(provider_code=self.code))
                return 0

            for tile_matrix_set in tile_matrix_sets:
                if tile_matrix_set['identifier'] == self.tilematrixset:
                    self.tilematrixset = tile_matrix_set
                    break

            if not self.tilematrixset:
                print(_('No tile matrix set found for provider {provider_code}. Skipping.').
                      format(provider_code=self.code))
                return 0

            self.scaledenominator =\
                numpy.array([float(x['ScaleDenominator']) for x in self.tilematrixset['tilematrices']])
            self.top_left_corner =\
                [[float(x) for x in y['TopLeftCorner'].split()] for y in self.tilematrixset['tilematrices']]

            units_per_pix = 0.00028 if self.epsg_code not in ['4326'] else 2.5152827955e-09
            self.resolutions = units_per_pix * self.scaledenominator

        if self.grid_type == 'webmercator':
            self.request_type = 'tms'
            self.tile_size = 256
            self.epsg_code = 3857
            self.top_left_corner = [[-20037508.34, 20037508.34] for r in range(0, 21)]
            self.resolutions = numpy.array([20037508.34/(128 * 2 ** r) for r in range(0, 21)])

        if not self.request_type:
            UI.lvprint(2, _('Error in reading provider definition file for {path}').format(path=file_path))
            return 0
        elif self.request_type.lower() not in VALID_IMAGERY_REQUEST_TYPES:
            UI.vprint(0, unknown_type_text.format(var='request_type', provider_code=self.code, value=self.request_type))
            return 0

        return 1


def read_tile_matrix_sets_from_file(file_name):
    tile_matrix_sets = []
    tm_parsed = read_xml_file(file_name)
    xml_namespaces = {
        'wmts': 'http://www.opengis.net/wmts/1.0',
        'ows': 'http://www.opengis.net/ows/1.1'
    }

    if not tm_parsed or isinstance(tm_parsed, int):
        return 0

    xml_matrix_sets = tm_parsed.findall('wmts:Contents/wmts:TileMatrixSet', xml_namespaces)

    for xml_matrix_set in xml_matrix_sets:
        tile_matrix_set = {
            'tilematrices': [],
            'identifier': xml_matrix_set.find('ows:Identifier', xml_namespaces).text
        }
        xml_matrices = xml_matrix_set.findall('wmts:TileMatrix', xml_namespaces)

        for xml_matrix in xml_matrices:
            tile_matrix = {}

            for elem in xml_matrix.findall('*'):
                field = elem.tag.split('}')[1]
                if field == 'Identifier':
                    field = field.lower()
                tile_matrix[field] = elem.text

            tile_matrix_set['tilematrices'].append(tile_matrix)

        tile_matrix_sets.append(tile_matrix_set)

    return tile_matrix_sets


class CombinedEntry:

    def __init__(self):
        self.layer_code = ''
        self.extent_code = ''
        self.color_code = 'none'
        self.priority = 'medium'


class CombinedProvider:

    def __init__(self):
        self.code = ''
        self.combined_list = []

    def parse_from_file(self, file_path):
        f = open(file_path)
        lines = f.readlines()
        f.close()

        self.code = os.path.split(file_path)[1].split('.')[0]

        for line in lines:
            line = line.strip()
            if '#' in line:
                if line[0] == '#':
                    continue
                else:
                    line = line.split('#')[0].strip()

            if not line:
                continue

            entry = CombinedEntry()

            try:
                entry.layer_code, entry.extent_code, entry.color_code, entry.priority = line.split()
            except ValueError:
                UI.lvprint(1, _('Combined provider {provider_code} did not contain valid providers. Skipped').
                           format(provider_code=self.code))
                return 0

            if entry.priority not in VALID_COMBINED_PRIORITIES:
                UI.lvprint(2, _('Unknown priority in combined provider {provider_code}: {prio}').
                           format(provider_code=self.code, prio=entry.priority))
                continue

            self.combined_list.append(entry)

        return 1


class ImageExtent:

    def __init__(self, extent_code=''):
        self.code = extent_code
        self.directory = None
        self.epsg_code = None
        self.mask_bounds = None
        self.mask_width = None
        self.buffer_width = None
        self.blur_width = None
        self.low_res = False

    def parse_from_file(self, file_path):
        f = open(file_path)
        lines = f.readlines()
        f.close()

        file_dir = os.path.split(file_path)[0]
        self.code = os.path.split(file_path)[1].split('.')[0]
        self.directory = os.path.split(file_dir)[1]
        valid_keys = list(vars(self).keys())

        for line in lines:
            line = line.strip()
            if '#' in line:
                if line[0] == '#':
                    continue
                else:
                    line = line.split('#')[0].strip()

            if '=' not in line:
                continue

            items = line.split('=')
            key = items[0].strip()
            value = items[1].strip()
            key = key.lower()

            if value[0] in ['[', '{'] or value in ['True', 'False']:
                value = eval(value)
            else:
                try:
                    value = float(value)
                except ValueError:
                    pass

            if key not in valid_keys:
                UI.lvprint(0, _('{key} is not a valid line in provider {provider_code}. Skipping.').
                           format(key=key, provider_code=self.code))
                return 0
            else:
                setattr(self, key, value)

        # structuring data
        error_reading_text = _('Error in reading {var} for provider {provider_code}')

        if self.mask_bounds and isinstance(self.mask_bounds, str):
            try:
                self.mask_bounds = [float(x) for x in self.mask_bounds.split(',')]
            except ValueError:
                print(error_reading_text.format(var='mask_bounds', provider_code=self.code))
                return 0

        if self.directory == 'LowRes':
            self.low_res = True

        return 1


class ColorFilter:

    def __init__(self):
        self.code = ''
        self.filters = []

    def parse_from_file(self, file_path):
        f = open(file_path)
        lines = f.readlines()
        f.close()

        self.code = os.path.split(file_path)[1].split('.')[0]
        color_filters = []

        try:
            for line in lines:
                line = line.strip()
                if '#' in line:
                    if line[0] == '#':
                        continue
                    else:
                        line = line.split('#')[0].strip()

                if not line:
                    continue

                items = line.split()
                color_filters.append([items[0]] + [float(x) for x in items[1:]])

            self.filters = color_filters
        except ValueError:
            UI.lvprint(2, _('Could not understand color filter {color_code} - skipping.').format(color_code=self.code))
            return 0

        return 1


def read_xml_file(file_name):
    try:
        xfile = open(file_name, 'r', encoding='utf-8')
    except FileNotFoundError:
        print(_('File not found; {file_name}').format(file_name=file_name))
        return 0
    except OSError:
        print(_('Could not open {file_name} for reading.').format(file_name=file_name))
        return 0

    xml_raw = xfile.read()
    xfile.close()

    try:
        xml_parsed = ET.fromstring(xml_raw)
    except ET.ParseError:
        print(_('Error parsing XML data from {file_name}, possibly corrupted.').format(file_name=file_name))
        return 0

    return xml_parsed
