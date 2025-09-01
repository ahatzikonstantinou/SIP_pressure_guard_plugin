import os
import json
import time
import gv
from urls import urls  # Get access to SIP's URLs
import web
from sip import template_render  #  Needed for working with web.py templates
from webpages import ProtectedPage
from plugins import mqtt


DATA_FILE = u"./data/pressure_guard.json"


# Add new URLs to access classes in this plugin.
# fmt: off
urls.extend([
    u"/pressure-guard-get-data", u"plugins.pressure_guard.get_pressure_data",
    u"/pressure-guard-publish-mqtt", u"plugins.pressure_guard.publish_mqtt",
    u"/pressure-guard-save-all-settings", u"plugins.pressure_guard.save_all_settings",
    u"/pressure-guard-get-settings", u"plugins.pressure_guard.get_settings"
    ])
# fmt: on 


if not hasattr(gv, "master_block_rules"):
    gv.master_block_rules = {}


# Add this plugin to the PLUGINS menu ["Menu Name", "URL"], (Optional)
gv.plugin_menu.append([_(u"Pressure Guard Plugin"), u"/pressure-guard-get-settings"])


# Plugin state
pressure_value = None
pressure_timestamp = None
gv.master_blocked = [False] * gv.sd["nst"]
settings = {
    "mqtt": {
        "publish": "",
        "subscribe": ""
    },
    "rules": {}
}
# settings = {}  # {station_index: {"op": ">", "val": 1.2}}


# MQTT setup
subscribe_topic = "sensors/pressure"
publish_topic = "commands/pump"


def fill_gv():
    gv.master_blocked = [False] * gv.sd["nst"]

    if not pressure_value:
        return
    
    for sid_str, rule in settings["rules"].items():
        sid = int(sid_str)  # station index (1-based)
        op = rule["op"]
        val = rule["val"]

        if op == "<":
            gv.master_blocked[sid - 1] = pressure_value < val
        elif op == ">":
            gv.master_blocked[sid - 1] = pressure_value > val
        elif op == "=":
            gv.master_blocked[sid - 1] = pressure_value == val
        elif op == "!=":
            gv.master_blocked[sid - 1] = pressure_value != val
        elif op == "<=":
            gv.master_blocked[sid - 1] = pressure_value <= val
        elif op == ">=":
            gv.master_blocked[sid - 1] = pressure_value >= val

    print(f"Filled gv.master_blocked: {json.dumps(gv.master_blocked)}")


# Load settings from file
def load_settings():
    global settings
    if os.path.exists(DATA_FILE):
        print( f"Pressure Guard data file {DATA_FILE} exists")
        with open(DATA_FILE) as f:
            settings = json.load(f)
            print(f"Loaded settings: {json.dumps(settings, indent=4, sort_keys=True)}")
    else:
        print( "Pressure Guard data file {DATA_FILE} does NOT exists")
        # Initialize default structure if file doesn't exist
        settings = {
            "mqtt": {
                "publish": "",
                "subscribe": ""
            },
            "rules": {}
        }
    update_mqtt_subscription(settings["mqtt"]["subscribe"])
    fill_gv()


def update_mqtt_subscription(topic):
    if not hasattr(update_mqtt_subscription, "subscribe_topic"):
        print(f"Initializing subscribe_topic = None")
        update_mqtt_subscription.subscribe_topic = None  # initialize once

    if mqtt and mqtt.is_connected() and update_mqtt_subscription.subscribe_topic:
        print(f"Unsubscribe({update_mqtt_subscription.subscribe_topic})")
        mqtt.unsubscribe(update_mqtt_subscription.subscribe_topic)

    if topic.strip():
        print(f"Will subscribe to topic '{topic}'")
        if mqtt.is_connected():
            mqtt.subscribe(topic, on_message, 2)
            update_mqtt_subscription.subscribe_topic = topic
        else:
            print(f"Mqtt is not connected: {mqtt.is_connected()}")
    else:
        print(f"New topic is empty '{topic}'")

load_settings()


def on_message(client, msg):
    global pressure_value, pressure_timestamp
    try:
        pressure_value = float(msg.payload.decode())
        pressure_timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        # for i, name in enumerate(gv.snames):
        #     if (i + 1) in gv.sd["mas"] and i in settings["rules"]:
        #         rule = settings["rules"][i]
        #         op = rule["op"]
        #         val = rule["val"]
        #         gv.master_blocked[i] = not eval(f"{pressure_value} {op} {val}")
        print(f"Received mqtt {msg.payload}")
        fill_gv()
    except Exception as e:
        print("MQTT error:", e)


# Main plugin page
class master_guard(ProtectedPage):
    def GET(self):
        return open("plugins/master_guard/templates/master_guard.html")


# Endpoint: get pressure
class get_pressure_data(ProtectedPage):
    def GET(self):
        return json.dumps('{ "pressure": pressure_value, "timestamp": pressure_timestamp}')


# Endpoint: publish empty MQTT message
class publish_mqtt(ProtectedPage):
    def POST(self):
        q = web.input()
        topic = q.get("topic", "")
        try:
            mqtt.publish(topic, "")
            return json.dumps({"success": True, "topic": topic})
        except Exception as e:
            return json.dumps({"success": False, "topic": topic, "error": str(e)})


# Endpoint: get settings
class get_settings(ProtectedPage):
    def GET(self):
        load_settings()
        print(f"Sending settings: {json.dumps(settings)}")
        return template_render.pressure_guard(json.dumps(settings), gv.snames, gv.sd['mas'])  # open settings page


class save_all_settings(ProtectedPage):
    def POST(self):
        global settings
        try:
            data = json.loads(web.data())
            print(f"Saving: {json.dumps(data, indent=4)}")
            settings["mqtt"]["subscribe"] = data.get("subscribe", "")
            settings["mqtt"]["publish"] = data.get("publish", "")

            settings["rules"] = {}  # start clean
            rules = data.get("rules", {})
            for sid_str, rule in rules.items():
                sid = int(sid_str)
                op = rule.get("op")
                val = float(rule.get("val", 0))
                # print(json.dumps(settings, indent=4, sort_keys=True))
                # print(f"sid: {sid}, op: {op}, val: {val}")
                settings["rules"][sid] = {"op": op, "val": val}

            fill_gv()
            update_mqtt_subscription(settings["mqtt"]["subscribe"])
            print(f"Final: {json.dumps(settings, indent=4)}", )

            #Save to file
            with open(DATA_FILE, u"w") as f:
                json.dump(settings, f, indent=4)            

            return json.dumps({"success": True})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
