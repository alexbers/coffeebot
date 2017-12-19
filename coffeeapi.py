import requests
import json
import sys
import time
import os

from secrets import LOGIN, PASSWORD, MACHINE_ID, DEV_ID

API_HOST = "app.24-u.co.uk"

HEADERS = {
    "x-api-version": "1.0",
    "x-api-lang": "en",
    "X-App-Version": "24U/Android-22/Google Nexus 4 - 5.1.0 - API 22 - 768x1280/1.6.1"
}

TOKEN_PATH = "db/token.txt"

def obtain_token(login, password):
    URL = "https://%s/Token" % API_HOST

    data = {
        "grant_type": "password",
        "username": login,
        "password": password,
        "devid": DEV_ID
    }

    resp = requests.post(URL, data=data, headers=HEADERS)
    token = resp.json()["access_token"]

    return token


def obtain_and_cache_token(login, password):
    token = obtain_token(LOGIN, PASSWORD)
    open_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    with  os.fdopen(os.open(TOKEN_PATH, open_flags, 0o600), "w") as f:
        f.write(token)
    return token


def get_or_obtain_token():
    try:
        token = open(TOKEN_PATH).read().strip()
    except FileNotFoundError:
        token = obtain_and_cache_token(LOGIN, PASSWORD)

    account = get_account(token)
    if "userInfo" not in account:
        token = obtain_and_cache_token(LOGIN, PASSWORD)
    return token

    
def call_api(token, endpoint, method="GET", data=None):
    headers = HEADERS.copy()
    headers["Authorization"] = "bearer " + token
    headers["Content-type"] = "application/json"

    url = "https://%s/%s" % (API_HOST, endpoint)

    resp = requests.request(method, url, headers=headers, data=json.dumps(data))

    return resp.json()


def get_account(token):
    return call_api(token, "api/Account/UserInfo")


def get_payment_info(token):
    return call_api(token, "api/Payment")

def get_order_id(token):
    resp = call_api(token, "/api/Machine/%s@uonline" % MACHINE_ID)
    machine = resp["machine"]
    good_machine = (machine["status"] == "Ready")
    good_machine &= (machine["decimalPoint"] == 2)
    good_machine &= (machine["currency"] == "RUB")
    good_machine &= ("orderId" in machine)

    if not good_machine:
        print("bad machine", file=sys.stderr)
        return None

    return machine["orderId"]


def get_first_payment_method(token):
    resp = get_payment_info(token)
    return resp['paymentMethods'][0]


def wait_for_reciept(token, order_id, expect_credit):
    ATTEMPTS = 6
    TIMEOUT = 5

    for i in range(ATTEMPTS):
        resp = call_api(token, "/api/Machine/Receipt/%d" % order_id)
        if resp.get("receipt", {}).get("paymentAmount", 0) == expect_credit:
            return True
        time.sleep(TIMEOUT)
    return False


def buy_cofee(token=None, test_mode=False):
    CREDIT = 3500

    if not token:
        token = get_or_obtain_token()

    payment_method = get_first_payment_method(token)
    order_id = get_order_id(token)

    if test_mode:
        return True, "ok"

    data = {
        "orderId": order_id,
        "credit": CREDIT,
        "paymentMethod": payment_method
    }

    resp = call_api(token, "/api/Machine/Order", method="POST", data=data)

    if "status" not in resp:
        return False, "no status code: %s" % resp
    
    if not resp["status"]:
        return False, resp.get("message", "no message")

    result = wait_for_reciept(token, order_id, CREDIT)
    if not result:
        return False, "wait_for_reciept failed"

    return True, "%s" % resp

