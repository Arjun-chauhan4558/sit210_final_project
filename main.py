
"""
Pothole Detection System — Raspberry Pi Main Application.

Workers:
- MPU6050 sampling and independent road-impact reporting
- NEO-6M GPS reading
- Camera and YOLO pothole detection
- Background report uploading
- Backend location/nearby synchronization
"""

import os
import time
import socket
import logging
import threading
import uuid
from datetime import datetime, timezone

import config
import sensors
import camera_yolo
import network_sync
import arduino_wifi

os.makedirs(os.path.dirname(config.LOG_FILE) or ".", exist_ok=True)

logging.basicConfig(
    filename=config.LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

running = True


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def check_wifi_connection():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2.0)
            sock.connect(("8.8.8.8", 53))
        return True, "CONNECTED"
    except Exception:
        return False, "DISCONNECTED"


def report_location():
    gps = sensors.get_gps_snapshot()

    if gps["gps_fix"] and gps["latitude"] is not None:
        return (
            gps["latitude"],
            gps["longitude"],
            True,
            gps["gps_hdop"]
        )

    if config.USE_GPS_FALLBACK_FOR_REPORTS:
        return (
            config.DEMO_FALLBACK_LATITUDE,
            config.DEMO_FALLBACK_LONGITUDE,
            False,
            None
        )

    return None, None, False, None


def make_report_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def run_startup_diagnostics():
    print("\n==================================================")
    print(" Pothole Detection System — Startup Status")
    print("==================================================")

    camera_ok, camera_message = camera_yolo.init_camera()
    print("CAMERA:      ", "READY" if camera_ok else camera_message)

    yolo_ok, yolo_message = camera_yolo.init_yolo_model()
    print("YOLO MODEL:  ", "READY" if yolo_ok else yolo_message)

    gps_ok, gps_message = sensors.init_gps()
    if gps_ok:
        print("GPS:          Waiting up to 15 seconds for fix...")
        start = time.time()
        while time.time() - start < 15:
            sensors.update_gps()
            if sensors.get_gps_snapshot()["gps_fix"]:
                break
            time.sleep(0.1)

        gps = sensors.get_gps_snapshot()
        if gps["gps_fix"]:
            print("GPS:          FIX LOCKED")
            print("GPS LATITUDE: ", gps["latitude"])
            print("GPS LONGITUDE:", gps["longitude"])
        else:
            print("GPS:          CONNECTED, NO FIX")
    else:
        print("GPS:         ", gps_message)

    mpu_ok, mpu_message = sensors.init_mpu6050()
    print("MPU6050:     ", "CONNECTED" if mpu_ok else mpu_message)

    wifi_ok, wifi_message = check_wifi_connection()
    print("WI-FI:       ", wifi_message)

    api_ok, api_message = network_sync.check_backend_connection()
    print("WEBSITE API: ", api_message)

    arduino_ok, arduino_message = arduino_wifi.check_arduino_connection()
    print("ARDUINO:     ", arduino_message)

    if not camera_ok or not yolo_ok:
        print("WARNING: Camera/YOLO detection is unavailable.")
    if not mpu_ok:
        print("WARNING: MPU6050 impact detection is unavailable.")

    print("--------------------------------------------------")
    print("SYSTEM STATUS: RUNNING WITH AVAILABLE COMPONENTS")
    print("==================================================\n")

    logging.info("Startup diagnostics completed.")


def create_sensor_fields(mpu):
    return {
        "accel_x_ms2": mpu["accel_x_ms2"],
        "accel_y_ms2": mpu["accel_y_ms2"],
        "accel_z_ms2": mpu["accel_z_ms2"],
        "gyro_x_degs": mpu["gyro_x_degs"],
        "gyro_y_degs": mpu["gyro_y_degs"],
        "gyro_z_degs": mpu["gyro_z_degs"],
        "acceleration_magnitude": mpu["acceleration_magnitude"]
    }


def mpu6050_worker():
    global running

    while running:
        impact_detected = sensors.update_mpu6050()

        if impact_detected:
            mpu = sensors.get_mpu_snapshot()
            latitude, longitude, gps_fix, gps_accuracy = report_location()

            report_data = {
                "report_id": make_report_id("pi-impact"),
                "device_id": config.DEVICE_ID,
                "timestamp": utc_timestamp(),
                "detection_class": "road_impact",
                "latitude": latitude,
                "longitude": longitude,
                "gps_fix": gps_fix,
                "gps_accuracy": gps_accuracy,
                **create_sensor_fields(mpu)
            }

            print(
                "[MPU6050] Road impact detected. "
                f"Magnitude: {mpu['acceleration_magnitude']} m/s2"
            )

            network_sync.enqueue_report(report_data, None)

        time.sleep(config.MPU6050_SAMPLE_DELAY)


def gps_worker():
    global running

    while running:
        sensors.update_gps()
        time.sleep(0.05)


def camera_detection_worker():
    global running

    while running:
        detected, confidence, bbox, image_bytes = camera_yolo.detect_pothole()

        if detected:
            latitude, longitude, gps_fix, gps_accuracy = report_location()
            mpu = sensors.get_mpu_snapshot()

            report_data = {
                "report_id": make_report_id("pi-camera"),
                "device_id": config.DEVICE_ID,
                "timestamp": utc_timestamp(),
                "detection_class": "pothole",
                "confidence": confidence,
                "bbox": bbox,
                "latitude": latitude,
                "longitude": longitude,
                "gps_fix": gps_fix,
                "gps_accuracy": gps_accuracy,
                "mpu6050": create_sensor_fields(mpu)
            }

            print(
                f"[YOLO] Pothole detected. Confidence: {confidence}, "
                f"Bounding box: {bbox}"
            )
            network_sync.enqueue_report(report_data, image_bytes)

        time.sleep(0.02)


def periodic_sync_worker():
    global running

    last_location_ping = 0.0
    last_nearby_query = 0.0
    last_offline_sync = 0.0

    while running:
        now = time.monotonic()
        gps = sensors.get_gps_snapshot()

        if now - last_location_ping >= config.LOCATION_PING_INTERVAL_SECONDS:
            network_sync.send_location_ping(
                gps["latitude"],
                gps["longitude"],
                gps["gps_fix"],
                gps["gps_hdop"]
            )
            last_location_ping = now

        if now - last_nearby_query >= config.NEARBY_QUERY_INTERVAL_SECONDS:
            if gps["gps_fix"] and gps["latitude"] is not None:
                nearby = network_sync.get_nearby_potholes(
                    gps["latitude"],
                    gps["longitude"],
                    config.NEARBY_RADIUS_METERS
                )

                if nearby:
                    closest = nearby[0]
                    distance = closest.get("distance_meters", 0)
                    severity = closest.get("severity", "medium")
                    pothole_id = closest.get("pothole_id", "")

                    if 2.5 <= distance <= 7:
                        if distance >= 1:
                            distance_text = f"{int(distance)}m"
                        else:
                            distance_text = f"{int(round(distance * 100))}cm"

                        print(
                            f"[Warning] Nearby pothole {pothole_id}: "
                            f"{distance_text}"
                        )
                        arduino_wifi.send_pothole_warning(
                            distance_text, severity, pothole_id
                        )
                    else:
                        arduino_wifi.clear_warning()
                else:
                    arduino_wifi.clear_warning()

            last_nearby_query = now

        if now - last_offline_sync >= 30:
            network_sync.sync_offline_queue()
            last_offline_sync = now

        time.sleep(1)


def main():
    global running

    run_startup_diagnostics()

    workers = [
        threading.Thread(
            target=mpu6050_worker,
            daemon=True,
            name="MPU6050Worker"
        ),
        threading.Thread(
            target=gps_worker,
            daemon=True,
            name="GPSWorker"
        ),
        threading.Thread(
            target=camera_detection_worker,
            daemon=True,
            name="CameraDetectionWorker"
        ),
        threading.Thread(
            target=network_sync.upload_worker_loop,
            daemon=True,
            name="UploadQueueWorker"
        ),
        threading.Thread(
            target=periodic_sync_worker,
            daemon=True,
            name="PeriodicSyncWorker"
        )
    ]

    for worker in workers:
        worker.start()

    print("Pothole Detection System is running. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Pothole Detection System...")
        running = False
        camera_yolo.release_camera()

        if sensors.gps_serial is not None:
            try:
                sensors.gps_serial.close()
            except Exception:
                pass

        if sensors.mpu_bus is not None:
            try:
                sensors.mpu_bus.close()
            except Exception:
                pass

        print("Hardware released. Application stopped.")


if __name__ == "__main__":
    main()
