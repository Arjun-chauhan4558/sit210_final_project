/*
  Pothole Detection System — Arduino Nano 33 IoT Warning Receiver
  Hardware:
  - Arduino Nano 33 IoT (Wi-Fi Enabled)
  - 0.96-inch I2C OLED Display (SSD1306, Address 0x3C)
    * VCC -> 3.3V
    * GND -> GND
    * SDA -> A4 (SDA)
    * SCL -> A5 (SCL)

  The Raspberry Pi sends warning commands over local Wi-Fi:
  - GET /warn?dist=50cm&severity=high&id=PH-01
  - GET /clear
  - GET /ping
*/

#include <WiFiNINA.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Wi-Fi Credentials
char ssid[] = "YOUR_WIFI_SSID";
char pass[] = "YOUR_WIFI_PASSWORD";

WiFiServer server(80);

void setup() {
  Serial.begin(115200);

  // Initialize OLED Display
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("OLED init failed"));
  }
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 10);
  display.println(F("Pothole Detection"));
  display.println(F("System Nano 33 IoT"));
  display.println(F("Connecting Wi-Fi..."));
  display.display();

  // Connect to Wi-Fi
  int status = WL_IDLE_STATUS;
  while (status != WL_CONNECTED) {
    status = WiFi.begin(ssid, pass);
    delay(2000);
  }

  server.begin();

  // Display Ready Screen with Local IP
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println(F("Pothole Detection"));
  display.println(F("STATUS: READY"));
  display.setCursor(0, 24);
  display.print(F("IP: "));
  display.println(WiFi.localIP());
  display.setCursor(0, 42);
  display.println(F("ROAD CLEAR"));
  display.display();
}

void loop() {
  WiFiClient client = server.available();
  if (client) {
    String request = "";
    while (client.connected()) {
      if (client.available()) {
        char c = client.read();
        request += c;
        if (c == '\n') break;
      }
    }

    // Handle incoming HTTP request
    if (request.indexOf("GET /warn") >= 0) {
      int distIdx = request.indexOf("dist=");
      String distStr = "AHEAD";
      if (distIdx > 0) {
        int endIdx = request.indexOf("&", distIdx);
        if (endIdx < 0) endIdx = request.indexOf(" ", distIdx);
        distStr = request.substring(distIdx + 5, endIdx);
        // Clean URL encoded characters if any
        distStr.replace("%20", " ");
      }

      // Display Warning on OLED
      display.clearDisplay();
      display.fillRect(0, 0, 128, 16, SSD1306_WHITE);
      display.setTextColor(SSD1306_BLACK);
      display.setTextSize(1);
      display.setCursor(18, 4);
      display.println(F("! POTHOLE AHEAD !"));

      display.setTextColor(SSD1306_WHITE);
      display.setCursor(10, 26);
      display.setTextSize(2);
      display.print(distStr);

      display.setTextSize(1);
      display.setCursor(10, 48);
      display.println(F("SLOW DOWN VEHICLE"));
      display.display();

      client.println("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nWARN_DISPLAYED");

    } else if (request.indexOf("GET /clear") >= 0) {
      display.clearDisplay();
      display.setTextColor(SSD1306_WHITE);
      display.setTextSize(1);
      display.setCursor(0, 10);
      display.println(F("Pothole Detection"));
      display.setTextSize(2);
      display.setCursor(0, 30);
      display.println(F("ROAD CLEAR"));
      display.display();

      client.println("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nCLEARED");

    } else if (request.indexOf("GET /ping") >= 0) {
      client.println("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nPONG");
    } else {
      client.println("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nREADY");
    }

    delay(5);
    client.stop();
  }
}
