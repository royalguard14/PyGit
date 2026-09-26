#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Updater.h>

const char* PYGIT_FIRMWARE_URL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/main/nodemcu/firmware.bin";

const char* PYGIT_MD5_URL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/main/nodemcu/firmware.md5";

const char* PYGIT_LOCAL_HASH_FILE = "/pygit_firmware.md5";

String normalizeHash(String value) {
  value.trim();

  int spacePos = value.indexOf(' ');
  if (spacePos > 0) {
    value = value.substring(0, spacePos);
  }

  int tabPos = value.indexOf('\t');
  if (tabPos > 0) {
    value = value.substring(0, tabPos);
  }

  value.trim();
  value.toLowerCase();

  return value;
}

String readLocalFirmwareHash() {
  if (!LittleFS.exists(PYGIT_LOCAL_HASH_FILE)) {
    return "";
  }

  File f = LittleFS.open(PYGIT_LOCAL_HASH_FILE, "r");

  if (!f) {
    return "";
  }

  String hash = normalizeHash(f.readString());
  f.close();

  return hash;
}

bool saveLocalFirmwareHash(const String& hash) {
  File f = LittleFS.open(PYGIT_LOCAL_HASH_FILE, "w");

  if (!f) {
    Serial.println("WARNING: Cannot save local firmware hash.");
    return false;
  }

  f.println(hash);
  f.close();

  return true;
}

String fetchRemoteFirmwareHash() {
  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;

  String url = String(PYGIT_MD5_URL) + "?pygit=" + String(millis());

  Serial.print("Update identity URL: ");
  Serial.println(url);

  if (!http.begin(client, url)) {
    Serial.println("Update identity HTTP setup FAILED.");
    return "";
  }

  http.setTimeout(15000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.setRedirectLimit(5);
  http.setUserAgent("PyGit-NodeMCU");
  http.addHeader("Cache-Control", "no-cache, no-store, max-age=0");
  http.addHeader("Pragma", "no-cache");

  int code = http.GET();

  Serial.print("Update identity HTTP Code: ");
  Serial.println(code);

  if (code != HTTP_CODE_OK) {
    Serial.println("Could not read firmware identity.");
    http.end();
    return "";
  }

  String hash = normalizeHash(http.getString());
  http.end();

  if (hash.length() != 32) {
    Serial.println("Invalid firmware identity received.");
    return "";
  }

  return hash;
}

bool downloadAndInstallFirmware(const String& expectedHash) {
  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;

  String url = String(PYGIT_FIRMWARE_URL) + "?pygit=" + String(millis());

  Serial.println("Downloading updated PyGit code...");
  Serial.print("Firmware URL: ");
  Serial.println(url);

  if (!http.begin(client, url)) {
    Serial.println("Firmware HTTP setup FAILED.");
    return false;
  }

  http.setTimeout(30000);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.setRedirectLimit(5);
  http.useHTTP10(true);
  http.setUserAgent("PyGit-NodeMCU");
  http.addHeader("Cache-Control", "no-cache, no-store, max-age=0");
  http.addHeader("Pragma", "no-cache");

  int code = http.GET();

  Serial.print("Firmware HTTP Code: ");
  Serial.println(code);

  if (code != HTTP_CODE_OK) {
    Serial.println("Firmware download FAILED.");
    http.end();
    return false;
  }

  int contentLength = http.getSize();

  Serial.print("Firmware size: ");
  Serial.print(contentLength);
  Serial.println(" bytes");

  if (contentLength <= 0) {
    Serial.println("Firmware size is invalid.");
    http.end();
    return false;
  }

  WiFiClient* stream = http.getStreamPtr();

  if (!stream) {
    Serial.println("Firmware stream unavailable.");
    http.end();
    return false;
  }

  if (!Update.begin((size_t)contentLength, U_FLASH)) {
    Serial.print("Update.begin() FAILED: ");
    Serial.println(Update.getErrorString());
    http.end();
    return false;
  }

  // ESP8266's built-in updater supports MD5 verification.
  if (!Update.setMD5(expectedHash.c_str())) {
    Serial.println("Could not configure firmware MD5 verification.");
    Update.end();
    http.end();
    return false;
  }

  Serial.println("Writing updated code to OTA flash area...");

  size_t written = Update.writeStream(*stream);

  Serial.print("Written: ");
  Serial.print(written);
  Serial.print("/");
  Serial.println(contentLength);

  if (written != (size_t)contentLength) {
    Serial.print("Firmware write FAILED: ");
    Serial.println(Update.getErrorString());
    Update.end();
    http.end();
    return false;
  }

  if (!Update.end()) {
    Serial.print("Firmware update FAILED: ");
    Serial.println(Update.getErrorString());
    http.end();
    return false;
  }

  http.end();

  if (!Update.isFinished()) {
    Serial.println("Firmware update is not finished.");
    return false;
  }

  if (!saveLocalFirmwareHash(expectedHash)) {
    Serial.println("WARNING: Firmware updated but local identity could not be saved.");
    return false;
  }

  Serial.println("PyGit code update successful!");
  Serial.println("Restarting into the updated code...");

  delay(1000);
  ESP.restart();

  return true;
}

void checkPyGitCodeUpdate() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("ERROR: WiFi is not connected.");
    return;
  }

  Serial.println();
  Serial.println("==============================");
  Serial.println("PYGIT CODE UPDATE CHECK");
  Serial.println("==============================");

  String remoteHash = fetchRemoteFirmwareHash();

  if (remoteHash.length() == 0) {
    Serial.println("Update check skipped.");
    Serial.println("==============================");
    return;
  }

  String localHash = readLocalFirmwareHash();

  Serial.print("Local code identity:  ");
  Serial.println(localHash.length() ? localHash : "(none)");

  Serial.print("GitHub code identity: ");
  Serial.println(remoteHash);

  if (localHash == remoteHash) {
    Serial.println("Code is up to date.");
    Serial.println("==============================");
    return;
  }

  if (localHash.length() == 0) {
    Serial.println("No local code identity found.");
    Serial.println("This device will download the current GitHub code.");
  } else {
    Serial.println("Different code detected.");
    Serial.println("Downloading the latest GitHub code...");
  }

  Serial.println("==============================");

  downloadAndInstallFirmware(remoteHash);
}
