from gateway.gateway import sendSerial
import paho.mqtt.client as mqttclient
import time
import json
import serial.tools.list_ports

TIMER_CYCLE = 10  # milisecond
timer_counter = 0
timer_flag = 0


def software_timer_init():
    global timer_counter, timer_flag
    timer_counter = 0
    timer_flag = 0


def get_timer_flag():
    return timer_flag


def set_timer(duration):
    global timer_counter, timer_flag
    if (timer_counter == 0):
        timer_flag = 0
        timer_counter = duration / TIMER_CYCLE


def run_timer():
    global timer_counter, timer_flag
    if (timer_counter > 0):
        timer_counter = timer_counter - 1
        if (timer_counter == 0):
            timer_flag = 1


"""
FSM
"""
IDLE = 0
SEND_DATA = 1
WAIT_ACK = 2
SEND_ACK = 3
ERROR_LOG = 4

state = IDLE
SEND_MAX = 5
SEND_INTERVAL = 100  # milisecond
counter_failure = 0

serial_data_available = 0
mqtt_data_available = 0
ack_received_successful = 0

"""
MQTT and SERIAL
"""
BROKER_ADDRESS = 'demo.thingsboard.io'
PORT = 1883
mess = ''

cmd = 1

THINGS_BOARD_ACCESS_TOKEN = 'iQ9yDkYe5YnwTqaTeB8N'
bbc_port = 'COM4'
if len(bbc_port) > 0:
    ser = serial.Serial(port=bbc_port, baudrate=115200)


def processData(data):
    data = data.replace('!', '')
    data = data.replace('#', '')
    splitData = data.split(':')
    print(splitData)
    serialized_data = {}
    serialized_data[splitData[1]] = splitData[2]
    return serialized_data


def read_serial():
    bytesToRead = ser.inWaiting()
    if (bytesToRead > 0):
        global mess, serial_data_available, ack_received_successful
        mess = mess + ser.read(bytesToRead).decode('UTF-8')
        if ('#' in mess) and ('!' in mess):
            start = mess.find('!')
            end = mess.find('#')
            serialized_data = processData(mess[start:end + 1])
            if (serialized_data['ACK'] == '1'):
                ack_received_successful = 1
            else:
                client.publish('v1/devices/me/telemetry',
                               json.dumps(serialized_data), 1)
                serial_data_available = 1
            mess = '' if end == len(mess) else mess[end + 1:]


def send_serial(data):
    if len(bbc_port) <= 0:
        return 0

    ser.write((data + '#').encode())
    return 1


def subscribed(client, userdata, mid, granted_qos):
    print('Subscribed...')


def recv_message(client, userdata, message):
    global mqtt_data_available, cmd
    print('Received: ', message.payload.decode('utf-8'))
    temp_data = {'value': True}

    try:
        jsonobj = json.loads(message.payload)
        if jsonobj['method'] == 'setLED':
            # set cmd for Microblit platform
            cmd = 1 if (jsonobj['params'] == True) else 0
            # send feedback to update button in Thingsboard via attribute getLED
            temp_data['getLED'] = jsonobj['params']
            client.publish('v1/devices/me/attributes',
                           json.dumps(temp_data), 1)

        if jsonobj['method'] == 'setFAN':
            cmd = 3 if (jsonobj['params'] == True) else 2
            temp_data['getFAN'] = jsonobj['params']
            client.publish('v1/devices/me/attributes',
                           json.dumps(temp_data), 1)

        mqtt_data_available = 1
    except:
        pass


def connected(client, usedata, flags, rc):
    if rc == 0:
        print('Thingsboard connected successfully!!')
        client.subscribe('v1/devices/me/rpc/request/+')
    else:
        print('Connection is failed')


client = mqttclient.Client('Gateway_Thingsboard')
client.username_pw_set(THINGS_BOARD_ACCESS_TOKEN)

client.on_connect = connected
client.connect(BROKER_ADDRESS, 1883)
client.loop_start()

client.on_subscribe = subscribed
client.on_message = recv_message

# Run Stop and Wait FSM
software_timer_init()
while True:
    if state == IDLE:
        read_serial()
        if serial_data_available == 1:
            serial_data_available = 0
            state = SEND_ACK
        elif mqtt_data_available == 1:
            mqtt_data_available = 0
            state = SEND_DATA

    elif state == SEND_DATA:
        if send_serial(cmd) == 1:
            set_timer(SEND_INTERVAL)
            state = WAIT_ACK

    elif state == WAIT_ACK:
        read_serial()
        if ack_received_successful == 1:
            state = IDLE
        elif get_timer_flag() == 1:
            counter_failure = counter_failure + 1
            if counter_failure >= SEND_MAX:
                counter_failure = 0
                state = ERROR_LOG
            else:
                state = SEND_DATA

    elif state == SEND_ACK:
        if send_serial('ACK') == 1:
            state = IDLE

    elif state == ERROR_LOG:
        print('send failed')
        state = IDLE

    run_timer()
    time.sleep(TIMER_CYCLE / 1000)
