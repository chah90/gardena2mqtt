import asyncio
import logging
import time
import os
import signal
from threading import Thread
import json
from gardena.smart_system import SmartSystem
import paho.mqtt.client as mqtt

def publish_hass_discovery_gardena2mqtt():
    mqttclient.publish(f"{homeassistantdiscoverytopic}/binary_sensor/gardena2mqtt_Connectivity/config", json.dumps({
        "~": mqttprefix,
        "name": "Gardena2MQTT",
        "unique_id": "gardena2mqtt_connectivity",
        "state_topic": "~/connected",
        "device_class": "connectivity",
        "entity_category": "diagnostic",
        "value_template": "{{ iif(int(value) > 0, 'ON', 'OFF') }}",
        "device": {
            "name": "Gardena2MQTT",
            "manufacturer": "Domochip",
            "sw_version": versionnumber,
            "identifiers": ["gardena2mqtt"]
        }
    }))

def publish_hass_discovery_mower(device):
    # Lawn Mower
    mqttclient.publish(f"{homeassistantdiscoverytopic}/lawn_mower/gardena2mqtt_{device.serial}/config", json.dumps({
        "~": f"{mqttprefix}/{device.name}",
        "name": "Lawn Mower",
        "unique_id": device.serial,
        "activity_state_topic": "~",
        "activity_value_template": "{% if value_json.activity in ['OK_CUTTING','OK_CUTTING_TIMER_OVERRIDDEN','OK_SEARCHING','OK_LEAVING','OK_CHARGING'] %}mowing{% elif value_json.activity in ['PAUSED'] %}paused{% elif value_json.activity in ['PARKED_TIMER','PARKED_PARK_SELECTED','PARKED_AUTOTIMER'] %}docked{% elif value_json.activity in ['NONE'] %}error{% else %}unknown{% endif %}",
        "availability": {
            "topic": f"{mqttprefix}/connected",
            "value_template": "{{ iif(int(value) > 1, 'online', 'offline') }}"
        },
        "device": {
            "name": device.name,
            "manufacturer": "Gardena",
            "model": "GARDENA smart Mower",
            "identifiers": [device.serial, device.id]
        },
        "dock_command_topic": f"~/command",
        "dock_command_template": '{"command":"park_until_next_task"}',
        "pause_command_topic": f"~/command",
        "pause_command_template": '{"command":"park_until_further_notice"}',
        "start_mowing_command_topic": f"~/command",
        "start_mowing_command_template": '{"command":"start_dont_override"}'
    }))
    # Connectivity
    mqttclient.publish(f"{homeassistantdiscoverytopic}/binary_sensor/gardena2mqtt_{device.serial}_Connectivity/config", json.dumps({
        "~": mqttprefix,
        "name": "Connectivity",
        "unique_id": f"{device.serial}_connectivity",
        "state_topic": "~/connected",
        "device_class": "connectivity",
        "entity_category": "diagnostic",
        "value_template": "{{ iif(int(value) > 1, 'ON', 'OFF') }}",
        "device": {
            "name": device.name,
            "manufacturer": "Gardena",
            "model": "GARDENA smart Mower",
            "identifiers": [device.serial, device.id]
        }
    }))
    # Battery
    mqttclient.publish(f"{homeassistantdiscoverytopic}/sensor/gardena2mqtt_{device.serial}_Battery/config", json.dumps({
        "~": f"{mqttprefix}/{device.name}",
        "name": "Battery",
        "unique_id": f"{device.serial}_battery",
        "state_topic": "~",
        "value_template": "{{ value_json.battery_level }}",
        "device_class": "battery",
        "availability": {
            "topic": f"{mqttprefix}/connected",
            "value_template": "{{ iif(int(value) > 1, 'online', 'offline') }}"
        },
        "device": {
            "name": device.name,
            "manufacturer": "Gardena",
            "model": "GARDENA smart Mower",
            "identifiers": [device.serial, device.id]
        },
        "unit_of_measurement": "%"
    }))

def publish_device(device):
    infos = {"datetime":time.strftime("%Y-%m-%d %H:%M:%S")}
    for attrName in vars(device):
        if not attrName.startswith('_') and attrName not in ('location', 'callbacks'):
            infos[attrName] = getattr(device, attrName)
    mqttclient.publish(f"{mqttprefix}/{device.name}", json.dumps(infos))

def publish_everything():
    global location
    for device in location.devices.values():
        if homeassistant:
            match device.type:
                case "MOWER":
                    publish_hass_discovery_mower(device)
                case _:
                    # todo
                    pass
        publish_device(device)

def subscribe_device(device):
    if mqttclientconnected:
        mqttclient.subscribe(f"{mqttprefix}/{device.name}/control")

def subscribe_everything():
    global location
    for device in location.devices.values():
        subscribe_device(device)


# callback when the broker responds to our connection request.
def on_mqtt_connect(client, userdata, flags, reason_code, properties):
    global mqttclientconnected
    mqttclientconnected = True
    logging.info("Connected to MQTT host")
    if homeassistant:
        publish_hass_discovery_gardena2mqtt()
    subscribe_everything()
    if not smartsystemclientconnected:
        mqttclient.publish(f"{mqttprefix}/connected", "1", 0, True)
    else:
        mqttclient.publish(f"{mqttprefix}/connected", "2", 0, True)
        publish_everything()


# callback when the client disconnects from the broker.
def on_mqtt_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    global mqttclientconnected
    mqttclientconnected = False
    logging.info("Disconnected from MQTT host")
    
# callback when a message has been received on a topic that the client subscribes to.
def on_mqtt_message(client, userdata, msg):

    global location

    splittedTopic = msg.topic.split('/')
    splittedTopic[len(splittedTopic)-1] = 'result'
    resultTopic = '/'.join(splittedTopic)

    try:
        decodedPayload = msg.payload.decode('utf-8')
    except:
        logging.error('Message skipped: payload %s is not valid on topic %s', msg.payload.hex(), msg.topic)
        mqttclient.publish(resultTopic, json.dumps({"result":"error", "reason":"Message ignored as payload can't be decoded", "datetime":time.strftime("%Y-%m-%d %H:%M:%S"), "request":msg.payload.hex()}, ensure_ascii=False))
        return

    # looking for the right device
    thisDeviceName = splittedTopic[len(splittedTopic)-2]
    for device in location.devices.values():
        if device.name == thisDeviceName:
            thisDevice = device
    
    # parse payload
    try:
        parsedPayload = json.loads(decodedPayload)
    except:
        logging.error(f'Incorrect JSON received : {decodedPayload}')
        mqttclient.publish(resultTopic, json.dumps({"result":"error", "reason":"Incorrect JSON received", "datetime":time.strftime("%Y-%m-%d %H:%M:%S"), "request":decodedPayload}, ensure_ascii=False))
        return

    if 'command' not in parsedPayload:
        logging.error(f'command missing in payload received : {decodedPayload}')
        mqttclient.publish(resultTopic, json.dumps({"result":"error", "reason":"command missing in payload received", "datetime":time.strftime("%Y-%m-%d %H:%M:%S"), "request":decodedPayload}, ensure_ascii=False))
        return

    if not type(parsedPayload['command']) is str:
        logging.error(f'Incorrect command in payload received : {decodedPayload}')
        mqttclient.publish(resultTopic, json.dumps({"result":"error", "reason":"Incorrect command in payload received", "datetime":time.strftime("%Y-%m-%d %H:%M:%S"), "request":decodedPayload}, ensure_ascii=False))
        return

    # looking for the method requested
    try:
        thisDeviceMethod = getattr(thisDevice, parsedPayload['command'])
    except:
        logging.error(f'command received doesn\'t exists for this device: {decodedPayload}')
        mqttclient.publish(resultTopic, json.dumps({"result":"error", "reason":"command received doesn\'t exists for this device", "datetime":time.strftime("%Y-%m-%d %H:%M:%S"), "request":decodedPayload}, ensure_ascii=False))
        return

    if not callable(thisDeviceMethod):
        logging.error(f'command received doesn\'t exists for this device: {decodedPayload}')
        mqttclient.publish(resultTopic, json.dumps({"result":"error", "reason":"command received doesn\'t exists for this device", "datetime":time.strftime("%Y-%m-%d %H:%M:%S"), "request":decodedPayload}, ensure_ascii=False))
        return

    params = []

    # looking fore required params
    listOfParam = list(thisDeviceMethod.__code__.co_varnames)
    for paramName in thisDeviceMethod.__code__.co_varnames:
        if paramName not in ('self', 'data'):
            try:
                params.append(parsedPayload[paramName])
            except:
                logging.error(f'The parameter {paramName} is missing. command can\'t be executed')
                mqttclient.publish(resultTopic, json.dumps({"result":"error", "reason":f'The parameter {paramName} is missing. command can\'t be executed', "datetime":time.strftime("%Y-%m-%d %H:%M:%S"), "request":decodedPayload}, ensure_ascii=False))
                return

    # run the command
    try:
        if len(params) == 0:
            asyncio.run(thisDeviceMethod())
        elif len(params) == 1:
            asyncio.run(thisDeviceMethod(params[0]))
        elif len(params) == 2:
            asyncio.run(thisDeviceMethod(params[0], params[1]))
    except:
        logging.exception(f'execution of the command failed: {decodedPayload}')
        mqttclient.publish(resultTopic, json.dumps({"result":"error", "reason":"execution of the command failed", "datetime":time.strftime("%Y-%m-%d %H:%M:%S"), "request":decodedPayload}, ensure_ascii=False))
        return

    mqttclient.publish(resultTopic, json.dumps({"result":"success", "datetime":time.strftime("%Y-%m-%d %H:%M:%S"), "request":parsedPayload}, ensure_ascii=False))

def on_ws_status_changed(status):
    global smartsystemclientconnected
    logging.info(f'WebSocket status : {status}')
    smartsystemclientconnected = status
    if mqttclientconnected:
        mqttclient.publish(f"{mqttprefix}/connected", ("2" if smartsystemclientconnected else "1"), 0, True)
        if status:
            publish_everything()

def on_device_update(device):
    print(f"The device {device.name} has been updated !")
    if mqttclientconnected:
        publish_device(device)

def shutdown(signum=None, frame=None):
    eventloop.stop()





if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s: %(message)s", level=logging.INFO, datefmt="%H:%M:%S")

    versionnumber = '1.6.0'

    logging.info(f'===== gardena2mqtt v{versionnumber} =====')

    # devmode is used to start container but not the code itself, then you can connect interactively and run this script by yourself
    # docker exec -it gardena2mqtt /bin/sh
    if os.getenv("DEVMODE", 0) == "1":
        logging.info('DEVMODE mode : press Enter to continue')
        try:
            input()
            logging.info('')
        except EOFError as e:
            # EOFError means we're not in interactive so loop forever
            while 1:
                time.sleep(3600)

    gardenaclientid = os.getenv("GARDENA_CLIENT_ID")
    gardenaclientsecret = os.getenv("GARDENA_CLIENT_SECRET")
    mqttprefix = os.getenv("MQTT_PREFIX", "gardena2mqtt")
    mqtthost = os.getenv("MQTT_HOST", "localhost")
    mqttport = os.getenv("MQTT_PORT", 1883)
    mqttclientid = os.getenv("MQTT_CLIENTID", "gardena2mqtt")
    mqttuser = os.getenv("MQTT_USER")
    mqttpassword = os.getenv("MQTT_PASSWORD")
    homeassistant = os.getenv("HOMEASSISTANT", 1)
    homeassistantdiscoverytopic = os.getenv("HOMEASSISTANT_DISCOVERY_TOPIC", "homeassistant")

    logging.info(f"Use mqtt config {mqtthost}:{mqttport}")

    logging.info('===== Prepare MQTT Client =====')
    mqttclient = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, mqttclientid)
    mqttclient.username_pw_set(mqttuser, mqttpassword)
    mqttclient.on_connect = on_mqtt_connect
    mqttclient.on_disconnect = on_mqtt_disconnect
    mqttclient.on_message = on_mqtt_message
    mqttclient.will_set(f"{mqttprefix}/connected", "0", 0, True)
    mqttthread = Thread(target=mqttclient.loop_forever)

    mqttclientconnected = False


    logging.info('===== Prepare SmartSystem Client =====')
    logging.info(' - create')
    smart_system = SmartSystem(client_id=gardenaclientid, client_secret=gardenaclientsecret)
    eventloop = asyncio.new_event_loop()

    # register signal handlers to stop the container
    eventloop.add_signal_handler(signal.SIGINT, shutdown)
    eventloop.add_signal_handler(signal.SIGTERM, shutdown)

    logging.info(' - authenticate')
    eventloop.run_until_complete(smart_system.authenticate())
    logging.info(' - update location list')
    eventloop.run_until_complete(smart_system.update_locations())

    location = list(smart_system.locations.values())[0]

    logging.info(' - update device list')
    eventloop.run_until_complete(smart_system.update_devices(location))

    # add callbacks
    smart_system.add_ws_status_callback(on_ws_status_changed)
    for device in location.devices.values():
        device.add_callback(on_device_update)

    smartsystemclientconnected = False


    logging.info('===== Connection To MQTT Broker =====')
    mqttclient.connect(mqtthost, mqttport)
    mqttthread.start()

    # Wait up to 5 seconds for MQTT connection
    for i in range(50):
        if mqttclientconnected:
            break
        time.sleep(0.1)

    if not mqttclientconnected:
        logging.error('Failed to connect to MQTT broker')
        exit(1)


    logging.info('===== Connection To Gardena SmartSystem =====')
    wstask = eventloop.create_task(smart_system.start_ws(location))

    # mqtt is running in a separate Thread and now main one is executing smart_system in event loop (waiting for a stop)
    eventloop.run_forever()

    # stop the smart system
    eventloop.run_until_complete(smart_system.quit())
    # # wait for the websocket task to finish
    # eventloop.run_until_complete(wstask)

    # due to a bug in the library (1.3.9 currently), we need to cancel the task and then run the event loop until it's done
    wstask.cancel()
    try:
        eventloop.run_until_complete(wstask)
    except:
        pass

    eventloop.close()

    if mqttclientconnected:
        mqttclient.publish(f"{mqttprefix}/connected", "0", 0, True)
    mqttclient.disconnect()
    mqttthread.join()
