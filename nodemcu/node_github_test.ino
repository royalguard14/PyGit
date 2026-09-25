#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>

const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASSWORD";

const char* githubURL =
  "https://raw.githubusercontent.com/royalguard14/PyGit/main/nodemcu/node_test.txt";

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

  if (!http.begin(client, githubURL)) {
    Serial.println("HTTP connection setup FAILED.");
    return;
  }

  int httpCode = http.GET();

  Serial.print("HTTP Code: ");
  Serial.println(httpCode);

  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();

    Serial.println();
    Serial.println("===== GITHUB CONTENT =====");
    Serial.println(payload);
    Serial.println("==========================");
    Serial.println();

    Serial.println("TEST SUCCESSFUL!");
  } else {
    Serial.println("GitHub download FAILED.");
  }

  http.end();
}

void loop() {
}
