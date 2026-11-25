# Pothole Detection System — Raspberry Pi Software

Raspberry Pi 4 device software for the **Pothole Detection System**.

This software runs on the Raspberry Pi 4 inside the inspection car. It captures camera frames using **Picamera2** (Camera Module V2), runs the trained **YOLO26n NCNN** pothole detection model, reads **NEO-6M GPS** coordinates and **MPU6050** acceleration and gyroscope values, uploads detection reports to the municipal website backend through a background upload queue, and sends advance warning alerts over Wi-Fi to an **Arduino Nano 33 IoT** connected to a 0.96-inch OLED display.

---

## 1. Trained YOLO26n NCNN Model Details

The software is configured to use the trained model located on the Raspberry Pi at:

`/home/arjun_4558x/pothole_detection/models/best_ncnn_model`

- **Architecture:** YOLO26n
- **Format:** NCNN (`model.ncnn.param`, `model.ncnn.bin`, `metadata.yaml`, `model_ncnn.py`)
- **Input Size:** 320 × 320 pixels
- **Input Blob:** `in0`
- **Output Blob:** `out0`
- **Classes:** 1 (`pothole`, Class ID: 0)

The model detects potholes. Speed breaker classification is managed through administrator review on the website.

---

## 2. Hardware Pin Connections (Raspberry Pi 4)

### A. NEO-6M GPS Module (UART Serial)

Connect to the hardware UART (`/dev/serial0` at 9600 baud).

| GPS Pin | Raspberry Pi Physical Pin | GPIO / Function |
|---|---|---|
| VCC | Pin 2 | 5V Power (if breakout supports 5V) |
| GND | Pin 6 | Ground |
| TX | Pin 10 | GPIO15 (UART RX) |
| RX | Pin 8 | GPIO14 (UART TX) |

### B. MPU6050 Accelerometer and Gyroscope (I²C)

Connect to I²C Bus 1 at address `0x68`.

| MPU6050 Pin | Raspberry Pi Physical Pin | GPIO / Function |
|---|---|---|
| VCC | Pin 1 | 3.3V Power |
| GND | Pin 9 | Ground |
| SDA | Pin 3 | GPIO2 (I²C1 SDA) |
| SCL | Pin 5 | GPIO3 (I²C1 SCL) |

The MPU6050 INT pin is not required for standard polling operation.

### C. Raspberry Pi Camera Module V2

Connect directly to the onboard CSI camera connector.

### D. Arduino Nano 33 IoT with 0.96-inch OLED

The OLED is connected directly to the Arduino Nano 33 IoT:

- SDA → A4
- SCL → A5
- VCC → 3.3V
- GND → GND

Communication between the Raspberry Pi and Arduino takes place wirelessly over the local Wi-Fi network.

---

## 3. Installation on Raspberry Pi

Extract the project ZIP into its own folder named `Pothole_Detection_Raspberry_Pi`.

```bash
cd ~

unzip Pothole_Detection_Raspberry_Pi.zip -d Pothole_Detection_Raspberry_Pi

cd Pothole_Detection_Raspberry_Pi

source ~/pothole_detection/venv/bin/activate

pip install -r requirements.txt
```

### System Dependencies

Install the following dependencies if they are not already available:

- **Picamera2:** `sudo apt install python3-picamera2`
- **OpenCV:** `sudo apt install python3-opencv`
- **NCNN Python bindings:** `pip install ncnn`

### Existing Files Preserved

- Uses the existing trained model at `/home/arjun_4558x/pothole_detection/models/best_ncnn_model`.
- Does not modify or overwrite the motor controller `car.py`.
- Does not recreate the existing Python virtual environment.

---

## 4. Website Device Registration and Configuration

1. Open the municipal website in a browser (for example, `http://<SERVER_IP>:5000`).
2. Log in using the website administrator account.
3. Navigate to **Device Management**.
4. Click **Register New Device**.
5. Enter the device details:
   - **Unique Device ID:** For example, `pi4-pothole-unit-01`
   - **Device Name / Vehicle Assignment:** For example, `Melbourne Patrol Car #1`
   - **Hardware / Operational Notes:** `Pi 4 + Camera V2 + NEO-6M + MPU6050`
6. Click **Register & Generate Key**.
7. Copy the generated device API key.

Open `config.py` and configure the connection details:

```python
BACKEND_URL = "http://YOUR_SERVER_IP:5000"
DEVICE_ID = "pi4-pothole-unit-01"
DEVICE_API_KEY = "pi-key-YOUR_GENERATED_KEY"
ARDUINO_IP = "192.168.1.150"
```

Replace the example values with your actual server address, registered device ID, generated API key, and Arduino IP address.

---

## 5. Running the Main Application

Activate the Python virtual environment and start the application:

```bash
source ~/pothole_detection/venv/bin/activate

python main.py
```

### Startup Diagnostics

At startup, the software checks the availability of its main components.

Example startup status:

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

---

## 6. Operational Architecture and Fault Tolerance

### Background Upload Queue

When a pothole is detected, the report is handed to a background queue. This prevents network upload delays from blocking camera processing.

### GPS Fix Handling

- Uses actual GPS coordinates when a satellite fix is available.
- If GPS has no satellite fix, coordinates are set to `null` and `gps_fix=false`.
- Does not generate fake GPS coordinates.
- Nearby pothole queries are not performed without a valid GPS fix.
- HDOP is recorded as a unitless GPS quality factor, not as a distance in metres.

### Offline Queue

If Wi-Fi connectivity is lost, reports are saved locally in the `offline_queue/` directory. A background task automatically uploads queued reports when connectivity is restored.

### Cooldown Debounce

A cooldown timer prevents the same pothole from being uploaded repeatedly in consecutive camera frames.

### Separate MPU6050 Sampling

MPU6050 accelerometer and gyroscope readings are collected in a separate thread at approximately 50 Hz.

---

## 7. Arduino Nano 33 IoT Firmware

The Arduino sketch is included in:

`arduino_nano_oled/arduino_nano_oled.ino`

1. Open the sketch in Arduino IDE.
2. Enter your Wi-Fi SSID and password in `ssid` and `pass`.
3. Select the Arduino Nano 33 IoT board.
4. Upload the firmware.
5. The Arduino connects to the local Wi-Fi network and starts its TCP server.
6. Configure the Arduino's assigned IP address in `config.py` under `ARDUINO_IP`.

The Arduino receives warning messages from the Raspberry Pi and displays pothole alerts on the OLED.
