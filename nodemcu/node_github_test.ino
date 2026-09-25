#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <LittleFS.h>
#include <ArduinoJson.h>

const char* WIFI_CONFIG = "/wifi_config.json";

const char* githubURL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/refs/heads/main/nodemcu/node_test.txt";

String wifiSSID = "";
String wifiPassword = "";

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

  DynamicJsonDocument doc(1024);
  DeserializationError err = deserializeJson(doc, f);
  f.close();

  if (err) {
    Serial.print("ERROR: Invalid wifi_config.json: ");
    Serial.println(err.c_str());
    return false;
  }

  wifiSSID = doc["ssid"] | "";
  wifiPassword = doc["password"] | "";

  if (wifiSSID.length() == 0 || wifiPassword.length() == 0) {
    Serial.println("ERROR: ssid/password missing in wifi_config.json.");
    return false;
  }

  return true;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("==============================");
  Serial.println("NodeMCU GitHub Test");
  Serial.println("==============================");

  // Load Wi-Fi credentials from LittleFS.
  if (!LittleFS.begin()) {
    Serial.println("ERROR: LittleFS mount FAILED.");
    return;
  }

  Serial.println("LittleFS mounted.");

  if (!loadWiFiConfig()) {
    Serial.println("Wi-Fi configuration FAILED.");
    return;
  }

  Serial.println("Wi-Fi configuration loaded from LittleFS.");

  Serial.print("Connecting to WiFi");

  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  Serial.println();
  Serial.println("Connecting to GitHub...");

  WiFiClientSecure client;
  client.setInsecure(); // Temporary connectivity test only.

  HTTPClient http;

  // Cache-busting helps make sure the NodeMCU requests the current file.
  String url = String(githubURL) + "?pygit=" + String(millis());

  Serial.print("URL: ");
  Serial.println(url);

  if (!http.begin(client, url)) {
    Serial.println("HTTP connection setup FAILED.");
    return;
  }

  http.setTimeout(15000);

  int httpCode = http.GET();

  Serial.print("HTTP Code: ");
  Serial.println(httpCode);

  String payload = http.getString();

  if (httpCode == HTTP_CODE_OK) {
    Serial.println();
    Serial.println("===== GITHUB CONTENT =====");
    Serial.println(payload);
    Serial.println("==========================");
    Serial.println();

    Serial.println("TEST SUCCESSFUL!");
  } else {
    Serial.println();
    Serial.println("GitHub download FAILED.");
    Serial.println("===== SERVER RESPONSE =====");
    Serial.println(payload);
    Serial.println("==========================");
  }

  http.end();
}

void loop() {
}
