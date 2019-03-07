# Here
import time
import requests
import random

Here_time = time.time()
Here_value = None


def custom_request(**kwargs):
    global Here_value
    Here_value = get_here_value()

    tilematrix = kwargs['tilematrix']
    til_x = kwargs['til_x']
    til_y = kwargs['til_y']

    url = "https://" + random.choice(['1', '2', '3', '4']) +\
          ".aerial.maps.api.here.com/maptile/2.1/maptile/" + Here_value + "/satellite.day/" +\
          str(tilematrix) + "/" + str(til_x) + "/" + str(til_y) +\
          "/256/jpg?app_id=bC4fb9WQfCCZfkxspD4z&app_code=K2Cpd_EKDzrZb1tz0zdpeQ"
    return url, None


def get_here_value():
    global Here_time, Here_value
    while Here_value == "loading":
        print("    Waiting for Here value to be updated.")
        time.sleep(3)
    if not Here_value or (time.time() - Here_time) >= 10000:
        Here_value = "loading"
        Here_value = str(requests.get('https://wego.here.com').content).\
            split('aerial.maps.api.here.com/maptile/2.1')[1][:100].split('"')[4]
        Here_time = time.time()
    return Here_value
