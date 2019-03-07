# NorgeIbilder
import time
import requests

NIB_time = time.time()
NIB_token = None


def custom_request(**kwargs):
    global NIB_token
    NIB_token = get_nib_token()

    tilematrix = kwargs['tilematrix']
    til_x = kwargs['til_x']
    til_y = kwargs['til_y']

    url = "http://agsservices.norgeibilder.no/arcgis/rest/services/Nibcache_UTM33_EUREF89_v2/MapServer/tile/" +\
          str(tilematrix) + "/" + str(til_y) + "/" + str(til_x) + "?token=" + NIB_token
    return url, None


def get_nib_token():
    global NIB_time, NIB_token
    while NIB_token == "loading":
        print("    Waiting for NIB token to be updated.")
        time.sleep(3)
    if not NIB_token or (time.time() - NIB_time) >= 3600:
        NIB_token = "loading"
        NIB_token = str(requests.get('http://www.norgeibilder.no').content).split('nibToken')[1].split("'")[1][:-1]
        NIB_time = time.time()
    return NIB_token
