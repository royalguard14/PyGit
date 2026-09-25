#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <LiquidCrystal_I2C.h>
#include <vector>

// ===== CONFIG =====
#define COIN_PIN D5
#define BTN_UP   D3
#define BTN_DOWN D4

struct PCInfo { String name; String ip; };
std::vector<PCInfo> pcs;

ESP8266WebServer server(80);
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ===== STATE =====
bool wifiConnected = false;
String storedPassword = "password";
String selectedPC = "";

int minutesPerPulse = 8;
int pulseCount = 0;
int lastCoin = HIGH;

unsigned long pulse_gap_ms = 300;
unsigned int debounce_us = 500;

// WiFi
const char* ssid = "Bautista";
const char* pass = "@Sufyanbautista30";

// ===== UTILITIES =====
void showSelectedPC() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("selectedPC : ");
  lcd.print(selectedPC.substring(0, 3)); // fits LCD
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

  pcs.clear();
  for (JsonVariant v : doc["pcs"].as<JsonArray>()) {
    PCInfo p;
    p.name = v["name"].as<String>();
    p.ip   = v["ip"].as<String>();
    pcs.push_back(p);
  }

  if (!pcs.empty()) selectedPC = pcs[0].name;
  if (selectedPC == "") selectedPC = "PC1";
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

// ===== WEB HANDLERS =====
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

// ===== SETUP =====
void setup() {
  Serial.begin(115200);

  lcd.init();
  lcd.backlight();

  pinMode(COIN_PIN, INPUT_PULLUP);
  pinMode(BTN_UP, INPUT_PULLUP);
  pinMode(BTN_DOWN, INPUT_PULLUP);
  lastCoin = digitalRead(COIN_PIN);

  LittleFS.begin();
  loadConfig();

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, pass);

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

  server.on("/", handleDashboard);
  server.on("/dashboard", handleDashboard);
  server.on("/setting", handleSettings);
  server.on("/editor", handleEditor);
  server.begin();

  showSelectedPC();
}

// ===== LOOP =====
void loop() {
  server.handleClient();

  // update WiFi status (DO NOT RETURN)
  wifiConnected = (WiFi.status() == WL_CONNECTED);

  // ===== BUTTON SELECT =====
  if (digitalRead(BTN_UP) == LOW && pcs.size() > 0) {
    delay(200);
    int idx = 0;
    for (int i = 0; i < pcs.size(); i++)
      if (pcs[i].name == selectedPC) idx = i;
    idx = (idx + 1) % pcs.size();
    selectedPC = pcs[idx].name;
    Serial.println("Selected PC: " + selectedPC);
    showSelectedPC();
  }

  if (digitalRead(BTN_DOWN) == LOW && pcs.size() > 0) {
    delay(200);
    int idx = 0;
    for (int i = 0; i < pcs.size(); i++)
      if (pcs[i].name == selectedPC) idx = i;
    idx = (idx - 1 + pcs.size()) % pcs.size();
    selectedPC = pcs[idx].name;
    Serial.println("Selected PC: " + selectedPC);
    showSelectedPC();
  }

  // ===== COIN LOGIC (ORIGINAL – WORKING) =====
  int coinState = digitalRead(COIN_PIN);
  static unsigned long lastPulseTime = 0;
  static unsigned long lastCoinTime = 0;

  if (coinState == LOW && lastCoin == HIGH &&
      (micros() - lastCoinTime) > debounce_us) {
    pulseCount++;
    lastPulseTime = millis();
    lastCoinTime = micros();
    Serial.println("COIN PULSE");
  }
  lastCoin = coinState;

  if (pulseCount > 0 && (millis() - lastPulseTime) > pulse_gap_ms) {
    int minutes = pulseCount * minutesPerPulse;

    PCInfo* pc = findPC(selectedPC);
    if (pc && wifiConnected) {
      WiFiClient client;
      client.setTimeout(1000);
      Serial.println("Trying TCP to " + pc->ip);
      if (client.connect(pc->ip.c_str(), 5000)) {
        String msg = pc->name + ":+" + String(minutes) + "\n";
        client.print(msg);
        client.stop();
        Serial.println("TCP SENT: " + msg);
      } else {
        Serial.println("TCP FAILED");
      }
    }

    logCoin(selectedPC, minutes);

    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(selectedPC.substring(0, 8));
    lcd.print(" = ");
    lcd.print(minutes);

    pulseCount = 0;
  }
}
