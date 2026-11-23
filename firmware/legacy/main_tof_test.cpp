/**
 * @file main.cpp
 * @brief Test y Verificación del Sensor Láser ToF VL53L1X
 * @project ArcSim_VR
 *
 * Conexión I2C en ESP32:
 *   - VCC  -> 3V3 (3.3V)
 *   - GND  -> GND
 *   - SDA  -> Pin D21 (GPIO 21)
 *   - SCL  -> Pin D22 (GPIO 22)
 *   (Pines XSHUT y GPIO1 quedan libres / desconectados)
 *
 * Este código:
 *   1. Escanea el bus I2C para confirmar que el sensor responde en 0x29.
 *   2. Configura el VL53L1X en modo de distancia corta (Short Mode, hasta 1.3 m).
 *   3. Muestra la distancia en milímetros y centímetros en tiempo real a 50 Hz.
 */

#include <Arduino.h>
#include <Wire.h>
#include <VL53L1X.h>

#define PIN_SDA   21
#define PIN_SCL   22
#define PIN_LED    2

VL53L1X sensor;

// Función para escanear y reportar qué chips están conectados al bus I2C
void scan_i2c_bus() {
    Serial.println("\n--- Escaneando bus I2C (SDA=21, SCL=22) ---");
    byte count = 0;
    for (byte addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf("  [DISPOSITIVO ENCONTRADO] en direccion 0x%02X: ", addr);
            if (addr == 0x29) {
                Serial.println("-> Sensor ToF Laser (VL53L1X / VL53L0X)");
            } else if (addr == 0x68) {
                Serial.println("-> Acelerometro/Giroscopio (MPU-6050)");
            } else {
                Serial.println("-> Dispositivo desconocido");
            }
            count++;
        }
    }
    if (count == 0) {
        Serial.println("  [ERROR] ¡No se detectó NINGÚN dispositivo en el bus I2C!");
        Serial.println("  Revisa: cables VCC (3.3V), GND, SDA (D21) y SCL (D22).");
    }
    Serial.println("-------------------------------------------\n");
}

void setup() {
    Serial.begin(115200);
    pinMode(PIN_LED, OUTPUT);
    digitalWrite(PIN_LED, LOW);

    // Inicializar bus I2C a 400 kHz (Fast Mode)
    Wire.begin(PIN_SDA, PIN_SCL, 400000L);
    delay(500);

    Serial.println("\n=======================================================");
    Serial.println("      ArcSim_VR - Verificación ToF VL53L1X");
    Serial.println("=======================================================");

    // 1. Escaneo inicial
    scan_i2c_bus();

    // 2. Timeout de I2C del sensor para evitar bloqueos
    sensor.setTimeout(500);

    // 3. Inicializar el sensor ToF
    if (!sensor.init()) {
        Serial.println("\n[ERROR CRÍTICO] ¡Falló al inicializar el sensor VL53L1X!");
        Serial.println("Causas posibles:");
        Serial.println("  1. El cable SDA o SCL está flojo o invertido.");
        Serial.println("  2. El pin XSHUT del sensor está en masa (debe quedar libre).");
        Serial.println("  3. El sensor no está recibiendo 3.3V.");
        while (true) {
            digitalWrite(PIN_LED, !digitalRead(PIN_LED));
            delay(150);
        }
    }

    Serial.println("[OK] Sensor VL53L1X inicializado con éxito.");

    // 4. Configurar modo de distancia corta (Short Mode):
    // Rango de 0 a 1.3 metros. Es el modo con mayor inmunidad a la luz ambiente
    // y máxima precisión milimétrica (ideal para soldadura de 0 a 200 mm).
    sensor.setDistanceMode(VL53L1X::Short);

    // 5. Presupuesto de tiempo por medición: 20 ms (50 mediciones por segundo / 50 Hz)
    sensor.setMeasurementTimingBudget(20000);

    // 6. Iniciar mediciones continuas cada 20 ms
    sensor.startContinuous(20);

    Serial.println("[OK] Mediciones continuas iniciadas a 50 Hz.");
    Serial.println("\nMueve la mano o una superficie frente al sensor:\n");
    delay(1000);
}

void loop() {
    // Leer distancia en milímetros
    uint16_t distance_mm = sensor.read();

    // Verificar si ocurrió un timeout
    if (sensor.timeoutOccurred()) {
        Serial.println("[ALERTA] Timeout en lectura I2C del sensor");
        return;
    }

    // Estado de la medición (0 = Rango válido sin errores)
    uint8_t range_status = sensor.ranging_data.range_status;

    if (range_status == 0) {
        digitalWrite(PIN_LED, HIGH);

        // Barra gráfica visual ASCII para ver el acercamiento en la consola
        char bar[26];
        int filled = constrain(distance_mm / 15, 0, 25);
        for (int i = 0; i < 25; i++) {
            bar[i] = (i < filled) ? '=' : ' ';
        }
        bar[25] = '\0';

        // Formato claro en milímetros y centímetros
        Serial.printf("Distancia: %4u mm  (%5.1f cm)  [%s]\n",
                      distance_mm, distance_mm / 10.0f, bar);
    } else {
        digitalWrite(PIN_LED, LOW);
        // Códigos de estado del sensor VL53L1X
        const char* status_desc = "Objeto fuera de rango";
        if (range_status == 1) status_desc = "Falla de señal (retorno muy débil)";
        else if (range_status == 2) status_desc = "Falla de sigma (ruido óptico)";
        else if (range_status == 4) status_desc = "Fuera de rango máximo";

        Serial.printf("Distancia: [---]  Status: %s (Cod: %d)\n", status_desc, range_status);
    }

    delay(30); // ~33 lecturas por segundo para una consola legible
}
