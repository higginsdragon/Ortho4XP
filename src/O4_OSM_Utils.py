import os
import time
import bz2
import random
import requests
import numpy
from shapely import geometry, ops
import O4_UI_Utils as UI
import O4_File_Names as FNAMES
from xml.etree import ElementTree

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
        self.dicosmn_reverse = {}    # reverese of the previous one
        self.dicosmw={}
        self.next_node_id = -1
        self.next_way_id = -1
        self.next_rel_id = -1
        # rels already sorted out and containing nodeids rather than wayids
        self.dicosmr = {}
        # ids of objects directly queried, not of child or
        # parent objects pulled indirectly by queries. Since
        # osm ids are only unique per object type we need one for each:
        self.dicosmfirst = {'n': set(), 'w': set(), 'r': set()}
        self.dicosmtags = {'n': {}, 'w': {}, 'r': {}}
        self.dicosm = [self.dicosmn,
                       self.dicosmw,
                       self.dicosmr,
                       self.dicosmfirst,
                       self.dicosmtags]

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
            osm_parsed = ElementTree.fromstring(osm_input)
        except ElementTree.ParseError:
            UI.vprint(1, "    Error parsing OSM data, probably corrupted or malformed. Skipping.")
            return 0

        def process_tags(parent, parent_id, parent_type):
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
                if (not input_tags) or (('all', '') in target_tags[parent_type])\
                    or ((k, '') in target_tags[parent_type])\
                        or ((k, v) in target_tags[parent_type]):
                    if osm_id not in self.dicosmtags[parent_type]:
                        self.dicosmtags[parent_type][parent_id] = {k: v}
                    else:
                        self.dicosmtags[parent_type][parent_id][k] = v

                    # If so, do we need to declare this osm_id as a first catch, not one only brought with as a child
                    if input_tags and (((k, '') in input_tags[parent_type]) or ((k, v) in input_tags[parent_type])):
                        self.dicosmfirst[parent_type].add(parent_id)

            return 1

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
                osm_id = true_osm_id
                self.dicosmn_reverse[coords] = osm_id
                self.dicosmn[osm_id] = coords
                self.next_node_id -= 1

            # tags
            process_tags(node, osm_id, 'n')

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
            process_tags(way, osm_id, 'w')

        # relations
        # for airports, we don't want any relations with anything other than 2 inner or outer roles
        for relation in osm_parsed.findall('relation'):
            outer_roles = relation.findall("member[@type='way'][@role='outer']")
            inner_roles = relation.findall("member[@type='way'][@role='inner']")
            osm_id = relation.get('id')

            if len(outer_roles) == 2 or len(inner_roles) == 2:  # we continue
                true_osm_id = self.next_rel_id
                self.next_rel_id -= 1
                osm_id = true_osm_id
                self.dicosmr[osm_id] = {'outer': [], 'inner': []}

                if not input_tags:
                    self.dicosmfirst['r'].add(osm_id)

                # members
                if len(outer_roles) == 2:
                    members = outer_roles
                    role = 'outer'
                else:  # must be inner roles
                    members = inner_roles
                    role = 'inner'

                dupe_id_check = 0

                for member in members:
                    orig_way_id = member.get('ref')
                    try:
                        way_id = way_id_dict[orig_way_id]
                    except KeyError:  # no entry in way_id dictionary
                        continue

                    true_node_ids = self.dicosmw[way_id]

                    for true_node_id in true_node_ids:
                        if true_node_id != dupe_id_check:
                            self.dicosmr[osm_id][role].append(true_node_id)

                        dupe_id_check = true_node_id

                # tags
                process_tags(relation, osm_id, 'r')

            else:  # If there's more or less than 2 outer/inner way elements, it's not used, so skip it.
                UI.lvprint(2, "Relation id=", osm_id, "is ill formed and was not treated.")

        UI.vprint(2, "      A total of " + str(len(self.dicosmn) - initnodes) + " new node(s), " +
                  str(len(self.dicosmfirst['w']) - initways) + " new ways and " +
                  str(len(self.dicosmfirst['r']) - initrels) + " new relation(s).")
        return 1


    def write_to_file(self,filename):
        try:
            if filename[-4:]=='.bz2':
                fout=bz2.open(filename,'wt',encoding="utf-8")
            else:
                fout=open(filename,'w',encoding="utf-8")
        except:
            UI.vprint(1,"    Could not open",filename,"for writing.")
            return 0
        fout.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="Ortho4XP">\n')
        if not len(self.dicosmfirst['n']):
            for nodeid,(lonp,latp) in self.dicosmn.items():
                fout.write('  <node id="'+str(nodeid)+'" lat="'+'{:.7f}'.format(latp)+'" lon="'+'{:.7f}'.format(lonp)+'" version="1"/>\n')
        else:
            for nodeid,(lonp,latp) in self.dicosmn.items():
                if nodeid not in self.dicosmtags['n']:
                    fout.write('  <node id="'+str(nodeid)+'" lat="'+'{:.7f}'.format(latp)+'" lon="'+'{:.7f}'.format(lonp)+'" version="1"/>\n')
                else:
                    fout.write('  <node id="'+str(nodeid)+'" lat="'+'{:.7f}'.format(latp)+'" lon="'+'{:.7f}'.format(lonp)+'" version="1">\n')
                    for tag in self.dicosmtags['n'][nodeid]:
                        fout.write('    <tag k="'+tag+'" v="'+self.dicosmtags['n'][nodeid][tag]+'"/>\n')
                    fout.write('  </node>\n')
        for wayid in tuple(self.dicosmfirst['w'])+tuple(set(self.dicosmw).difference(self.dicosmfirst['w'])):
            fout.write('  <way id="'+str(wayid)+'" version="1">\n')
            for nodeid in self.dicosmw[wayid]:
                fout.write('    <nd ref="'+str(nodeid)+'"/>\n')
            for tag in self.dicosmtags['w'][wayid] if wayid in self.dicosmtags['w'] else []:
                fout.write('    <tag k="'+tag+'" v="'+self.dicosmtags['w'][wayid][tag]+'"/>\n')
            fout.write('  </way>\n')
        for relid in tuple(self.dicosmfirst['r'])+tuple(set(self.dicosmr).difference(self.dicosmfirst['r'])):
            fout.write('  <relation id="'+str(relid)+'" version="1">\n')
            for wayid in self.dicosmr[relid]['outer']:
                fout.write('    <member type="way" ref="'+str(wayid)+'" role="outer"/>\n')
            for wayid in self.dicosmr[relid]['inner']:
                fout.write('    <member type="way" ref="'+str(wayid)+'" role="inner"/>\n')
            for tag in self.dicosmtags['r'][relid] if relid in self.dicosmtags['r'] else []:
                fout.write('    <tag k="'+tag+'" v="'+self.dicosmtags['r'][relid][tag]+'"/>\n')
            fout.write('  </relation>\n')
        fout.write('</osm>')
        fout.close()    
        return 1


def OSM_queries_to_OSM_layer(queries,osm_layer,lat,lon,tags_of_interest=[],server_code=None,cached_suffix=''):
    # this one is a bit complicated by a few checks of existing cached data which had different filenames
    # is versions prior to 1.30
    target_tags={'n':[],'w':[],'r':[]}
    input_tags={'n':[],'w':[],'r':[]}
    for query in queries:
        for tag in [query] if isinstance(query,str) else query:
            items=tag.split('"')
            osm_type=items[0][0]
            try: 
                target_tags[osm_type].append((items[1],items[3]))
                input_tags[osm_type].append((items[1],items[3]))
            except: 
                target_tags[osm_type].append((items[1],''))
                input_tags[osm_type].append((items[1],''))
            for tag in tags_of_interest:
                if isinstance(tag,str):
                    if (tag,'') not in target_tags[osm_type]: target_tags[osm_type].append((tag,''))
                else:
                    if tag not in target_tags[osm_type]:target_tags[osm_type].append(tag)
    cached_data_filename=FNAMES.osm_cached(lat, lon, cached_suffix)
    if cached_suffix and os.path.isfile(cached_data_filename):
        UI.vprint(1,"    * Recycling OSM data from",cached_data_filename)
        return osm_layer.update_dicosm(cached_data_filename,input_tags,target_tags)
    for query in queries:
        # look first for cached data (old scheme)
        if isinstance(query,str):
            old_cached_data_filename=FNAMES.osm_old_cached(lat, lon, query)
            if os.path.isfile(old_cached_data_filename):
                UI.vprint(1,"    * Recycling OSM data for",query)
                osm_layer.update_dicosm(old_cached_data_filename,input_tags,target_tags)
                continue
        UI.vprint(1,"    * Downloading OSM data for",query)        
        response=get_overpass_data(query,(lat,lon,lat+1,lon+1),server_code)
        if UI.red_flag: return 0
        if not response: 
           UI.logprint("No valid answer for",query,"after",max_osm_tentatives,", skipping it.") 
           UI.vprint(1,"      No valid answer after",max_osm_tentatives,", skipping it.")
           return 0
        osm_layer.update_dicosm(response,input_tags,target_tags)
    if cached_suffix: 
        osm_layer.write_to_file(cached_data_filename)
    return 1
##############################################################################

##############################################################################
def OSM_query_to_OSM_layer(query,bbox,osm_layer,tags_of_interest=[],server_code=None,cached_file_name=''):
    # this one is simpler and does not depend on the notion of tile
    target_tags={'n':[],'w':[],'r':[]}
    input_tags={'n':[],'w':[],'r':[]}
    for tag in [query] if isinstance(query,str) else query:
        items=tag.split('"')
        osm_type=items[0][0]
        try: 
            target_tags[osm_type].append((items[1],items[3]))
            input_tags[osm_type].append((items[1],items[3]))
        except: 
            target_tags[osm_type].append((items[1],''))
            input_tags[osm_type].append((items[1],''))
        for tag in tags_of_interest:
            if isinstance(tag,str):
                target_tags[osm_type].append((tag,''))
            else:
                target_tags[osm_type].append(tag)
    if cached_file_name and os.path.isfile(cached_file_name):
        UI.vprint(1,"    * Recycling OSM data from",cached_file_name)
        osm_layer.update_dicosm(cached_file_name,input_tags,target_tags)
    else:
        response=get_overpass_data(query,bbox,server_code)
        if UI.red_flag: return 0
        if not response: 
            UI.lvprint(1,"      No valid answer for",query,"after",max_osm_tentatives,", skipping it.")
            return 0
        osm_layer.update_dicosm(response,input_tags,target_tags)
        if cached_file_name: osm_layer.write_to_file(cached_file_name)
    return 1
##############################################################################


##############################################################################
def get_overpass_data(query,bbox,server_code=None):
    tentative=1
    while True:
        s=requests.Session()
        if not server_code:
           true_server_code = random.choice(list(overpass_servers.keys())) if overpass_server_choice=='random' else overpass_server_choice
        base_url=overpass_servers[true_server_code]
        if isinstance(query,str):
            overpass_query=query+str(bbox)+";"
        else: # query is a tuple 
            overpass_query=''.join([x+str(bbox)+";" for x in query])
        url=base_url+"?data=("+overpass_query+");(._;>>;);out meta;"
        UI.vprint(3,url)
        try:
            r=s.get(url, timeout=60)
            UI.vprint(3, "OSM response status :",str(r.status_code))
            if r.status_code == 200:
                if b"</osm>" not in r.content[-10:] and b"</OSM>" not in r.content[-10:]:
                    UI.vprint(1,"        OSM server",true_server_code,"sent a corrupted answer (no closing </osm> tag in answer), new tentative in",2**tentative,"sec...")
                elif len(r.content)<=1000 and b"error" in r.content:
                    UI.vprint(1,"        OSM server",true_server_code,"sent us an error code for the data (data too big ?), new tentative in",2**tentative,"sec...")
                else:
                    break
            else:
                UI.vprint(1,"        OSM server",true_server_code,"rejected our query, new tentative in",2**tentative,"sec...")
        except:
            UI.vprint(1,"        OSM server",true_server_code,"was too busy, new tentative in",2**tentative,"sec...")
        if tentative>=max_osm_tentatives:
            return 0
        if UI.red_flag: return 0
        time.sleep(2**tentative)
        tentative+=1
    return r.content
##############################################################################

##############################################################################
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

