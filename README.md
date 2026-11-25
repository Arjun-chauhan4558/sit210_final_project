# Pothole Detection System — Raspberry Pi Software

Raspberry Pi 4 device software for **Pothole Detection System**.

This software runs on the Raspberry Pi 4 inside the inspection car, captures camera frames using **Picamera2** (Camera Module V2), runs your trained **YOLO26n NCNN** pothole model, reads **NEO-6M GPS** coordinates and **MPU6050** acceleration/gyroscope values, uploads detection reports to the municipal website backend via a background upload queue, and transmits advance warning alerts over Wi-Fi to an **Arduino Nano 33 IoT** driving a 0.96-inch OLED display.

---

## 1. Trained YOLO26n NCNN Model Details

The software is configured to use your exact trained model located on the Raspberry Pi at:
`/home/arjun_4558x/pothole_detection/models/best_ncnn_model`

- **Architecture:** YOLO26n
- **Format:** NCNN (`model.ncnn.param`, `model.ncnn.bin`, `metadata.yaml`, `model_ncnn.py`)
- **Input Size:** 320 x 320 pixels (Input blob: `in0`)
- **Output Blob:** `out0` (5 x 2100 anchors, `[cx, cy, w, h, score]`)
- **Classes:** 1 (`pothole`, Class ID: 0)

*Note: The model has only one class (pothole). It does not classify speed breakers; that classification is managed through administrator review on the website.*

---

## 2. Hardware Pin Connections (Raspberry Pi 4)

### A. NEO-6M GPS Module (UART Serial)
Connect to the hardware UART (`/dev/serial0` at 9600 baud):

| GPS Pin | Raspberry Pi 4 Physical Pin | GPIO / Function |
| :--- | :--- | :--- |
| **VCC** | **Pin 2** | 5V Power (if breakout supports 5V) |
| **GND** | **Pin 6** | Ground |
| **TX** | **Pin 10** | GPIO15 (UART RX) |
| **RX** | **Pin 8** | GPIO14 (UART TX) |

### B. MPU6050 Accelerometer & Gyroscope (I²C)
Connect to I²C Bus 1 (`0x68` address):

| MPU6050 Pin | Raspberry Pi 4 Physical Pin | GPIO / Function |
| :--- | :--- | :--- |
| **VCC** | **Pin 1** | 3.3V Power |
| **GND** | **Pin 9** | Ground |
| **SDA** | **Pin 3** | GPIO2 (I²C1 SDA) |
| **SCL** | **Pin 5** | GPIO3 (I²C1 SCL) |

*(Note: The MPU6050 INT pin is not required for standard polling operation).*

### C. Raspberry Pi Camera Module V2
- Connect directly to the onboard **CSI camera connector**.

### D. Arduino Nano 33 IoT with 0.96-inch OLED
- The 0.96-inch OLED is connected directly to the Arduino Nano 33 IoT (A4 = SDA, A5 = SCL, 3.3V, GND).
- Communication between the Raspberry Pi 4 and the Arduino occurs wirelessly over **local Wi-Fi**.

---

## 3. Installation on Raspberry Pi

Extract the ZIP into its own separate folder `Pothole_Detection_Raspberry_Pi`:

```bash
cd ~

# 1. Unzip into its own dedicated folder
unzip Pothole_Detection_Raspberry_Pi.zip -d Pothole_Detection_Raspberry_Pi
cd Pothole_Detection_Raspberry_Pi

# 2. Activate your existing Python virtual environment
source ~/pothole_detection/venv/bin/activate

# 3. Install required Python packages
pip install -r requirements.txt
```

### System Dependencies on Raspberry Pi OS
If not already installed in your environment:
- **Picamera2 (libcamera interface):** `sudo apt install python3-picamera2`
- **OpenCV:** `sudo apt install python3-opencv`
- **NCNN Python bindings:** `pip install ncnn`

> **Existing Files Preserved:**
> - Uses your existing model in `/home/arjun_4558x/pothole_detection/models/best_ncnn_model`.
> - Does NOT modify or overwrite your motor controller `car.py`.
> - Does NOT recreate your virtual environment.

---

## 4. Website Device Registration & Configuration

1. Open your website in a browser (e.g. `http://<SERVER_IP>:5000`).
2. Log in with your website administrator account.
3. In the sidebar, go to **Device Management**.
4. Click **Register New Device**:
   - **Unique Device ID:** e.g. `pi4-pothole-unit-01`
   - **Device Name / Vehicle Assignment:** e.g. `Melbourne Patrol Car #1`
   - **Hardware / Operational Notes:** e.g. `Pi 4 + Camera V2 + NEO-6M + MPU6050`
   - Click **Register & Generate Key**.
5. Copy the generated device API key (`pi-key-...`).

6. Open `config.py` in `Pothole_Detection_Raspberry_Pi` and set your credentials:
```python
BACKEND_URL = "http://YOUR_SERVER_IP:5000"
DEVICE_ID = "pi4-pothole-unit-01"
DEVICE_API_KEY = "pi-key-YOUR_GENERATED_KEY"
ARDUINO_IP = "192.168.1.150"
```

---

## 5. Test Communication with `send_test_data.py`

Run the one-shot communication utility before starting the full detection system:

```bash
python send_test_data.py
```

### What `send_test_data.py` does:
- Sends **ONE** read-only check to verify your `DEVICE_ID` and `DEVICE_API_KEY`.
- Does **NOT** start camera or YOLO.
- Does **NOT** require GPS or MPU6050.
- Does **NOT** create any fake pothole reports or fake location updates.
- Prints `RESULT: SUCCESS!` or the exact error.

---

## 6. Running the Main Application

Run the main application:

```bash
python main.py
```

### Startup Diagnostics
At startup, the software checks each component independently:

```text
==================================================
      Pothole Detection System — Startup Status   
==================================================
CAMERA:      READY
YOLO MODEL:  READY
GPS:         CONNECTED (FIX LOCKED)
MPU6050:     CONNECTED
WI-FI:       CONNECTED
WEBSITE API: CONNECTED
ARDUINO:     CONNECTED
--------------------------------------------------
SYSTEM STATUS: RUNNING
==================================================
```

### Operational Architecture & Fault Tolerance
- **Background Upload Queue:** When a pothole is detected, the report is handed off to a background queue immediately so camera processing is never blocked by network latency.
- **GPS Fix Handling:** If GPS has no satellite fix indoors, coordinates are set to `null` and `gps_fix=false`. Never invents fake coordinates. HDOP is recorded as a unitless quality factor (not metres). Does not query nearby potholes without a fix.
- **Offline Queue:** If Wi-Fi is lost, reports are saved locally to `offline_queue/`. A background task automatically uploads them as soon as Wi-Fi reconnects.
- **Cooldown Debounce:** A timer prevents uploading the same pothole repeatedly in every camera frame.
- **Separate MPU6050 Sampling:** MPU6050 accelerometer and gyroscope readings are polled in their own thread at ~50 Hz.

---

## 7. Miniature Demo Road (190 cm Track)

For tabletop or indoor track demonstrations:
- **Total Track Length:** 190 cm
- **Pothole Defect Position:** 100 cm from start
- **Warning Distance:** 50 cm before pothole (triggers at 50 cm position)

> Real GPS cannot measure millimeter positions on a miniature 190 cm track. To demonstrate the warning sequence on your track without satellite reception:

```python
from demo_road import run_miniature_demo_sequence
run_miniature_demo_sequence()
```

This triggers the warning on the Arduino Nano 33 IoT OLED when the car reaches 50 cm, and clears it once the car passes 100 cm.

---

## 8. Arduino Nano 33 IoT Firmware

The Arduino sketch is included in `arduino_nano_oled/arduino_nano_oled.ino`:
1. Open in Arduino IDE.
2. Enter your Wi-Fi SSID and password in `ssid` and `pass`.
3. Flash to the **Arduino Nano 33 IoT**.
4. The Arduino will print its assigned IP address on the 0.96-inch OLED screen. Put this IP into `config.py` under `ARDUINO_IP`.
