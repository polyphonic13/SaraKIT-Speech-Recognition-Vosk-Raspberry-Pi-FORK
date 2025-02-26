# sudo apt-get install pip
# sudo apt-get install -y python3-pyaudio
# sudo pip3 install vosk

import argparse
import os
import sys
import json
import contextlib
import pyaudio
import io
from vosk import Model, KaldiRecognizer
import time
import threading as th
import RPi.GPIO as GPIO
import paho.mqtt.client as mqtt

appreciationKeywords = ["thank", "thanks", "gracias"]

isMQTTConnected = False
isNightModeActive = False
isKeyPhraseActive = False
isCommandReceived = False
isJustCompletedActivity = False
isRespondingToGratitude = False
isPromptStateActive = False
text = ""
# sleep for 3 seconds after keyphrase received to prevent listening to jorge's speech during command
KEY_PHRASE_TIMEOUT_DURATION = 3
THREAD_TIMER_DURATION = 5
# pause after hearing command
COMMAND_TIMEOUT_DURATION = 2
COMMAND_PREFIX = "spokenCommand: "
KEYWORD_HEARD = "keywordHeard"
KEYWORD_TIMEOUT = "keywordTimeout"
APPRECIATION_HEARD = "appreciationHeard"
PROMPT_STATE_TIMEOUT = "promptStateTimeout"

# region LED
LED_PIN = 6
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(LED_PIN, GPIO.OUT)
# testing
GPIO.output(LED_PIN, GPIO.HIGH)

# endregion

keywordPhrases = [
    "hey george",
    "yo george",
    "ey george",
    "who george",
    "he george",
    "her george",
    "hey jorge",
    "ey jorge",
    "yo jorge",
    "her jorge",
    "hey whore hey",
    "hey your head",
    "hey or hey",
    "hey whore her",
    "her or her",
    "hey or her",
    "a jorge",
    "ay jorge",
    "hurry jorge",
    "hey your hey",
    "pay more hey",
    "hey warhead",
]

# region mqtt
MQTT_SECRET_FILE = "../mqtt-secret.json"
mqttFile = open(MQTT_SECRET_FILE)
mqttData = json.load(mqttFile)


def onConnect(c, userdata, flags, rc):
    global client, isMQTTConnected
    print(
        "[INFO] Connected with result code "
        + str(rc)
        + " is connected = "
        + str(client.is_connected())
    )
    isMQTTConnected = True
    if not isNightModeActive:
        print("[INFO] publishing isNightModeActive = False")
        # GPIO.output(LED_PIN, GPIO.HIGH)
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(mqttData["incomingTopic"])


def publish(message):
    print("[INFO] publishing " + message)
    global client
    ret = client.publish(mqttData["outgoingTopic"], message)


def publishTimeout():
    global isCommandReceived
    print("[INFO] done with pause; publishing timeout")
    publish(KEYWORD_TIMEOUT)
    isCommandReceived = False


def publishActivityTimeout():
    global isKeyPhraseActive, isCommandReceived, KEYWORD_TIMEOUT
    publish(KEYWORD_TIMEOUT)
    isKeyPhraseActive = False
    isCommandReceived = False

    print("[INFO] listening resumed")


def onPublish(c, userData, result):
    # print("[INFO] published \n")
    pass


def onMessage(c, userdata, message):
    global isAwake, isJustCompletedActivity, isRespondingToGratitude, isPromptStateActive, isNightModeActive
    print(
        "[INFO] mqtt message received: " + message.topic + " : " + str(message.payload)
    )
    msg = str(message.payload)
    if "commandFailed" in msg:
        print("[INFO] commandFailed received")
        isJustCompletedActivity = False
    elif "speechEnded" in msg or "activityCompleted" in msg:
        print("[INFO] speechEnded received, about to call setIdle")
        if isPromptStateActive:
            print("[INFO] prompt state still active")
        elif isRespondingToGratitude:
            isRespondingToGratitude = False
        else:
            isJustCompletedActivity = True
            timer = th.Timer(THREAD_TIMER_DURATION * 2, setIsJustCompletedActivityFalse)
            timer.start()
    elif "setPromptStateActive" in msg:
        print("[INFO] promptActive received, about to call setIsInPromptState")
        isPromptStateActive = True
        # give user 15 seconds to respond
        timer = th.Timer(THREAD_TIMER_DURATION * 3, setIsPromptActiveFalse)
        timer.start()
    elif "beginNightMode" in msg:
        isNightModeActive = True
        GPIO.output(LED_PIN, GPIO.LOW)
    elif "endNightMode" in msg:
        isNightModeActive = False
        if isMQTTConnected:
            GPIO.output(LED_PIN, GPIO.HIGH)


def onDisconnect(c, userData, message):
    print("[WARNING] mqtt disconnected")
    # GPIO.output(LED_PIN, GPIO.LOW)
    isMQTTConnected = False
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
# endregion


def setIsJustCompletedActivityFalse():
    global isJustCompletedActivity
    print("[INFO] setting isJustCompletedActivity to False")
    isJustCompletedActivity = False


def setIsPromptActiveFalse():
    global isPromptStateActive
    isPromptStateActive = False
    publish(PROMPT_STATE_TIMEOUT)


# Path to the Vosk model
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
stream = p.open(
    format=format,
    channels=channels,
    rate=sample_rate,
    input=True,
    frames_per_buffer=chunk_size,
)
recognizer = KaldiRecognizer(model, sample_rate)

os.system("clear")
print("\nSpeak now...")

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    "-l",
    "--list-devices",
    action="store_true",
    help="show list of audio devices and exit",
)

try:
    while True:
        data = stream.read(chunk_size)
        if recognizer.AcceptWaveform(data):
            result_json = json.loads(recognizer.Result())
            text = result_json.get("text", "")
            if text:
                print("\r" + text, end="\n")
                if isPromptStateActive:
                    concat = COMMAND_PREFIX + text[l:]
                    publish(concat)
                    isPromptStateActive = False
                elif not isKeyPhraseActive:
                    print(
                        "key phrase not active, isJustCompletedActivity = "
                        + str(isJustCompletedActivity)
                    )
                    for kwp in keywordPhrases:
                        if isJustCompletedActivity:
                            for aws in appreciationKeywords:
                                if aws in text:
                                    if not isRespondingToGratitude:
                                        isRespondingToGratitude = True
                                        print(
                                            "about to publish APPRECIATION_HEARD message"
                                        )
                                        publish(APPRECIATION_HEARD)
                        elif kwp in text:
                            print(
                                "[INFO] keyword phrase found, isCommandReceived = "
                                + str(isCommandReceived)
                            )
                            publish(KEYWORD_HEARD)
                            # keyphrase and command received together
                            l = len(kwp) + 1
                            if len(text) > l:
                                # isCommandReceived = True
                                # isKeyPhraseActive = False
                                print("[INFO] command received with keyword phrase")
                                # publish(text[l:])
                                concat = COMMAND_PREFIX + text[l:]
                                text = ""
                                print(
                                    "[INFO] going to publish "
                                    + concat
                                    + " to topic: "
                                    + mqttData["outgoingTopic"]
                                    + " is connected = "
                                    + str(client.is_connected())
                                )
                                publish(concat)
                                # time.sleep(KEY_PHRASE_TIMEOUT_DURATION)
                                timer = th.Timer(THREAD_TIMER_DURATION, publishTimeout)
                                timer.start()
                            else:
                                isKeyPhraseActive = True

                elif not isCommandReceived and isKeyPhraseActive:
                    isCommandReceived = True
                    print("[INFO] post pause, publishing " + text)
                    publish(COMMAND_PREFIX + text)
                    timer = th.Timer(THREAD_TIMER_DURATION, publishActivityTimeout)
                    timer.start()

        else:
            partial_json = json.loads(recognizer.PartialResult())
            partial = partial_json.get("partial", "")
            sys.stdout.write("\r" + partial)
            sys.stdout.flush()

except KeyboardInterrupt:
    client.loop_stop()
    print("\nDone")
    parser.exit(0)
except Exception as e:
    client.loop_stop()
    parser.exit(type(e).__name__ + ": " + str(e))
