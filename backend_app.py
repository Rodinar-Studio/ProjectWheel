import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
import ctypes
from ctypes import wintypes
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import vgamepad as vg
try:
    import serial
except ImportError:
    serial = None

# ----------------- Base Directory Helper -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ----------------- Windows Joystick (winmm.dll) Native Interface -----------------
winmm = ctypes.WinDLL('winmm.dll')

class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("dwXpos", wintypes.DWORD),
        ("dwYpos", wintypes.DWORD),
        ("dwZpos", wintypes.DWORD),
        ("dwRpos", wintypes.DWORD),
        ("dwUpos", wintypes.DWORD),
        ("dwVpos", wintypes.DWORD),
        ("dwButtons", wintypes.DWORD),
        ("dwButtonNumber", wintypes.DWORD),
        ("dwPOV", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("dwReserved2", wintypes.DWORD),
    ]

JOY_RETURNALL = 0xFF
JOY_RETURNPOV = 0x00000040
JOY_RETURNBUTTONS = 0x00000080
JOY_RETURNX = 0x00000001
JOY_RETURNY = 0x00000002
JOY_RETURNZ = 0x00000004
JOY_RETURNR = 0x00000008
JOY_RETURNU = 0x00000010
JOY_RETURNV = 0x00000020

# ----------------- Settings & State -----------------
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
DEFAULT_SETTINGS = {
    "gas": {"deadzone": 5, "sensitivity": 1.0, "activation_point": 5, "direction": "both"},
    "brake": {"deadzone": 5, "sensitivity": 1.0, "activation_point": 5, "direction": "both"},
    "wheel_deadzone": 0.0,
    "bluetooth_port": "None",
    "wheel_device_id": 0,
    "shifter_device_id": 1,
    "shifter_mode": "none",
    "wheel_invert": False
}

settings = DEFAULT_SETTINGS.copy()

def load_settings():
    global settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                settings = json.load(f)
                print("Settings loaded successfully.")
        except Exception as e:
            print("Error loading settings, using defaults:", e)
            settings = DEFAULT_SETTINGS.copy()
    else:
        save_settings()

def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
        print("Settings saved successfully.")
    except Exception as e:
        print("Error saving settings:", e)

load_settings()

# Live State
pedal_state = {
    "gas": {"value": 0.0, "raw": 0.0, "phone_id": None},
    "brake": {"value": 0.0, "raw": 0.0, "phone_id": None}
}

calibration_offsets = {
    "gas": 0.0,
    "brake": 0.0
}

wheel_state = {
    "connected": False,
    "name": "Yok",
    "axes": {"X": 32768, "Y": 32768, "Z": 32768, "R": 32768, "U": 32768, "V": 32768},
    "buttons": [False] * 32,
    "pov": 65535
}

shifter_state = {
    "connected": False,
    "name": "Yok",
    "axes": {"X": 32768, "Y": 32768, "Z": 32768, "R": 32768, "U": 32768, "V": 32768},
    "buttons": [False] * 32,
    "pov": 65535
}

# Emulated controller
gamepad = vg.VX360Gamepad()

# Websocket managers
webui_sockets = []
pedal_sockets = {}

# Helper to find ADB path
def find_adb():
    # 1. Check local directory first
    local_paths = [
        os.path.join(BASE_DIR, "adb.exe"),
        os.path.join(BASE_DIR, "platform-tools", "adb.exe")
    ]
    for path in local_paths:
        if os.path.exists(path):
            return path

    # 2. Check system PATH
    adb_path = shutil.which("adb")
    if adb_path:
        return adb_path
    
    # 3. Check common installations
    common_paths = [
        "C:\\Android\\platform-tools\\adb.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
        "C:\\Program Files\\Android\\Android Studio\\bin\\adb.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
    return None

# ----------------- Pedal Processing -----------------
def process_pedal_value(raw_angle, pedal_type):
    cfg = settings.get(pedal_type, {})
    deadzone = cfg.get('deadzone', 5)
    sensitivity = cfg.get('sensitivity', 1.0)
    activation_point = cfg.get('activation_point', 5)
    direction = cfg.get('direction', 'both')
    
    # Apply WebUI calibration offset
    adjusted = raw_angle - calibration_offsets.get(pedal_type, 0.0)
    
    if direction == 'positive':
        val = adjusted if adjusted > 0 else 0.0
    elif direction == 'negative':
        val = -adjusted if adjusted < 0 else 0.0
    else: # 'both'
        val = abs(adjusted)
    
    if val < activation_point:
        return 0.0
        
    val = val - activation_point
    
    if val < deadzone:
        return 0.0
        
    # Scale: assume 45 degrees is full press
    max_angle = 45.0
    val = val * sensitivity
    
    normalized = val / max_angle
    if normalized > 1.0:
        normalized = 1.0
    return normalized

last_printed_gas = -1
last_printed_brake = -1

# ----------------- Virtual Controller Update -----------------
def update_virtual_controller():
    global last_printed_gas, last_printed_brake
    # 1. Update Pedals (Triggers)
    gas_val = int(pedal_state['gas']['value'] * 255)
    brake_val = int(pedal_state['brake']['value'] * 255)
    
    if gas_val != last_printed_gas or brake_val != last_printed_brake:
        print(f"[Gamepad Triggers] Gas: {gas_val}, Brake: {brake_val}")
        last_printed_gas = gas_val
        last_printed_brake = brake_val
        
    gamepad.right_trigger(value=gas_val)
    gamepad.left_trigger(value=brake_val)
    
    # 2. Update Steering Axis (Left Joystick X)
    raw_x = wheel_state["axes"]["X"]
    norm_x = raw_x - 32768
    
    wheel_deadzone_pct = settings.get("wheel_deadzone", 0.0)
    deadzone_val = (wheel_deadzone_pct / 100.0) * 32768.0
    
    if abs(norm_x) < deadzone_val:
        norm_x = 0
    else:
        # Scale smoothly from deadzone edge to limits
        if norm_x > 0:
            scaled_x = ((norm_x - deadzone_val) / (32768.0 - deadzone_val)) * 32767.0
        else:
            scaled_x = ((norm_x + deadzone_val) / (32768.0 - deadzone_val)) * 32768.0
        norm_x = int(scaled_x)
        
    if norm_x < -32768: norm_x = -32768
    if norm_x > 32767: norm_x = 32767
    
    if settings.get("wheel_invert", False):
        norm_x = -norm_x
        if norm_x < -32768: norm_x = -32768
        if norm_x > 32767: norm_x = 32767
        
    gamepad.left_joystick(x_value=norm_x, y_value=0)
    
    # 3. Update D-pad (POV Hat)
    pov = wheel_state["pov"]
    if pov == 65535:
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
    else:
        if pov == 0 or pov == 31500 or pov == 4500:
            gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        else:
            gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
            
        if pov == 18000 or pov == 13500 or pov == 22500:
            gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        else:
            gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
            
        if pov == 27000 or pov == 22500 or pov == 31500:
            gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        else:
            gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
            
        if pov == 9000 or pov == 4500 or pov == 13500:
            gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
        else:
            gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)

    # 4. Update Buttons (Xbox 360 layout)
    mappings = {
        0: vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
        1: vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
        2: vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
        3: vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
        4: vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
        5: vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
        6: vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
        7: vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
        8: vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
        9: vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
    }
    
    for phys_idx, virt_btn in mappings.items():
        if phys_idx < len(wheel_state["buttons"]):
            if wheel_state["buttons"][phys_idx]:
                gamepad.press_button(button=virt_btn)
            else:
                gamepad.release_button(button=virt_btn)

    # 5. Shifter Logic
    shifter_mode = settings.get("shifter_mode", "none")
    shifter_conn = shifter_state.get("connected", False)
    
    if shifter_conn and shifter_mode != "none":
        if shifter_mode == "sequential_axis":
            # Y-axis (forward/backward on joystick)
            y_val = shifter_state["axes"]["Y"]
            if y_val < 15000:     # Forward -> Shift Up
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
            elif y_val > 50000:   # Backward -> Shift Down
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
            else:
                if not (wheel_state["connected"] and len(wheel_state["buttons"]) > 5 and wheel_state["buttons"][5]):
                    gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
                if not (wheel_state["connected"] and len(wheel_state["buttons"]) > 4 and wheel_state["buttons"][4]):
                    gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
                    
        elif shifter_mode == "sequential_buttons":
            # Physical buttons 0 (trigger) and 1 (thumb button) on Logitech
            if shifter_state["buttons"][0]: # Trigger -> Shift Up (RB)
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
            else:
                if not (wheel_state["connected"] and len(wheel_state["buttons"]) > 5 and wheel_state["buttons"][5]):
                    gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
                    
            if shifter_state["buttons"][1]: # Thumb -> Shift Down (LB)
                gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
            else:
                if not (wheel_state["connected"] and len(wheel_state["buttons"]) > 4 and wheel_state["buttons"][4]):
                    gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
                    
        elif shifter_mode == "manual_h":
            # Manual H-Shifter Mode (6 gears + 1 reverse) using analog zones
            # X and Y are in range 0 - 65535, center is ~32768
            x_val = shifter_state["axes"]["X"]
            y_val = shifter_state["axes"]["Y"]
            
            # Map X zones: Sol (<22000), Orta (22000-43000), Sağ (>43000)
            # Map Y zones: İleri (<22000), Geri (>43000)
            
            gear1 = (x_val < 22000 and y_val < 22000)
            gear2 = (x_val < 22000 and y_val > 43000)
            gear3 = (x_val >= 22000 and x_val <= 43000 and y_val < 22000)
            gear4 = (x_val >= 22000 and x_val <= 43000 and y_val > 43000)
            gear5 = (x_val > 43000 and y_val < 22000)
            gear6 = (x_val > 43000 and y_val > 43000)
            gearR = shifter_state["buttons"][0] # Trigger is Reverse
            
            # Map gears to buttons: A(1), B(2), X(3), Y(4), LB(5), RB(6), BACK(R)
            gears = {
                vg.XUSB_BUTTON.XUSB_GAMEPAD_A: gear1,
                vg.XUSB_BUTTON.XUSB_GAMEPAD_B: gear2,
                vg.XUSB_BUTTON.XUSB_GAMEPAD_X: gear3,
                vg.XUSB_BUTTON.XUSB_GAMEPAD_Y: gear4,
                vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER: gear5,
                vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER: gear6,
                vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK: gearR
            }
            
            for btn, active in gears.items():
                if active:
                    gamepad.press_button(button=btn)
                else:
                    # Only release if steering wheel is not pressing it
                    wheel_pressed = False
                    for w_idx, w_btn in mappings.items():
                        if w_btn == btn and w_idx < len(wheel_state["buttons"]) and wheel_state["buttons"][w_idx]:
                            wheel_pressed = True
                            break
                    if not wheel_pressed:
                        gamepad.release_button(button=btn)
                        
        elif shifter_mode == "automatic_prnd":
            # Automatic PRND mode using Y axis and Trigger button
            # Forward -> D (Drive - A button)
            # Backward -> R (Reverse - B button)
            # Center -> N (Neutral - X button)
            # Trigger -> P (Park - Y button)
            y_val = shifter_state["axes"]["Y"]
            trigger = shifter_state["buttons"][0]
            
            drive = (y_val < 15000 and not trigger)
            reverse = (y_val > 50000 and not trigger)
            neutral = (y_val >= 15000 and y_val <= 50000 and not trigger)
            park = trigger
            
            modes = {
                vg.XUSB_BUTTON.XUSB_GAMEPAD_A: drive,
                vg.XUSB_BUTTON.XUSB_GAMEPAD_B: reverse,
                vg.XUSB_BUTTON.XUSB_GAMEPAD_X: neutral,
                vg.XUSB_BUTTON.XUSB_GAMEPAD_Y: park
            }
            
            for btn, active in modes.items():
                if active:
                    gamepad.press_button(button=btn)
                else:
                    wheel_pressed = False
                    for w_idx, w_btn in mappings.items():
                        if w_btn == btn and w_idx < len(wheel_state["buttons"]) and wheel_state["buttons"][w_idx]:
                            wheel_pressed = True
                            break
                    if not wheel_pressed:
                        gamepad.release_button(button=btn)
                
    gamepad.update()

# ----------------- Background Thread: Physical Wheel & Shifter Reader -----------------
def wheel_reader_loop():
    info_wheel = JOYINFOEX()
    info_wheel.dwSize = ctypes.sizeof(info_wheel)
    info_wheel.dwFlags = JOY_RETURNALL

    info_shifter = JOYINFOEX()
    info_shifter.dwSize = ctypes.sizeof(info_shifter)
    info_shifter.dwFlags = JOY_RETURNALL
    
    while True:
        wheel_id = settings.get("wheel_device_id", 0)
        shifter_id = settings.get("shifter_device_id", 1)
        
        # 1. Read Physical Wheel
        res_wheel = winmm.joyGetPosEx(wheel_id, ctypes.byref(info_wheel))
        if res_wheel == 0:
            wheel_state["connected"] = True
            wheel_state["name"] = f"Fiziksel Direksiyon (ID: {wheel_id})"
            
            wheel_state["axes"]["X"] = info_wheel.dwXpos
            wheel_state["axes"]["Y"] = info_wheel.dwYpos
            wheel_state["axes"]["Z"] = info_wheel.dwZpos
            wheel_state["axes"]["R"] = info_wheel.dwRpos
            wheel_state["axes"]["U"] = info_wheel.dwUpos
            wheel_state["axes"]["V"] = info_wheel.dwVpos
            
            wheel_state["pov"] = info_wheel.dwPOV
            
            for i in range(32):
                wheel_state["buttons"][i] = bool(info_wheel.dwButtons & (1 << i))
        else:
            wheel_state["connected"] = False
            wheel_state["name"] = "Bağlı Değil"
            wheel_state["axes"] = {"X": 32768, "Y": 32768, "Z": 32768, "R": 32768, "U": 32768, "V": 32768}
            wheel_state["buttons"] = [False] * 32
            wheel_state["pov"] = 65535

        # 2. Read Physical Shifter
        shifter_mode = settings.get("shifter_mode", "none")
        if shifter_mode != "none":
            res_shifter = winmm.joyGetPosEx(shifter_id, ctypes.byref(info_shifter))
            if res_shifter == 0:
                shifter_state["connected"] = True
                shifter_state["name"] = f"Vites Joystick (ID: {shifter_id})"
                
                shifter_state["axes"]["X"] = info_shifter.dwXpos
                shifter_state["axes"]["Y"] = info_shifter.dwYpos
                shifter_state["axes"]["Z"] = info_shifter.dwZpos
                shifter_state["axes"]["R"] = info_shifter.dwRpos
                shifter_state["axes"]["U"] = info_shifter.dwUpos
                shifter_state["axes"]["V"] = info_shifter.dwVpos
                
                shifter_state["pov"] = info_shifter.dwPOV
                
                for i in range(32):
                    shifter_state["buttons"][i] = bool(info_shifter.dwButtons & (1 << i))
            else:
                shifter_state["connected"] = False
                shifter_state["name"] = "Bağlı Değil"
                shifter_state["axes"] = {"X": 32768, "Y": 32768, "Z": 32768, "R": 32768, "U": 32768, "V": 32768}
                shifter_state["buttons"] = [False] * 32
                shifter_state["pov"] = 65535
        else:
            shifter_state["connected"] = False
            shifter_state["name"] = "Devre Dışı"
            shifter_state["axes"] = {"X": 32768, "Y": 32768, "Z": 32768, "R": 32768, "U": 32768, "V": 32768}
            shifter_state["buttons"] = [False] * 32
            shifter_state["pov"] = 65535
            
        update_virtual_controller()
        time.sleep(0.005)

# Start the thread
threading.Thread(target=wheel_reader_loop, daemon=True).start()

# ----------------- FastAPI App -----------------
app = FastAPI()

# Broadcast helper for asyncio
async def broadcast_state():
    while True:
        if webui_sockets:
            data = json.dumps({
                "type": "state_update",
                "wheel": wheel_state,
                "shifter": shifter_state,
                "pedals": {
                    "gas": {
                        "value": pedal_state["gas"]["value"],
                        "raw": pedal_state["gas"]["raw"],
                        "connected": pedal_state["gas"]["phone_id"] is not None
                    },
                    "brake": {
                        "value": pedal_state["brake"]["value"],
                        "raw": pedal_state["brake"]["raw"],
                        "connected": pedal_state["brake"]["phone_id"] is not None
                    }
                },
                "settings": settings
            })
            for ws in list(webui_sockets):
                try:
                    await ws.send_text(data)
                except Exception:
                    if ws in webui_sockets:
                        webui_sockets.remove(ws)
        await asyncio.sleep(0.033)

def bluetooth_serial_listener():
    if not serial:
        print("[Bluetooth] pyserial module not available.")
        return
        
    last_port = None
    ser = None
    while True:
        port = settings.get("bluetooth_port", "None")
        if port == "None":
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                last_port = None
            time.sleep(1)
            continue
            
        if port != last_port or not ser or not ser.is_open:
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass
            try:
                print(f"[Bluetooth] Opening serial port {port}...")
                ser = serial.Serial(port, 115200, timeout=0.1)
                last_port = port
                print(f"[Bluetooth] Serial port {port} opened successfully!")
            except Exception as e:
                print(f"[Bluetooth] Failed to open serial port {port}: {e}")
                last_port = port
                time.sleep(3)
                continue
        
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    try:
                        msg = json.loads(line)
                        p_type = msg.get("pedal_type")
                        phone_id = msg.get("phone_id")
                        
                        if msg.get("action") == "assign":
                            pedal_state[p_type]["phone_id"] = phone_id
                            print(f"[Bluetooth] Phone {phone_id} registered as {p_type}")
                        elif "angle" in msg:
                            angle = msg.get("angle", 0.0)
                            if p_type in pedal_state and pedal_state[p_type]["phone_id"] == phone_id:
                                pedal_state[p_type]["raw"] = angle
                                pedal_state[p_type]["value"] = process_pedal_value(angle, p_type)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"[Bluetooth] Serial read error on {port}: {e}")
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            last_port = None
            time.sleep(1)
        time.sleep(0.005)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcast_state())
    # Start Bluetooth Serial background thread
    bt_thread = threading.Thread(target=bluetooth_serial_listener, daemon=True)
    bt_thread.start()

# ----------------- REST Endpoints -----------------
class PedalSetting(BaseModel):
    deadzone: int
    sensitivity: float
    activation_point: int
    direction: str = "both"

class SettingsPayload(BaseModel):
    gas: PedalSetting
    brake: PedalSetting
    wheel_deadzone: float = 0.0
    bluetooth_port: str = "None"
    wheel_device_id: int = 0
    shifter_device_id: int = 1
    shifter_mode: str = "none"
    wheel_invert: bool = False

@app.post("/api/settings")
async def update_settings(payload: SettingsPayload):
    global settings
    settings["gas"] = payload.gas.dict()
    settings["brake"] = payload.brake.dict()
    settings["wheel_deadzone"] = payload.wheel_deadzone
    settings["bluetooth_port"] = payload.bluetooth_port
    settings["wheel_device_id"] = payload.wheel_device_id
    settings["shifter_device_id"] = payload.shifter_device_id
    settings["shifter_mode"] = payload.shifter_mode
    settings["wheel_invert"] = payload.wheel_invert
    save_settings()
    return {"status": "success", "settings": settings}

@app.get("/api/settings")
async def get_settings():
    return settings

@app.post("/api/adb_reverse")
async def run_adb_reverse():
    adb_path = find_adb()
    if not adb_path:
        return JSONResponse(
            status_code=404, 
            content={"status": "error", "message": "ADB bulunamadı. Lütfen Android Studio veya adb.exe kurup sistem PATH'ine ekleyin."}
        )
    try:
        devices_out = subprocess.run([adb_path, "devices"], capture_output=True, text=True)
        reverse_out = subprocess.run([adb_path, "reverse", "tcp:8000", "tcp:8000"], capture_output=True, text=True)
        return {
            "status": "success", 
            "devices": devices_out.stdout.strip(), 
            "message": f"ADB Reverse başarıyla kuruldu ({os.path.basename(adb_path)}). Telefonunuzda http://localhost:8000 adresine girebilirsiniz."
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/adb_devices")
async def get_adb_devices():
    adb_path = find_adb()
    if not adb_path:
        return {"status": "error", "message": "ADB bulunamadı."}
    try:
        devices_out = subprocess.run([adb_path, "devices"], capture_output=True, text=True)
        return {"status": "success", "output": devices_out.stdout.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/download/gyro-pedal.apk")
async def download_apk():
    # Looks for the APK in the script directory (as bundled in ZIP)
    apk_path = os.path.join(BASE_DIR, "gyro-pedal.apk")
    if os.path.exists(apk_path):
        return FileResponse(apk_path, media_type="application/vnd.android.package-archive", filename="gyro-pedal.apk")
    
    # Fallback to Flutter build path if running in dev environment
    dev_apk_path = os.path.join(BASE_DIR, "gyro_pedal_app", "build", "app", "outputs", "flutter-apk", "app-release.apk")
    if os.path.exists(dev_apk_path):
        return FileResponse(dev_apk_path, media_type="application/vnd.android.package-archive", filename="gyro-pedal.apk")
        
    return JSONResponse(status_code=404, content={"status": "error", "message": "APK dosyası sunucuda bulunamadı."})

# ----------------- WebUI Pages -----------------
@app.get("/")
async def get_dashboard():
    dashboard_path = os.path.join(BASE_DIR, "templates", "dashboard.html")
    if not os.path.exists(dashboard_path):
        return HTMLResponse("<h3>templates/dashboard.html dosyası bulunamadı.</h3>", status_code=404)
    with open(dashboard_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html)

@app.get("/pedal_client")
async def get_pedal_client():
    client_path = os.path.join(BASE_DIR, "templates", "pedal.html")
    if not os.path.exists(client_path):
        return HTMLResponse("<h3>templates/pedal.html dosyası bulunamadı.</h3>", status_code=404)
    with open(client_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html)

# ----------------- WebSocket Endpoints -----------------
@app.websocket("/ws/webui")
async def ws_webui(websocket: WebSocket):
    await websocket.accept()
    webui_sockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "update_settings":
                global settings
                settings["gas"] = msg["settings"]["gas"]
                settings["brake"] = msg["settings"]["brake"]
                settings["wheel_deadzone"] = msg["settings"].get("wheel_deadzone", 0.0)
                settings["bluetooth_port"] = msg["settings"].get("bluetooth_port", "None")
                settings["wheel_device_id"] = msg["settings"].get("wheel_device_id", 0)
                settings["shifter_device_id"] = msg["settings"].get("shifter_device_id", 1)
                settings["shifter_mode"] = msg["settings"].get("shifter_mode", "none")
                settings["wheel_invert"] = msg["settings"].get("wheel_invert", False)
                save_settings()
            elif msg.get("type") == "calibrate_pedal":
                p_type = msg.get("pedal_type")
                if p_type in calibration_offsets:
                    calibration_offsets[p_type] = pedal_state[p_type]["raw"]
                    print(f"WebUI calibrated pedal {p_type} to offset {calibration_offsets[p_type]}")
    except WebSocketDisconnect:
        webui_sockets.remove(websocket)
    except Exception:
        if websocket in webui_sockets:
            webui_sockets.remove(websocket)

@app.websocket("/ws/pedal")
async def ws_pedal(websocket: WebSocket):
    await websocket.accept()
    phone_id = None
    assigned_pedal = None
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("action") == "assign":
                phone_id = msg.get("phone_id")
                assigned_pedal = msg.get("pedal_type")
                
                if assigned_pedal in pedal_sockets:
                    try:
                        await pedal_sockets[assigned_pedal].close()
                    except Exception:
                        pass
                
                pedal_sockets[assigned_pedal] = websocket
                pedal_state[assigned_pedal]["phone_id"] = phone_id
                print(f"Phone {phone_id} registered as {assigned_pedal}")
                
            elif "angle" in msg:
                p_type = msg.get("pedal_type")
                angle = msg.get("angle", 0.0)
                
                if p_type in pedal_state and pedal_state[p_type]["phone_id"] == msg.get("phone_id"):
                    pedal_state[p_type]["raw"] = angle
                    pedal_state[p_type]["value"] = process_pedal_value(angle, p_type)
                    
    except WebSocketDisconnect:
        print(f"Pedal websocket disconnected: {assigned_pedal} ({phone_id})")
        if assigned_pedal and pedal_state[assigned_pedal]["phone_id"] == phone_id:
            pedal_state[assigned_pedal]["phone_id"] = None
            pedal_state[assigned_pedal]["value"] = 0.0
            pedal_state[assigned_pedal]["raw"] = 0.0
            calibration_offsets[assigned_pedal] = 0.0
            if assigned_pedal in pedal_sockets:
                del pedal_sockets[assigned_pedal]
    except Exception as e:
        print(f"Error in pedal websocket {assigned_pedal}: {e}")
        if assigned_pedal and pedal_state[assigned_pedal]["phone_id"] == phone_id:
            pedal_state[assigned_pedal]["phone_id"] = None
            pedal_state[assigned_pedal]["value"] = 0.0
            pedal_state[assigned_pedal]["raw"] = 0.0
            calibration_offsets[assigned_pedal] = 0.0
            if assigned_pedal in pedal_sockets:
                del pedal_sockets[assigned_pedal]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
