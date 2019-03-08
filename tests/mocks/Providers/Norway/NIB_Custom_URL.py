# NorgeIbilder
import time

NIB_time = time.time()
NIB_token = None


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


def custom_request(**kwargs):
    global NIB_token
    NIB_token = get_NIB_token()

    for key in kwargs:
        eval(key + '=' + kwargs[key])

    url = "http://agsservices.norgeibilder.no/arcgis/rest/services/Nibcache_UTM33_EUREF89_v2/MapServer/tile/" +\
          str(tilematrix) + "/" + str(til_y) + "/" + str(til_x) + "?token=" + NIB_token
    return url, None


def custom_tms_request(tilematrix, til_x, til_y, provider):
    NIB_token = get_NIB_token()
    url = "http://agsservices.norgeibilder.no/arcgis/rest/services/Nibcache_UTM33_EUREF89_v2/MapServer/tile/" + str(
        tilematrix) + "/" + str(til_y) + "/" + str(til_x) + "?token=" + NIB_token
    return (url, None)
