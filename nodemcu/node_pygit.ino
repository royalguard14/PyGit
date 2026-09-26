#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <LittleFS.h>
#include <ESP8266WebServer.h>

const char* WIFI_CONFIG = "/wifi_config.json";
const char* DEVICE_CONFIG_FILE = "/device_config.json";
const char* CONFIG_URL = "https://api.github.com/repos/royalguard14/PyGit/contents/nodemcu/data/config.json?ref=main";

const uint8_t FLASH_BUTTON = 0;
const uint8_t COIN_PIN = 12;              // D6 / GPIO12 - coinslot
const uint8_t TRIGGER_PIN = 14;            // D5 / GPIO14 - client trigger
const unsigned long WIFI_SETUP_WINDOW = 5000;
const unsigned long CHECK_INTERVAL = 60000;
const unsigned long COIN_DEBOUNCE_MS = 100;

const uint16_t COIN_SERVER_PORT = 5001;
const unsigned long DEFAULT_TIME_PER_PULSE = 500;

unsigned long lastCheck = 0;
volatile unsigned long lastCoinInterrupt = 0;
volatile bool coinPulseDetected = false;
unsigned long timeInputPerPulse = DEFAULT_TIME_PER_PULSE;

String wifiSSID, wifiPassword;
ESP8266WebServer server(80);
WiFiServer coinServer(COIN_SERVER_PORT);
WiFiClient coinClient;

String jsonValue(const String& json, const String& key) {
  String token = "\"" + key + "\"";
  int p = json.indexOf(token);
  if (p < 0) return "";
  p = json.indexOf(':', p + token.length());
  if (p < 0) return "";
  int a = json.indexOf('\"', p + 1);
  if (a < 0) return "";
  int b = json.indexOf('\"', a + 1);
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
      else if (c == '\"') quoted = false;
      continue;
    }
    if (c == '\"') quoted = true;
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

void applyDeviceConfig(const String& object) {
  String value = jsonValue(object, "time_input_per_pulse");
  if (value.length()) {
    unsigned long parsed = value.toInt();
    if (parsed > 0) timeInputPerPulse = parsed;
  }
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

void loadLocalDeviceConfig() {
  if (!LittleFS.exists(DEVICE_CONFIG_FILE)) return;

  File f = LittleFS.open(DEVICE_CONFIG_FILE, "r");
  if (!f) return;

  String object = f.readString();
  f.close();
  applyDeviceConfig(object);
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
  f.print("{\n  \"ssid\": \"");
  f.print(ssid);
  f.print("\",\n  \"password\": \"");
  f.print(password);
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
    if (f) {
      localVersion = jsonValue(f.readString(), "version");
      f.close();
    }
  }

  Serial.print("Local config:  ");
  Serial.println(localVersion.length() ? localVersion : "(none)");

  Serial.print("GitHub config: ");
  Serial.println(remoteVersion);

  if (localVersion != remoteVersion) {
    Serial.println("New device configuration detected.");
    saveDeviceConfig(remoteObject);
    applyDeviceConfig(remoteObject);
    showDeviceConfig(remoteObject);
  } else {
    applyDeviceConfig(remoteObject);
    Serial.println("Device configuration is up to date.");
  }

  Serial.print("Active time per pulse: ");
  Serial.print(timeInputPerPulse);
  Serial.println(" seconds");

  Serial.println("==============================");
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

  Serial.print("HTTP Code: ");
  Serial.println(code);

  if (code != HTTP_CODE_OK) {
    Serial.println("GitHub config download FAILED.");
    http.end();
    return;
  }

  String remote = http.getString();
  http.end();

  Serial.println("config.json downloaded.");
  checkDeviceConfig(remote);
}

void ICACHE_RAM_ATTR coinInterrupt() {
  unsigned long now = millis();

  if (now - lastCoinInterrupt >= COIN_DEBOUNCE_MS) {
    lastCoinInterrupt = now;
    coinPulseDetected = true;
  }
}

void startCoinServer() {
  coinServer.begin();
  coinServer.setNoDelay(true);

  Serial.print("Coin server: TCP port ");
  Serial.println(COIN_SERVER_PORT);
}

void handleCoinClient() {
  if (!coinClient || !coinClient.connected()) {
    if (coinClient) coinClient.stop();

    WiFiClient newClient = coinServer.available();

    if (newClient) {
      coinClient = newClient;
      Serial.println("Coin receiver client connected.");
      coinClient.println("PYGIT READY");
    }
  }

  if (coinClient && coinClient.connected() && coinClient.available()) {
    while (coinClient.available()) coinClient.read();
  }
}

void handleCoinPulse() {
  bool pulse = false;

  noInterrupts();
  if (coinPulseDetected) {
    coinPulseDetected = false;
    pulse = true;
  }
  interrupts();

  if (!pulse) return;

  Serial.println();
  Serial.println("------------------------------");
  Serial.println("COIN PULSE DETECTED");
  Serial.println("Pulse width assumption: 50 ms");
  Serial.print("Time input per pulse: ");
  Serial.print(timeInputPerPulse);
  Serial.println(" seconds");

  // GPIO14 is the client trigger. LOW means the client is active/selected.
  if (digitalRead(TRIGGER_PIN) != LOW) {
    Serial.println("Trigger inactive (GPIO14 HIGH). Coin ignored.");
    Serial.println("------------------------------");
    return;
  }

  Serial.println("Trigger active (GPIO14 LOW).");

  if (coinClient && coinClient.connected()) {
    coinClient.print("COIN:");
    coinClient.println(timeInputPerPulse);
    Serial.println("Coin value sent to active receiver.");
  } else {
    Serial.println("No receiver connected. Coin ignored.");
  }

  Serial.println("------------------------------");
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
  loadLocalDeviceConfig();

  pinMode(COIN_PIN, INPUT_PULLUP);
  pinMode(TRIGGER_PIN, INPUT_PULLUP);

  attachInterrupt(digitalPinToInterrupt(COIN_PIN), coinInterrupt, FALLING);

  if (flashPressedAtStartup()) startWiFiSetup();

  if (!loadWiFiConfig()) startWiFiSetup();

  Serial.println("Wi-Fi configuration loaded from LittleFS.");

  if (!connectWiFi()) startWiFiSetup();

  Serial.println("\nPyGit base code online.");

  checkGitHubConfig();
  startCoinServer();

  Serial.println("Coinslot input: D6 / GPIO12");
  Serial.println("Expected coin pulse: LOW for about 50 ms");
  Serial.println("Trigger input: D5 / GPIO14");
  Serial.println("Trigger active: LOW");
  Serial.println("Waiting for Side A receiver...");

  lastCheck = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    return;
  }

  handleCoinClient();
  handleCoinPulse();

  if (millis() - lastCheck >= CHECK_INTERVAL) {
    lastCheck = millis();
    checkGitHubConfig();
  }

  delay(2);
}
