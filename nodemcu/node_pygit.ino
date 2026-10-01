#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <LittleFS.h>
#include <ESP8266WebServer.h>
#include <DNSServer.h>

const char* WIFI_CONFIG = "/wifi_config.json";
const char* DEVICE_CONFIG_FILE = "/device_config.json";
const char* CONFIG_URL = "https://api.github.com/repos/royalguard14/PyGit/contents/nodemcu/data/config.json?ref=main";

const uint8_t FLASH_BUTTON = 0;
const uint8_t COIN_PIN = 12;
const uint8_t TRIGGER_PIN = 14;
const unsigned long WIFI_SETUP_WINDOW = 5000;
const unsigned long CHECK_INTERVAL = 60000;
const unsigned long COIN_DEBOUNCE_MS = 100;

const uint16_t CONTROL_PORT = 5001;
const uint16_t DEFAULT_PC_PORT = 5000;
const unsigned long DEFAULT_TIME_PER_PULSE = 10;

const unsigned long CONTROL_GRACE_MS = 10000;
const unsigned long CONTROL_HEARTBEAT_MS = 3000;

unsigned long lastCheck = 0;
volatile unsigned long lastCoinInterrupt = 0;
volatile bool coinPulseDetected = false;
unsigned long timeInputPerPulse = DEFAULT_TIME_PER_PULSE;
unsigned long lastControlHeartbeat = 0;
unsigned long controlLostSince = 0;

String wifiSSID, wifiPassword;
ESP8266WebServer server(80);
DNSServer dnsServer;
const byte DNS_PORT = 53;
IPAddress apIP(192, 168, 4, 1);
IPAddress apGateway(192, 168, 4, 1);
IPAddress apSubnet(255, 255, 255, 0);
WiFiServer controlServer(CONTROL_PORT);

WiFiClient controlClient;
WiFiClient receiverClient;

bool activeClient = false;
String activePcName = "";
IPAddress activePcIP;
uint16_t activePcPort = DEFAULT_PC_PORT;

void serialLog(const String& message) {
  Serial.print("[PYGIT] ");
  Serial.println(message);
}


String jsonValue(const String& json, const String& key) {
  String token = "\"" + key + "\"";
  int p = json.indexOf(token);
  if (p < 0) return "";

  p = json.indexOf(':', p + token.length());
  if (p < 0) return "";

  int a = p + 1;
  while (a < (int)json.length() && isspace((unsigned char)json[a])) a++;
  if (a >= (int)json.length() || json[a] != '"') return "";

  a++;
  String value = "";
  bool escaped = false;

  for (int i = a; i < (int)json.length(); i++) {
    char c = json[i];
    if (escaped) {
      if (c == '"' || c == 92 || c == '/') value += c;
      else if (c == 'n') value += '\n';
      else if (c == 'r') value += '\r';
      else if (c == 't') value += '\t';
      else value += c;
      escaped = false;
      continue;
    }
    if (c == '\\') {
      escaped = true;
      continue;
    }
    if (c == '"') return value;
    value += c;
  }
  return value;
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
  if (!f) return;
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

void loadLocalDeviceConfig() {
  if (!LittleFS.exists(DEVICE_CONFIG_FILE)) return;
  File f = LittleFS.open(DEVICE_CONFIG_FILE, "r");
  if (!f) return;
  String object = f.readString();
  f.close();
  applyDeviceConfig(object);
}

bool loadWiFiConfig() {
  String configPath = WIFI_CONFIG;

  if (!LittleFS.exists(configPath)) {
    if (LittleFS.exists("/data/wifi_config.json")) configPath = "/data/wifi_config.json";
    else return false;
  }

  File f = LittleFS.open(configPath, "r");
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

void handleCaptivePortal() {
  server.sendHeader("Location", String("http://") + apIP.toString(), true);
  server.send(302, "text/plain", "Redirecting to PyGit WiFi Setup...");
}

void startWiFiSetup() {
  WiFi.disconnect();
  delay(100);
  WiFi.mode(WIFI_AP);

  String ap = "PyGit-" + WiFi.macAddress();
  ap.replace(":", "");

  WiFi.softAPConfig(apIP, apGateway, apSubnet);
  WiFi.softAP(ap.c_str());
  dnsServer.start(DNS_PORT, "*", apIP);

  server.on("/", HTTP_GET, []() {
    server.send(200, "text/html",
      "<!doctype html><html><head>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<title>PyGit WiFi Setup</title></head><body>"
      "<h2>PyGit WiFi Setup</h2>"
      "<form method='POST' action='/save'>"
      "SSID:<br><input name='ssid' required autocomplete='off'><br><br>"
      "Password:<br><input name='password' type='password' autocomplete='off'><br><br>"
      "<button type='submit'>Save & Connect</button>"
      "</form></body></html>");
  });

  server.on("/generate_204", HTTP_GET, []() {
    server.sendHeader("Location", "http://" + apIP.toString() + "/", true);
    server.send(302, "text/plain", "PyGit WiFi Setup");
  });
  server.on("/hotspot-detect.html", HTTP_GET, []() {
    server.send(200, "text/html", "<meta http-equiv='refresh' content='0;url=http://" + apIP.toString() + "/'>");
  });
  server.on("/connecttest.txt", HTTP_GET, []() {
    server.sendHeader("Location", "http://" + apIP.toString() + "/", true);
    server.send(302, "text/plain", "PyGit WiFi Setup");
  });
  server.on("/ncsi.txt", HTTP_GET, []() {
    server.sendHeader("Location", "http://" + apIP.toString() + "/", true);
    server.send(302, "text/plain", "PyGit WiFi Setup");
  });

  server.on("/save", HTTP_POST, []() {
    String ssid = server.arg("ssid");
    String password = server.arg("password");
    ssid.trim();

    if (!ssid.length()) {
      server.send(400, "text/plain", "SSID is required.");
      return;
    }
    if (!saveWiFiConfig(ssid, password)) {
      server.send(500, "text/plain", "Could not save WiFi configuration.");
      return;
    }

    server.send(200, "text/html", "<h2>Saved.</h2><p>Wi-Fi credentials saved. Restarting NodeMCU...</p>");
    delay(1000);
    ESP.restart();
  });

  server.onNotFound(handleCaptivePortal);
  server.begin();

  while (true) {
    dnsServer.processNextRequest();
    server.handleClient();
    delay(2);
  }
}

bool flashPressedAtStartup() {
  pinMode(FLASH_BUTTON, INPUT_PULLUP);
  unsigned long started = millis();
  while (millis() - started < WIFI_SETUP_WINDOW) {
    if (digitalRead(FLASH_BUTTON) == LOW) return true;
    delay(10);
  }
  return false;
}

bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());

  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(500);
  return WiFi.status() == WL_CONNECTED;
}

void checkDeviceConfig(const String& remote) {
  String remoteObject = deviceObject(remote, WiFi.macAddress());
  if (!remoteObject.length()) return;

  String remoteVersion = jsonValue(remoteObject, "version");
  String localVersion;

  if (LittleFS.exists(DEVICE_CONFIG_FILE)) {
    File f = LittleFS.open(DEVICE_CONFIG_FILE, "r");
    if (f) {
      localVersion = jsonValue(f.readString(), "version");
      f.close();
    }
  }

  if (localVersion != remoteVersion) {
    serialLog("Device config update: " + localVersion + " -> " + remoteVersion);
    saveDeviceConfig(remoteObject);
    applyDeviceConfig(remoteObject);
  } else {
    applyDeviceConfig(remoteObject);
  }
}

void checkGitHubConfig() {
  if (WiFi.status() != WL_CONNECTED) return;

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  String url = String(CONFIG_URL) + "&pygit=" + String(millis());

  if (!http.begin(client, url)) return;

  http.setTimeout(15000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.setRedirectLimit(5);
  http.addHeader("Accept", "application/vnd.github.raw+json");
  http.addHeader("Cache-Control", "no-cache, no-store, max-age=0");
  http.addHeader("Pragma", "no-cache");
  http.addHeader("User-Agent", "PyGit-NodeMCU");

  int code = http.GET();
  if (code == HTTP_CODE_OK) {
    String remote = http.getString();
    http.end();
    checkDeviceConfig(remote);
    return;
  }
  http.end();
}

void ICACHE_RAM_ATTR coinInterrupt() {
  unsigned long now = millis();
  if (now - lastCoinInterrupt >= COIN_DEBOUNCE_MS) {
    lastCoinInterrupt = now;
    coinPulseDetected = true;
  }
}

void startCoinServer() {
  controlServer.begin();
  controlServer.setNoDelay(true);
}

void clearActiveClient(const char* reason) {
  serialLog("ACTIVE RELEASED: " + String(reason));
  if (receiverClient) receiverClient.stop();
  if (controlClient) controlClient.stop();

  activeClient = false;
  lastControlHeartbeat = 0;
  controlLostSince = 0;
  digitalWrite(TRIGGER_PIN, LOW);
  activePcName = "";
  activePcIP = IPAddress(0, 0, 0, 0);
  activePcPort = DEFAULT_PC_PORT;
}

bool connectToPCReceiver() {
  if (!activeClient) return false;
  if (receiverClient && receiverClient.connected()) return true;
  if (receiverClient) receiverClient.stop();

  if (!receiverClient.connect(activePcIP, activePcPort)) return false;
  receiverClient.setNoDelay(true);
  return true;
}

void processStatus(WiFiClient& client) {
  serialLog("STATUS request -> " + String(activeClient ? "ACTIVE: " + activePcName : "NONE"));
  client.print("NODEMCU|");
  client.print(WiFi.localIP());
  client.print("|");
  if (activeClient) client.println(activePcName);
  else client.println("NONE");
}

void processRequest(const String& line, WiFiClient& client) {
  String requestLine = line;
  requestLine.trim();

  if (requestLine == "STATUS") {
    processStatus(client);
    return;
  }

  int p1 = requestLine.indexOf('|');
  int p2 = line.indexOf('|', p1 + 1);
  int p3 = line.indexOf('|', p2 + 1);
  if (p1 < 0 || p2 < 0 || p3 < 0) {
    client.println("ERROR|INVALID REQUEST");
    return;
  }

  String command = requestLine.substring(0, p1);
  String pcName = requestLine.substring(p1 + 1, p2);
  String pcIPText = requestLine.substring(p2 + 1, p3);
  String pcPortText = requestLine.substring(p3 + 1);

  command.trim();
  pcName.trim();
  pcIPText.trim();
  pcPortText.trim();

  if (command != "REQUEST") {
    serialLog("Unknown command: " + command);
    client.println("ERROR|UNKNOWN COMMAND");
    return;
  }

  IPAddress pcIP;
  if (!pcIP.fromString(pcIPText)) {
    client.println("ERROR|INVALID IP");
    return;
  }

  uint16_t pcPort = pcPortText.toInt();
  if (pcPort == 0) pcPort = DEFAULT_PC_PORT;

  serialLog("REQUEST from " + pcName + " (" + pcIPText + ":" + String(pcPort) + ")");

  if (activeClient) {
    if (activePcName == pcName && activePcIP == pcIP && activePcPort == pcPort) {
      serialLog("REQUEST accepted again for active PC: " + activePcName);
      client.println("ACCEPTED|" + activePcName);
      return;
    }

    serialLog("REQUEST rejected. Active PC: " + activePcName);
    client.print("REJECTED|ACTIVE|");
    client.print(activePcName);
    client.print("|");
    client.print(activePcIP);
    client.print("|");
    client.println(activePcPort);
    return;
  }

  activeClient = true;
  lastControlHeartbeat = millis();
  serialLog("CLAIMING NodeMCU for " + pcName + " -> GPIO14 HIGH");
  controlLostSince = 0;
  digitalWrite(TRIGGER_PIN, HIGH);
  activePcName = pcName;
  activePcIP = pcIP;
  activePcPort = pcPort;

  if (!connectToPCReceiver()) {
    serialLog("PC receiver unreachable: " + pcIPText + ":" + String(pcPort));
    client.println("REJECTED|PC_UNREACHABLE");
    clearActiveClient("PC receiver unreachable");
    return;
  }

  controlClient = client;
  controlClient.setNoDelay(true);
  serialLog("ACCEPTED: " + activePcName + " (" + activePcIP.toString() + ":" + String(activePcPort) + ")");
  client.print("ACCEPTED|");
  client.println(activePcName);
}

void handleControlServer() {
  if (activeClient) {
    if (!controlClient || !controlClient.connected()) {
      if (controlLostSince == 0) controlLostSince = millis();
      else if (millis() - controlLostSince >= CONTROL_GRACE_MS) {
        clearActiveClient("Control connection lost");
        return;
      }
    } else {
      controlLostSince = 0;
      while (controlClient.available()) {
        String line = controlClient.readStringUntil('\n');
        line.trim();
        if (line == "PING") {
          serialLog("PING from " + activePcName + " -> PONG");
          controlClient.println("PONG");
          lastControlHeartbeat = millis();
          continue;
        }
        if (line.startsWith("RELEASE|")) {
          String pcName = line.substring(8);
          pcName.trim();
          if (pcName == activePcName) {
            serialLog("RELEASE request from " + pcName);
            controlClient.println("RELEASED|" + activePcName);
            clearActiveClient("Client requested release");
            return;
          }
        }
      }
      if (millis() - lastControlHeartbeat >= CONTROL_HEARTBEAT_MS * 2) {
        controlClient.println("PONG");
        lastControlHeartbeat = millis();
      }
    }

    WiFiClient newClient = controlServer.available();
    if (newClient) {
      newClient.setTimeout(2);
      newClient.setNoDelay(true);
      String line = newClient.readStringUntil('\n');
      line.trim();
      if (line.length()) processRequest(line, newClient);
      newClient.stop();
    }
    return;
  }

  WiFiClient newClient = controlServer.available();
  if (!newClient) return;

  newClient.setTimeout(2);
  newClient.setNoDelay(true);
  String line = newClient.readStringUntil('\n');
  line.trim();
  if (!line.length()) {
    newClient.stop();
    return;
  }

  processRequest(line, newClient);
  if (!activeClient) {
    delay(10);
    newClient.stop();
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
  if (!activeClient) {
    serialLog("COIN pulse ignored: no active PC");
    return;
  }

  serialLog("COIN pulse -> " + activePcName + ":+" + String(timeInputPerPulse) + " min");
  digitalWrite(TRIGGER_PIN, HIGH);

  if (!receiverClient || !receiverClient.connected()) {
    if (!connectToPCReceiver()) {
      serialLog("Unable to reconnect to receiver.");
      clearActiveClient("PC receiver connection lost");
      return;
    }
  }

  receiverClient.print(activePcName);
  receiverClient.print(":+");
  receiverClient.println(timeInputPerPulse);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  serialLog("NodeMCU starting...");
  serialLog("MAC: " + WiFi.macAddress());

  if (!LittleFS.begin()) return;
  loadLocalDeviceConfig();
  serialLog("Local device config loaded. Time per pulse: " + String(timeInputPerPulse) + " min");

  pinMode(COIN_PIN, INPUT_PULLUP);
  pinMode(TRIGGER_PIN, OUTPUT);
  digitalWrite(TRIGGER_PIN, LOW);
  attachInterrupt(digitalPinToInterrupt(COIN_PIN), coinInterrupt, FALLING);

  if (flashPressedAtStartup()) startWiFiSetup();

  if (!loadWiFiConfig()) {
    serialLog("Wi-Fi config not found. Starting setup AP...");
    startWiFiSetup();
  }
  serialLog("Connecting to Wi-Fi: " + wifiSSID);
  if (!connectWiFi()) {
    serialLog("Wi-Fi connection failed. Starting setup AP...");
    startWiFiSetup();
  }
  serialLog("Wi-Fi connected. IP: " + WiFi.localIP().toString());

  checkGitHubConfig();
  serialLog("Device config checked. Time per pulse: " + String(timeInputPerPulse) + " min");
  startCoinServer();
  serialLog("Control server listening on port " + String(CONTROL_PORT));
  serialLog("GPIO14 initialized LOW.");
  lastCheck = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    return;
  }

  handleControlServer();
  handleCoinPulse();

  if (millis() - lastCheck >= CHECK_INTERVAL) {
    lastCheck = millis();
    checkGitHubConfig();
  }

  delay(2);
}
