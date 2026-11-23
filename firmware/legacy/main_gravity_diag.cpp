/**
 * @file main.cpp
 * @brief Diagnóstico Rápido de Ejes y Gravedad para MPU-6050 Vertical
 * @project ArcSim_VR
 *
 * Este script lee las aceleraciones físicas en tiempo real (en unidades de 'g')
 * para determinar con precisión matemática qué eje corresponde a:
 *   1. GRAVEDAD (Eje vertical / Arriba-Abajo)
 *   2. PITCH (Ángulo de avance / inclinación frontal)
 *   3. ROLL (Ángulo de trabajo / inclinación lateral)
 */

#include <Arduino.h>
#include <Wire.h>

#define MPU_ADDR            0x68
#define PIN_SDA             21
#define PIN_SCL             22

#define REG_PWR_MGMT_1      0x6B
#define REG_CONFIG          0x1A
#define REG_ACCEL_XOUT_H    0x3B

void mpu_write(uint8_t reg, uint8_t data) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    Wire.write(data);
    Wire.endTransmission();
}

void setup() {
    Serial.begin(115200);
    Wire.begin(PIN_SDA, PIN_SCL, 400000L);
    delay(100);

    Serial.println("\n============================================================");
    Serial.println("  ArcSim_VR - Diagnóstico de Orientación MPU-6050");
    Serial.println("============================================================");

    // Despertar el MPU-6050
    mpu_write(REG_PWR_MGMT_1, 0x00);
    delay(50);
    // Activar filtro DLPF en 44 Hz para que la lectura sea suave y estable
    mpu_write(REG_CONFIG, 0x03);
    delay(50);

    // Verificar si responde en 0x68
    Wire.beginTransmission(MPU_ADDR);
    if (Wire.endTransmission() != 0) {
        Serial.println(">>> ERROR: No se detecta el MPU-6050 en 0x68. Revisa cables SDA (D21) y SCL (D22).");
        while (1) { delay(1000); }
    }

    Serial.println("[OK] Sensor MPU-6050 conectado y calibrado a 44 Hz DLPF.");
    Serial.println("------------------------------------------------------------");
    Serial.println("INSTRUCCIONES:");
    Serial.println("1. Sostén la herramienta en tu mano en la posición NORMAL de soldar");
    Serial.println("   (apuntando hacia adelante sobre la mesa, horizontal).");
    Serial.println("2. Mira cuál de los 3 ejes marca cerca de +1.00 g o -1.00 g.");
    Serial.println("============================================================\n");
    delay(1500);
}

void loop() {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(REG_ACCEL_XOUT_H);
    Wire.endTransmission(false);
    Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)14);

    if (Wire.available() >= 14) {
        int16_t ax_raw = (Wire.read() << 8) | Wire.read();
        int16_t ay_raw = (Wire.read() << 8) | Wire.read();
        int16_t az_raw = (Wire.read() << 8) | Wire.read();
        Wire.read(); Wire.read(); // Temp
        int16_t gx_raw = (Wire.read() << 8) | Wire.read();
        int16_t gy_raw = (Wire.read() << 8) | Wire.read();
        int16_t gz_raw = (Wire.read() << 8) | Wire.read();

        // Convertir a aceleración en g (1g = gravedad terrestre)
        float ax = (float)ax_raw / 16384.0f;
        float ay = (float)ay_raw / 16384.0f;
        float az = (float)az_raw / 16384.0f;

        // Detectar automáticamente el eje dominante de gravedad
        const char* eje_gravedad = "Indefinido";
        if (fabs(ax) > 0.75f) eje_gravedad = (ax > 0) ? "Eje +X (Vertical)" : "Eje -X (Vertical Invertido)";
        else if (fabs(ay) > 0.75f) eje_gravedad = (ay > 0) ? "Eje +Y (Vertical)" : "Eje -Y (Vertical Invertido)";
        else if (fabs(az) > 0.75f) eje_gravedad = (az > 0) ? "Eje +Z (Vertical)" : "Eje -Z (Vertical Invertido)";

        // Imprimir a 10 Hz
        Serial.printf("Ax: %+.2f g | Ay: %+.2f g | Az: %+.2f g   ===>  Gravedad: [%s]\n",
                      ax, ay, az, eje_gravedad);
    }

    delay(100);
}
