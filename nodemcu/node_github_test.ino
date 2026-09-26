#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <LittleFS.h>
#include <ESP8266WebServer.h>
#include <Updater.h>

const char* WIFI_CONFIG = "/wifi_config.json";
const char* DEVICE_CONFIG_FILE = "/device_config.json";

const int SETUP_BUTTON_PIN = 0;
const unsigned long SETUP_WINDOW = 5000;
const unsigned long UPDATE_CHECK_INTERVAL = 60000;
unsigned long lastUpdateCheck = 0;

// Firmware version. GitHub Actions does NOT change this automatically.
const char* LOCAL_FIRMWARE_VERSION = "1.0.3";

const char* FIRMWARE_URL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/main/nodemcu/firmware.bin";

const char* configURL =
  "https://api.github.com/repos/royalguard14/PyGit/contents/nodemcu/data/config.json?ref=main";

String wifiSSID = "";
String wifiPassword = "";

ESP8266WebServer server(80);

String readJsonValue(const String& json, const String& key) {
  String searchKey = "\""+ key + "\"";
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

String readDeviceObject(const String& json, const String& mac) {
  String deviceKey = "\""+ mac + "\"";
  int devicePos = json.indexOf(deviceKey);
  if (devicePos < 0) return "";

  int objectStart = json.indexOf('{', devicePos);
  if (objectStart < 0) return "";

  int objectEnd = json.indexOf('}', objectStart);
  if (objectEnd < 0) return "";

  return json.substring(objectStart, objectEnd + 1);
}

String readGeneralFirmwareVersion(const String& json) {
  int generalPos = json.indexOf("\"general_version\"");
  if (generalPos < 0) return "";

  int inoPos = json.indexOf("\"ino\"", generalPos);
  if (inoPos < 0) return "";

  return readJsonValue(json.substring(inoPos), "ino");
}

String readDeviceConfigVersion(const String& deviceObject) {
  return readJsonValue(deviceObject, "version");
}

void saveDeviceConfig(const String& deviceObject) {
  File f = LittleFS.open(DEVICE_CONFIG_FILE, "w");
  if (!f) {
    Serial.println("WARNING: Cannot save device configuration.");
    return;
  }
  f.print(deviceObject);
  f.close();
  Serial.println("Device configuration saved to LittleFS.");
}

void showDeviceConfig(const String& deviceObject) {
  Serial.println();
  Serial.println("------------------------------");
  Serial.println("DEVICE CONFIGURATION");
  Serial.println("------------------------------");

  Serial.print("Config version: ");
  Serial.println(readJsonValue(deviceObject, "version"));

  String shopName = readJsonValue(deviceObject, "shop_name");
  String googleSheet = readJsonValue(deviceObject, "google_sheet");
  String timeInput = readJsonValue(deviceObject, "time_input_per_pulse");

  if (shopName.length()) {
    Serial.print("Shop name: ");
    Serial.println(shopName);
  }
  if (googleSheet.length()) {
    Serial.print("Google Sheet: ");
    Serial.println(googleSheet);
  }
  if (timeInput.length()) {
    Serial.print("Time input/pulse: ");
    Serial.println(timeInput);
  }

  Serial.println("------------------------------");
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
      "</head><body><h2>PyGit NodeMCU Setup</h2>"
      "<p>Enter the Wi-Fi credentials for this device.</p>"
      "<form method='POST' action='/save'>"
      "<label>Wi-Fi Name (SSID)</label><input name='ssid' required>"
      "<label>Password</label><input name='password' type='password'>"
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

    server.send(200, "text/html",
      "<html><body><h2>Wi-Fi saved!</h2>"
      "<p>The NodeMCU will restart and connect to the new network.</p>"
      "</body></html>");

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
  Serial.print("GitHub general:  ");
  Serial.println(remoteVersion);

  int localMajor = 0, localMinor = 0, localPatch = 0;
  int remoteMajor = 0, remoteMinor = 0, remotePatch = 0;

  sscanf(LOCAL_FIRMWARE_VERSION, "%d.%d.%d", &localMajor, &localMinor, &localPatch);
  sscanf(remoteVersion.c_str(), "%d.%d.%d", &remoteMajor, &remoteMinor, &remotePatch);

  bool newer =
    (remoteMajor > localMajor) ||
    (remoteMajor == localMajor && remoteMinor > localMinor) ||
    (remoteMajor == localMajor && remoteMinor == localMinor && remotePatch > localPatch);

  bool same =
    remoteMajor == localMajor &&
    remoteMinor == localMinor &&
    remotePatch == localPatch;

  if (!newer) {
    if (same) {
      Serial.println("Firmware is up to date.");
    } else {
      Serial.println("GitHub firmware is older. No automatic downgrade.");
    }

    Serial.println("==============================");
    return;
  }

  Serial.println("Newer firmware detected!");
  Serial.println("Starting OTA update...");
  Serial.println("==============================");

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  String url = String(FIRMWARE_URL) + "?pygit=" + String(millis());

  Serial.println("Connecting to firmware server...");
  Serial.print("Firmware URL: ");
  Serial.println(url);

  if (!http.begin(client, url)) {
    Serial.println("OTA HTTP setup FAILED.");
    return;
  }

  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.setRedirectLimit(5);
  http.setTimeout(30000);
  http.useHTTP10(true);
  http.setUserAgent("PyGit-NodeMCU");
  http.addHeader("Cache-Control", "no-cache, no-store, max-age=0");
  http.addHeader("Pragma", "no-cache");

  int httpCode = http.GET();

  Serial.print("Firmware HTTP Code: ");
  Serial.println(httpCode);

  if (httpCode != HTTP_CODE_OK) {
    Serial.print("Firmware download FAILED: ");
    Serial.println(http.errorToString(httpCode));
    http.end();
    return;
  }

  int contentLength = http.getSize();

  Serial.print("Firmware size: ");
  Serial.print(contentLength);
  Serial.println(" bytes");

  if (contentLength <= 0) {
    Serial.println("OTA FAILED: Invalid firmware size.");
    http.end();
    return;
  }

  WiFiClient* stream = http.getStreamPtr();

  if (!stream) {
    Serial.println("OTA FAILED: Firmware stream unavailable.");
    http.end();
    return;
  }

  if (!Update.begin((size_t)contentLength, U_FLASH)) {
    Serial.print("OTA FAILED: Update.begin(): ");
    Serial.println(Update.getErrorString());
    http.end();
    return;
  }

  Serial.println("Downloading firmware to flash...");

  size_t written = Update.writeStream(*stream);

  Serial.print("Written: ");
  Serial.print(written);
  Serial.print("/");
  Serial.println(contentLength);

  if (written != (size_t)contentLength) {
    Serial.print("OTA FAILED: Incomplete download. Update error: ");
    Serial.println(Update.getErrorString());
    Update.end();
    http.end();
    return;
  }

  if (!Update.end()) {
    Serial.print("OTA FAILED: Update.end(): ");
    Serial.println(Update.getErrorString());
    http.end();
    return;
  }

  http.end();

  if (!Update.isFinished()) {
    Serial.println("OTA FAILED: Update is not finished.");
    return;
  }

  Serial.println("OTA update successful!");
  Serial.println("Restarting...");
  delay(1000);
  ESP.restart();
}

void checkDeviceConfiguration(const String& remoteConfig) {
  String deviceMAC = WiFi.macAddress();
  String deviceObject = readDeviceObject(remoteConfig, deviceMAC);

  Serial.println();
  Serial.println("==============================");
  Serial.println("DEVICE CONFIG CHECK");
  Serial.println("==============================");

  if (deviceObject.length() == 0) {
    Serial.println("Device NOT found in config.json!");
    Serial.print("MAC searched: ");
    Serial.println(deviceMAC);
    return;
  }

  String remoteConfigVersion = readDeviceConfigVersion(deviceObject);
  String localConfigVersion = "";

  if (LittleFS.exists(DEVICE_CONFIG_FILE)) {
    File f = LittleFS.open(DEVICE_CONFIG_FILE, "r");
    if (f) {
      localConfigVersion = readDeviceConfigVersion(f.readString());
      f.close();
    }
  }

  Serial.print("MAC: ");
  Serial.println(deviceMAC);
  Serial.print("Local config:  ");
  Serial.println(localConfigVersion.length() ? localConfigVersion : "(none)");
  Serial.print("GitHub config: ");
  Serial.println(remoteConfigVersion);

  if (localConfigVersion != remoteConfigVersion) {
    Serial.println("New device configuration detected.");
    saveDeviceConfig(deviceObject);
    showDeviceConfig(deviceObject);
  } else {
    Serial.println("Device configuration is up to date.");
  }

  Serial.println("==============================");
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

  checkDeviceConfiguration(payload);
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

  if (setupButtonRequested()) {
    setupWiFiPortal();
    return;
  }

  if (!loadWiFiConfig()) {
    setupWiFiPortal();
    return;
  }

  Serial.println("Wi-Fi configuration loaded from LittleFS.");

  if (!connectToWiFi()) {
    setupWiFiPortal();
    return;
  }

  Serial.println();
  Serial.print("PyGit Firmware ");
  Serial.println(LOCAL_FIRMWARE_VERSION);
  Serial.println("Hello from node_github_test.ino!");
  Serial.println("OTA TEST BUILD: 1.0.3");

  checkGitHubConfig();
  lastUpdateCheck = millis();
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    if (millis() - lastUpdateCheck >= UPDATE_CHECK_INTERVAL) {
      lastUpdateCheck = millis();
      checkGitHubConfig();
    }
  } else {
    static unsigned long lastReconnectAttempt = 0;

    if (millis() - lastReconnectAttempt >= 10000) {
      lastReconnectAttempt = millis();

      Serial.println();
      Serial.println("WiFi disconnected. Reconnecting...");
      WiFi.disconnect();
      WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());

      if (connectToWiFi()) {
        checkGitHubConfig();
        lastUpdateCheck = millis();
      }
    }
  }
}
