#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <LittleFS.h>
#include <ESP8266WebServer.h>
#include <Updater.h>

const char* WIFI_CONFIG = "/wifi_config.json";
const char* DEVICE_CONFIG_FILE = "/device_config.json";
const char* CONFIG_URL = "https://api.github.com/repos/royalguard14/PyGit/contents/nodemcu/data/config.json?ref=main";
const char* PYGIT_FIRMWARE_URL = "https://raw.githubusercontent.com/royalguard14/PyGit/main/nodemcu/firmware.bin";
const char* PYGIT_MD5_URL = "https://raw.githubusercontent.com/royalguard14/PyGit/main/nodemcu/firmware.md5";
const char* PYGIT_LOCAL_HASH_FILE = "/pygit_firmware.md5";

const uint8_t FLASH_BUTTON = 0;
const unsigned long WIFI_SETUP_WINDOW = 5000;
const unsigned long CHECK_INTERVAL = 60000;
unsigned long lastCheck = 0;

String wifiSSID, wifiPassword;
ESP8266WebServer server(80);

String jsonValue(const String& json, const String& key) {
  String token = "\"" + key + "\"";
  int p = json.indexOf(token);
  if (p < 0) return "";
  p = json.indexOf(':', p + token.length());
  if (p < 0) return "";
  int a = json.indexOf('"', p + 1);
  if (a < 0) return "";
  int b = json.indexOf('"', a + 1);
  if (b < 0) return "";
  return json.substring(a + 1, b);
}

String deviceObject(const String& json, const String& mac) {
  int p = json.indexOf("\"" + mac + "\"");
  if (p < 0) return "";
  int start = json.indexOf('{', p);
  if (start < 0) return "";

  int depth = 0;
  bool quoted = false, escaped = false;
  for (int i = start; i < (int)json.length(); i++) {
    char c = json[i];
    if (quoted) {
      if (escaped) escaped = false;
      else if (c == '\\') escaped = true;
      else if (c == '"') quoted = false;
      continue;
    }
    if (c == '"') quoted = true;
    else if (c == '{') depth++;
    else if (c == '}' && --depth == 0) return json.substring(start, i + 1);
  }
  return "";
}

void saveDeviceConfig(const String& object) {
  File f = LittleFS.open(DEVICE_CONFIG_FILE, "w");
  if (!f) {
    Serial.println("WARNING: Cannot save device configuration.");
    return;
  }
  f.print(object);
  f.close();
}

void showDeviceConfig(const String& object) {
  Serial.println();
  Serial.println("------------------------------");
  Serial.println("DEVICE CONFIGURATION");
  Serial.println("------------------------------");
  Serial.print("Config version: "); Serial.println(jsonValue(object, "version"));
  Serial.print("Shop name: "); Serial.println(jsonValue(object, "shop_name"));
  Serial.print("Google Sheet: "); Serial.println(jsonValue(object, "google_sheet"));
  Serial.print("Time input/pulse: "); Serial.println(jsonValue(object, "time_input_per_pulse"));
  Serial.println("------------------------------");
}

bool loadWiFiConfig() {
  if (!LittleFS.exists(WIFI_CONFIG)) return false;
  File f = LittleFS.open(WIFI_CONFIG, "r");
  if (!f) return false;
  String json = f.readString();
  f.close();
  wifiSSID = jsonValue(json, "ssid");
  wifiPassword = jsonValue(json, "password");
  return wifiSSID.length() > 0;
}

bool saveWiFiConfig(const String& ssid, const String& password) {
  File f = LittleFS.open(WIFI_CONFIG, "w");
  if (!f) return false;
  f.print("{\n  \"ssid\": \""); f.print(ssid);
  f.print("\",\n  \"password\": \""); f.print(password);
  f.println("\"\n}");
  f.close();
  wifiSSID = ssid;
  wifiPassword = password;
  return true;
}

void startWiFiSetup() {
  WiFi.mode(WIFI_AP);
  String ap = "PyGit-" + WiFi.macAddress();
  ap.replace(":", "");
  WiFi.softAP(ap.c_str());

  Serial.println("\n==============================");
  Serial.println("Wi-Fi Setup Mode");
  Serial.println("==============================");
  Serial.print("Setup SSID: "); Serial.println(ap);
  Serial.print("Open: http://"); Serial.println(WiFi.softAPIP());

  server.on("/", HTTP_GET, []() {
    server.send(200, "text/html",
      "<meta name='viewport' content='width=device-width'>"
      "<h2>PyGit WiFi Setup</h2>"
      "<form method='POST' action='/save'>"
      "SSID:<br><input name='ssid' required><br><br>"
      "Password:<br><input name='password' type='password'><br><br>"
      "<button>Save & Connect</button></form>");
  });

  server.on("/save", HTTP_POST, []() {
    String ssid = server.arg("ssid");
    String password = server.arg("password");
    ssid.trim();
    if (!saveWiFiConfig(ssid, password)) {
      server.send(500, "text/plain", "Could not save WiFi configuration.");
      return;
    }
    server.send(200, "text/html", "<h2>Saved.</h2><p>Restarting...</p>");
    delay(1000);
    ESP.restart();
  });

  server.begin();
  while (true) {
    server.handleClient();
    delay(2);
  }
}

bool flashPressedAtStartup() {
  pinMode(FLASH_BUTTON, INPUT_PULLUP);
  Serial.println("Press FLASH within 5 seconds for Wi-Fi setup...");
  unsigned long started = millis();
  while (millis() - started < WIFI_SETUP_WINDOW) {
    if (digitalRead(FLASH_BUTTON) == LOW) return true;
    delay(10);
  }
  Serial.println("No Wi-Fi setup requested.");
  return false;
}

bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());
  Serial.print("Connecting to WiFi");
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) return false;
  Serial.println("WiFi connected!");
  Serial.print("IP: "); Serial.println(WiFi.localIP());
  Serial.print("Device MAC: "); Serial.println(WiFi.macAddress());
  return true;
}

void checkDeviceConfig(const String& remote) {
  String mac = WiFi.macAddress();
  String remoteObject = deviceObject(remote, mac);

  Serial.println("\n==============================");
  Serial.println("DEVICE CONFIG CHECK");
  Serial.println("==============================");
  Serial.print("MAC: "); Serial.println(mac);

  if (!remoteObject.length()) {
    Serial.println("Device NOT found in config.json!");
    return;
  }

  String remoteVersion = jsonValue(remoteObject, "version");
  String localVersion;
  if (LittleFS.exists(DEVICE_CONFIG_FILE)) {
    File f = LittleFS.open(DEVICE_CONFIG_FILE, "r");
    if (f) { localVersion = jsonValue(f.readString(), "version"); f.close(); }
  }

  Serial.print("Local config:  "); Serial.println(localVersion.length() ? localVersion : "(none)");
  Serial.print("GitHub config: "); Serial.println(remoteVersion);

  if (localVersion != remoteVersion) {
    Serial.println("New device configuration detected.");
    saveDeviceConfig(remoteObject);
    showDeviceConfig(remoteObject);
  } else {
    Serial.println("Device configuration is up to date.");
  }
  Serial.println("==============================");
}

String normalizeHash(String value) {
  value.trim();
  int p = value.indexOf(' ');
  if (p > 0) value = value.substring(0, p);
  p = value.indexOf('\t');
  if (p > 0) value = value.substring(0, p);
  value.trim();
  value.toLowerCase();
  return value;
}

String localFirmwareHash() {
  if (!LittleFS.exists(PYGIT_LOCAL_HASH_FILE)) return "";
  File f = LittleFS.open(PYGIT_LOCAL_HASH_FILE, "r");
  if (!f) return "";
  String h = normalizeHash(f.readString());
  f.close();
  return h;
}

bool saveFirmwareHash(const String& hash) {
  File f = LittleFS.open(PYGIT_LOCAL_HASH_FILE, "w");
  if (!f) return false;
  f.println(hash);
  f.close();
  return true;
}

String remoteFirmwareHash() {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;
  String url = String(PYGIT_MD5_URL) + "?pygit=" + String(millis());

  Serial.print("Update identity URL: "); Serial.println(url);
  if (!http.begin(client, url)) return "";
  http.setTimeout(15000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.setRedirectLimit(5);
  http.addHeader("Cache-Control", "no-cache, no-store, max-age=0");
  http.addHeader("Pragma", "no-cache");
  http.addHeader("User-Agent", "PyGit-NodeMCU");

  int code = http.GET();
  Serial.print("Update identity HTTP Code: "); Serial.println(code);
  if (code != HTTP_CODE_OK) { http.end(); return ""; }

  String h = normalizeHash(http.getString());
  http.end();
  if (h.length() != 32) return "";
  return h;
}

bool downloadFirmware(const String& expectedHash) {
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;
  String url = String(PYGIT_FIRMWARE_URL) + "?pygit=" + String(millis());

  Serial.println("Downloading updated PyGit code...");
  Serial.print("Firmware URL: "); Serial.println(url);
  if (!http.begin(client, url)) return false;
  http.setTimeout(30000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.setRedirectLimit(5);
  http.useHTTP10(true);
  http.addHeader("Cache-Control", "no-cache, no-store, max-age=0");
  http.addHeader("Pragma", "no-cache");
  http.addHeader("User-Agent", "PyGit-NodeMCU");

  int code = http.GET();
  Serial.print("Firmware HTTP Code: "); Serial.println(code);
  if (code != HTTP_CODE_OK) { http.end(); return false; }

  int size = http.getSize();
  Serial.print("Firmware size: "); Serial.print(size); Serial.println(" bytes");
  if (size <= 0) { http.end(); return false; }

  WiFiClient* stream = http.getStreamPtr();
  if (!stream) { http.end(); return false; }

  if (!Update.begin((size_t)size, U_FLASH)) {
    Serial.print("Update.begin() FAILED: "); Serial.println(Update.getErrorString());
    http.end(); return false;
  }

  if (!Update.setMD5(expectedHash.c_str())) {
    Serial.println("Could not configure firmware MD5 verification.");
    Update.end(); http.end(); return false;
  }

  size_t written = Update.writeStream(*stream);
  Serial.print("Written: "); Serial.print(written); Serial.print("/"); Serial.println(size);

  if (written != (size_t)size) {
    Serial.print("Firmware write FAILED: "); Serial.println(Update.getErrorString());
    Update.end(); http.end(); return false;
  }

  if (!Update.end() || !Update.isFinished()) {
    Serial.print("Firmware update FAILED: "); Serial.println(Update.getErrorString());
    http.end(); return false;
  }

  http.end();
  saveFirmwareHash(expectedHash);
  Serial.println("PyGit code update successful!");
  Serial.println("Restarting into updated code...");
  delay(1000);
  ESP.restart();
  return true;
}

void checkPyGitCodeUpdate() {
  if (WiFi.status() != WL_CONNECTED) return;

  Serial.println("\n==============================");
  Serial.println("PYGIT CODE UPDATE CHECK");
  Serial.println("==============================");

  String remoteHash = remoteFirmwareHash();
  if (!remoteHash.length()) {
    Serial.println("Update check skipped.");
    Serial.println("==============================");
    return;
  }

  String localHash = localFirmwareHash();
  Serial.print("Local code identity:  "); Serial.println(localHash.length() ? localHash : "(none)");
  Serial.print("GitHub code identity: "); Serial.println(remoteHash);

  if (localHash == remoteHash) {
    Serial.println("Code is up to date.");
    Serial.println("==============================");
    return;
  }

  Serial.println("Different code detected. Downloading latest firmware...");
  Serial.println("==============================");
  downloadFirmware(remoteHash);
}

void checkGitHubConfig() {
  if (WiFi.status() != WL_CONNECTED) return;

  Serial.println("\nChecking GitHub config.json...");
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;
  String url = String(CONFIG_URL) + "&pygit=" + String(millis());

  Serial.print("Config URL: "); Serial.println(url);
  if (!http.begin(client, url)) {
    Serial.println("HTTP connection setup FAILED.");
    return;
  }
  http.setTimeout(15000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.setRedirectLimit(5);
  http.addHeader("Accept", "application/vnd.github.raw+json");
  http.addHeader("Cache-Control", "no-cache, no-store, max-age=0");
  http.addHeader("Pragma", "no-cache");
  http.addHeader("User-Agent", "PyGit-NodeMCU");

  int code = http.GET();
  Serial.print("HTTP Code: "); Serial.println(code);
  if (code != HTTP_CODE_OK) {
    Serial.println("GitHub config download FAILED.");
    http.end();
    return;
  }

  String remote = http.getString();
  http.end();
  Serial.println("config.json downloaded.");
  Serial.println("[PYGIT] Step 1/3: processing device configuration...");
  delay(50);
  checkDeviceConfig(remote);
  Serial.println("[PYGIT] Step 2/3: device configuration finished.");
  Serial.println("[PYGIT] Step 3/3: checking firmware identity...");
  delay(50);
  checkPyGitCodeUpdate();
  Serial.println("[PYGIT] Update check finished.");
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n==============================");
  Serial.println("NodeMCU PyGit");
  Serial.println("==============================");

  if (!LittleFS.begin()) {
    Serial.println("ERROR: LittleFS mount FAILED.");
    return;
  }
  Serial.println("LittleFS mounted.");

  if (flashPressedAtStartup()) startWiFiSetup();
  if (!loadWiFiConfig()) startWiFiSetup();
  Serial.println("Wi-Fi configuration loaded from LittleFS.");

  if (!connectWiFi()) startWiFiSetup();
  Serial.println("\nPyGit base code online.");
  checkGitHubConfig();
  lastCheck = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    return;
  }
  if (millis() - lastCheck >= CHECK_INTERVAL) {
    lastCheck = millis();
    checkGitHubConfig();
  }
}
