# Denmark
import time
import requests

DK_time = time.time()
DK_ticket = None


def custom_request(**kwargs):
    bbox = kwargs['bbox']
    width = kwargs['width']
    height = kwargs['height']

    (xmin, ymax, xmax, ymin) = bbox
    bbox_string = str(xmin) + ',' + str(ymin) + ',' + str(xmax) + ',' + str(ymax)
    url = "http://kortforsyningen.kms.dk/orto_foraar?TICKET=" + get_dk_ticket() +\
          "&SERVICE=WMS&VERSION=1.1.1&FORMAT=image/jpeg&REQUEST=GetMap&LAYERS=orto_foraar" +\
          "&STYLES=&SRS=EPSG:3857&WIDTH=" + str(width) + "&HEIGHT=" + str(height) + "&BBOX=" + bbox_string
    return url, None


def get_dk_ticket():
    global DK_time, DK_ticket
    while DK_ticket == "loading":
        print("    Waiting for DK ticket to be updated.")
        time.sleep(3)
    if not DK_ticket or (time.time() - DK_time) >= 3600:
        DK_ticket = "loading"
        tmp = requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS
        requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS = 'HIGH:!DH:!aNULL'
        DK_ticket = requests.get("https://sdfekort.dk/spatialmap?").content.decode().split('ticket=')[1].split("'")[0]
        requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS = tmp
        DK_time = time.time()
    return DK_ticket
