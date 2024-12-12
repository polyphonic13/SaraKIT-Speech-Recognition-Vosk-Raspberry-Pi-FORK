# sudo apt-get install pip
# sudo apt-get install -y python3-pyaudio
# sudo pip3 install vosk

import os
import sys
import json
import contextlib
import pyaudio
import io
from vosk import Model, KaldiRecognizer

# mqtt
import paho.mqtt.client as mqtt

MQTT_SECRET_FILE = "../mqtt-secret.json"
mqttFile = open(MQTT_SECRET_FILE)
mqttData = json.load(mqttFile)

def onConnect(c, userdata, flags, rc):
    global client
    print(
        "[INFO] Connected with result code "
        + str(rc)
        + " is connected = "
        + str(client.is_connected())
    )
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(mqttData["topic"])

def publish(message):
    print("[INFO] publishing " + message)
    global client
    ret = client.publish(mqttData["topic"], message)

def publishTimeout():
    global isCommandReceived
    print("[INFO] done with pause; publishing timeout")
    publish(keywordTimeout)
    isCommandReceived = False

def publishActivityTimeout():
    global isKeyPhraseActive, isCommandReceived, keywordTimeout
    # time.sleep(KEY_PHRASE_TIMEOUT_DURATION)
    publish(keywordTimeout)
    isKeyPhraseActive = False
    isCommandReceived = False

    print("[INFO] listening resumed")

def onPublish(c, userData, result):
    # print("[INFO] published \n")
    pass

def onMessage(c, userdata, message):
    global isAwake, isJustCompletedActivity, isRespondingToGratitude
    print(
        "[INFO] mqtt message received: " + message.topic + " : " + str(message.payload)
    )
    msg = str(message.payload)

def onDisconnect(c, userData, message):
    print("[WARNING] mqtt disconnected")
    client.reconnect()

client = mqtt.Client()  # create new instance
client.username_pw_set(
    mqttData["user"], mqttData["password"]
)  # set username and password
client.on_connect = onConnect  # attach function to callback
client.on_message = onMessage  # attach function to callback
client.on_publish = onPublish
client.on_disconnect = onDisconnect
print("[INFO] about to call connect on mqtt client")
client.connect(mqttData["broker"], port=mqttData["port"])  # connect to broker
client.loop_start()

# Path to the Vosk model
#model_path = "models/vosk-model-small-pl-0.22/"
model_path = "models/vosk-model-small-en-us-0.15/"
if not os.path.exists(model_path):
    print(f"Model '{model_path}' was not found. Please check the path.")
    exit(1)

model = Model(model_path)

# Settings for PyAudio
sample_rate = 16000
chunk_size = 8192
format = pyaudio.paInt16
channels = 1

# Initialization of PyAudio and speech recognition
p = pyaudio.PyAudio()
stream = p.open(format=format, channels=channels, rate=sample_rate, input=True, frames_per_buffer=chunk_size)
recognizer = KaldiRecognizer(model, sample_rate)

os.system('clear')
print("\nSpeak now...")

while True:
    data = stream.read(chunk_size)
    if recognizer.AcceptWaveform(data):
        result_json = json.loads(recognizer.Result())
        text = result_json.get('text', '')
        if text:
            print("\r" + text, end='\n')
    else:
        partial_json = json.loads(recognizer.PartialResult())
        partial = partial_json.get('partial', '')
        sys.stdout.write('\r' + partial)
        sys.stdout.flush()
