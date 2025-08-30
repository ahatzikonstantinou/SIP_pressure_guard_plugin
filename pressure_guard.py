import json
import time
import gv
from urls import urls  # Get access to SIP's URLs
import web
from sip import template_render  #  Needed for working with web.py templates
from webpages import ProtectedPage
from plugins import mqtt

# Add new URLs to access classes in this plugin.
# fmt: off
urls.extend([
    u"/pressure-guard-get-data", u"plugins.pressure_guard.get_pressure_data",
    u"/pressure-guard-publish-mqtt", u"plugins.pressure_guard.publish_mqtt",
    u"/pressure-guard-save-settings", u"plugins.pressure_guard.save_settings",
    u"/pressure-guard-get-settings", u"plugins.pressure_guard.get_settings"
    ])
# fmt: on 

# Add this plugin to the PLUGINS menu ["Menu Name", "URL"], (Optional)
gv.plugin_menu.append([_(u"Pressure Guard Plugin"), u"/pressure-guard-get-settings"])

# Plugin state
pressure_value = None
pressure_timestamp = None
gv.master_blocked = [False] * gv.sd["nst"]
settings = {}  # {station_index: {"op": ">", "val": 1.2}}

# MQTT setup
subscribe_topic = "sensors/pressure"
publish_topic = "commands/pump"

def on_message(client, userdata, msg):
    global pressure_value, pressure_timestamp
    try:
        pressure_value = float(msg.payload.decode())
        pressure_timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        for i, name in enumerate(gv.snames):
            if (i + 1) in gv.sd["mas"] and i in settings:
                rule = settings[i]
                op = rule["op"]
                val = rule["val"]
                gv.master_blocked[i] = not eval(f"{pressure_value} {op} {val}")
    except Exception as e:
        print("MQTT error:", e)

mqtt.subscribe(subscribe_topic, on_message, 2)

# Main plugin page
class master_guard(ProtectedPage):
    def GET(self):
        return open("plugins/master_guard/templates/master_guard.html")

# Endpoint: get pressure
class get_pressure_data(ProtectedPage):
    def GET(self):
        return json.dumps({
            "pressure": pressure_value,
            "timestamp": pressure_timestamp
        })

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

# Endpoint: save settings
class save_settings(ProtectedPage):
    def POST(self):
        q = web.input()
        sid = int(q.get("sid"))
        op = q.get("op")
        val = float(q.get("val"))
        settings[sid] = {"op": op, "val": val}
        return json.dumps({"success": True})

# Endpoint: get settings
class get_settings(ProtectedPage):
    def GET(self):
        # return json.dumps(settings)
        return template_render.pressure_guard(settings, gv.snames, gv.sd['mas'])  # open settings page
