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
