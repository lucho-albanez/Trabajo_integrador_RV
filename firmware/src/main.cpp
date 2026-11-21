/**
 * @file main.cpp
 * @brief Laboratorio de Pruebas MPU-6050 y Gemelo Digital en Tiempo Real
 * @project ArcSim_VR
 *
 * Código minimalista, directo y documentado línea por línea.
 * Comunica por I2C nativo (Wire.h) sin librerías externas complejas.
 * Permite cambiar la frecuencia del filtro pasa-bajos (DLPF) en tiempo real
 * desde la consola serie para analizar el ruido del acelerómetro.
 */

#include <Arduino.h>
#include <Wire.h>
#include <math.h>

// ==============================================================================
// DEFINICIÓN DE PINES Y DIRECCIONES I2C
// ==============================================================================
#define PIN_SDA           21
#define PIN_SCL           22
#define PIN_PULSADOR      4    // Conexión a GND (INPUT_PULLUP)
#define PIN_LED           2    // LED onboard de la ESP32

#define MPU_ADDR          0x68 // Dirección I2C por defecto (AD0 a GND)

// Registros internos del silicio del MPU-6050
#define REG_SMPLRT_DIV    0x19 // Divisor de tasa de muestreo
#define REG_CONFIG        0x1A // ¡AQUÍ ESTÁ EL FILTRO PASA-BAJOS (DLPF)!
#define REG_GYRO_CONFIG   0x1B // Rango del giroscopio
#define REG_ACCEL_CONFIG  0x1C // Rango del acelerómetro
#define REG_PWR_MGMT_1    0x6B // Gestión de energía (wake-up)
#define REG_ACCEL_XOUT_H  0x3B // Primer byte de las 14 lecturas consecutivas

// ==============================================================================
// TABLA DE FRECUENCIAS DEL FILTRO PASA-BAJOS (DLPF - REGISTRO 0x1A)
// ==============================================================================
// Modo 0: Acel 260 Hz (0.0 ms retardo) | Giro 256 Hz (0.98 ms) -> RUIDO MÁXIMO
// Modo 1: Acel 184 Hz (2.0 ms retardo) | Giro 188 Hz (1.90 ms)
// Modo 2: Acel  94 Hz (3.0 ms retardo) | Giro  98 Hz (2.80 ms)
// Modo 3: Acel  44 Hz (4.9 ms retardo) | Giro  42 Hz (4.80 ms) -> Balance clásico
// Modo 4: Acel  21 Hz (8.5 ms retardo) | Giro  20 Hz (8.30 ms)
// Modo 5: Acel  10 Hz (13.8 ms)        | Giro  10 Hz (13.4 ms) -> Muy suave (Soldadura)
// Modo 6: Acel   5 Hz (19.0 ms)        | Giro   5 Hz (18.6 ms) -> Filtrado extremo

uint8_t dlpf_mode = 3; // Arrancamos en Modo 3 (44 Hz)

// ==============================================================================
// VARIABLES FÍSICAS Y DE ORIENTACIÓN
// ==============================================================================
// Calibración de offsets del giroscopio
float gyro_offset_x = 0.0f;
float gyro_offset_y = 0.0f;
float gyro_offset_z = 0.0f;

// Ángulos calculados (° grados)
float roll  = 0.0f;
float pitch = 0.0f;
float yaw   = 0.0f;

// Cuaternión para el Gemelo Digital en Godot (qw, qx, qy, qz)
float qw = 1.0f, qx = 0.0f, qy = 0.0f, qz = 0.0f;

// Control de tiempo para el integrador
unsigned long last_time_micros = 0;

// Modo de salida por consola:
// false = MODO GRAFICADOR / PLOTTER (para ver el ruido en vivo)
// true  = MODO JSON GODOT (para rotar el gemelo digital en 3D)
bool output_mode_json = true;

// ==============================================================================
// FUNCIONES AUXILIARES I2C
// ==============================================================================
void mpu_write_register(uint8_t reg, uint8_t data) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    Wire.write(data);
    Wire.endTransmission();
}

void set_dlpf_filter(uint8_t mode) {
    if (mode > 6) mode = 6;
    dlpf_mode = mode;
    // Los bits [2:0] de REG_CONFIG configuran el DLPF_CFG
    mpu_write_register(REG_CONFIG, dlpf_mode);
}

void calibrate_gyro() {
    digitalWrite(PIN_LED, HIGH);

    float sum_x = 0.0f, sum_y = 0.0f, sum_z = 0.0f;
    const int SAMPLES = 200;

    for (int i = 0; i < SAMPLES; i++) {
        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x43); // GYRO_XOUT_H
        Wire.endTransmission(false);
        Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)6);

        int16_t gx_raw = (Wire.read() << 8) | Wire.read();
        int16_t gy_raw = (Wire.read() << 8) | Wire.read();
        int16_t gz_raw = (Wire.read() << 8) | Wire.read();

        sum_x += (float)gx_raw / 131.0f;
        sum_y += (float)gy_raw / 131.0f;
        sum_z += (float)gz_raw / 131.0f;
        delay(2);
    }

    gyro_offset_x = sum_x / SAMPLES;
    gyro_offset_y = sum_y / SAMPLES;
    gyro_offset_z = sum_z / SAMPLES;

    digitalWrite(PIN_LED, LOW);
    
    // Limpiar buffers y resetear delta de tiempo para evitar saltos
    while (Serial.available()) { Serial.read(); }
    last_time_micros = micros();
    yaw = 0.0f; // Reiniciar el yaw
}

// Conversión de Euler (Roll, Pitch, Yaw en radianes) a Cuaternión normalizado
void euler_to_quaternion(float r_rad, float p_rad, float y_rad) {
    float cr = cosf(r_rad * 0.5f);
    float sr = sinf(r_rad * 0.5f);
    float cp = cosf(p_rad * 0.5f);
    float sp = sinf(p_rad * 0.5f);
    float cy = cosf(y_rad * 0.5f);
    float sy = sinf(y_rad * 0.5f);

    qw = cr * cp * cy + sr * sp * sy;
    qx = sr * cp * cy - cr * sp * sy;
    qy = cr * sp * cy + sr * cp * sy;
    qz = cr * cp * sy - sr * sp * cy;
}

// ==============================================================================
// SETUP
// ==============================================================================
void setup() {
    Serial.begin(115200);
    pinMode(PIN_LED, OUTPUT);
    pinMode(PIN_PULSADOR, INPUT_PULLUP);

    // Inicializar bus I2C a 400 kHz (Fast Mode)
    Wire.begin(PIN_SDA, PIN_SCL, 400000L);
    delay(100);

    Serial.println("\n=======================================================");
    Serial.println("  ArcSim_VR - MPU-6050 & Gemelo Digital ESP32");
    Serial.println("=======================================================");

    // 1. Despertar el MPU-6050 (por defecto arranca dormido con el bit SLEEP = 1)
    mpu_write_register(REG_PWR_MGMT_1, 0x00);
    delay(20);

    // 2. Comprobar si el sensor responde (registro WHO_AM_I = 0x75, debe dar 0x68)
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x75);
    Wire.endTransmission(false);
    Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)1);
    if (!Wire.available() || Wire.read() != 0x68) {
        Serial.println("[ERROR] ¡No se detectó el MPU-6050 en I2C (0x68)!");
        Serial.println("Revisa los cables: VCC->3V3, GND->GND, SDA->D21, SCL->D22.");
        while (true) {
            digitalWrite(PIN_LED, !digitalRead(PIN_LED));
            delay(200);
        }
    }
    Serial.println("[OK] MPU-6050 detectado correctamente.");

    // 3. Configurar rangos:
    // Acelerómetro: ±2g (sensibilidad: 16384 LSB/g) -> REG 0x1C = 0x00
    mpu_write_register(REG_ACCEL_CONFIG, 0x00);
    // Giroscopio: ±250 °/s (sensibilidad: 131 LSB/(°/s)) -> REG 0x1B = 0x00
    mpu_write_register(REG_GYRO_CONFIG, 0x00);

    // 4. Aplicar Filtro Pasa-Bajos Digital inicial (DLPF = 3 -> 44 Hz)
    set_dlpf_filter(dlpf_mode);
    Serial.printf("[OK] Filtro DLPF inicial activado: MODO %d (44 Hz)\n", dlpf_mode);

    // 5. Calibrar giroscopio con la placa en reposo
    calibrate_gyro();

    last_time_micros = micros();

    Serial.println("-------------------------------------------------------");
    Serial.println("COMANDOS POR CONSOLA (escribe una tecla y presiona Enter):");
    Serial.println("  '0' a '6' : Cambia la frecuencia del filtro DLPF en vivo.");
    Serial.println("  'm'       : Alterna entre formato GRAFICADOR y JSON GODOT.");
    Serial.println("  'c'       : Recalibra el giroscopio en reposo.");
    Serial.println("-------------------------------------------------------\n");
    delay(1000);
}

// ==============================================================================
// LOOP PRINCIPAL
// ==============================================================================
void loop() {
    // --------------------------------------------------------------------------
    // 1. Escuchar comandos serie del usuario
    // --------------------------------------------------------------------------
    if (Serial.available()) {
        char cmd = Serial.read();
        if (cmd >= '0' && cmd <= '6') {
            set_dlpf_filter(cmd - '0');
            const char* nombres[] = {"260 Hz (Sin filtro)", "184 Hz", "94 Hz", "44 Hz (Equilibrado)", "21 Hz", "10 Hz (Suave)", "5 Hz (Extremo)"};
            Serial.printf("\n>>> [DLPF CAMBIADO] Modo %d: %s\n\n", dlpf_mode, nombres[dlpf_mode]);
        } else if (cmd == 'm' || cmd == 'M') {
            output_mode_json = !output_mode_json;
            Serial.printf("\n>>> [MODO] %s\n\n", output_mode_json ? "JSON PARA GODOT" : "GRAFICADOR / PLOTTER");
        } else if (cmd == 'c' || cmd == 'C') {
            calibrate_gyro();
        }
    }

    // --------------------------------------------------------------------------
    // 2. Leer los 14 registros de mediciones por I2C (Burst Read)
    // --------------------------------------------------------------------------
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(REG_ACCEL_XOUT_H); // Empezamos en 0x3B
    Wire.endTransmission(false);
    Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)14);

    if (Wire.available() < 14) return;

    int16_t ax_raw = (Wire.read() << 8) | Wire.read();
    int16_t ay_raw = (Wire.read() << 8) | Wire.read();
    int16_t az_raw = (Wire.read() << 8) | Wire.read();
    int16_t temp_raw = (Wire.read() << 8) | Wire.read();
    int16_t gx_raw = (Wire.read() << 8) | Wire.read();
    int16_t gy_raw = (Wire.read() << 8) | Wire.read();
    int16_t gz_raw = (Wire.read() << 8) | Wire.read();

    // Convertir a unidades físicas (g y grados/segundo)
    float ax = (float)ax_raw / 16384.0f;
    float ay = (float)ay_raw / 16384.0f;
    float az = (float)az_raw / 16384.0f;

    float gx = ((float)gx_raw / 131.0f) - gyro_offset_x;
    float gy = ((float)gy_raw / 131.0f) - gyro_offset_y;
    float gz = ((float)gz_raw / 131.0f) - gyro_offset_z;

    // --------------------------------------------------------------------------
    // 3. Delta de tiempo (dt) e integración del giroscopio
    // --------------------------------------------------------------------------
    unsigned long now_micros = micros();
    float dt = (float)(now_micros - last_time_micros) * 1e-6f;
    last_time_micros = now_micros;
    if (dt > 0.1f) dt = 0.02f; // Protección ante saltos de tiempo

    // Ángulos estimados a partir de la gravedad (Acelerómetro)
    // Roll (alabeo): inclinación lateral
    float accel_roll = atan2f(-ax, az) * 57.2957795f;
    // Pitch (cabeceo): inclinación frontal
    float accel_pitch = atan2f(ay, sqrtf(ax * ax + az * az)) * 57.2957795f;

    // --------------------------------------------------------------------------
    // 4. Filtro Complementario (Fusión sensorial limpia)
    // 96% giroscopio (rápido y sin vibraciones) + 4% acelerómetro (sin deriva)
    // --------------------------------------------------------------------------
    roll  = 0.96f * (roll + gx * dt) + 0.04f * accel_roll;
    pitch = 0.96f * (pitch + gy * dt) + 0.04f * accel_pitch;
    yaw   = yaw + gz * dt; // El yaw no tiene referencia de gravedad, se integra

    // Convertir a cuaternión para Godot (en radianes)
    euler_to_quaternion(roll * 0.01745329f, pitch * 0.01745329f, yaw * 0.01745329f);

    // Lectura del pulsador físico (invertido por INPUT_PULLUP: presionado = 1, suelto = 0)
    int boton = (digitalRead(PIN_PULSADOR) == LOW) ? 1 : 0;

    // --------------------------------------------------------------------------
    // 5. Salida de datos formateada (a ~50 Hz / 20 ms)
    // --------------------------------------------------------------------------
    if (output_mode_json) {
        // Formato JSON compatible directo con Godot DeviceLink:
        // qw, qx, qy, qz (orientación 3D), r, p, y (grados), d (distancia), b (botón)
        Serial.printf("{\"qw\":%.4f,\"qx\":%.4f,\"qy\":%.4f,\"qz\":%.4f,\"r\":%.1f,\"p\":%.1f,\"y\":%.1f,\"d\":0.0,\"b\":%d,\"dlpf\":%d}\n",
                      qw, qx, qy, qz, roll, pitch, yaw, boton, dlpf_mode);
    } else {
        // Formato para Serial Plotter (para graficar el ruido del acelerómetro vs filtro):
        // Muestra la aceleración instantánea y los ángulos
        Serial.printf(">Pitch:%.2f,Roll:%.2f,Accel_X:%.3f,Accel_Y:%.3f,Accel_Z:%.3f,DLPF:%d\n",
                      pitch, roll, ax, ay, az, dlpf_mode);
    }

    delay(20); // ~50 lecturas por segundo (50 Hz)
}
