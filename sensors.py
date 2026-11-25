import math
import time
import threading
import config

# -------------------------------------------------------------------
# GPS
# -------------------------------------------------------------------

latest_gps = {
    "latitude": None,
    "longitude": None,
    "gps_fix": False,
    "gps_hdop": None
}

gps_serial = None
gps_connected = False
gps_lock = threading.Lock()


def init_gps():
    global gps_serial, gps_connected

    try:
        import serial
        gps_serial = serial.Serial(
            port=config.GPS_PORT,
            baudrate=config.GPS_BAUD,
            timeout=config.GPS_TIMEOUT
        )
        gps_connected = True
        return True, "CONNECTED"
    except Exception as e:
        gps_serial = None
        gps_connected = False
        return False, f"NOT WORKING ({e})"


def convert_nmea_coord(coord_str, direction):
    if not coord_str or not direction:
        return None

    try:
        value = float(coord_str)
        degrees = int(value / 100)
        minutes = value - degrees * 100
        result = degrees + minutes / 60.0

        if direction in ("S", "W"):
            result = -result

        return round(result, 6)
    except (ValueError, TypeError):
        return None


def update_gps():
    if not gps_connected or gps_serial is None:
        return

    try:
        if gps_serial.in_waiting <= 0:
            return

        line = gps_serial.readline().decode(
            "ascii", errors="ignore"
        ).strip()

        if line.startswith(("$GPGGA", "$GNGGA")):
            parts = line.split(",")

            if len(parts) >= 9:
                fix_quality = parts[6]

                if fix_quality in ("1", "2"):
                    lat = convert_nmea_coord(parts[2], parts[3])
                    lon = convert_nmea_coord(parts[4], parts[5])
                    hdop = float(parts[8]) if parts[8] else None

                    if lat is not None and lon is not None:
                        with gps_lock:
                            latest_gps["latitude"] = lat
                            latest_gps["longitude"] = lon
                            latest_gps["gps_fix"] = True
                            latest_gps["gps_hdop"] = hdop

                elif fix_quality == "0":
                    with gps_lock:
                        latest_gps["gps_fix"] = False

        elif line.startswith(("$GPRMC", "$GNRMC")):
            parts = line.split(",")

            if len(parts) >= 7 and parts[2] == "A":
                lat = convert_nmea_coord(parts[3], parts[4])
                lon = convert_nmea_coord(parts[5], parts[6])

                if lat is not None and lon is not None:
                    with gps_lock:
                        latest_gps["latitude"] = lat
                        latest_gps["longitude"] = lon
                        latest_gps["gps_fix"] = True

    except Exception as e:
        print("[GPS] Read error:", e)


def get_gps_snapshot():
    with gps_lock:
        return dict(latest_gps)


# -------------------------------------------------------------------
# MPU6050
# -------------------------------------------------------------------

latest_mpu = {
    "accel_x_ms2": 0.0,
    "accel_y_ms2": 0.0,
    "accel_z_ms2": 0.0,
    "gyro_x_degs": 0.0,
    "gyro_y_degs": 0.0,
    "gyro_z_degs": 0.0,
    "acceleration_magnitude": 9.80665
}

mpu_bus = None
mpu_connected = False
mpu_lock = threading.Lock()
last_impact_time = 0.0


def init_mpu6050():
    global mpu_bus, mpu_connected

    try:
        from smbus2 import SMBus

        mpu_bus = SMBus(config.MPU6050_BUS)
        address = config.MPU6050_ADDRESS

        # Wake up the MPU6050.
        mpu_bus.write_byte_data(address, 0x6B, 0x00)

        # Accelerometer +/- 2g; gyroscope +/- 250 degrees/second.
        mpu_bus.write_byte_data(address, 0x1C, 0x00)
        mpu_bus.write_byte_data(address, 0x1B, 0x00)

        mpu_connected = True
        return True, "CONNECTED"

    except Exception as e:
        mpu_bus = None
        mpu_connected = False
        return False, f"NOT WORKING ({e})"


def get_mpu_snapshot():
    with mpu_lock:
        return dict(latest_mpu)


def update_mpu6050():
    """
    Read one MPU6050 sample.
    Returns True when a new impact event passes the threshold and cooldown.
    """
    global last_impact_time

    if not mpu_connected or mpu_bus is None:
        return False

    try:
        data = mpu_bus.read_i2c_block_data(
            config.MPU6050_ADDRESS, 0x3B, 14
        )

        def signed_value(high, low):
            value = (high << 8) | low
            if value >= 32768:
                value -= 65536
            return value

        raw_ax = signed_value(data[0], data[1])
        raw_ay = signed_value(data[2], data[3])
        raw_az = signed_value(data[4], data[5])

        raw_gx = signed_value(data[8], data[9])
        raw_gy = signed_value(data[10], data[11])
        raw_gz = signed_value(data[12], data[13])

        ax = (raw_ax / 16384.0) * 9.80665
        ay = (raw_ay / 16384.0) * 9.80665
        az = (raw_az / 16384.0) * 9.80665

        gx = raw_gx / 131.0
        gy = raw_gy / 131.0
        gz = raw_gz / 131.0

        magnitude = math.sqrt(ax * ax + ay * ay + az * az)

        with mpu_lock:
            latest_mpu["accel_x_ms2"] = round(ax, 4)
            latest_mpu["accel_y_ms2"] = round(ay, 4)
            latest_mpu["accel_z_ms2"] = round(az, 4)
            latest_mpu["gyro_x_degs"] = round(gx, 4)
            latest_mpu["gyro_y_degs"] = round(gy, 4)
            latest_mpu["gyro_z_degs"] = round(gz, 4)
            latest_mpu["acceleration_magnitude"] = round(magnitude, 4)

        # Simple starting detector: deviation from gravity magnitude.
        impact_strength = abs(magnitude - 9.80665)
        now = time.monotonic()

        if impact_strength >= config.MPU_IMPACT_THRESHOLD_MS2:
            if now - last_impact_time >= config.MPU_IMPACT_COOLDOWN_SECONDS:
                last_impact_time = now
                return True

        return False

    except Exception as e:
        print("[MPU6050] Read error:", e)
        return False
