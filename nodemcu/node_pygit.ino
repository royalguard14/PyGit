#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <LittleFS.h>
#include <ESP8266WebServer.h>
#include <ESP8266httpUpdate.h>

const char* WIFI_CONFIG = "/wifi_config.json";

// Built-in FLASH button on most NodeMCU ESP8266 boards.
const int SETUP_BUTTON_PIN = 0; // GPIO0 / D3

// After normal boot, give the user a short window to press FLASH
// and enter Wi-Fi setup mode without interfering with the bootloader.
const unsigned long SETUP_WINDOW = 5000;

// Version of the firmware currently flashed on this base device.
// Change this when creating a new firmware release.
const char* LOCAL_FIRMWARE_VERSION = "1.0.0";

const char* FIRMWARE_URL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/main/nodemcu/firmware.bin";

const char* configURL =
  "https://api.github.com/repos/royalguard14/PyGit/contents/nodemcu/data/config.json?ref=main";

String wifiSSID = "";
String wifiPassword = "";

ESP8266WebServer server(80);

// Simple JSON value reader.
// This avoids requiring the ArduinoJson library.
String readJsonValue(const String& json, const String& key) {
  String searchKey = "\"" + key + "\"";
  int keyPos = json.indexOf(searchKey);

  if (keyPos < 0) return "";

  int colonPos = json.indexOf(':', keyPos + searchKey.length());
  if (colonPos < 0) return "";

  int quoteStart = json.indexOf('"', colonPos + 1);
  if (quoteStart < 0) return "";

  int quoteEnd = json.indexOf('"', quoteStart + 1);
  if (quoteEnd < 0) return "";

  return json.substring(quoteStart + 1, quoteEnd);
}

bool saveWiFiConfig(const String& ssid, const String& password) {
  File f = LittleFS.open(WIFI_CONFIG, "w");

  if (!f) {
    Serial.println("ERROR: Cannot create /wifi_config.json.");
    return false;
  }

  f.println("{");
  f.print("  \"ssid\": \"");
  f.print(ssid);
  f.println("\",");
  f.print("  \"password\": \"");
  f.print(password);
  f.println("\"");
  f.println("}");

  f.close();

  wifiSSID = ssid;
  wifiPassword = password;

  Serial.println("Wi-Fi configuration saved to LittleFS.");
  return true;
}

bool setupButtonRequested() {
  pinMode(SETUP_BUTTON_PIN, INPUT_PULLUP);

  Serial.println();
  Serial.println("Press FLASH within 5 seconds for Wi-Fi setup...");

  unsigned long startTime = millis();

  while (millis() - startTime < SETUP_WINDOW) {
    if (digitalRead(SETUP_BUTTON_PIN) == LOW) {
      Serial.println("FLASH button detected.");
      Serial.println("Entering Wi-Fi setup mode...");
      delay(300);
      return true;
    }

    delay(10);
  }

  Serial.println("No Wi-Fi setup requested.");
  return false;
}

bool loadWiFiConfig() {
  if (!LittleFS.exists(WIFI_CONFIG)) {
    Serial.println("No /wifi_config.json found.");
    return false;
  }

  File f = LittleFS.open(WIFI_CONFIG, "r");

  if (!f) {
    Serial.println("ERROR: Cannot open /wifi_config.json.");
    return false;
  }

  String json = f.readString();
  f.close();

  wifiSSID = readJsonValue(json, "ssid");
  wifiPassword = readJsonValue(json, "password");

  if (wifiSSID.length() == 0) {
    Serial.println("ERROR: ssid missing in wifi_config.json.");
    return false;
  }

  return true;
}

void setupWiFiPortal() {
  Serial.println();
  Serial.println("==============================");
  Serial.println("Wi-Fi Setup Mode");
  Serial.println("==============================");

  WiFi.disconnect();
  delay(300);

  WiFi.mode(WIFI_AP);
  String apName = "PyGit-" + WiFi.macAddress();
  apName.replace(":", "");

  WiFi.softAP(apName.c_str());

  IPAddress apIP = WiFi.softAPIP();

  Serial.print("Setup WiFi: ");
  Serial.println(apName);
  Serial.print("Open this address: http://");
  Serial.println(apIP);

  server.on("/", HTTP_GET, []() {
    String html =
      "<!DOCTYPE html><html><head>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<title>PyGit WiFi Setup</title>"
      "<style>body{font-family:Arial;max-width:420px;margin:40px auto;padding:20px}"
      "input{width:100%;padding:12px;margin:8px 0;box-sizing:border-box}"
      "button{width:100%;padding:12px;margin-top:10px;font-size:16px}</style>"
      "</head><body>"
      "<h2>PyGit NodeMCU Setup</h2>"
      "<p>Enter the Wi-Fi credentials for this device.</p>"
      "<form method='POST' action='/save'>"
      "<label>Wi-Fi Name (SSID)</label>"
      "<input name='ssid' required>"
      "<label>Password</label>"
      "<input name='password' type='password'>"
      "<button type='submit'>Save & Connect</button>"
      "</form></body></html>";

    server.send(200, "text/html", html);
  });

  server.on("/save", HTTP_POST, []() {
    String ssid = server.arg("ssid");
    String password = server.arg("password");

    ssid.trim();

    if (ssid.length() == 0) {
      server.send(400, "text/plain", "SSID is required.");
      return;
    }

    if (!saveWiFiConfig(ssid, password)) {
      server.send(500, "text/plain", "Failed to save Wi-Fi configuration.");
      return;
    }

    server.send(
      200,
      "text/html",
      "<html><body><h2>Wi-Fi saved!</h2>"
      "<p>The NodeMCU will restart and connect to the new network.</p>"
      "</body></html>"
    );

    delay(1500);
    ESP.restart();
  });

  server.begin();

  Serial.println("Wi-Fi setup portal started.");
  Serial.println("Waiting for Wi-Fi credentials...");

  while (true) {
    server.handleClient();
    delay(2);
  }
}

bool connectToWiFi() {
  Serial.print("Connecting to WiFi");

  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());

  int attempts = 0;

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");

    attempts++;

    if (attempts >= 40) {
      Serial.println();
      Serial.println("WiFi connection timeout!");
      return false;
    }
  }

  Serial.println();
  Serial.println("WiFi connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  Serial.print("Device MAC: ");
  Serial.println(WiFi.macAddress());

  return true;
}

// Finds the version belonging to this ESP MAC.
String readDeviceVersion(const String& json, const String& mac) {
  String deviceKey = "\"" + mac + "\"";
  int devicePos = json.indexOf(deviceKey);

  if (devicePos < 0) return "";

  int versionPos = json.indexOf("\"version\"", devicePos);

  if (versionPos < 0) return "";

  return readJsonValue(json.substring(versionPos), "version");
}

String readGeneralFirmwareVersion(const String& json) {
  int generalPos = json.indexOf("\"general_version\"");
  if (generalPos < 0) return "";

  int inoPos = json.indexOf("\"ino\"", generalPos);
  if (inoPos < 0) return "";

  return readJsonValue(json.substring(inoPos), "ino");
}

void checkForFirmwareUpdate(const String& remoteConfig) {
  String remoteVersion = readGeneralFirmwareVersion(remoteConfig);

  if (remoteVersion.length() == 0) {
    Serial.println("Firmware version not found in config.json.");
    return;
  }

  Serial.println();
  Serial.println("==============================");
  Serial.println("FIRMWARE VERSION CHECK");
  Serial.println("==============================");
  Serial.print("Local firmware:  ");
  Serial.println(LOCAL_FIRMWARE_VERSION);
  Serial.print("GitHub firmware: ");
  Serial.println(remoteVersion);

  if (remoteVersion == LOCAL_FIRMWARE_VERSION) {
    Serial.println("Firmware is up to date.");
    Serial.println("==============================");
    return;
  }

  Serial.println("New firmware detected!");
  Serial.println("Starting OTA update...");
  Serial.println("==============================");

  WiFiClientSecure client;
  client.setInsecure();

  String url = String(FIRMWARE_URL) + "?pygit=" + String(millis());

  t_httpUpdate_return result = ESPhttpUpdate.update(client, url);

  switch (result) {
    case HTTP_UPDATE_FAILED:
      Serial.print("OTA update FAILED. Error: ");
      Serial.println(ESPhttpUpdate.getLastError());
      Serial.print("Message: ");
      Serial.println(ESPhttpUpdate.getLastErrorString());
      break;

    case HTTP_UPDATE_NO_UPDATES:
      Serial.println("OTA: No update available.");
      break;

    case HTTP_UPDATE_OK:
      Serial.println("OTA update successful. Restarting...");
      break;
  }
}

void checkGitHubConfig() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("ERROR: WiFi is not connected.");
    return;
  }

  Serial.println();
  Serial.println("Checking GitHub config.json...");

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;

  String url = String(configURL) + "&pygit=" + String(millis());

  Serial.print("Config URL: ");
  Serial.println(url);

  if (!http.begin(client, url)) {
    Serial.println("HTTP connection setup FAILED.");
    return;
  }

  http.setTimeout(15000);
  http.addHeader("Accept", "application/vnd.github.raw+json");
  http.addHeader("Cache-Control", "no-cache, no-store, max-age=0");
  http.addHeader("Pragma", "no-cache");
  http.addHeader("User-Agent", "PyGit-NodeMCU");

  int httpCode = http.GET();

  Serial.print("HTTP Code: ");
  Serial.println(httpCode);

  if (httpCode != HTTP_CODE_OK) {
    Serial.println("GitHub config download FAILED.");
    Serial.println(http.getString());
    http.end();
    return;
  }

  String payload = http.getString();
  http.end();

  Serial.println("config.json downloaded.");

  String deviceMAC = WiFi.macAddress();

  Serial.print("Device MAC: ");
  Serial.println(deviceMAC);

  String version = readDeviceVersion(payload, deviceMAC);

  if (version.length() == 0) {
    Serial.println();
    Serial.println("Device NOT found in config.json!");
    Serial.print("MAC searched: ");
    Serial.println(deviceMAC);
    return;
  }

  Serial.println();
  Serial.println("==============================");
  Serial.println("DEVICE FOUND!");
  Serial.println("==============================");
  Serial.print("MAC: ");
  Serial.println(deviceMAC);
  Serial.print("Version: ");
  Serial.println(version);
  Serial.println("==============================");
  Serial.println("CONFIG CHECK SUCCESSFUL!");

  // Check the general firmware version after the config/device check.
  checkForFirmwareUpdate(payload);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("==============================");
  Serial.println("NodeMCU PyGit");
  Serial.println("==============================");

  if (!LittleFS.begin()) {
    Serial.println("ERROR: LittleFS mount FAILED.");
    return;
  }

  Serial.println("LittleFS mounted.");

  // Check the built-in FLASH button AFTER normal firmware startup.
  // This avoids interfering with the ESP8266 bootloader.
  if (setupButtonRequested()) {
    setupWiFiPortal();
    return;
  }

  // If credentials are missing/invalid, start the browser setup portal.
  if (!loadWiFiConfig()) {
    setupWiFiPortal();
    return;
  }

  Serial.println("Wi-Fi configuration loaded from LittleFS.");

  // Normal boot: connect using the saved local credentials.
  if (!connectToWiFi()) {
    // If the saved Wi-Fi no longer works, allow reconfiguration
    // without requiring another firmware upload.
    setupWiFiPortal();
    return;
  }

  // Phase 1 test:
  // connect WiFi -> identify device -> read remote config -> print version.
  Serial.println();
  Serial.println("Hello World!");
  Serial.print("PyGit Firmware ");
  Serial.println(LOCAL_FIRMWARE_VERSION);

  checkGitHubConfig();
}

void loop() {
}
