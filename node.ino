#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <LiquidCrystal_I2C.h>
#include <vector>

#define COIN_PIN    D6       // GPIO12 - coin pulse
#define TRIGGER_PIN D5       // GPIO14 - client trigger

const char* WIFI_CONFIG = "/wifi_config.json";

struct PCInfo { String name; String ip; };
std::vector<PCInfo> pcs;

ESP8266WebServer server(80);
LiquidCrystal_I2C lcd(0x27, 16, 2);

bool wifiConnected = false;
String selectedPC = "";
String wifiSSID = "";
String wifiPassword = "";

int minutesPerPulse = 8;
int pulseCount = 0;
unsigned long pulse_gap_ms = 300;
unsigned int debounce_us = 500;
unsigned long selectionTimeoutMs = 30000;
unsigned long selectionStartedAt = 0;

void showStatus() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Target:");
  if (selectedPC.length() > 0) lcd.print(selectedPC.substring(0, 9));
  else lcd.print("NONE");
  lcd.setCursor(0, 1);
  lcd.print(digitalRead(TRIGGER_PIN) == LOW ? "TRIGGER READY" : "Waiting...");
}

void clearSelection(const String &reason) {
  if (selectedPC.length() > 0)
    Serial.println("Target cleared: " + selectedPC + " (" + reason + ")");
  selectedPC = "";
  selectionStartedAt = 0;
  showStatus();
}

bool loadWiFiConfig() {
  if (!LittleFS.exists(WIFI_CONFIG)) {
    Serial.println("ERROR: /wifi_config.json not found.");
    return false;
  }

  File f = LittleFS.open(WIFI_CONFIG, "r");
  if (!f) return false;

  DynamicJsonDocument doc(1024);
  DeserializationError err = deserializeJson(doc, f);
  f.close();

  if (err) {
    Serial.println("ERROR: Invalid wifi_config.json");
    return false;
  }

  wifiSSID = doc["ssid"] | "";
  wifiPassword = doc["password"] | "";

  wifiSSID.trim();

  if (wifiSSID.length() == 0) {
    Serial.println("ERROR: WiFi SSID is empty.");
    return false;
  }

  Serial.println("WiFi credentials loaded from LittleFS.");
  return true;
}

void loadConfig() {
  if (!LittleFS.exists("/config.json")) return;

  File f = LittleFS.open("/config.json", "r");
  DynamicJsonDocument doc(4096);

  if (deserializeJson(doc, f)) {
    f.close();
    return;
  }
  f.close();

  minutesPerPulse = doc["minutes_per_pulse"] | minutesPerPulse;
  pulse_gap_ms = doc["pulse_gap_ms"] | pulse_gap_ms;
  debounce_us = doc["debounce_us"] | debounce_us;
  selectionTimeoutMs = doc["selection_timeout_ms"] | selectionTimeoutMs;

  pcs.clear();
  JsonArray arr = doc["pcs"].as<JsonArray>();

  for (JsonVariant v : arr) {
    PCInfo p;
    p.name = v["name"].as<String>();
    p.ip = v["ip"].as<String>();
    if (p.name.length() > 0 && p.ip.length() > 0) pcs.push_back(p);
  }
}

PCInfo* findPC(const String &name) {
  for (auto &p : pcs)
    if (p.name == name) return &p;
  return nullptr;
}

void logCoin(const String &pcName, int minutes) {
  File f = LittleFS.open("/log.txt", "a");
  if (!f) return;
  f.printf("%lu,%s,%d\n", millis(), pcName.c_str(), minutes);
  f.close();
}

// Client presses ADD and selects a target:
// GET /select?pc=PC1
void handleSelect() {
  if (!server.hasArg("pc")) {
    server.send(400, "text/plain", "Missing pc");
    return;
  }

  String pcName = server.arg("pc");
  pcName.trim();

  PCInfo* pc = findPC(pcName);
  if (!pc) {
    server.send(404, "text/plain", "Unknown PC: " + pcName);
    return;
  }

  selectedPC = pcName;
  selectionStartedAt = millis();

  Serial.println();
  Serial.println("CLIENT TARGET SELECTED: " + selectedPC);
  Serial.println("Waiting for GPIO14 trigger...");

  showStatus();
  server.send(200, "text/plain", "OK:" + selectedPC);
}

void handleCancel() {
  clearSelection("client cancelled");
  server.send(200, "text/plain", "CANCELLED");
}

void handleStatus() {
  String json = "{";
  json += "\"target\":\"" + selectedPC + "\",";
  json += "\"trigger\":" + String(digitalRead(TRIGGER_PIN) == LOW ? "true" : "false") + ",";
  json += "\"wifi\":" + String(wifiConnected ? "true" : "false");
  json += "}";
  server.send(200, "application/json", json);
}

void handleDashboard() {
  if (LittleFS.exists("/dashboard.html")) {
    File f = LittleFS.open("/dashboard.html", "r");
    server.streamFile(f, "text/html");
    f.close();
  } else server.send(404, "text/plain", "dashboard.html not found");
}

void handleSettings() {
  if (LittleFS.exists("/setting.html")) {
    File f = LittleFS.open("/setting.html", "r");
    server.streamFile(f, "text/html");
    f.close();
  } else server.send(404, "text/plain", "setting.html not found");
}

void handleEditor() {
  if (LittleFS.exists("/editor.html")) {
    File f = LittleFS.open("/editor.html", "r");
    server.streamFile(f, "text/html");
    f.close();
  } else server.send(404, "text/plain", "editor.html not found");
}


const char* FIRMWARE_HASH_URL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/refs/heads/main/nodemcu/firmware.sha256";
const char* FIRMWARE_BIN_URL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/refs/heads/main/nodemcu/firmware.bin";
const char* LOCAL_FIRMWARE_HASH = "/firmware.sha256";

String normalizeHash(String value) {
  value.trim();
  value.toLowerCase();
  return value;
}

String hashToHex(BearSSL::HashSHA256 &hash) {
  const uint8_t* digest = (const uint8_t*)hash.hash();
  const char hex[] = "0123456789abcdef";
  String result;
  result.reserve(64);
  for (int i = 0; i < 32; i++) {
    result += hex[(digest[i] >> 4) & 0x0F];
    result += hex[digest[i] & 0x0F];
  }
  return result;
}

String loadLocalFirmwareHash() {
  if (!LittleFS.exists(LOCAL_FIRMWARE_HASH)) return "";
  File f = LittleFS.open(LOCAL_FIRMWARE_HASH, "r");
  if (!f) return "";
  String hash = f.readString();
  f.close();
  return normalizeHash(hash);
}

bool saveLocalFirmwareHash(const String &hash) {
  File f = LittleFS.open(LOCAL_FIRMWARE_HASH, "w");
  if (!f) return false;
  f.println(hash);
  f.close();
  return true;
}

String getRemoteFirmwareHash() {
  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  String url = String(FIRMWARE_HASH_URL) + "?pygit=" + String(millis());

  if (!http.begin(client, url)) return "";

  http.setTimeout(15000);
  int httpCode = http.GET();

  if (httpCode != HTTP_CODE_OK) {
    Serial.print("OTA: hash HTTP code: ");
    Serial.println(httpCode);
    http.end();
    return "";
  }

  String hash = http.getString();
  http.end();
  hash = normalizeHash(hash);

  if (hash.length() != 64) return "";
  return hash;
}

bool downloadAndInstallFirmware(const String &remoteHash) {
  Serial.println("OTA: NEW FIRMWARE DETECTED.");
  Serial.println("OTA: downloading firmware...");

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  String url = String(FIRMWARE_BIN_URL) + "?pygit=" + String(millis());

  if (!http.begin(client, url)) {
    Serial.println("OTA: firmware connection setup FAILED.");
    return false;
  }

  http.setTimeout(30000);
  int httpCode = http.GET();

  if (httpCode != HTTP_CODE_OK) {
    Serial.print("OTA: firmware HTTP code: ");
    Serial.println(httpCode);
    http.end();
    return false;
  }

  int contentLength = http.getSize();

  if (contentLength <= 0) {
    Serial.println("OTA: invalid firmware size.");
    http.end();
    return false;
  }

  Serial.print("OTA: firmware size = ");
  Serial.print(contentLength);
  Serial.println(" bytes");

  if (!Update.begin((size_t)contentLength, U_FLASH)) {
    Serial.print("OTA: Update.begin FAILED: ");
    Serial.println(Update.errorString());
    http.end();
    return false;
  }

  BearSSL::HashSHA256 hash;
  hash.begin();

  Stream* stream = http.getStreamPtr();
  uint8_t buffer[1024];
  size_t totalWritten = 0;
  unsigned long lastDataAt = millis();

  while (totalWritten < (size_t)contentLength &&
         millis() - lastDataAt < 30000) {

    size_t availableBytes = stream->available();

    if (availableBytes == 0) {
      delay(1);
      continue;
    }

    size_t toRead = min(availableBytes, sizeof(buffer));
    size_t remaining = (size_t)contentLength - totalWritten;
    if (toRead > remaining) toRead = remaining;

    size_t readBytes = stream->readBytes(buffer, toRead);

    if (readBytes == 0) continue;

    lastDataAt = millis();
    hash.add(buffer, readBytes);

    size_t written = Update.write(buffer, readBytes);

    if (written != readBytes) {
      Serial.println("OTA: firmware write FAILED.");
      Update.abort();
      http.end();
      return false;
    }

    totalWritten += written;
    Serial.print("OTA: ");
    Serial.print((totalWritten * 100UL) / contentLength);
    Serial.println("%");
  }

  http.end();

  if (totalWritten != (size_t)contentLength) {
    Serial.println("OTA: incomplete firmware download.");
    Update.abort();
    return false;
  }

  hash.end();
  String downloadedHash = hashToHex(hash);

  Serial.print("OTA: downloaded SHA-256 = ");
  Serial.println(downloadedHash);
  Serial.print("OTA: expected SHA-256   = ");
  Serial.println(remoteHash);

  if (downloadedHash != remoteHash) {
    Serial.println("OTA: SHA-256 MISMATCH. Update rejected.");
    Update.abort();
    return false;
  }

  if (!Update.end(true)) {
    Serial.print("OTA: Update.end FAILED: ");
    Serial.println(Update.errorString());
    Update.abort();
    return false;
  }

  Serial.println("OTA: firmware written successfully.");

  if (!saveLocalFirmwareHash(remoteHash)) {
    Serial.println("OTA: hash save FAILED.");
    Serial.println("OTA: current firmware will remain active; update will retry.");
    return false;
  }

  Serial.println("OTA: new hash saved.");
  Serial.println("OTA: restarting...");
  delay(1000);
  ESP.restart();

  return true;
}

void checkForFirmwareUpdate() {
  if (!wifiConnected) {
    Serial.println("OTA: WiFi unavailable. Skipping update check.");
    return;
  }

  Serial.println();
  Serial.println("Checking GitHub firmware...");

  String remoteHash = getRemoteFirmwareHash();

  if (remoteHash.length() != 64) {
    Serial.println("OTA: firmware hash unavailable. Running current firmware.");
    return;
  }

  String localHash = loadLocalFirmwareHash();

  Serial.print("OTA: local hash  = ");
  if (localHash.length()) Serial.println(localHash);
  else Serial.println("(none)");

  Serial.print("OTA: remote hash = ");
  Serial.println(remoteHash);

  if (localHash == remoteHash) {
    Serial.println("OTA: firmware is already up to date.");
    return;
  }

  downloadAndInstallFirmware(remoteHash);
}

void setup() {
  Serial.begin(115200);

  lcd.init();
  lcd.backlight();

  pinMode(COIN_PIN, INPUT_PULLUP);
  pinMode(TRIGGER_PIN, INPUT_PULLUP);

  if (!LittleFS.begin()) {
    Serial.println("LittleFS mount FAILED.");
  }

  loadConfig();

  if (!loadWiFiConfig()) {
    lcd.clear();
    lcd.print("WiFi config");
    lcd.setCursor(0, 1);
    lcd.print("missing!");
  } else {
    WiFi.mode(WIFI_STA);
    WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());

    lcd.clear();
    lcd.print("Connecting...");

    int retry = 0;
    while (WiFi.status() != WL_CONNECTED && retry < 30) {
      delay(500);
      retry++;
    }

    wifiConnected = (WiFi.status() == WL_CONNECTED);

    if (wifiConnected) {
      Serial.println("WiFi connected: " + WiFi.localIP().toString());
      Serial.println("MAC: " + WiFi.macAddress());
    } else {
      Serial.println("WiFi failed");
    }
  }

  checkForFirmwareUpdate();

  server.on("/select", HTTP_GET, handleSelect);
  server.on("/cancel", HTTP_GET, handleCancel);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/", handleDashboard);
  server.on("/dashboard", handleDashboard);
  server.on("/setting", handleSettings);
  server.on("/editor", handleEditor);
  server.begin();

  showStatus();
}

void loop() {
  server.handleClient();
  wifiConnected = (WiFi.status() == WL_CONNECTED);

  if (selectedPC.length() > 0 &&
      selectionStartedAt > 0 &&
      millis() - selectionStartedAt > selectionTimeoutMs) {
    clearSelection("selection timeout");
  }

  // Coinslot pulse is approximately 50 ms.
  // Detect the HIGH -> LOW edge on D6/GPIO12.
  int coinState = digitalRead(COIN_PIN);
  static int lastCoin = HIGH;
  static unsigned long lastPulseTime = 0;
  static unsigned long lastCoinTime = 0;

  if (coinState == LOW &&
      lastCoin == HIGH &&
      micros() - lastCoinTime > debounce_us) {
    pulseCount++;
    lastPulseTime = millis();
    lastCoinTime = micros();
    Serial.println("COIN PULSE");
  }

  lastCoin = coinState;

  if (pulseCount > 0 && millis() - lastPulseTime > pulse_gap_ms) {
    bool triggerActive = digitalRead(TRIGGER_PIN) == LOW;

    if (selectedPC.length() == 0) {
      Serial.println("COIN IGNORED: no client selected.");
    } else if (!triggerActive) {
      Serial.println("COIN IGNORED: GPIO14 trigger is not active.");
    } else {
      int minutes = pulseCount * minutesPerPulse;
      PCInfo* pc = findPC(selectedPC);

      if (pc && wifiConnected) {
        WiFiClient client;
        client.setTimeout(1000);

        if (client.connect(pc->ip.c_str(), 5000)) {
          String msg = pc->name + ":+" + String(minutes) + "\n";
          client.print(msg);
          client.stop();

          Serial.println("TCP SENT: " + msg);
          logCoin(selectedPC, minutes);

          lcd.clear();
          lcd.setCursor(0, 0);
          lcd.print(selectedPC.substring(0, 8));
          lcd.setCursor(0, 1);
          lcd.print("+");
          lcd.print(minutes);
          lcd.print(" minutes");
        } else {
          Serial.println("TCP FAILED");
        }
      } else {
        Serial.println("TARGET PC NOT AVAILABLE");
      }
    }

    pulseCount = 0;
  }

  static int lastTriggerState = HIGH;
  int triggerState = digitalRead(TRIGGER_PIN);

  if (lastTriggerState == LOW &&
      triggerState == HIGH &&
      selectedPC.length() > 0) {
    Serial.println("GPIO14 RELEASED.");
    clearSelection("trigger released");
  }

  lastTriggerState = triggerState;
}
