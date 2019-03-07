import time 
import os
import sys
import importlib.machinery
import glob
import subprocess
import io
import requests
import queue
import random
from math import ceil, log, tan, pi
import numpy
from PIL import Image, ImageFilter, ImageEnhance,  ImageOps
import O4_UI_Utils as UI
import O4_Geo_Utils as GEO
import O4_File_Names as FNAMES
import O4_File_Parser as O4Parser
import O4_Vector_Utils as VECT
import O4_Mesh_Utils as MESH
import O4_OSM_Utils as OSM
import O4_Mask_Utils as MASK
from O4_Parallel_Utils import parallel_execute
from typing import Tuple, Type, Union
import gettext  # for future localization
_ = gettext.gettext

Image.MAX_IMAGE_PIXELS = 1000000000  # Not a decompression bomb attack!

http_timeout = 10
check_tms_response = False
max_connect_retries = 10
max_baddata_retries = 10

user_agent_generic = "Mozilla/5.0 (X11; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0"
request_headers_generic = {
    'User-Agent': user_agent_generic,
    'Accept': '*/*',
    'Connection': 'keep-alive',
    'Accept-Encoding': 'gzip, deflate'
}

if 'dar' in sys.platform:
    dds_convert_cmd = os.path.join(UI.Ortho4XP_dir,"Utils","nvcompress","nvcompress.app") 
    gdal_transl_cmd = "gdal_translate"
    gdalwarp_cmd    = "gdalwarp"
    devnull_rdir    = " >/dev/null 2>&1"
elif 'win' in sys.platform: 
    dds_convert_cmd = os.path.join(UI.Ortho4XP_dir, "Utils", "nvcompress", "nvcompress.exe") 
    gdal_transl_cmd = "gdal_translate.exe"
    gdalwarp_cmd    = "gdalwarp.exe"
    devnull_rdir    = " > nul  2>&1"
else:
    dds_convert_cmd = "nvcompress" 
    gdal_transl_cmd = "gdal_translate"
    gdalwarp_cmd    = "gdalwarp"
    devnull_rdir    = " >/dev/null 2>&1 "
    

extents_dict = {}
color_filters_dict = {'none': []}
providers_dict = {}
combined_providers_dict = {}
local_combined_providers_dict = {}


# The initialize functions place providers, extents, and color filters into easily-accessible globals
# for all functions in the module.
def initialize_extents_dict() -> None:
    """
    Looks for .ext files (in Extents/) and parses them all into module's extents_dict variable.
    :return: None
    """
    # Add a default extent.
    extents_dict['global'] = O4Parser.ImageExtent('global')

    for dir_name in os.listdir(FNAMES.Extent_dir):
        if not os.path.isdir(os.path.join(FNAMES.Extent_dir, dir_name)):
            continue
        for file_path in glob.glob(os.path.join(FNAMES.Extent_dir, dir_name, '*.ext')):
            extent = O4Parser.ImageExtent()

            if not extent.parse_from_file(file_path):
                continue

            extents_dict[extent.code] = extent


def initialize_color_filters_dict() -> None:
    """
    Looks for .flt files (in Filters/) and parses them all into module's color_filters_dict variable.
    :return: None
    """
    for file_path in glob.glob(os.path.join(FNAMES.Filter_dir, '*.flt')):
        color_filter = O4Parser.ColorFilter()

        if not color_filter.parse_from_file(file_path):
            continue

        color_filters_dict[color_filter.code] = color_filter.filters


def initialize_providers_dict() -> None:
    """
    Looks for .lay files (in Providers/) and parses them all into module's providers_dict variable.
    :return: None
    """
    for dir_name in os.listdir(FNAMES.Provider_dir):
        if not os.path.isdir(os.path.join(FNAMES.Provider_dir, dir_name)):
            continue
        for file_path in glob.glob(os.path.join(FNAMES.Provider_dir, dir_name, '*.lay')):
            provider = O4Parser.ImageProvider()

            if not provider.parse_from_file(file_path):
                continue

            if provider.epsg_code:
                try:
                    GEO.epsg[provider.epsg_code] = GEO.pyproj.Proj(init='epsg:' + str(provider.epsg_code))
                except RuntimeError:
                    UI.vprint(0, _('Error in EPSG code for provider {pcode}').format(pcode=provider.code))
                    continue

            providers_dict[provider.code] = provider


def initialize_combined_providers_dict() -> None:
    """
    Looks for .comb files (in Providers/) and parses them all into module's combined_providers_dict variable.
    :return: None
    """
    unknown_error_message = _('Unknown {key} in combined provider {comb_code}: {layer_code}')
    for file_path in glob.glob(os.path.join(FNAMES.Provider_dir, '*.comb')):
        combined_provider = O4Parser.CombinedProvider()

        if not combined_provider.parse_from_file(file_path):
            continue

        combined_entries = []
        for entry in combined_provider.combined_list:
            if entry.layer_code not in providers_dict:
                print(unknown_error_message.
                      format(key='provider', comb_code=combined_provider.code, layer_code=entry.layer_code))
                continue

            if entry.extent_code == 'default':
                entry.extent_code = providers_dict[entry.layer_code].extent

            if (entry.extent_code not in extents_dict) or \
                    (entry.extent_code[0] == '!' and entry.extent_code[1:] not in extents_dict):
                print(unknown_error_message.
                      format(key='extent', comb_code=combined_provider.code, layer_code=entry.extent_code))
                continue

            if entry.color_code == 'default':
                entry.color_code = providers_dict[entry.layer_code].color_filters

            if entry.color_code not in color_filters_dict:
                # This seems to be here due to backwards-compatibility, not in current filter files.
                try:
                    if entry.color_code[0] == 'L':
                        b = 1
                    elif entry.color_code[0] == 'D':
                        b = -1
                    else:
                        continue

                    brightness = b * float(entry.color_code[1:3])
                    contrast = float(entry.color_code[4:6])
                    color_filters_dict[entry.color_code] = [['brightness-contrast', brightness, contrast]]

                    if len(entry.color_code) > 6:
                        saturation = float(entry.color_code[7:9])
                        color_filters_dict[entry.color_code].append(['saturation', saturation])
                except ValueError:
                    print(unknown_error_message.
                          format(key='color filter', comb_code=combined_provider.code, layer_code=entry.color_code))
                    continue

            # Priority is filtered out when parsing the file.
            combined_entries.append(entry)

        if combined_entries:
            combined_providers_dict[combined_provider.code] = combined_entries
        else:
            print(_('Combined provider {provider_code} did not contain valid providers. Skipped.').
                  format(provider_code=combined_provider.code))


def initialize_local_combined_providers_dict(tile) -> bool:
    """
    Selects from the list of providers the only ones whose coverage intersects the given tile and creates
    masks for the necessary providers. Also places data into global local_combined_providers_dict
    :param tile: Tile object
    :return: True or False
    """
    global local_combined_providers_dict, extents_dict
    local_combined_providers_dict = {}
    test_set = {tile.default_website}

    UI.vprint(1, _('-> Initializing providers with potential data on this tile.'))

    for region in tile.zone_list[:]:
        test_set.add(region[2])

    for provider_code in test_set.intersection(combined_providers_dict):
            combined_list = []

            for combined_entry in combined_providers_dict[provider_code]:
                bbox = (tile.lon, tile.lat + 1, tile.lon + 1, tile.lat)
                if combined_entry.priority == 'mask':
                    is_mask_layer = (tile.lat, tile.lon, tile.mask_zl)
                else:
                    is_mask_layer = False

                if has_data(bbox, combined_entry.extent_code, is_mask_layer=is_mask_layer):
                    combined_list.append(combined_entry)

            if combined_list:
                if len(combined_list) != 1:
                    new_combined_list = []
                    for combined_entry in combined_list:
                        name = combined_entry.extent_code
                        if name[0] == '!':
                            name = name[1:]
                        if extents_dict[name].low_res:
                            new_extent = O4Parser.ImageExtent()
                            new_extent.code = name + "_" + FNAMES.short_latlon(tile.lat, tile.lon)
                            new_extent.directory = 'Auto'
                            new_extent.mask_bounds = [tile.lon - 0.1, tile.lat - 0.1, tile.lon + 1.1, tile.lat + 1.1]
                            extents_dict[new_extent.code] = new_extent

                            new_entry = O4Parser.CombinedEntry()
                            new_entry.layer_code = combined_entry.layer_code
                            new_entry.extent_code = new_extent.code
                            new_combined_list.append(new_entry)

                            if os.path.exists(os.path.join(FNAMES.Extent_dir, 'Auto', new_extent.code + '.png')):
                                UI.vprint(1, _('    Recycling layer mask for {name}').format(name=name))
                                continue
                            UI.vprint(1, _('    Building layer mask for {name}').format(name=name))
                            # need to build the extent mas over that tile
                            if not os.path.isdir(os.path.join(FNAMES.Extent_dir, 'Auto')):
                                os.makedirs(os.path.join(FNAMES.Extent_dir, 'Auto'))
                            cached_file_name = os.path.join(FNAMES.Extent_dir, 'LowRes', name + '.osm.bz2')

                            pixel_size = 10
                            if extents_dict[name].buffer_width:
                                buffer_width = extents_dict[name].buffer_width / pixel_size
                            else:
                                buffer_width = 0.0

                            if extents_dict[name].mask_width:
                                mask_width = int(extents_dict[name].mask_width / pixel_size)
                            else:
                                mask_width = int(100 / pixel_size)

                            pixel_size = pixel_size / 111139
                            vector_map = VECT.Vector_Map()
                            osm_layer = OSM.OSM_layer()

                            if not os.path.exists(cached_file_name):
                                UI.vprint(0, _('Error: missing OSM data for extent code {name}. Exiting.').
                                          format(name=name))
                                del extents_dict[new_extent.code]
                                return False

                            osm_layer.update_dicosm(cached_file_name)
                            multipolygon_area = OSM.OSM_to_MultiPolygon(osm_layer, 0, 0)
                            del osm_layer

                            if not multipolygon_area.area:
                                UI.vprint(0, _('Error: erroneous OSM data for extent code {name}. Skipped.').
                                          format(name=name))
                                continue

                            vector_map.encode_MultiPolygon(multipolygon_area,
                                                           VECT.dummy_alt,
                                                           'DUMMY',
                                                           check=False,
                                                           cut=False)
                            vector_map.write_node_file(name + '.node')  # TODO: Shouldn't these go in tmp/ ?
                            vector_map.write_poly_file(name + '.poly')
                            MESH.triangulate(name, '.')
                            ((xmin, ymin, xmax, ymax), mask_im) =\
                                MASK.triangulation_to_image(name, pixel_size, tuple(new_extent.mask_bounds))

                            if buffer_width:
                                mask_im = mask_im.filter(ImageFilter.GaussianBlur(buffer_width / 4))
                                if buffer_width > 0:
                                    mask_im = Image.fromarray((numpy.array(mask_im, dtype=numpy.uint8) > 0).
                                                              astype(numpy.uint8) * 255)
                                else:
                                    mask_im = Image.fromarray((numpy.array(mask_im, dtype=numpy.uint8) == 255).
                                                              astype(numpy.uint8) * 255)

                            if mask_width:
                                mask_width += 1
                                img_array = numpy.array(mask_im, dtype=numpy.uint8)
                                kernel = numpy.ones(int(mask_width)) / int(mask_width)
                                kernel = numpy.array(range(1, 2 * mask_width))
                                kernel[mask_width:] = range(mask_width - 1, 0, -1)
                                kernel = kernel / mask_width ** 2
                                for i in range(0, len(img_array)):
                                    img_array[i] = numpy.convolve(img_array[i], kernel, 'same')
                                img_array = img_array.transpose()
                                for i in range(0, len(img_array)):
                                    img_array[i] = numpy.convolve(img_array[i], kernel, 'same')
                                img_array = img_array.transpose()
                                img_array[img_array >= 128] = 255
                                img_array[img_array < 128] *= 2
                                img_array = numpy.array(img_array, dtype=numpy.uint8)
                                mask_im = Image.fromarray(img_array)

                            mask_im.save(os.path.join(FNAMES.Extent_dir, 'Auto', new_extent.code + '.png'))

                            for f in [name + '.poly', name + '.node', name + '.1.node', name + '.1.ele']:
                                try:
                                    os.remove(f)
                                except FileNotFoundError:
                                    pass
                        else:
                            new_combined_list.append(combined_entry)

                    local_combined_providers_dict[provider_code] = new_combined_list
                else:
                    local_combined_providers_dict[provider_code] = combined_list
            else:
                UI.vprint(1, _('Combined provider {pcode} did not contain data for this tile. Exiting.').
                          format(pcode=provider_code))
                return False
    UI.vprint(2, _('    Done.'))
    return True


def has_data(bbox, extent_code, return_mask=False, mask_size=(4096, 4096), is_sharp_resize=False, is_mask_layer=False):
    """
    This function checks whether a given provider has data intersecting the given bbox.
    IMPORTANT: THE EXTENT AND THE BBOX NEED TO BE USING THE SAME REFERENCE FRAME (e.g. ESPG CODE)
    IMPORTANT TOO: (x0,y0) is the top-left corner, (x1,y1) is the bottom-right

    :param bbox: bounding box to check within
    :param extent_code: extent code of the area (another bounding box)
    :param return_mask: True/False default FalseO4Parser.ImageProvider
    :param mask_size: tuple of size of mask image in pixels. default (4096, 4096)
    :param is_sharp_resize: determined if the upsamplique of the extent mask is nearest (good when sharp transitions
                            are) or bicubic (good in all other cases)
    :param is_mask_layer: (assuming EPSG:4326) allows to "multiply" extent masks with water masks, this is a smooth
                          alternative for the old sea_texture_params.
    :return: False or True or (in the latter case) the mask image over the bbox and properly resized according
    """
    (x0, y0, x1, y1) = bbox
    try:
        # global layers need special treatment 
        if extent_code == 'global' and (not is_mask_layer or (x1 - x0) == 1):
            return (not return_mask) or Image.new('L', mask_size, 'white')

        if extent_code[0] == '!':
            extent_code = extent_code[1:]
            negative = True
        else:
            negative = False

        if extent_code != 'global':
            (xmin, ymin, xmax, ymax) = extents_dict[extent_code].mask_bounds
        else:
            (xmin, ymin, xmax, ymax) = (-180, -90, 180, 90)

        if x0 > xmax or x1 < xmin or y0 < ymin or y1 > ymax:
            return negative

        if (not is_mask_layer) or (x1 - x0) == 1:
            mask_im = Image.open(os.path.join(FNAMES.Extent_dir, extents_dict[extent_code].directory,
                                              extents_dict[extent_code].code + '.png')).convert('L')
            (sizex, sizey) = mask_im.size
            pxx0 = int((x0 - xmin) / (xmax - xmin) * sizex)
            pxx1 = int((x1 - xmin) / (xmax - xmin) * sizex)
            pxy0 = int((ymax - y0) / (ymax - ymin) * sizey)
            pxy1 = int((ymax - y1) / (ymax - ymin) * sizey)

            if not return_mask:
                pxx0 = max(-1, pxx0)
                pxx1 = min(sizex, pxx1)
                pxy0 = max(-1, pxy0)
                pxy1 = min(sizey, pxy1)

            mask_im = mask_im.crop((pxx0, pxy0, pxx1, pxy1))
            if negative:
                mask_im = ImageOps.invert(mask_im)
            if not mask_im.getbbox():
                return False
            if not return_mask:
                return True
            if is_sharp_resize:
                return mask_im.resize(mask_size)
            else:
                return mask_im.resize(mask_size, Image.BICUBIC)
        else:
            # following code only visited when is_mask_layer is True
            # in which case it is passed as (lat,lon,mask_zl)
            # check if sea mask file exists
            (lat, lon, mask_zl) = is_mask_layer
            (m_tile_x, m_tile_y) = GEO.wgs84_to_orthogrid((y0 + y1) / 2, (x0 + x1) / 2, mask_zl)
            if os.path.isdir(os.path.join(FNAMES.mask_dir(lat, lon), 'Combined_imagery')):
                check_dir = os.path.join(FNAMES.mask_dir(lat, lon), 'Combined_imagery')
            else:
                check_dir = FNAMES.mask_dir(lat, lon)
            if not os.path.isfile(os.path.join(check_dir, FNAMES.legacy_mask(m_tile_x, m_tile_y))):
                return False
            # build extent mask_im
            if extent_code != 'global':
                mask_im = Image.open(os.path.join(FNAMES.Extent_dir, extents_dict[extent_code].directory,
                                                  extents_dict[extent_code].code + '.png')).convert('L')
                (sizex, sizey) = mask_im.size
                pxx0 = int((x0 - xmin) / (xmax - xmin) * sizex)
                pxx1 = int((x1 - xmin) / (xmax - xmin) * sizex)
                pxy0 = int((ymax - y0) / (ymax - ymin) * sizey)
                pxy1 = int((ymax - y1) / (ymax - ymin) * sizey)
                mask_im = mask_im.crop((pxx0, pxy0, pxx1, pxy1))

                if negative:
                    mask_im = ImageOps.invert(mask_im)
                if not mask_im.getbbox():
                    return False
                if is_sharp_resize:
                    mask_im = mask_im.resize(mask_size)
                else:
                    mask_im = mask_im.resize(mask_size, Image.BICUBIC)
            else:
                mask_im = Image.new('L', mask_size, 'white')

            # build sea mask_im2
            (ymax, xmin) = GEO.gtile_to_wgs84(m_tile_x, m_tile_y, mask_zl)
            (ymin, xmax) = GEO.gtile_to_wgs84(m_tile_x + 16, m_tile_y + 16, mask_zl)
            mask_im2 = Image.open(os.path.join(check_dir, FNAMES.legacy_mask(m_tile_x, m_tile_y))).convert("L")
            (sizex, sizey) = mask_im2.size
            pxx0 = int((x0 - xmin) / (xmax - xmin) * sizex)
            pxx1 = int((x1 - xmin) / (xmax - xmin) * sizex)
            pxy0 = int((ymax - y0) / (ymax - ymin) * sizey)
            pxy1 = int((ymax - y1) / (ymax - ymin) * sizey)
            mask_im2 = mask_im2.crop((pxx0, pxy0, pxx1, pxy1)).resize(mask_size, Image.BICUBIC)

            # invert it
            mask_array2 = 255 - numpy.array(mask_im2, dtype=numpy.uint8)

            # let full sea down (if you wish to...)
            # mask_array2[mask_array2==255]=0
            #  combine (multiply) both
            mask_array = numpy.array(mask_im, dtype=numpy.uint16)
            mask_array = (mask_array * mask_array2 / 255).astype(numpy.uint8)
            mask_im = Image.fromarray(mask_array).convert('L')

            if not mask_im.getbbox():
                return False
            if not return_mask:
                return True
            return mask_im
    except Exception as e:
        UI.vprint(1, _('Could not test coverage of {extent_code}!!!').format(extent_code=extent_code))
        UI.vprint(2, e)
        return False


def http_request_to_image(url: str, request_headers: Union[dict, None], http_session: any) -> Tuple[bool, any]:
    UI.vprint(3, _('HTTP request issued : {url} \nRequest headers : {headers}').
              format(url=url, headers=request_headers))
    tentative_request = 0
    tentative_image = 0
    stopped_text = _('Stopped')

    r = False
    while True:
        try:
            if request_headers:
                r = http_session.get(url, timeout=http_timeout, headers=request_headers)
            else:
                r = http_session.get(url, timeout=http_timeout)
            status_code = str(r)

            # Bing white image with small camera or Arcgis no data yet => try to down-sample to lower ZL
            if 'Content-Length' in r.headers and int(r.headers['Content-Length']) <= 2521:
                if int(r.headers['Content-Length']) == 1033 and 'virtualearth' in url:
                    UI.vprint(3, url, r.headers)
                    return False, 404
                if int(r.headers['Content-Length']) == 2521 and 'arcgisonline' in url:
                    UI.vprint(3, url, r.headers)
                    return False, 404

            if r.status_code == 200 and 'image' in r.headers['Content-Type']:
                try:
                    small_image = Image.open(io.BytesIO(r.content))
                    return True, small_image
                except TypeError:
                    UI.vprint(2, _('Server said "OK", but the received image was corrupted.'))
                    UI.vprint(3, url, r.headers)
            elif r.status_code == 404:
                UI.vprint(2, _('Server said "Not Found"'))
                UI.vprint(3, url, r.headers)
                break
            elif r.status_code == 200:
                UI.vprint(2, _('Server said "OK" but sent us the wrong Content-Type.'))
                UI.vprint(3, url, r.headers, r.content)
                break
            elif r.status_code == 403:
                UI.vprint(2, _("Server said 'Forbidden' ! (IP banned?)"))
                UI.vprint(3, url, r.headers, r.content)
                break
            elif r.status_code >= 500:
                UI.vprint(2, _("Server said 'Internal Error'."), r.status_code)
                if not check_tms_response:
                    break 
                time.sleep(2)
            else:
                UI.vprint(2, _("Un-managed Server answer: {status}").format(status=status_code))
                UI.vprint(3, url, r.headers)
                break

            if UI.red_flag:
                return False, stopped_text

            tentative_image += 1

        except requests.exceptions.RequestException as e:
            UI.vprint(2, _('Server could not be connected, retrying in 2 secs'))
            UI.vprint(3, e)
            if not check_tms_response:
                break

            # trying a new session ?
            http_session = requests.Session()
            time.sleep(2)

            if UI.red_flag:
                return False, stopped_text

            tentative_request += 1

        if tentative_request == max_connect_retries or tentative_image == max_baddata_retries:
            break 

    return False, r.status_code


def get_wms_image(bbox: tuple,
                  width: int,
                  height: int,
                  provider: any,
                  http_session: any) -> Tuple[bool, any]:
    request_headers = None

    # If the provider has a _Custom_URL.py file associated with it, dynamically load it as a module.
    if provider.has_custom_url:
        module_path = os.path.join(FNAMES.Provider_dir, provider.directory, provider.custom_url_module + '.py')
        custom_url_module = importlib.machinery.SourceFileLoader(provider.custom_url_module, module_path).load_module()
        (url, request_headers) =\
            custom_url_module.custom_request(bbox=bbox, width=width, height=height)
    else:
        (minx, maxy, maxx, miny) = bbox

        if provider.wms_version.split('.')[1] == '3':
            bbox_string = ','.join([str(miny), str(minx), str(maxy), str(maxx)])
            _RS = 'CRS'
        else:
            bbox_string = ','.join([str(minx), str(miny), str(maxx), str(maxy)])
            _RS = 'SRS'

        url_template = 'SERVICE=WMS&VERSION={wms_ver}&FORMAT=image/{img_type}&REQUEST=GetMap&LAYERS={layers}' +\
                       '&STYLES=&{rs}=EPSG:{epsg_code}&WIDTH={width}&HEIGHT={height}&BBOX={bbox}'
        url = provider.url_prefix + url_template.\
            format(wms_ver=provider.wms_version,
                   img_type=provider.image_type,
                   layers=provider.layers,
                   rs=_RS,
                   epsg_code=provider.epsg_code,
                   width=width,
                   height=height,
                   bbox=bbox_string)

    if not request_headers:
        if provider.fake_headers:
            request_headers = provider.fake_headers
        else:
            request_headers = request_headers_generic

    (success, data) = http_request_to_image(url, request_headers, http_session)

    if success:
        return True, data
    else:
        return False, Image.new('RGB', (width, height), 'white')


def get_wmts_image(tilematrix,
                   til_x: int,
                   til_y: int,
                   provider: any,
                   http_session: any) -> Tuple[bool, any]:
    til_x_orig, til_y_orig = til_x, til_y
    down_sample = 0
    while True:
        request_headers = None
        # If the provider has a _Custom_URL.py file associated with it, dynamically load it as a module.
        if provider.has_custom_url:
            module_path = os.path.join(FNAMES.Provider_dir, provider.directory, provider.custom_url_module + '.py')
            custom_url_module =\
                importlib.machinery.SourceFileLoader(provider.custom_url_module, module_path).load_module()
            (url, request_headers) = \
                custom_url_module.custom_request(tilematrix=tilematrix, til_x=til_x, til_y=til_y)
        elif provider.request_type == 'tms':  # TMS
            url = provider.url_template.replace('{zoom}', str(tilematrix))
            url = url.replace('{x}', str(til_x))
            url = url.replace('{y}', str(til_y))
            url = url.replace('{|y|}', str(abs(til_y) - 1))
            url = url.replace('{-y}', str(2 ** tilematrix - 1 - til_y))
            url = url.replace('{quadkey}', GEO.gtile_to_quadkey(til_x, til_y, tilematrix))
            url = url.replace('{xcenter}', str((til_x + 0.5) * provider.resolutions[tilematrix] * provider.tile_size +
                                               provider.top_left_corner[tilematrix][0]))
            url = url.replace('{ycenter}', str(
                -1 * (til_y + 0.5) * provider.resolutions[tilematrix] * provider.tile_size +
                provider.top_left_corner[tilematrix][1]))
            url = url.replace('{size}', str(int(provider.resolutions[tilematrix] * provider.tile_size)))
            if '{switch:' in url:
                (url_0, tmp) = url.split('{switch:')
                (tmp, url_2) = tmp.split('}')
                server_list = tmp.split(',')
                url_1 = random.choice(server_list).strip()
                url = url_0 + url_1 + url_2
        elif provider.request_type == 'wmts':  # WMTS
            url_template = '&SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile&LAYER={layer}&STYLE=' +\
                           '&FORMAT=image/{image_type}&TILEMATRIXSET={tilematrixset_id}&TILEMATRIX={matrix_id}' +\
                           '&TILEROW={row}&TILECOL={col}'
            url = provider.url_prefix + url_template.\
                format(layer=provider.layers,
                       image_type=provider.image_type,
                       tilematrixset_id=provider.tilematrixset['identifier'],
                       matrix_id=provider.tilematrixset['tilematrices'][tilematrix]['identifier'],
                       row=til_y,
                       col=til_x)
        elif provider.request_type == 'local_tms':  # LOCAL TMS
            # ! Too much specific, needs to be changed by a x,y-> file_name lambda fct
            url_local = provider.url_template.replace('{x}', str(5 * til_x).zfill(4))
            url_local = url_local.replace('{y}', str(-5 * til_y).zfill(4))
            if os.path.isfile(url_local):
                return True, Image.open(url_local)
            else:
                UI.vprint(2, _('! File {url_local) absent, using white texture instead !').format(url_local=url_local))
                return False, Image.new('RGB', (provider.tile_size, provider.tile_size), 'white')
        if not request_headers:
            if provider.fake_headers:
                request_headers = provider.fake_headers
            else:
                request_headers = request_headers_generic
        width = height = provider.tile_size
        (success, data) = http_request_to_image(url, request_headers, http_session)
        if success and not down_sample:
            return success, data
        elif success and down_sample:
            x0 = (til_x_orig - 2 ** down_sample * til_x) * width // (2 ** down_sample)
            y0 = (til_y_orig - 2 ** down_sample * til_y) * height // (2 ** down_sample)
            x1 = x0 + width // (2 ** down_sample)
            y1 = y0 + height // (2 ** down_sample)
            return success, data.crop((x0, y0, x1, y1)).resize((width, height), Image.BICUBIC)
        elif '[404]' in data:
            if not provider.grid_type or provider.grid_type != 'webmercator':
                return False, Image.new('RGB', (width, height), 'white')
            til_x = til_x // 2
            til_y = til_y // 2
            tilematrix -= 1
            down_sample += 1
            if down_sample >= 6:
                return False, Image.new('RGB', (width, height), 'white')
        else:
            return False, Image.new('RGB', (width, height), 'white')


def get_and_paste_wms_part(bbox, width: int, height: int, provider, big_image, x0, y0, http_session) -> bool:
    (success, small_image) = get_wms_image(bbox, width, height, provider, http_session)
    big_image.paste(small_image, (x0, y0))
    return success


def get_and_paste_wmts_part(tilematrix, til_x: int, til_y: int, provider, big_image, x0, y0, http_session, subt_size=None) -> bool:
    (success, small_image) = get_wmts_image(tilematrix, til_x, til_y, provider, http_session)
    if not subt_size:
        big_image.paste(small_image, (x0, y0))
    else:
        big_image.paste(small_image.resize(subt_size, Image.BICUBIC), (x0, y0))
    return success


def build_texture_from_tilbox(tilbox,zoomlevel,provider,progress=None):
    # less general than the next build_texture_from_bbox_and_size but probably slightly quicker
    (til_x_min,til_y_min,til_x_max,til_y_max)=tilbox
    parts_x=til_x_max-til_x_min
    parts_y=til_y_max-til_y_min
    width=height=provider.tile_size
    big_image=Image.new('RGB',(width*parts_x,height*parts_y))
    # we set-up the queue of downloads
    http_session=requests.Session() 
    download_queue=queue.Queue()
    for monty in range(0,parts_y):
        for montx in range(0,parts_x):
            x0=montx*width
            y0=monty*height
            fargs=(zoomlevel,til_x_min+montx,til_y_min+monty,provider,big_image,x0,y0,http_session)
            download_queue.put(fargs)
    # and finally activate them
    success=parallel_execute(get_and_paste_wmts_part,download_queue,provider.max_threads,progress)
    # once out big_image has been filled and we return it
    return (success,big_image)
###############################################################################################################################

###############################################################################################################################
def build_texture_from_bbox_and_size(t_bbox,t_epsg,t_size,provider):
    # warp will be needed for projections not parallel to 3857 or too large image_size
    # if warp is not needed, crop could still be needed if the grids do not match
    warp_needed=crop_needed=False
    (ulx,uly,lrx,lry)=t_bbox
    (t_sizex,t_sizey)=t_size
    if provider.epsg_code==3857:
        s_ulx,s_uly,s_lrx,s_lry=ulx,uly,lrx,lry
    else:
        (s_ulx,s_uly)=GEO.transform(t_epsg,provider.epsg_code,ulx,uly)
        (s_urx,s_ury)=GEO.transform(t_epsg,provider.epsg_code,lrx,uly)
        (s_llx,s_lly)=GEO.transform(t_epsg,provider.epsg_code,ulx,lry)
        (s_lrx,s_lry)=GEO.transform(t_epsg,provider.epsg_code,lrx,lry)
        (g_ulx,g_uly)=GEO.transform(t_epsg,'4326',ulx,uly)
        (g_lrx,g_lry)=GEO.transform(t_epsg,'4326',lrx,lry)
        if s_ulx!=s_llx or s_uly!=s_ury or s_lrx!=s_urx or s_lly!=s_lry or (g_uly-g_lry)>0.08:
            s_ulx=min(s_ulx,s_llx)
            s_uly=max(s_uly,s_ury)
            s_lrx=max(s_urx,s_lrx)
            s_lry=min(s_lly,s_lry)
            warp_needed=True
    x_range=s_lrx-s_ulx
    y_range=s_uly-s_lry
    if provider.request_type=='wms':
        wms_size=int(provider.wms_size)
        parts_x=int(ceil(t_sizex/wms_size))
        width=wms_size
        parts_y=int(ceil(t_sizey/wms_size))
        height=wms_size
    elif provider.request_type in ('wmts','tms','local_tms'):
        asked_resol=max(x_range/t_sizex,y_range/t_sizey)
        wmts_tilematrix=numpy.argmax(provider.resolutions<=asked_resol*1.1)
        wmts_resol=provider.resolutions[wmts_tilematrix]   # in s_epsg unit per pix !
        UI.vprint(3,"Asked resol:",asked_resol,"WMTS resol:",wmts_resol)
        width=height=provider.tile_size
        cell_size=wmts_resol*width
        [wmts_x0,wmts_y0]=provider.top_left_corner[wmts_tilematrix]
        til_x_min=int((s_ulx-wmts_x0)//cell_size)
        til_x_max=int((s_lrx-wmts_x0)//cell_size)
        til_y_min=int((wmts_y0-s_uly)//cell_size)
        til_y_max=int((wmts_y0-s_lry)//cell_size)
        parts_x=til_x_max-til_x_min+1
        parts_y=til_y_max-til_y_min+1
        s_box_ulx=wmts_x0+cell_size*til_x_min
        s_box_uly=wmts_y0-cell_size*til_y_min
        s_box_lrx=wmts_x0+cell_size*(til_x_max+1)
        s_box_lry=wmts_y0-cell_size*(til_y_max+1)
        if s_box_ulx!=s_ulx or s_box_uly!=s_uly or s_box_lrx!=s_lrx or s_box_lry!=s_lry:
            crop_x0=int(round((s_ulx-s_box_ulx)/wmts_resol))
            crop_y0=int(round((s_box_uly-s_uly)/wmts_resol))
            crop_x1=int(round((s_lrx-s_box_ulx)/wmts_resol))
            crop_y1=int(round((s_box_uly-s_lry)/wmts_resol))
            s_ulx=s_box_ulx    
            s_uly=s_box_uly    
            s_lrx=s_box_lrx
            s_lry=s_box_lry
            crop_needed=True
        downscale=int(min(log(width*parts_x/t_sizex),log(height/t_sizey))/log(2))-1
        if downscale>=1:
            width/=2**downscale
            height/=2**downscale
            subt_size=(width,height) 
        else:
            subt_size=None
    big_image=Image.new('RGB',(width*parts_x,height*parts_y)) 
    http_session=requests.Session()
    download_queue=queue.Queue()
    for monty in range(0,parts_y):
        for montx in range(0,parts_x):
            x0=montx*width
            y0=monty*height
            if provider.request_type=='wms':
                p_ulx=s_ulx+montx*x_range/parts_x
                p_uly=s_uly-monty*y_range/parts_y
                p_lrx=p_ulx+x_range/parts_x
                p_lry=p_uly-y_range/parts_y
                p_bbox=[p_ulx,p_uly,p_lrx,p_lry]
                fargs=[p_bbox[:],width,height,provider,big_image,x0,y0,http_session]
            elif provider.request_type in ['wmts','tms','local_tms']:
                fargs=[wmts_tilematrix,til_x_min+montx,til_y_min+monty,provider,big_image,x0,y0,http_session,subt_size]
            download_queue.put(fargs)

    # We execute the downloads and sub-image pastes
    if provider.request_type=='wms':
        success=parallel_execute(get_and_paste_wms_part,download_queue,provider.max_threads)
    elif provider.request_type in ['wmts','tms','local_tms']:
        success=parallel_execute(get_and_paste_wmts_part,download_queue,provider.max_threads)

    # We modify big_image if necessary
    if warp_needed:
        UI.vprint(3,"Warp needed")
        big_image=gdalwarp_alternative((s_ulx,s_uly,s_lrx,s_lry),provider.epsg_code,big_image,t_bbox,t_epsg,t_size)
    elif crop_needed:
        UI.vprint(3,"Crop needed")
        big_image=big_image.crop((crop_x0,crop_y0,crop_x1,crop_y1))
    if big_image.size!=t_size:
        UI.vprint(3,"Resize needed:"+str(t_size[0]/big_image.size[0])+" "+str(t_size[1]/big_image.size[1]))
        big_image=big_image.resize(t_size,Image.BICUBIC)
    return (success,big_image)


def download_jpeg_ortho(file_dir,file_name,til_x_left,til_y_top,zoomlevel,provider_code,super_resol_factor=1):
    provider = providers_dict[provider_code]

    # This isn't actually used in any current provider, only commented out in one.
    if hasattr(provider, 'super_resol_factor') and provider.super_resol_factor == 1:
        super_resol_factor = provider.super_resol_factor

    if provider.max_zl:
        if zoomlevel > provider.max_zl:
            super_resol_factor = 2 ** (provider.max_zl - zoomlevel)

    width = height = int(4096 * super_resol_factor)

    # we treat first the case of webmercator grid type servers
    if provider.grid_type and provider.grid_type == 'webmercator':
        tile_box = [til_x_left, til_y_top, til_x_left + 16, til_y_top + 16]
        tile_box_mod = [int(round(p * super_resol_factor)) for p in tile_box]
        zoom_shift = round(log(super_resol_factor) / log(2))
        (success, big_image) = build_texture_from_tilbox(tile_box_mod, zoomlevel + zoom_shift, provider)
    else:  # if not we are in the world of epsg:3857 bboxes
        [latmax,lonmin]=GEO.gtile_to_wgs84(til_x_left,til_y_top,zoomlevel)
        [latmin,lonmax]=GEO.gtile_to_wgs84(til_x_left+16,til_y_top+16,zoomlevel)
        [xmin,ymax]=GEO.transform('4326','3857',lonmin,latmax)
        [xmax,ymin]=GEO.transform('4326','3857',lonmax,latmin)
        (success,big_image)=build_texture_from_bbox_and_size([xmin,ymax,xmax,ymin],'3857',(width,height),provider)
    # if stop flag we do not wish to imprint a white texture
    if UI.red_flag: return 0
    if not success:
        UI.lvprint(1,"Part of image",file_name,"could not be obtained (even at lower ZL), it was filled with white there.")  
    if not os.path.exists(file_dir):
        os.makedirs(file_dir)
    try:
        if super_resol_factor==1:
            big_image.save(os.path.join(file_dir,file_name))
        else:
            big_image.resize((int(width/super_resol_factor),int(height/super_resol_factor)),Image.BICUBIC).save(os.path.join(file_dir,file_name))
    except Exception as e:
        UI.lvprint(0,"OS Error : could not save orthophoto on disk, received message :",e)
        return 0
    return 1
###############################################################################################################################

###############################################################################################################################
def build_jpeg_ortho(tile, til_x_left,til_y_top,zoomlevel,provider_code,out_file_name=''):
    texture_attributes=(til_x_left,til_y_top,zoomlevel,provider_code)
    if provider_code in local_combined_providers_dict:
        data_found=False
        for rlayer in local_combined_providers_dict[provider_code]:
            (y0,x0)=GEO.gtile_to_wgs84(til_x_left,til_y_top,zoomlevel)
            (y1,x1)=GEO.gtile_to_wgs84(til_x_left+16,til_y_top+16,zoomlevel)
            if len(local_combined_providers_dict[provider_code])==1 or has_data((x0,y0,x1,y1),rlayer.extent_code,is_mask_layer= (tile.lat,tile.lon, tile.mask_zl) if rlayer.priority=='mask' else False):
                data_found=True
                true_til_x_left=til_x_left
                true_til_y_top=til_y_top
                true_zl=zoomlevel
                max_zl=int(providers_dict[rlayer.layer_code].max_zl)
                if max_zl<zoomlevel:
                    (latmed,lonmed)=GEO.gtile_to_wgs84(til_x_left+8,til_y_top+8,zoomlevel)
                    (true_til_x_left,true_til_y_top)=GEO.wgs84_to_orthogrid(latmed,lonmed,max_zl)
                    true_zl=max_zl
                true_texture_attributes=(true_til_x_left,true_til_y_top,true_zl,rlayer.layer_code)
                true_file_name=FNAMES.jpeg_file_name_from_attributes(true_til_x_left, true_til_y_top, true_zl,rlayer.layer_code)
                true_file_dir=FNAMES.jpeg_file_dir_from_attributes(tile.lat, tile.lon,true_zl,providers_dict[rlayer.layer_code])
                if not os.path.isfile(os.path.join(true_file_dir,true_file_name)):
                    UI.vprint(1,"   Downloading missing orthophoto "+true_file_name+" (for combining in "+provider_code+")")
                    if not download_jpeg_ortho(true_file_dir,true_file_name,*true_texture_attributes):
                        return 0
                else:
                    UI.vprint(1,"   The orthophoto "+true_file_name+" (for combining in "+provider_code+") is already present.")
        if not data_found: 
            UI.lvprint(1,"     -> !!! Warning : No data found for building the combined texture",\
                    FNAMES.dds_file_name_from_attributes(*texture_attributes)," !!!")
            return 0
        if out_file_name:
            big_img=combine_textures(tile,til_x_left,til_y_top,zoomlevel,provider_code)
            big_img.convert('RGB').save(out_file_name)
        elif provider_code in providers_dict:  # In case one would like to save combined orthos as jpegs (this can be useful to use different masks parameters for imagery masks layers and actual masks
            file_name=FNAMES.jpeg_file_name_from_attributes(til_x_left, til_y_top, zoomlevel,provider_code)
            file_dir=FNAMES.jpeg_file_dir_from_attributes(tile.lat, tile.lon,zoomlevel,providers_dict[provider_code])
            big_img=combine_textures(tile,til_x_left,til_y_top,zoomlevel,provider_code)
            if not os.path.exists(file_dir):
                os.makedirs(file_dir)
            try:
                big_img.convert('RGB').save(os.path.join(file_dir,file_name))
            except Exception as e:
                UI.lvprint(0,"OS Error : could not save orthophoto on disk, received message :",e)
                return 0
    elif provider_code in providers_dict:  
        file_name=FNAMES.jpeg_file_name_from_attributes(til_x_left, til_y_top, zoomlevel,provider_code)
        file_dir=FNAMES.jpeg_file_dir_from_attributes(tile.lat, tile.lon,zoomlevel,providers_dict[provider_code])
        if not os.path.isfile(os.path.join(file_dir,file_name)):
            UI.vprint(1,"   Downloading missing orthophoto "+file_name)
            if not download_jpeg_ortho(file_dir,file_name,*texture_attributes):
                return 0
        else:
            UI.vprint(1,"   The orthophoto "+file_name+" is already present.")
    else:
        (tlat,tlon)=GEO.gtile_to_wgs84(til_x_left+8,til_y_top+8,zoomlevel)
        UI.vprint(1,"   Unknown provider",provider_code,"or it has no data around",tlat,tlon,".")
        return 0
    return 1
###############################################################################################################################

###############################################################################################################################
# Not used in Ortho4XP itself but useful for testing combined color filters at low zl
###############################################################################################################################
def build_combined_ortho(tile, latp,lonp,zoomlevel,provider_code,mask_zl,filename='test.png'):
    initialize_color_filters_dict()
    initialize_extents_dict()
    initialize_providers_dict()
    initialize_combined_providers_dict()
    (til_x_left,til_y_top)=GEO.wgs84_to_orthogrid(latp,lonp,zoomlevel)
    big_image=Image.new('RGBA',(4096,4096))
    (y0,x0)=GEO.gtile_to_wgs84(til_x_left,til_y_top,zoomlevel)
    (y1,x1)=GEO.gtile_to_wgs84(til_x_left+16,til_y_top+16,zoomlevel)
    mask_weight_below=numpy.zeros((4096,4096),dtype=numpy.uint16)
    for rlayer in combined_providers_dict[provider_code][::-1]:
        mask=has_data((x0,y0,x1,y1),rlayer.extent_code,return_mask=True,is_mask_layer=(tile.lat,tile.lon, tile.mask_zl) if rlayer.priority=='mask' else False)
        if not mask: continue
        # we turn the image mask into an array 
        mask=numpy.array(mask,dtype=numpy.uint16)
        true_til_x_left=til_x_left
        true_til_y_top=til_y_top
        true_zl=zoomlevel
        crop=False
        max_zl=int(providers_dict[rlayer.layer_code].max_zl)
        if max_zl<zoomlevel:
            (latmed,lonmed)=GEO.gtile_to_wgs84(til_x_left+8,til_y_top+8,zoomlevel)
            (true_til_x_left,true_til_y_top)=GEO.wgs84_to_orthogrid(latmed,lonmed,max_zl)
            true_zl=max_zl
            crop=True
            pixx0=round(256*(til_x_left*2**(max_zl-zoomlevel)-true_til_x_left))
            pixy0=round(256*(til_y_top*2**(max_zl-zoomlevel)-true_til_y_top))
            pixx1=round(pixx0+2**(12-zoomlevel+max_zl))
            pixy1=round(pixy0+2**(12-zoomlevel+max_zl))
        true_file_name=FNAMES.jpeg_file_name_from_attributes(true_til_x_left, true_til_y_top, true_zl,rlayer.layer_code)
        true_file_dir=FNAMES.jpeg_file_dir_from_attributes(tile.lat, tile.lon, true_zl,providers_dict[rlayer.layer_code])
        if not os.path.isfile(os.path.join(true_file_dir,true_file_name)):
            UI.vprint(1,"   Downloading missing orthophoto "+true_file_name+" (for combining in "+provider_code+")\n")
            download_jpeg_ortho(true_file_dir,true_file_name,true_til_x_left, true_til_y_top, true_zl,rlayer.layer_code)
        else:
            UI.vprint(1,"   The orthophoto "+true_file_name+" (for combining in "+provider_code+") is already present.\n")
        true_im=Image.open(os.path.join(true_file_dir,true_file_name))
        UI.vprint(2,"Imprinting for provider",rlayer,til_x_left,til_y_top) 
        true_im=color_transform(true_im,rlayer.color_code)
        if rlayer.priority=='mask' and tile.sea_texture_blur:
            UI.vprint(2,"Blur of a mask !")
            true_im=true_im.filter(ImageFilter.GaussianBlur(tile.sea_texture_blur*2**(true_zl-17)))
        if crop: 
            true_im=true_im.crop((pixx0,pixy0,pixx1,pixy1)).resize((4096,4096),Image.BICUBIC)
        # in case the smoothing of the extent mask was too strong we remove the
        # the mask (where it is nor 0 nor 255) the pixels for which the true_im
        # is all white
        # true_arr=numpy.array(true_im).astype(numpy.uint16)
        # mask[(numpy.sum(true_arr,axis=2)>=715)*(mask>=1)*(mask<=253)]=0
        # mask[(numpy.sum(true_arr,axis=2)<=15)*(mask>=1)*(mask<=253)]=0
        if rlayer.priority=='low':
            # low priority layers, do not increase mask_weight_below
            wasnt_zero=(mask_weight_below+mask)!=0
            mask[wasnt_zero]=255*mask[wasnt_zero]/(mask_weight_below+mask)[wasnt_zero]
        elif rlayer.priority in ['high','mask']:
            mask_weight_below+=mask
        elif rlayer.priority=='medium':
            not_zero=mask!=0
            mask_weight_below+=mask
            mask[not_zero]=255*mask[not_zero]/mask_weight_below[not_zero]
            # undecided about the next two lines
            # was_zero=mask_weight_below==0
            # mask[was_zero]=255 
        # we turn back the array mask into an image
        mask=Image.fromarray(mask.astype(numpy.uint8))
        big_image=Image.composite(true_im,big_image,mask)
    UI.vprint(2,"Finished imprinting",til_x_left,til_y_top)
    big_image.save(filename)
###############################################################################################################################

###############################################################################################################################
def build_geotiffs(tile,texture_attributes_list):
    UI.red_flag=False
    timer=time.time()
    initialize_color_filters_dict()
    initialize_providers_dict()   
    initialize_combined_providers_dict()   
    done=0
    todo=len(texture_attributes_list)
    for texture_attributes in texture_attributes_list:
        (til_x_left,til_y_top,zoomlevel,provider_code)=texture_attributes
        if build_jpeg_ortho(tile,til_x_left,til_y_top,zoomlevel,provider_code):
            convert_texture(tile,til_x_left,til_y_top,zoomlevel,provider_code,type='tif')
        done+=1
        UI.progress_bar(1,int(100*done/todo))
        if UI.red_flag: UI.exit_message_and_bottom_line() 
    UI.timings_and_bottom_line(timer)
    return
###############################################################################################################################

###############################################################################################################################
def build_texture_region(dest_dir,latmin,latmax,lonmin,lonmax,zoomlevel,provider_code):
    [til_xmin,til_ymin]=GEO.wgs84_to_orthogrid(latmax,lonmin,zoomlevel)
    [til_xmax,til_ymax]=GEO.wgs84_to_orthogrid(latmin,lonmax,zoomlevel)
    nbr_to_do=((til_ymax-til_ymin)/16+1)*((til_xmax-til_xmin)/16+1)
    print("Number of tiles to download at most : ",nbr_to_do)
    for til_y_top in range(til_ymin,til_ymax+1,16):
        for til_x_left in range(til_xmin,til_xmax+1,16):
            (y0,x0)=GEO.gtile_to_wgs84(til_x_left,til_y_top,zoomlevel)
            (y1,x1)=GEO.gtile_to_wgs84(til_x_left+16,til_y_top+16,zoomlevel)
            bbox_4326=(x0,y0,x1,y1)
            if has_data(bbox_4326,providers_dict[provider_code].extent,return_mask=False,mask_size=(4096,4096)):
                file_name=FNAMES.jpeg_file_name_from_attributes(til_x_left,til_y_top,zoomlevel,provider_code)
                if os.path.isfile(os.path.join(dest_dir,file_name)):
                    print("recycling one")
                    nbr_to_do-=1
                    continue 
                print("building one")
                download_jpeg_ortho(dest_dir,file_name,til_x_left,til_y_top,zoomlevel,provider_code,super_resol_factor=1)
            else:
                print("skipping one")
            nbr_to_do-=1
            print(nbr_to_do)
    return   
###############################################################################################################################

###############################################################################################################################
def build_provider_texture(dest_dir,provider_code,zoomlevel):
    (lonmin,latmin,lonmax,latmax)=extents_dict[providers_dict[provider_code].extent].mask_bounds
    build_texture_region(dest_dir,latmin,latmax,lonmin,lonmax,zoomlevel,provider_code)
    return   
###############################################################################################################################

###############################################################################################################################
def create_tile_preview(lat,lon,zoomlevel,provider_code):
    UI.red_flag=False
    if not os.path.exists(FNAMES.Preview_dir):
        os.makedirs(FNAMES.Preview_dir) 
    filepreview=FNAMES.preview(lat, lon, zoomlevel, provider_code)     
    if not os.path.isfile(filepreview):
        provider=providers_dict[provider_code]
        (til_x_min,til_y_min)=GEO.wgs84_to_gtile(lat+1,lon,zoomlevel)
        (til_x_max,til_y_max)=GEO.wgs84_to_gtile(lat,lon+1,zoomlevel)
        width=(til_x_max+1-til_x_min)*256
        height=(til_y_max+1-til_y_min)*256
        if provider.grid_type=='webmercator':
            tilbox=(til_x_min,til_y_min,til_x_max+1,til_y_max+1)
            dico_progress={'done':0,'bar':1}
            (success,big_image)=build_texture_from_tilbox(tilbox,zoomlevel,provider,progress=dico_progress)
        # if not we are in the world of epsg:3857 bboxes
        else:
            (latmax,lonmin)=GEO.gtile_to_wgs84(til_x_min,til_y_min,zoomlevel)
            (latmin,lonmax)=GEO.gtile_to_wgs84(til_x_max+1,til_y_max+1,zoomlevel)
            (xmin,ymax)=GEO.transform('4326','3857',lonmin,latmax)
            (xmax,ymin)=GEO.transform('4326','3857',lonmax,latmin)
            (success,big_image)=build_texture_from_bbox_and_size((xmin,ymax,xmax,ymin),'3857',(width,height),provider)
        if success: 
            big_image.save(filepreview)
            return 1
        else:
            try: big_image.save(filepreview)
            except: pass
            return 0
    return 1
###############################################################################################################################


###############################################################################################################################
#
#  PART II : Methods to transform textures (warp, color transform, combine)
#
###############################################################################################################################

###############################################################################################################################
def gdalwarp_alternative(s_bbox,s_epsg,s_im,t_bbox,t_epsg,t_size):
        [s_ulx,s_uly,s_lrx,s_lry]=s_bbox
        [t_ulx,t_uly,t_lrx,t_lry]=t_bbox
        (s_w,s_h)=s_im.size
        (t_w,t_h)=t_size
        t_quad = (0, 0, t_w, t_h)
        meshes = []
        def cut_quad_into_grid(quad, steps):
            w = quad[2]-quad[0]
            h = quad[3]-quad[1]
            x_step = w / float(steps)
            y_step = h / float(steps)
            y = quad[1]
            for k in range(steps):
                x = quad[0]
                for l in range(steps):
                    yield (int(x), int(y), int(x+x_step), int(y+y_step))
                    x += x_step
                y += y_step
        for quad in cut_quad_into_grid(t_quad,8):
            s_quad=[]
            for (t_pixx,t_pixy) in [(quad[0],quad[1]),(quad[0],quad[3]),(quad[2],quad[3]),(quad[2],quad[1])]:
                t_x=t_ulx+t_pixx/t_w*(t_lrx-t_ulx)
                t_y=t_uly-t_pixy/t_h*(t_uly-t_lry)
                (s_x,s_y)=GEO.transform(t_epsg,s_epsg,t_x,t_y)
                s_pixx=int(round((s_x-s_ulx)/(s_lrx-s_ulx)*s_w))    
                s_pixy=int(round((s_uly-s_y)/(s_uly-s_lry)*s_h))
                s_quad.extend((s_pixx,s_pixy))
            meshes.append((quad,s_quad))    
        return s_im.transform(t_size,Image.MESH,meshes,Image.BICUBIC)
###############################################################################################################################

###############################################################################################################################
def color_transform(im,color_code):
    try:
        for color_filter in color_filters_dict[color_code]:
            if color_filter.filters[0]=='brightness-contrast': #both range from -127 to 127, http://gimp.sourcearchive.com/documentation/2.6.1/gimpbrightnesscontrastconfig_8c-source.html
                (brightness,contrast)=color_filter.filters[1:3]
                if brightness>=0:  
                    im=im.point(lambda i: 128+tan(pi/4*(1+contrast/128))*(brightness+(255-brightness)/255*i-128))
                else:
                    im=im.point(lambda i: 128+tan(pi/4*(1+contrast/128))*((255+brightness)/255*i-128))
            elif color_filter.filters[0]=='saturation':
                saturation=color_filter.filters[1]
                im=ImageEnhance.Color(im).enhance(1+saturation/100)
            elif color_filter.filters[0]=='sharpness':
                im=ImageEnhance.Sharpness(im).enhance(color_filter.filters[1])
            elif color_filter.filters[0]=='blur':
                im=im.filter(ImageFilter.GaussianBlur(color_filter.filters[1]))
            elif color_filter.filters[0]=='levels': # levels range between 0 and 255, gamma is neutral at 1 / https://pippin.gimp.org/image-processing/chap_point.html
                bands=im.split()
                for j in [0,1,2]:
                    in_min,gamma,in_max,out_min,out_max=color_filter.filters[5*j+1:5*j+6]
                    bands[j].paste(bands[j].point(lambda i: out_min+(out_max-out_min)*((max(in_min,min(i,in_max))-in_min)/(in_max-in_min))**(1/gamma)))
                im=Image.merge(im.mode,bands)
        return im
    except:
        return im
###############################################################################################################################

###############################################################################################################################
def combine_textures(tile,til_x_left,til_y_top,zoomlevel,provider_code):
    big_image=Image.new('RGBA',(4096,4096))
    (y0,x0)=GEO.gtile_to_wgs84(til_x_left,til_y_top,zoomlevel)
    (y1,x1)=GEO.gtile_to_wgs84(til_x_left+16,til_y_top+16,zoomlevel)
    mask_weight_below=numpy.zeros((4096,4096),dtype=numpy.uint16)
    if len(local_combined_providers_dict[provider_code])==1: # we do not need to bother with masks then 
        rlayer=local_combined_providers_dict[provider_code][0]
        true_til_x_left=til_x_left
        true_til_y_top=til_y_top
        true_zl=zoomlevel
        crop=False
        max_zl=int(providers_dict[rlayer.layer_code].max_zl)
        if max_zl<zoomlevel:
            (latmed,lonmed)=GEO.gtile_to_wgs84(til_x_left+8,til_y_top+8,zoomlevel)
            (true_til_x_left,true_til_y_top)=GEO.wgs84_to_orthogrid(latmed,lonmed,max_zl)
            true_zl=max_zl
            crop=True
            pixx0=round(256*(til_x_left*2**(max_zl-zoomlevel)-true_til_x_left))
            pixy0=round(256*(til_y_top*2**(max_zl-zoomlevel)-true_til_y_top))
            pixx1=round(pixx0+2**(12-zoomlevel+max_zl))
            pixy1=round(pixy0+2**(12-zoomlevel+max_zl))
        true_file_name=FNAMES.jpeg_file_name_from_attributes(true_til_x_left, true_til_y_top, true_zl,rlayer.layer_code)
        true_file_dir=FNAMES.jpeg_file_dir_from_attributes(tile.lat, tile.lon, true_zl,providers_dict[rlayer.layer_code])
        true_im=Image.open(os.path.join(true_file_dir,true_file_name))
        UI.vprint(2,"Imprinting for provider",rlayer,til_x_left,til_y_top) 
        true_im=color_transform(true_im,rlayer.color_code)
        if rlayer.priority=='mask' and tile.sea_texture_blur:
            UI.vprint(2,"Blur of a mask !")
            true_im=true_im.filter(ImageFilter.GaussianBlur(tile.sea_texture_blur*2**(true_zl-17)))
        if crop: 
            true_im=true_im.crop((pixx0,pixy0,pixx1,pixy1)).resize((4096,4096),Image.BICUBIC)
        UI.vprint(2,"Finished imprinting",til_x_left,til_y_top)
        return true_im
    # the real situation now where there are more than one layer with data
    for rlayer in local_combined_providers_dict[provider_code][::-1]:
        mask=has_data((x0,y0,x1,y1),rlayer.extent_code,return_mask=True,is_mask_layer=(tile.lat,tile.lon, tile.mask_zl) if rlayer.priority=='mask' else False)
        if not mask: continue
        # we turn the image mask into an array 
        mask=numpy.array(mask,dtype=numpy.uint16)
        true_til_x_left=til_x_left
        true_til_y_top=til_y_top
        true_zl=zoomlevel
        crop=False
        max_zl=int(providers_dict[rlayer.layer_code].max_zl)
        if max_zl<zoomlevel:
            (latmed,lonmed)=GEO.gtile_to_wgs84(til_x_left+8,til_y_top+8,zoomlevel)
            (true_til_x_left,true_til_y_top)=GEO.wgs84_to_orthogrid(latmed,lonmed,max_zl)
            true_zl=max_zl
            crop=True
            pixx0=round(256*(til_x_left*2**(max_zl-zoomlevel)-true_til_x_left))
            pixy0=round(256*(til_y_top*2**(max_zl-zoomlevel)-true_til_y_top))
            pixx1=round(pixx0+2**(12-zoomlevel+max_zl))
            pixy1=round(pixy0+2**(12-zoomlevel+max_zl))
        true_file_name=FNAMES.jpeg_file_name_from_attributes(true_til_x_left, true_til_y_top, true_zl,rlayer.layer_code)
        true_file_dir=FNAMES.jpeg_file_dir_from_attributes(tile.lat, tile.lon, true_zl,providers_dict[rlayer.layer_code])
        true_im=Image.open(os.path.join(true_file_dir,true_file_name))
        UI.vprint(2,"Imprinting for provider",rlayer,til_x_left,til_y_top) 
        true_im=color_transform(true_im,rlayer.color_code)
        if rlayer.priority=='mask' and tile.sea_texture_blur:
            UI.vprint(2,"Blur of a mask !")
            true_im=true_im.filter(ImageFilter.GaussianBlur(tile.sea_texture_blur*2**(true_zl-17)))
        if crop: 
            true_im=true_im.crop((pixx0,pixy0,pixx1,pixy1)).resize((4096,4096),Image.BICUBIC)
        # in case the smoothing of the extent mask was too strong we remove the
        # the mask (where it is nor 0 nor 255) the pixels for which the true_im
        # is all white or all black
        true_arr=numpy.array(true_im).astype(numpy.uint16)
        mask[(numpy.sum(true_arr,axis=2)>=735)*(mask>=1)*(mask<=253)]=0
        mask[(numpy.sum(true_arr,axis=2)<=35)*(mask>=1)*(mask<=253)]=0
        if rlayer.priority=='low':
            # low priority layers, do not increase mask_weight_below
            wasnt_zero=(mask_weight_below+mask)!=0
            mask[wasnt_zero]=255*mask[wasnt_zero]/(mask_weight_below+mask)[wasnt_zero]
        elif rlayer.priority in ['high','mask']:
            mask_weight_below+=mask
        elif rlayer.priority=='medium':
            not_zero=mask!=0
            mask_weight_below+=mask
            mask[not_zero]=255*mask[not_zero]/mask_weight_below[not_zero]
            # undecided about the next two lines
            # was_zero=mask_weight_below==0
            # mask[was_zero]=255 
        # we turn back the array mask into an image
        mask=Image.fromarray(mask.astype(numpy.uint8))
        big_image=Image.composite(true_im,big_image,mask)
    UI.vprint(2,"Finished imprinting",til_x_left,til_y_top)
    return big_image
###############################################################################################################################

###############################################################################################################################
def convert_texture(tile,til_x_left,til_y_top,zoomlevel,provider_code,type='dds'):
    if type=='dds':
        out_file_name=FNAMES.dds_file_name_from_attributes(til_x_left,til_y_top,zoomlevel,provider_code)
        png_file_name=out_file_name.replace('dds','png')
    elif type=='tif':
        out_file_name=FNAMES.geotiff_file_name_from_attributes(til_x_left,til_y_top,zoomlevel,provider_code)
        if os.path.exists(os.path.join(FNAMES.Geotiff_dir,out_file_name)):
            try: os.remove(os.path.join(FNAMES.Geotiff_dir,out_file_name))
            except: pass
        png_file_name=out_file_name.replace('tif','png')
        tmp_tif_file_name = os.path.join(UI.Ortho4XP_dir,'tmp',out_file_name.replace('4326','3857'))
    UI.vprint(1,"   Converting orthophoto(s) to build texture "+out_file_name+".")
    erase_tmp_png=False
    erase_tmp_tif=False
    dxt5=False
    masked_texture=False
    if tile.imprint_masks_to_dds and type=='dds':
        masked_texture=os.path.exists(os.path.join(tile.build_dir,"textures",FNAMES.mask_file(til_x_left,til_y_top,zoomlevel,provider_code)))
        if masked_texture:
            mask_im=Image.open(os.path.join(tile.build_dir,"textures",FNAMES.mask_file(til_x_left,til_y_top,zoomlevel,provider_code))).convert('L')
    elif tile.imprint_masks_to_dds: # type = 'tif'
        if int(zoomlevel)>=tile.mask_zl:
            factor=2**(zoomlevel-tile.mask_zl)
            m_til_x=(int(til_x_left/factor)//16)*16
            m_til_y=(int(til_y_top/factor)//16)*16
            rx=int((til_x_left-factor*m_til_x)/16)
            ry=int((til_y_top-factor*m_til_y)/16)
            mask_file=os.path.join(FNAMES.mask_dir(tile.lat,tile.lon),FNAMES.legacy_mask(m_til_x,m_til_y))
            if os.path.isfile(mask_file): 
                big_img=Image.open(mask_file)
                x0=int(rx*4096/factor)
                y0=int(ry*4096/factor)
                mask_im=big_img.crop((x0,y0,x0+4096//factor,y0+4096//factor))
                small_array=numpy.array(mask_im,dtype=numpy.uint8)
                if small_array.max()>30: 
                    masked_texture=True
    if provider_code in providers_dict:
        jpeg_file_name=FNAMES.jpeg_file_name_from_attributes(til_x_left,til_y_top,zoomlevel,provider_code)
        file_dir=FNAMES.jpeg_file_dir_from_attributes(tile.lat, tile.lon, zoomlevel, providers_dict[provider_code])
    if (provider_code in local_combined_providers_dict) and ((provider_code not in providers_dict) or not os.path.exists(os.path.join(file_dir,jpeg_file_name))):
        big_image=combine_textures(tile,til_x_left,til_y_top,zoomlevel,provider_code)
        if masked_texture:
            UI.vprint(2,"      Applying alpha mask directly to orthophoto.")
            big_image.putalpha(mask_im.resize((4096,4096),Image.BICUBIC))
            if type=='dds':
                try: os.remove(os.path.join(tile.build_dir,"textures",FNAMES.mask_file(til_x_left,til_y_top,zoomlevel,provider_code))) 
                except: pass
            dxt5=True
        file_to_convert=os.path.join(UI.Ortho4XP_dir,'tmp',png_file_name)
        erase_tmp_png=True
        big_image.save(file_to_convert)
        # If one wanted to distribute jpegs instead of dds, uncomment the next line
        # big_image.convert('RGB').save(os.path.join(tile.build_dir,'textures',out_file_name.replace('dds','jpg')),quality=70)
    # now if provider_code was not in local_combined_providers_dict but color correction is required
    elif providers_dict[provider_code].color_filters!='none' or masked_texture:
        big_image=Image.open(os.path.join(file_dir,jpeg_file_name),'r').convert('RGB')
        if providers_dict[provider_code].color_filters!='none':
            big_image=color_transform(big_image,providers_dict[provider_code].color_filters)
        if masked_texture:
            UI.vprint(2,"      Applying alpha mask directly to orthophoto.")
            big_image.putalpha(mask_im.resize((4096,4096),Image.BICUBIC))
            if type=='dds':
                try: os.remove(os.path.join(tile.build_dir,"textures",FNAMES.mask_file(til_x_left,til_y_top,zoomlevel,provider_code))) 
                except: pass
            dxt5=True
        file_to_convert=os.path.join(UI.Ortho4XP_dir,'tmp',png_file_name)
        erase_tmp_png=True
        big_image.save(file_to_convert) 
    # finally if nothing needs to be done prior to the conversion
    else:
        file_to_convert=os.path.join(file_dir,jpeg_file_name)
    # eventually the dds conversion
    if type=='dds':
        if not dxt5:
            conv_cmd=[dds_convert_cmd,'-bc1','-fast',file_to_convert,os.path.join(tile.build_dir,'textures',out_file_name),devnull_rdir]
        else:
            conv_cmd=[dds_convert_cmd,'-bc3','-fast',file_to_convert,os.path.join(tile.build_dir,'textures',out_file_name),devnull_rdir]
    else:
        (latmax,lonmin)=GEO.gtile_to_wgs84(til_x_left,til_y_top,zoomlevel)
        (latmin,lonmax)=GEO.gtile_to_wgs84(til_x_left+16,til_y_top+16,zoomlevel)
        (xmin,ymin)=GEO.transform('4326','3857',lonmin,latmin)
        (xmax,ymax)=GEO.transform('4326','3857',lonmax,latmax)
        if latmax-latmin < 0.04:
            conv_cmd=[gdal_transl_cmd,'-of','Gtiff','-co','COMPRESS=JPEG','-a_ullr',str(lonmin),str(latmax),str(lonmax),str(latmin),'-a_srs','epsg:4326',file_to_convert,os.path.join(FNAMES.Geotiff_dir,out_file_name)]     
        else:
            geotag_cmd=[gdal_transl_cmd,'-of','Gtiff','-co','COMPRESS=JPEG','-a_ullr',str(xmin),str(ymax),str(xmax),str(ymin),'-a_srs','epsg:3857',file_to_convert,tmp_tif_file_name] 
            erase_tmp_tif=True
            if subprocess.call(geotag_cmd,stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT):
                UI.vprint(1,"ERROR: Could not geotag texture (gdal not present ?) ",os.path.join(tile.build_dir,'textures',out_file_name))
                try: os.remove(os.path.join(UI.Ortho4XP_dir,'tmp',png_file_name))
                except: pass  
                return
            conv_cmd=[gdalwarp_cmd,'-of','Gtiff','-co','COMPRESS=JPEG','-s_srs','epsg:3857','-t_srs','epsg:4326','-ts','4096','4096','-rb',tmp_tif_file_name,os.path.join(FNAMES.Geotiff_dir,out_file_name)] 
    tentative=0
    while True:
        if not subprocess.call(conv_cmd,stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT):
            break
        tentative+=1
        if tentative==10:
            UI.lvprint(1,"ERROR: Could not convert texture",os.path.join(tile.build_dir,'textures',out_file_name),"(10 tries)")
            break
        UI.lvprint(1,"WARNING: Could not convert texture",os.path.join(tile.build_dir,'textures',out_file_name))
        time.sleep(1)
    if erase_tmp_png:
        try: os.remove(os.path.join(UI.Ortho4XP_dir,'tmp',png_file_name))
        except: pass
    if erase_tmp_tif:
        try: os.remove(os.path.join(UI.Ortho4XP_dir,'tmp',png_file_name))
        except: pass
    return 
###############################################################################################################################

def geotag(input_file_name):
    suffix=input_file_name.split('.')[-1]
    out_file_name=input_file_name.replace(suffix,'tiff')
    items=input_file_name.split('_')
    til_y_top=int(items[0])
    til_x_left=int(items[1])
    zoomlevel=int(items[-1][-6:-4])
    (latmax,lonmin)=GEO.gtile_to_wgs84(til_x_left,til_y_top,zoomlevel)
    (latmin,lonmax)=GEO.gtile_to_wgs84(til_x_left+16,til_y_top+16,zoomlevel)
    conv_cmd=[gdal_transl_cmd,'-of','Gtiff','-co','COMPRESS=JPEG','-a_ullr',str(lonmin),str(latmax),str(lonmax),str(latmin),'-a_srs','epsg:4326',input_file_name,out_file_name] 
    tentative=0
    while True:
        if not subprocess.call(conv_cmd):
            break
        tentative+=1
        if tentative==10:
            print("ERROR: Could not convert texture",out_file_name,"(10 tries)")
            break
        print("WARNING: Could not convert texture",out_file_name)
        time.sleep(1)
