
import serial
import pynmea2

gps = serial.Serial('/dev/serial0', 9600, timeout=1)

print("Waiting for GPS location...")

while True:
    line = gps.readline().decode('ascii', errors='ignore').strip()

    if line.startswith('$GPRMC'):
        try:
            msg = pynmea2.parse(line)

            if msg.status == 'A':
                print("Latitude:", msg.latitude)
                print("Longitude:", msg.longitude)
                print("----------------------")
            else:
                print("Waiting for GPS fix...")

        except:
            pass
