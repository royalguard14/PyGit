#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <LittleFS.h>

const char* WIFI_CONFIG = "/wifi_config.json";

const char* configURL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/refs/heads/main/nodemcu/data/config.json";

String wifiSSID = "";
String wifiPassword = "";

// Simple JSON value reader.
// This avoids requiring the ArduinoJson library.
String readJsonValue(const String& json, const String& key) {
  String searchKey = "\""+ key +"\"";
  int keyPos = json.indexOf(searchKey);

  if (keyPos < 0) {
    return "";
  }

  int colonPos = json.indexOf(':', keyPos + searchKey.length());

  if (colonPos < 0) {
    return "";
  }

  int quoteStart = json.indexOf('"', colonPos + 1);

  if (quoteStart < 0) {
    return "";
  }

  int quoteEnd = json.indexOf('"', quoteStart + 1);

  if (quoteEnd < 0) {
    return "";
  }

  return json.substring(quoteStart + 1, quoteEnd);
}

bool loadWiFiConfig() {
  if (!LittleFS.exists(WIFI_CONFIG)) {
    Serial.println("ERROR: /wifi_config.json not found.");
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

  if (wifiSSID.length() == 0 || wifiPassword.length() == 0) {
    Serial.println("ERROR: ssid/password missing in wifi_config.json.");
    return false;
  }

  return true;
}

// Finds the version belonging to this ESP MAC.
// Current test config is intentionally simple and does not require
// ArduinoJson yet.
String readDeviceVersion(const String& json, const String& mac) {
  String deviceKey = "\"" + mac + "\"";
  int devicePos = json.indexOf(deviceKey);

  if (devicePos < 0) {
    return "";
  }

  int versionPos = json.indexOf("\"version\"", devicePos);

  if (versionPos < 0) {
    return "";
  }

  return readJsonValue(json.substring(versionPos), "version");
}

void checkGitHubConfig() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("ERROR: WiFi is not connected.");
    return;
  }

  Serial.println();
  Serial.println("Checking GitHub config.json...");

  WiFiClientSecure client;
  client.setInsecure(); // Temporary test only.

  HTTPClient http;

  // Cache-busting helps request the current GitHub file.
  String url = String(configURL) + "?pygit=" + String(millis());

  Serial.print("Config URL: ");
  Serial.println(url);

  if (!http.begin(client, url)) {
    Serial.println("HTTP connection setup FAILED.");
    return;
  }

  http.setTimeout(15000);

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
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("==============================");
  Serial.println("NodeMCU GitHub Config Test");
  Serial.println("==============================");

  // Mount LittleFS.
  if (!LittleFS.begin()) {
    Serial.println("ERROR: LittleFS mount FAILED.");
    return;
  }

  Serial.println("LittleFS mounted.");

  // Load Wi-Fi credentials from local wifi_config.json.
  if (!loadWiFiConfig()) {
    Serial.println("Wi-Fi configuration FAILED.");
    return;
  }

  Serial.println("Wi-Fi configuration loaded from LittleFS.");

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
      return;
    }
  }

  Serial.println();
  Serial.println("WiFi connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  Serial.print("Device MAC: ");
  Serial.println(WiFi.macAddress());

  // Phase 1 test:
  // connect WiFi -> identify device -> read remote config -> print version.
  checkGitHubConfig();
}

void loop() {
}
