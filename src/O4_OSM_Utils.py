import os
import time
import bz2
import random
import requests
import numpy
from shapely import geometry, ops
import O4_UI_Utils as UI
import O4_File_Names as FNAMES
import xml.etree.ElementTree as ET

overpass_servers={
        "DE": "http://overpass-api.de/api/interpreter",
        "FR": "http://api.openstreetmap.fr/oapi/interpreter",
        "KU": "https://overpass.kumi.systems/api/interpreter",
        "RU": "http://overpass.osm.rambler.ru/cgi/interpreter"
        }
overpass_server_choice = "DE"
max_osm_tentatives = 8


class OSM_layer:

    def __init__(self):
        self.dicosmn = {}            # keys are ints (ids) and values are tuple of (lat,lon)
        self.dicosmn_reverse = {}    # reverse of the previous one
        self.dicosmw = {}
        self.next_node_id = -1
        self.next_way_id = -1
        self.next_rel_id = -1
        # relations already sorted out and containing node ids rather than way ids
        self.dicosmr = {}
        # original relations containing way ids only, not sorted and/or reversed -- for use in relation tracking
        self.dicosmrorig = {}
        # ids of objects directly queried, not of child or
        # parent objects pulled indirectly by queries. Since
        # osm ids are only unique per object type we need one for each:
        self.dicosmfirst = {'n': set(), 'w': set(), 'r': set()}     # tag ids
        self.dicosmtags = {'n': {}, 'w': {}, 'r': {}}               # tag contents
        self.dicosm = [self.dicosmn,
                       self.dicosmw,
                       self.dicosmr,
                       self.dicosmfirst,
                       self.dicosmtags]
        self.target_tags = {'n': [], 'w': [], 'r': []}
        self.input_tags = {'n': [], 'w': [], 'r': []}

    def update_dicosm(self, osm_input, input_tags=None, target_tags=None):
        """
        Takes OSM data (or a string to an OSM file path) and reads it into several OSM_layer dictionaries for easier
        access, adding to them if necessary and preventing duplicate nodes.

        Ortho4XP uses it's own internal numbering system, fresh for each lat/long layer, starting at -1 and going down
        to avoid conflicts with OSM servers. These internal negative IDs are referred to as "true" IDs.

        :param osm_input: encoded OSM xml bytestring or a string to a cached OSM filename
        :param input_tags: (dict or None) are the input query tags (per OSM type)
        :param target_tags: (dict or None) are the the tags which should be kept (per OSM type)
            It is expected that if not None the target_tags contains the input_tags
        :return: 1/True or 0/False
        """
        initnodes = len(self.dicosmn)
        initways = len(self.dicosmfirst['w'])
        initrels = len(self.dicosmfirst['r'])
        node_id_dict = {}
        way_id_dict = {}
        self.input_tags = input_tags
        self.target_tags = target_tags

        if isinstance(osm_input, str):
            # pointer to a cached filename
            osm_file_name = osm_input
            try:
                if osm_file_name[-4:] == '.bz2':
                    pfile = bz2.open(osm_file_name, 'rt', encoding="utf-8")
                else:
                    pfile = open(osm_file_name, 'r', encoding="utf-8")

                osm_input = pfile.read()
                pfile.close()
            except FileNotFoundError:
                UI.vprint(1, "    ", osm_file_name, "does not exist.")
                return 0
            except OSError:
                UI.vprint(1, "    Could not open", osm_file_name, "for reading (corrupted ?).")
                return 0

        try:
            osm_parsed = ET.fromstring(osm_input)
        except ET.ParseError:
            UI.vprint(1, "    Error parsing OSM data, probably corrupted or malformed.")
            return 0

        # nodes
        for node in osm_parsed.findall('node'):
            osm_id = node.get('id')
            latp = float(node.get('lat'))
            lonp = float(node.get('lon'))
            coords = (lonp, latp)
            if coords in self.dicosmn_reverse:
                true_osm_id = self.dicosmn_reverse[coords]
                node_id_dict[osm_id] = true_osm_id
            else:
                true_osm_id = self.next_node_id
                node_id_dict[osm_id] = true_osm_id
                self.dicosmn_reverse[coords] = true_osm_id
                self.dicosmn[true_osm_id] = coords
                self.next_node_id -= 1

            # tags
            self.process_tags(node, true_osm_id, 'n')

        # ways
        for way in osm_parsed.findall('way'):
            osm_id = way.get('id')
            true_osm_id = self.next_way_id
            self.next_way_id -= 1
            way_id_dict[osm_id] = true_osm_id
            osm_id = true_osm_id
            self.dicosmw[osm_id] = []
            if not input_tags:
                self.dicosmfirst['w'].add(osm_id)

            # nd (node ref)
            for nd in way.findall('nd'):
                self.dicosmw[osm_id].append(node_id_dict[nd.get('ref')])

            # tags
            self.process_tags(way, osm_id, 'w')

        # relations
        for relation in osm_parsed.findall('relation'):
            outer_roles = relation.findall("member[@type='way'][@role='outer']")
            inner_roles = relation.findall("member[@type='way'][@role='inner']")
            members = outer_roles + inner_roles

            if members:
                true_osm_id = self.next_rel_id
                self.next_rel_id -= 1
                osm_id = true_osm_id
                self.dicosmr[osm_id] = {'outer': [], 'inner': []}
                self.dicosmrorig[osm_id] = {'outer': [], 'inner': []}

                if not input_tags:
                    self.dicosmfirst['r'].add(osm_id)

                # members
                non_contiguous_ways = {'outer': {}, 'inner': {}}

                for member in members:
                    orig_way_id = member.get('ref')
                    role = member.get('role')

                    try:
                        way_id = way_id_dict[orig_way_id]
                    except KeyError:  # no entry in way_id dictionary
                        continue

                    self.dicosmrorig[osm_id][role].append(way_id)
                    start_point = self.dicosmw[way_id][0]
                    end_point = self.dicosmw[way_id][-1]

                    if start_point == end_point:  # nice closed path
                        self.dicosmr[osm_id][role].append(self.dicosmw[way_id])
                    else:
                        non_contiguous_ways[role][way_id] = [start_point, end_point]

                # for paths composed of multiple ways
                for role in ['outer', 'inner']:
                    if non_contiguous_ways[role]:
                        complete_way = []
                        way_ids = list(non_contiguous_ways[role].keys())
                        edge_nodes = list(non_contiguous_ways[role].values())

                        # check for ill formed relations
                        node_ids = [n for e in edge_nodes for n in e]
                        if check_too_many_ids(node_ids):
                            # If there's more or less than 2 ways attached to a node point, it's bad, so remove it.
                            UI.lvprint(2, "Relation id=", osm_id, "is ill formed and was not treated.")
                            del self.dicosmr[osm_id]
                            del self.dicosmrorig[osm_id]
                            if osm_id in self.dicosmfirst['r']:
                                self.dicosmfirst['r'].remove(osm_id)
                            if osm_id in self.dicosmtags['r']:
                                del(self.dicosmtags['r'][osm_id])
                            self.next_rel_id += 1
                            break

                        # Start it with the first
                        complete_way += self.dicosmw[way_ids.pop(0)]
                        del edge_nodes[0]
                        last = complete_way[-1]
                        first_node_index = [i[0] for i in edge_nodes]
                        last_node_index = [i[1] for i in edge_nodes]

                        while len(way_ids) > 0:
                            path_start = False

                            if last in first_node_index:
                                node_index = first_node_index.index(last)
                            elif last in last_node_index:
                                node_index = last_node_index.index(last)
                            else:  # more paths in this relation, start from beginning of list
                                node_index = 0
                                last = last_node_index[0]
                                self.dicosmr[osm_id][role].append(complete_way)
                                complete_way = []
                                path_start = True

                            node_ids = self.dicosmw[way_ids[node_index]].copy()
                            node_points = edge_nodes[node_index]

                            if not path_start and node_points.index(last) == 1:
                                node_ids.reverse()

                            del node_ids[0]
                            complete_way += node_ids
                            last = complete_way[-1]
                            del first_node_index[node_index]
                            del last_node_index[node_index]
                            del way_ids[node_index]
                            del edge_nodes[node_index]

                        self.dicosmr[osm_id][role].append(complete_way)

                # tags
                self.process_tags(relation, osm_id, 'r')

        UI.vprint(2, "      A total of " + str(len(self.dicosmn) - initnodes) + " new node(s), " +
                  str(len(self.dicosmfirst['w']) - initways) + " new ways and " +
                  str(len(self.dicosmfirst['r']) - initrels) + " new relation(s).")
        return 1

    def process_tags(self, parent, parent_id, parent_type):
        """
        There are multiple attribute types which require getting nested tags, so keeping the function DRY and
        within scope.

        :param parent: (object) the parsed XML tag object
        :param parent_id: (int) the ID of the parent tag
        :param parent_type: (str) the type of the parent
        :return: 1/True
        """
        # Maybe move this into the class in the future for testing purposes.
        for tag in parent.findall('tag'):
            # Do we need to catch that tag?
            k = tag.get('k')
            v = tag.get('v')
            if (not self.input_tags) or (('all', '') in self.target_tags[parent_type]) \
                    or ((k, '') in self.target_tags[parent_type]) \
                    or ((k, v) in self.target_tags[parent_type]):
                if parent_id not in self.dicosmtags[parent_type]:
                    self.dicosmtags[parent_type][parent_id] = {k: v}
                else:
                    self.dicosmtags[parent_type][parent_id][k] = v

                # If so, do we need to declare this osm_id as a first catch, not one only brought with as a child
                if self.input_tags and (((k, '') in self.input_tags[parent_type])
                                        or ((k, v) in self.input_tags[parent_type])):
                    self.dicosmfirst[parent_type].add(parent_id)

        return 1

    def write_to_file(self, filename):
        """
        Writes the OSMLayer object to a file.

        :param filename: full path and file name
        :return: 1/True or 0/False
        """
        osm = ET.Element('osm', attrib={'generator': 'Ortho4XP', 'version': '0.6'})

        # nodes
        for node_id, (lonp, latp) in self.dicosmn.items():
            node = ET.SubElement(osm, 'node', attrib={'id': str(node_id),
                                                      'lat': str('{:.7f}'.format(latp)),
                                                      'lon': str('{:.7f}'.format(lonp)),
                                                      'version': '1'})
            if node_id in self.dicosmfirst['n']:  # tags!
                for tag in self.dicosmtags['n'][node_id]:
                    ET.SubElement(node, 'tag', attrib={'k': tag, 'v': self.dicosmtags['n'][node_id][tag]})

        # ways
        for way_id in self.dicosmw.keys():
            way = ET.SubElement(osm, 'way', attrib={'id': str(way_id), 'version': '1'})
            for node_id in self.dicosmw[way_id]:
                ET.SubElement(way, 'nd', attrib={'ref': str(node_id)})
            if way_id in self.dicosmtags['w']:
                for tag in self.dicosmtags['w'][way_id]:
                    ET.SubElement(way, 'tag', attrib={'k': tag, 'v': self.dicosmtags['w'][way_id][tag]})

        # relations
        for relation_id in self.dicosmr.keys():
            relation = ET.SubElement(osm, 'relation', attrib={'id': str(relation_id), 'version': '1'})
            for role in ['outer', 'inner']:
                for way_id in self.dicosmrorig[relation_id][role]:
                    ET.SubElement(relation, 'member', attrib={'type': 'way', 'ref': str(way_id), 'role': role})
            if relation_id in self.dicosmtags['r']:
                for tag in self.dicosmtags['r'][relation_id]:
                    ET.SubElement(relation, 'tag', attrib={'k': tag, 'v': self.dicosmtags['r'][relation_id][tag]})

        xml_indent(osm)
        tree = ET.ElementTree(osm)

        try:
            if filename[-4:] == '.bz2':
                fout = bz2.open(filename, 'wb')
                tree.write(fout, encoding='UTF-8', xml_declaration=True)
                fout.close()
            else:
                tree.write(filename, encoding='UTF-8', xml_declaration=True)
        except OSError:
            UI.vprint(1, "    Could not open", filename, "for writing.")
            return 0

        return 1


def xml_indent(elem, level=0):
    """
    Because ElementTree doesn't do newlines or indents, this will add them to the elements so the file is pretty.

    :param elem: pass the root element here
    :param level: the indent level
    :return: 
    """
    i = '\n' + level * '  '
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + '  '
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            xml_indent(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

    return 1


def check_too_many_ids(ids):
    """used for checking ill-formed relations in a layer"""
    id_counts = {}
    for i in ids:
        if i in id_counts:
            id_counts[i] += 1
        else:
            id_counts[i] = 1

    for c in list(id_counts.values()):
        if c != 2:
            return 1

    return 0


def OSM_query_to_OSM_layer(queries, bbox, osm_layer, tags_of_interest=None, server_code=None, cached_file_name=''):
    """
    Takes queries for a tile and then gets the OSM data either by local file if cached, or OSM server if new request.
    Also checks for legacy pre 1.30 cached files.

    :param queries: array or string of different OSM queries, e.g. ['way["highway"="motorway"]']
    :param bbox: tuple bounding box of coordinates, e.g (41, -88, 42, -87)
    :param osm_layer: the OSMLayer object to add to
    :param tags_of_interest: an array of tags to filter by, e.g. ["bridge","tunnel"]
    :param server_code: OSM server code to use, e.g. 'DE'
    :param cached_file_name: the file name to use for disk caching
    :return: 1/True or 0/False
    """
    target_tags = {'n': [], 'w': [], 'r': []}
    input_tags = {'n': [], 'w': [], 'r': []}
    lat = bbox[0]
    lon = bbox[1]

    # This is done to avoid mutable objects in default parameters. See: http://effbot.org/zone/default-values.htm
    if tags_of_interest is None:
        tags_of_interest = []

    # In case it's just a query string
    if isinstance(queries, str):
        queries = [queries.split(',')]

    for query in queries:
        for value in [query] if isinstance(query, str) else query:
            items = value.split('"')
            osm_type = items[0][0]

            try:
                target_tags[osm_type].append((items[1], items[3]))
                input_tags[osm_type].append((items[1], items[3]))
            except IndexError:
                target_tags[osm_type].append((items[1], ''))
                input_tags[osm_type].append((items[1], ''))

            for tag in tags_of_interest:
                if isinstance(tag, str):
                    if (tag, '') not in target_tags[osm_type]:
                        target_tags[osm_type].append((tag, ''))
                else:  # it's already a tuple
                    if tag not in target_tags[osm_type]:
                        target_tags[osm_type].append(tag)

    if cached_file_name and os.path.isfile(cached_file_name):
        UI.vprint(1, "    * Recycling OSM data from", cached_file_name)
        # If file is bad, gracefully continue to download new data.
        if osm_layer.update_dicosm(cached_file_name, input_tags, target_tags):
            return 1

    for query in queries:
        # this one is a bit complicated by a few checks of existing cached data which had different filenames
        # is versions prior to 1.30
        # look first for cached data (old scheme) -- legacy
        if isinstance(query, str):
            old_cached_data_filename = FNAMES.osm_old_cached(lat, lon, query)
            if os.path.isfile(old_cached_data_filename):
                UI.vprint(1, "    * Recycling OSM data for", query)
                osm_layer.update_dicosm(old_cached_data_filename, input_tags, target_tags)
                continue

        UI.vprint(1, "    * Downloading OSM data for", query)
        response = get_overpass_data(query, bbox, server_code)

        if UI.red_flag:
            return 0

        if not response:
            UI.lvprint(1, "      No valid answer for", query, "after", max_osm_tentatives, ", skipping it.")
            return 0

        osm_layer.update_dicosm(response, input_tags, target_tags)

    if cached_file_name:
        osm_layer.write_to_file(cached_file_name)

    return 1


def OSM_queries_to_OSM_layer(queries, osm_layer, lat, lon, tags_of_interest=None, server_code=None, cached_suffix=''):
    """
    Similar to OSM_query_to_OSM_layer but just accepting the lat/long of a tile

    :param queries: array of different OSM queries, e.g. ['way["highway"="motorway"]']
    :param osm_layer: the OSMLayer object to add to
    :param lat: the latitude of the tile
    :param lon: the longitude of the tile
    :param tags_of_interest: an array of tags to filter by, e.g. ["bridge","tunnel"]
    :param server_code: OSM server code to use, e.g. 'DE'
    :param cached_suffix: the suffix to use for the cached filename, e.g. 'airports' becomes +00-000_airports.osm.bz2
    :return: 1/True or 0/False
    """
    bbox = (lat, lon, lat + 1, lon + 1)
    cached_data_filename = FNAMES.osm_cached(lat, lon, cached_suffix)

    return OSM_query_to_OSM_layer(queries, bbox, osm_layer, tags_of_interest, server_code, cached_data_filename)


def get_overpass_data(query, bbox, server_code=None):
    """
    Directly calls the OSM server to get the requested data, returning the raw response.

    :param query: the OSM queries as a raw string or tuple
    :param bbox: tuple lat/long bounding box, e.g. (41, -88, 42, -87)
    :param server_code: The server code to use, or 'random'
    :return: request content or 0/False
    """
    tentative = 1
    server_keys = overpass_servers.keys()
    true_server_code = overpass_server_choice  # defining this here in case a bad server code is passed in

    while True:
        s = requests.Session()

        if 'random' in [server_code, true_server_code]:
            true_server_code = random.choice(list(server_keys))
        elif server_code:
            if server_code in server_keys:
                true_server_code = server_code
            else:
                UI.vprint(1, "        Bad server code, defaulting to", true_server_code)

        base_url = overpass_servers[true_server_code]

        if isinstance(query, str):
            overpass_query = query + str(bbox) + ";"
        else:  # query is a tuple
            overpass_query = ''.join([x + str(bbox) + ";" for x in query])

        url = base_url + "?data=(" + overpass_query + ");(._;>>;);out meta;"
        UI.vprint(3, url)

        try:
            r = s.get(url, timeout=60)
            UI.vprint(3, "OSM response status :", str(r.status_code))
            if r.status_code == 200:
                if b"</osm>" not in r.content[-10:] and b"</OSM>" not in r.content[-10:]:
                    UI.vprint(1, "        OSM server", true_server_code,
                              "sent a corrupted answer (no closing </osm> tag in answer), new tentative in",
                              2**tentative, "sec...")
                elif len(r.content) <= 1000 and b"error" in r.content:
                    UI.vprint(1, "        OSM server", true_server_code,
                              "sent us an error code for the data (data too big ?), new tentative in",
                              2**tentative, "sec...")
                else:
                    break
            else:
                UI.vprint(1, "        OSM server", true_server_code,
                          "rejected our query, new tentative in", 2**tentative, "sec...")

        except requests.Timeout:
            UI.vprint(1, "        OSM server", true_server_code,
                      "was too busy, new tentative in", 2**tentative, "sec...")
        except requests.exceptions.RequestException:
            UI.vprint(1, "        OSM server", true_server_code,
                      "raised an error and cannot connect. Try a different server.")
            return 0

        if tentative >= max_osm_tentatives:
            return 0

        if UI.red_flag:
            return 0

        time.sleep(2**tentative)
        tentative += 1

    return r.content


def OSM_to_MultiLineString(osm_layer,lat,lon,tags_for_exclusion=set(),filter=None):
    multiline=[]
    multiline_reject=[]
    todo=len(osm_layer.dicosmfirst['w'])
    step=int(todo/100)+1
    done=0
    filtered_segs=0
    for wayid in osm_layer.dicosmfirst['w']:
        if done%step==0: UI.progress_bar(1,int(100*done/todo))
        if tags_for_exclusion and wayid in osm_layer.dicosmtags['w'] \
          and not set(osm_layer.dicosmtags['w'][wayid].keys()).isdisjoint(tags_for_exclusion):
            done+=1
            continue  
        way=numpy.round(numpy.array([osm_layer.dicosmn[nodeid] for nodeid in osm_layer.dicosmw[wayid]],dtype=numpy.float64)-numpy.array([[lon,lat]],dtype=numpy.float64),7) 
        if filter and not filter(way,filtered_segs):
            try:
                multiline_reject.append(geometry.LineString(way))
            except:
                pass
            done+=1
            continue
        try:
            multiline.append(geometry.LineString(way))
            filtered_segs+=len(way)
        except:
            pass
        done+=1
    UI.progress_bar(1,100)
    if not filter:
        return geometry.MultiLineString(multiline)
    else:
        UI.vprint(2,"      Number of filtered segs :",filtered_segs)
        return (geometry.MultiLineString(multiline),geometry.MultiLineString(multiline_reject))
##############################################################################

##############################################################################
def OSM_to_MultiPolygon(osm_layer,lat,lon,filter=None):
    multilist=[]
    excludelist=[]
    todo=len(osm_layer.dicosmfirst['w'])+len(osm_layer.dicosmfirst['r'])
    step=int(todo/100)+1
    done=0
    for wayid in osm_layer.dicosmfirst['w']:
        if done%step==0: UI.progress_bar(1,int(100*done/todo))
        if osm_layer.dicosmw[wayid][0]!=osm_layer.dicosmw[wayid][-1]: 
            UI.logprint("Non closed way starting at",osm_layer.dicosmn[osm_layer.dicosmw[wayid][0]],", skipped.")
            done+=1
            continue
        way=numpy.round(numpy.array([osm_layer.dicosmn[nodeid] for nodeid in osm_layer.dicosmw[wayid]],dtype=numpy.float64)-numpy.array([[lon,lat]],dtype=numpy.float64),7) 
        try:
            pol=geometry.Polygon(way)
            if not pol.area: continue
            if not pol.is_valid:
                UI.logprint("Invalid OSM way starting at",osm_layer.dicosmn[osm_layer.dicosmw[wayid][0]],", skipped.")
                done+=1
                continue
        except Exception as e:
            UI.vprint(2,e)
            done+=1
            continue
        if filter and filter(pol,wayid,osm_layer.dicosmtags['w']):
            excludelist.append(pol)
        else:
            multilist.append(pol) 
        done+=1
    for relid in osm_layer.dicosmfirst['r']:
        if done%step==0: UI.progress_bar(1,int(100*done/todo))
        try:
            multiout=[geometry.Polygon(numpy.round(numpy.array([osm_layer.dicosmn[nodeid] \
                                        for nodeid in nodelist],dtype=numpy.float64)-numpy.array([lon,lat],dtype=numpy.float64),7))\
                                        for nodelist in osm_layer.dicosmr[relid]['outer']]
            multiout=ops.cascaded_union([geom for geom in multiout if geom.is_valid])
            multiin=[geometry.Polygon(numpy.round(numpy.array([osm_layer.dicosmn[nodeid]\
                                        for nodeid in nodelist],dtype=numpy.float64)-numpy.array([lon,lat],dtype=numpy.float64),7))\
                                        for nodelist in osm_layer.dicosmr[relid]['inner']]
            multiin=ops.cascaded_union([geom for geom in multiin if geom.is_valid])
        except Exception as e:
            UI.logprint(e)
            done+=1
            continue
        multipol = multiout.difference(multiin)
        if filter and filter(multipol,relid,osm_layer.dicosmtags['r']):
            targetlist=excludelist
        else:
            targetlist=multilist 
        for pol in multipol.geoms if ('Multi' in multipol.geom_type or 'Collection' in multipol.geom_type) else [multipol]:
            if not pol.area: 
                done+=1
                continue
            if not pol.is_valid: 
                UI.logprint("Relation",relid,"contains an invalid polygon which was discarded") 
                done+=1
                continue
            targetlist.append(pol)  
        done+=1
    if filter:
        ret_val=(geometry.MultiPolygon(multilist),geometry.MultiPolygon(excludelist))
        UI.vprint(2,"    Total number of geometries:",len(ret_val[0].geoms),len(ret_val[1].geoms))
    else:
        ret_val=geometry.MultiPolygon(multilist)
        UI.vprint(2,"    Total number of geometries:",len(ret_val.geoms))
    UI.progress_bar(1,100)
    return ret_val
##############################################################################

