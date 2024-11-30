import sounddevice as sd
import numpy as np
import speech_recognition as sr
import asyncio
import websockets
import json
import tempfile
import os
from pynput.mouse import Listener, Button
from scipy.io.wavfile import write
from rapidfuzz import process
from queue import SimpleQueue
from vehicle_api import VehicleApi
from openai import OpenAI

# Configuration
SAMPLE_RATE = 48000
CHANNELS = 1
MICROPHONE_DEVICE = None
audio_buffer = SimpleQueue()  # Thread-safe queue for audio chunks
road_names = []
MATCH_THRESHOLD = 65
VEHICLE_MATCH_THRESHOLD = 75

transcription_queue = SimpleQueue()  # Queue for transcribed results
vehicle_queue = SimpleQueue()
log_queue = SimpleQueue()
CAPTURE_AUDIO = False

# Event loop reference for async calls from other threads
main_event_loop = None
vehicle_api = VehicleApi()
vehicle_names = vehicle_api.get_all_vehicle_names()

def load_api_key_from_json(file_path="config.json"):
    """
    Load the OpenAI API key from a JSON file.

    :param file_path: Path to the JSON file containing the API key.
    :return: The API key as a string.
    """
    try:
        with open(file_path, "r") as file:
            config = json.load(file)
            api_key = config.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("API key not found in the JSON file.")
            return api_key
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file '{file_path}' not found.")
    except json.JSONDecodeError:
        raise ValueError(f"Configuration file '{file_path}' is not a valid JSON file.")
    except Exception as e:
        raise Exception(f"Error loading API key: {e}")

api_key = load_api_key_from_json()
client = OpenAI(api_key=api_key)


# Load road names
def load_road_names(file_path):
    global road_names
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
            road_names = [item['properties']['id'] for item in data]
            print(f"Loaded {len(road_names)} road names.")
    except Exception as e:
        print(f"Error loading road names: {e}")


# Mouse event listener
def on_click(x, y, button, pressed):
    global CAPTURE_AUDIO, main_event_loop
    if button == Button.middle:
        CAPTURE_AUDIO = pressed
        if not pressed:
            # Schedule the coroutine in the main thread's event loop
            asyncio.run_coroutine_threadsafe(process_audio_clip(), main_event_loop)


# Audio callback
def audio_callback(indata, frames, time, status):
    if status:
        print(f"Audio callback status: {status}")
    if CAPTURE_AUDIO:
        audio_buffer.put(indata.copy())  # Add data to the buffer


# Start audio stream
async def start_audio_stream():
    """
    Starts the audio stream in a non-blocking way.
    """
    global MICROPHONE_DEVICE
    MICROPHONE_DEVICE = find_microphone_device()
    print(f"Using device: {sd.query_devices(MICROPHONE_DEVICE)['name']}")
    await run_audio_stream()

async def run_audio_stream():
    """
    Runs the audio stream asynchronously without blocking the event loop.
    """
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            device=MICROPHONE_DEVICE,
            callback=audio_callback
        ):
            print("Audio stream started. Waiting for audio input...")
            # Keep the stream running and allow other async tasks to execute
            while True:
                await asyncio.sleep(0.1)  # Yield control back to the event loop
    except Exception as e:
        print(f"Error in audio stream: {e}")


# Match transcription with road names
def match_road_name(transcription):
    global road_names
    if not road_names:
        print("No road names loaded.")
        return None
    match, score, _ = process.extractOne(transcription, road_names)
    print(f"Matched: {match} (Score: {score})")
    if score >= MATCH_THRESHOLD:
        return match
    return None

def match_vehicle_name(transcription):
    print("Checking vehicle match")
    global vehicle_names
    if not vehicle_names:
        print("No vehicles loaded")
        return None
    print("Trying to match")
    print(process.extract(transcription, vehicle_names))
    match, score, _ = process.extractOne(transcription, vehicle_names)
    print(f"Matched: {match} (Score: {score})")
    if score >= VEHICLE_MATCH_THRESHOLD:
        return match

def get_vehicle_name(vehicle_name):
    return vehicle_api.get_image_for_name(vehicle_name)

# Process audio buffer
async def process_audio_clip():
    if audio_buffer.empty():
        print("No audio recorded.")
        return

    audio_data = []
    while not audio_buffer.empty():
        audio_data.append(audio_buffer.get())

    audio_data = np.concatenate(audio_data, axis=0)

    # Save to temporary WAV file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
        write(temp_wav.name, SAMPLE_RATE, (audio_data * 32767).astype(np.int16))
        temp_filename = temp_wav.name
        print(temp_filename)

    # try:
    print("Trying the whisper API")
    # Use the OpenAI Whisper API
    with open(temp_filename, 'rb') as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file, 
            response_format="text"
        )
        log_queue.put(f"Transcription: {transcription}")
        matched_road = match_road_name(transcription)
        matched_vehicle_name = match_vehicle_name(transcription)
        if matched_road:
            transcription_queue.put(matched_road)
        if matched_vehicle_name:
            vehicle_queue.put(matched_vehicle_name)
    os.remove(temp_filename)


# WebSocket server
async def websocket_handler(websocket):
    print("WebSocket client connected.")
    try:
        while True:
            if not transcription_queue.empty():
                matched_road = transcription_queue.get()
                await websocket.send(json.dumps({
                    'type': 'match',
                    'data': matched_road
                }))
            if not vehicle_queue.empty():
                matched_vehicle = vehicle_queue.get()
                await websocket.send(json.dumps({
                    'type': 'vehicle',
                    'data': {
                        'name': matched_vehicle,
                        'image': vehicle_api.get_image_for_name(matched_vehicle)
                    }
                }))

            if not log_queue.empty():
                log_message = log_queue.get()
                await websocket.send(json.dumps({
                    'type': 'log',
                    'data': log_message
                }))
            await asyncio.sleep(0.1)  # Prevent tight loop
    except websockets.ConnectionClosed as e:
        print(e)
        print("WebSocket client disconnected.")


async def start_websocket_server():
    print("Starting WebSocket server...")
    async with websockets.serve(websocket_handler, "localhost", 8080):
        await asyncio.Future()


# Find microphone
def find_microphone_device():
    devices = sd.query_devices()
    for idx, device in enumerate(devices):
        if "microphone" in device["name"].lower() and device["max_input_channels"] > 0:
            try:
                sd.check_input_settings(device=idx, samplerate=SAMPLE_RATE)
                return idx
            except Exception as e:
                print(f"Device not supported: {e}")
    raise Exception("No valid microphone device found.")


async def main():
    global main_event_loop
    main_event_loop = asyncio.get_event_loop()  # Store the main thread's event loop

    load_road_names("roads.json")

    # Start mouse listener
    mouse_listener = Listener(on_click=on_click)
    mouse_listener.start()

    # Run audio stream and WebSocket server concurrently
    await asyncio.gather(
        start_audio_stream(),
        start_websocket_server()
    )


if __name__ == "__main__":
    # Load the API key
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting...")
