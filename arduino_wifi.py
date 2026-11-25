
import socket
import config


def send_message(message):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(config.ARDUINO_TIMEOUT)
            s.connect((config.ARDUINO_IP, config.ARDUINO_PORT))
            s.sendall((message + "\n").encode())
        return True
    except Exception as e:
        print("Arduino communication error:", e)
        return False


def check_arduino_connection():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(config.ARDUINO_TIMEOUT)
            s.connect((config.ARDUINO_IP, config.ARDUINO_PORT))
        return True, "CONNECTED"
    except Exception as e:
        return False, f"NOT CONNECTED ({e})"


def send_pothole_warning(distance_display, severity="high", pothole_id=""):
    message = f"POTHOLE,{distance_display}"
    return send_message(message)


def clear_warning():
    return send_message("CLEAR")
