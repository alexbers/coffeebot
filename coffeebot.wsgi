import time
import json
import re
import sys
import os
import requests
import traceback

import coffeeapi

from secrets import BOT_TOKEN, TG_ADMIN_ID, MACHINE_ID

RESP_HEADERS = [("Content-Type", "application/json")]

DB_PATH = "%s/db" % os.path.dirname(os.path.abspath(__file__))

def update_cups_left(user_id, cups):
    open("%s/user_%d/cups.txt" % (DB_PATH, user_id), "w").write(str(cups))


def get_cups_left(user_id):
    try:
        os.mkdir("%s/user_%d" % (DB_PATH, user_id))
    except FileExistsError:
        pass

    open("%s/user_%d/cups.txt" % (DB_PATH, user_id), "a").close()
    cups = open("%s/user_%d/cups.txt" % (DB_PATH, user_id), "r").read().strip()

    try:
        cups = int(cups)
    except ValueError:
        cups = 1
        update_cups_left(user_id, cups)

    return cups

def send_msg(user_id, text, buttons=[]):
    url = "https://api.telegram.org/bot%s/sendMessage" % BOT_TOKEN

    data = json.dumps({
        "chat_id": user_id,
        "text": text,
        "reply_markup": {
            "keyboard": [[{"text": t}] for t in buttons],
            "resize_keyboard": True,
        }
    })

    headers = {"Content-Type": "application/json"}

    ans = requests.post(url, data=data, headers=headers)
    if ans.status_code != 200:
        print("Failed to send msg to %d: %s" % (user_id, text), file=sys.stderr)
    return ans.status_code == 200


def get_machine_op_rate_wait(machine_id):
    RATE_LIMIT = 60

    try:
        os.mkdir("%s/machine_%d" % (DB_PATH, machine_id))
    except FileExistsError:
        pass

    open("%s/machine_%d/last_op.txt" % (DB_PATH, machine_id), "a").close()
    last_op_time = open("%s/machine_%d/last_op.txt" % (DB_PATH, machine_id), "r").read().strip()

    try:
        last_op_time = int(last_op_time)
    except ValueError:
        last_op_time = 0

    return max(0, RATE_LIMIT - int(time.time() - last_op_time))

def update_machine_op_time(machine_id):
    open("%s/machine_%d/last_op.txt" % (DB_PATH, machine_id), "w").write(str(int(time.time())))


def get_cups_by_code(code):
    if not re.fullmatch(r"[A-Z0-9_]+", code):
        return 0

    try:
        code_file = "%s/codes/%s.txt" % (DB_PATH, code)
        cups = int(open(code_file).read().strip())
        return cups
    except FileNotFoundError:
        return 0

def disable_code(code):
    if not re.fullmatch(r"[A-Z0-9_]+", code):
        return

    code_file = "%s/codes/%s.txt" % (DB_PATH, code)
    if os.path.exists(code_file):
        open(code_file, "w").write("0")

def create_code(code, amount):
    if not re.fullmatch(r"[A-Z0-9_]+", code):
        return False

    code_file = "%s/codes/%s.txt" % (DB_PATH, code)
    open(code_file, "w").write(str(amount))
    return True

def format_user(user):
    ans = user["first_name"]
    if "last_name" in user:
        ans += " " + user["last_name"]
    if "username" in user:
        ans += " aka " + user["username"]
    ans += " (%d)" % user["id"]
    return ans


def handle_request(request):
    msg = request["message"]
    msg_text = msg.get("text", "")
    if "from" not in msg or msg["from"]["is_bot"]:
        return

    msg_from = msg["from"]
    msg_from_id = int(msg_from["id"])

    cups_left = get_cups_left(msg_from_id)

    if msg_text == "☕":
        if cups_left == 0:
            send_msg(msg_from_id, "Для начала введите кофекод")
        else:
            send_msg(msg_from_id, "Осталось чашек: %d. Готовим?  " % cups_left +
                     "(автомат на шестом этаже матмеха)", ["✅", "❌"])
    elif msg_text == "✅":
        if cups_left == 0:
            send_msg(msg_from_id, "Для начала введите кофекод")
        else:
            wait_time = get_machine_op_rate_wait(MACHINE_ID)
            if wait_time > 0:
                send_msg(msg_from_id, "Слишком быстрые запросы, подождите %d сек." % wait_time, ["☕"])
            else:
                result = coffeeapi.buy_cofee(test_mode=True)
                if result:
                    cups_left -= 1
                    update_cups_left(msg_from_id, cups_left)
                    update_machine_op_time(MACHINE_ID)
                    send_msg(msg_from_id, "Команда ушла автомату", ["☕"])
                    send_msg(TG_ADMIN_ID, "Кофе доставлен пользователю %s" % format_user(msg_from))
                else:
                    send_msg(msg_from_id, "Ошибка при передаче команды автомату", ["☕"])
                    send_msg(TG_ADMIN_ID, "Ошибка доставки кофе пользователю %s" % format_user(msg_from))
    elif msg_text.upper().startswith("COFFEE_"):
        code = msg_text.upper()
        code_cups = get_cups_by_code(code)
        if code_cups > 0:
            cups_left += code_cups
            update_cups_left(msg_from_id, cups_left)

            send_msg(msg_from_id, "Хороший кофекод! Осталось чашек кофе: %d" % cups_left, ["☕"])
            disable_code(code)
        else:
            send_msg(msg_from_id, "Плохой кофекод :(", ["☕"])

    # administrative commands
    elif msg_from_id == TG_ADMIN_ID:
        m = re.fullmatch(r"/createcode\s+(COFFEE_[A-Z0-9_]+)\s+([0-9]+)", msg_text)
        if m:
            code = m.group(1)
            amount = int(m.group(2))
            if create_code(code, amount):
                send_msg(msg_from_id, "Кофекод создан")
            else:
                send_msg(msg_from_id, "Ошибка создания кофекода")
        else:
            send_msg(msg_from_id, "Хз", ["☕"])    

    else:
        send_msg(msg_from_id, "☕ ?", ["☕"])


def application(environ, start_response):
    if environ["REQUEST_METHOD"] != "POST":
        start_response("405 Method Not Allowed", RESP_HEADERS)
        return [json.dumps({"result": "bad method"}).encode()]

    try:
        request_body_size = int(environ.get('CONTENT_LENGTH', 0))
    except ValueError:
        request_body_size = 0
    request_body = environ['wsgi.input'].read(request_body_size)

    try:
        request = json.loads(request_body.decode("utf-8"))
    except json.decoder.JSONDecodeError:
        start_response("400 Bad Request", RESP_HEADERS)
        return [json.dumps({"result": "bad request",}).encode()]

    try:
        handle_request(request)
    except:
        traceback.print_exc()

    start_response("200 OK", RESP_HEADERS)
    return [b""]
