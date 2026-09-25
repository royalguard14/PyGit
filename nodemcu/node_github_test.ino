#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>

const char* ssid = "Bautista";
const char* password = "@Sufyanbautista30";

const char* githubURL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/refs/heads/main/nodemcu/node_test.txt";

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("==============================");
  Serial.println("NodeMCU GitHub Test");
  Serial.println("==============================");

  Serial.print("Connecting to WiFi");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

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
