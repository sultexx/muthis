// esp32_logic.ino — temperature-guard demo (Mut'his Phase 4 live-test sample).
// A TMP36 sensor on ADC pin 34 drives the onboard LED as an over-heat alarm.

const int SENSOR_PIN = 34;    // ADC1 channel (input-only pin on the ESP32)
const int LED_PIN = 2;        // onboard blue LED
const float LIMIT_C = 30.0;   // alarm threshold in Celsius

void setup() {
  Serial.begin(115200);       // USB log at the ESP32's usual baud rate
  pinMode(LED_PIN, OUTPUT);
}

float readCelsius() {
  int raw = analogRead(SENSOR_PIN);      // 12-bit ADC: 0..4095
  float volts = raw * 3.3 / 4095.0;      // counts -> volts (3.3 V reference)
  return (volts - 0.5) * 100.0;          // TMP36: 500 mV offset, 10 mV per °C
}

void loop() {
  float temp = readCelsius();
  digitalWrite(LED_PIN, temp > LIMIT_C ? HIGH : LOW);  // alarm LED
  Serial.println(temp);
  delay(1000);                           // one reading per second
}
