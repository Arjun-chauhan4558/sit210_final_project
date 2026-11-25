"""
Website communication and background report queue.
Supports camera reports with JPEG and road-impact reports without JPEG.
"""

import os
import json
import time
import glob
import queue
from datetime import datetime, timezone

import requests
import config

upload_queue = queue.Queue(maxsize=50)


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def ensure_offline_dir():
    os.makedirs(config.OFFLINE_QUEUE_DIR, exist_ok=True)


def check_backend_connection():
    try:
        response = requests.get(
            f"{config.BACKEND_URL}/api/health",
            timeout=3.0
        )
        if response.status_code == 200:
            return True, "CONNECTED"
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, f"NOT CONNECTED ({e})"


def enqueue_report(report_data, image_bytes=None):
    try:
        upload_queue.put_nowait((report_data, image_bytes))
        print(
            f"[Queue] Added {report_data.get('detection_class')} "
            f"report {report_data.get('report_id')}"
        )
        return True
    except queue.Full:
        save_report_offline(report_data, image_bytes)
        return False


def upload_worker_loop():
    while True:
        try:
            report_data, image_bytes = upload_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        try:
            upload_single_report(report_data, image_bytes)
        finally:
            upload_queue.task_done()


def upload_single_report(report_data, image_bytes=None):
    headers = {"X-Device-Key": config.DEVICE_API_KEY}
    url = f"{config.BACKEND_URL}/api/potholes/report"

    try:
        files = {}
        if image_bytes:
            files["image"] = ("pothole.jpg", image_bytes, "image/jpeg")

        form_data = {"report": json.dumps(report_data)}
        response = requests.post(
            url,
            headers=headers,
            data=form_data,
            files=files,
            timeout=8
        )

        if response.status_code in (200, 201):
            print(
                f"[Backend] {report_data.get('detection_class')} "
                f"report {report_data.get('report_id')} uploaded."
            )
            return True

        print(
            f"[Backend] Upload rejected: HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    except Exception as e:
        print("[Backend] Upload failed:", e)

    save_report_offline(report_data, image_bytes)
    return False


def save_report_offline(report_data, image_bytes=None):
    ensure_offline_dir()

    report_id = str(
        report_data.get("report_id", f"report_{int(time.time() * 1000)}")
    )
    json_path = os.path.join(config.OFFLINE_QUEUE_DIR, report_id + ".json")
    image_path = os.path.join(config.OFFLINE_QUEUE_DIR, report_id + ".jpg")

    try:
        with open(json_path, "w", encoding="utf-8") as file:
            json.dump(report_data, file, indent=2)

        if image_bytes:
            with open(image_path, "wb") as file:
                file.write(image_bytes)

        print(f"[Offline Queue] Saved report {report_id}.")
    except Exception as e:
        print("[Offline Queue] Save failed:", e)


def sync_offline_queue():
    ensure_offline_dir()

    json_files = sorted(
        glob.glob(os.path.join(config.OFFLINE_QUEUE_DIR, "*.json"))
    )

    for json_path in json_files:
        try:
            with open(json_path, "r", encoding="utf-8") as file:
                report_data = json.load(file)

            report_id = str(report_data.get("report_id", ""))
            image_path = os.path.join(
                config.OFFLINE_QUEUE_DIR, report_id + ".jpg"
            )

            image_bytes = None
            if os.path.exists(image_path):
                with open(image_path, "rb") as file:
                    image_bytes = file.read()

            if upload_single_report(report_data, image_bytes):
                os.remove(json_path)
                if os.path.exists(image_path):
                    os.remove(image_path)
            else:
                # Stop here; the network or server may still be unavailable.
                break

        except Exception as e:
            print("[Offline Queue] Sync error:", e)
            break


def send_location_ping(latitude, longitude, gps_fix, gps_hdop):
    headers = {
        "Content-Type": "application/json",
        "X-Device-Key": config.DEVICE_API_KEY
    }

    payload = {
        "device_id": config.DEVICE_ID,
        "latitude": latitude if gps_fix else None,
        "longitude": longitude if gps_fix else None,
        "gps_fix": bool(gps_fix),
        "gps_accuracy": gps_hdop if gps_fix else None,
        "timestamp": utc_timestamp()
    }

    try:
        response = requests.post(
            f"{config.BACKEND_URL}/api/devices/location",
            headers=headers,
            json=payload,
            timeout=4
        )
        if response.status_code not in (200, 201):
            print("[Backend] Location heartbeat:", response.status_code)
        return response.status_code in (200, 201)
    except Exception as e:
        print("[Backend] Location heartbeat failed:", e)
        return False


def get_nearby_potholes(latitude, longitude, radius_m=100):
    headers = {"X-Device-Key": config.DEVICE_API_KEY}
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "radius_m": radius_m
    }

    try:
        response = requests.get(
            f"{config.BACKEND_URL}/api/potholes/nearby",
            headers=headers,
            params=params,
            timeout=4
        )
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                return result.get("potholes", result.get("data", []))
    except Exception as e:
        print("[Backend] Nearby pothole request failed:", e)

    return []
