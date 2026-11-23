/**
 * @file main.cpp
 * @brief FIRMWARE MAESTRO UNIFICADO - ArcSim_VR
 * @project ArcSim_VR - Simulador Háptico de Soldadura SMAW con Gemelo Digital
 *
 * SUBSISTEMAS INTEGRADOS:
 *   1. IMU MPU-6050 (I2C 0x68):
 *      - Montaje Vertical: Eje Y = Gravedad (-1G), Eje X = Pitch (avance), Eje Z = Roll (trabajo)
 *      - Filtro DLPF en 44 Hz y Filtro Complementario (96% Giro / 4% Acel)
 *      - Cuaterniones 3D (qw, qx, qy, qz) para Godot
 *   2. ToF Láser VL53L1X (I2C 0x29):
 *      - Modo Corto (Short Mode) a 50 Hz, precisión milimétrica (distancia punta-chapa)
 *   3. Pulsador de Punta / Homing (GPIO 4):
 *      - Filtro antirrebote, cebado de arco instantáneo y Tara con pulsación de 2 s
 *   4. LED RGB HW-479 (GPIO 16-R, 17-G, 19-B):
 *      - PWM 5 kHz (Hardware LEDC): Naranja (Standby), Azul (Homing), Verde (Óptimo), Rojo (Alerta)
 *   5. Actuador Háptico IRFZ44N (GPIO 25):
 *      - PWM 1 kHz: Strike (70 ms), Zumbido de arco suave (25%), Pulsos de aviso, ¡Cortocircuito al 100%!
 *   6. Máquina de Estados Finita (FSM) de Soldadura SMAW en tiempo real
 *   7. Telemetría Serial JSON a 50 Hz compatible directa con Godot DeviceLink
 */

#include <Arduino.h>
#include <Wire.h>
#include <VL53L1X.h>
#include <math.h>

// ==============================================================================
// ASIGNACIÓN DE PINES
// ==============================================================================
#define PIN_I2C_SDA         21
#define PIN_I2C_SCL         22

#define PIN_RGB_R           16   // Canal Rojo LED (HW-479)
#define PIN_RGB_G           17   // Canal Verde LED (HW-479)
#define PIN_RGB_B           19   // Canal Azul LED (HW-479)

#define PIN_HAPTIC          25   // Control MOSFET IRFZ44N
#define PIN_BUTTON          4    // Pulsador de contacto / homing (INPUT_PULLUP)
#define PIN_STATUS_LED      2    // LED azul integrado DevKit

// Parámetros PWM Hardware (Core 3.x)
#define PWM_RGB_FREQ        5000
#define PWM_RGB_RES         8
#define PWM_HAPTIC_FREQ     1000
#define PWM_HAPTIC_RES      8

// Longitud calibrada del electrodo sobresaliente desde el sensor (55 mm nominal + 20.5 mm ajuste físico = 75.5 mm)
#define ELECTRODE_LENGTH_OFFSET_MM  75.5f

// Direcciones I2C
#define MPU_ADDR            0x68
#define REG_PWR_MGMT_1      0x6B
#define REG_CONFIG          0x1A
#define REG_ACCEL_XOUT_H    0x3B

// ==============================================================================
// MÁQUINA DE ESTADOS FINITA (FSM)
// ==============================================================================
enum SystemState {
    STATE_IDLE,        // 0: Standby / En espera (LED Naranja, Motor 0%)
    STATE_HOMING,      // 1: Contacto físico / Cebado (LED Azul, Pulso háptico seco)
    STATE_WELD_OK,     // 2: Soldadura óptima (LED Verde, Zumbido suave plasma)
    STATE_WELD_WARN,   // 3: Advertencia de técnica (LED Rojo, Pulsos de aviso)
    STATE_STICKING,    // 4: Electrodo pegado (LED Rojo, ¡Vibración violenta 100%!)
    STATE_ERROR        // 5: Falla de hardware / sensor (LED Rojo 1 Hz)
};

SystemState current_state = STATE_IDLE;
bool arc_active = false;

// ==============================================================================
// SENSORES Y OBJETOS
// ==============================================================================
VL53L1X distanceSensor;
bool tof_online = false;
bool mpu_online = false;

// Orientación y ángulos
float roll = 0.0f, pitch = 0.0f, yaw = 0.0f;
float qw = 1.0f, qx = 0.0f, qy = 0.0f, qz = 0.0f;
float gyro_offset_x = 0.0f, gyro_offset_y = 0.0f, gyro_offset_z = 0.0f;
unsigned long last_imu_time_micros = 0;
uint8_t dlpf_mode = 3;

// Distancia ToF (mm) y calibración dinámica de cero
float current_distance_mm = 0.0f;
float dynamic_offset_mm = ELECTRODE_LENGTH_OFFSET_MM;
uint16_t latest_raw_tof = 75;

// Pulsador y Antirrebote
bool last_stable_button = HIGH;
bool last_reading_button = HIGH;
unsigned long last_debounce_ms = 0;
unsigned long press_start_ms = 0;
bool long_press_handled = false;
int button_state_telemetry = 0;

// Temporizadores hápticos y patrones
unsigned long state_enter_ms = 0;
unsigned long haptic_pattern_ms = 0;
bool haptic_toggle = false;

// Loop de telemetría a 50 Hz (20 ms)
unsigned long last_telemetry_ms = 0;

// ==============================================================================
// CONTROL DE ACTUADORES (LED RGB & MOTOR)
// ==============================================================================
void set_rgb(uint8_t r, uint8_t g, uint8_t b) {
    ledcWrite(PIN_RGB_R, r);
    ledcWrite(PIN_RGB_G, g);
    ledcWrite(PIN_RGB_B, b);
}

void set_motor_duty(uint8_t duty) {
    ledcWrite(PIN_HAPTIC, duty);
}

void apply_actuators_for_state(SystemState state) {
    unsigned long now = millis();
    unsigned long elapsed = now - state_enter_ms;

    switch (state) {
        case STATE_IDLE:
            // Naranja cálido de soplete en reposo
            set_rgb(255, 40, 0);
            set_motor_duty(0);
            break;

        case STATE_HOMING:
            // Azul de contacto inicial
            set_rgb(0, 50, 255);
            // Pulso seco de cebado durante los primeros 70 ms
            if (elapsed <= 70) {
                set_motor_duty(200);
            } else {
                set_motor_duty(0);
            }
            break;

        case STATE_WELD_OK:
            // Verde puro de soldadura óptima
            set_rgb(0, 255, 0);
            // Zumbido suave continuo del plasma (~28% de potencia)
            set_motor_duty(70);
            break;

        case STATE_WELD_WARN:
            // Rojo continuo de técnica defectuosa
            set_rgb(255, 0, 0);
            // Patrón pulsante de aviso: 120 ms ON / 90 ms OFF
            if (now - haptic_pattern_ms > (haptic_toggle ? 120 : 90)) {
                haptic_pattern_ms = now;
                haptic_toggle = !haptic_toggle;
                set_motor_duty(haptic_toggle ? 125 : 0);
            }
            break;

        case STATE_STICKING:
            // Rojo continuo
            set_rgb(255, 0, 0);
            // ¡Vibración violenta al 100%!
            set_motor_duty(255);
            break;

        case STATE_ERROR:
            // Parpadeo a 1 Hz
            if ((now / 500) % 2 == 0) {
                set_rgb(255, 0, 0);
            } else {
                set_rgb(0, 0, 0);
            }
            set_motor_duty(0);
            break;
    }
}

void set_state(SystemState new_state) {
    if (current_state != new_state) {
        current_state = new_state;
        state_enter_ms = millis();
        haptic_pattern_ms = millis();
        haptic_toggle = true;
    }
}

// ==============================================================================
// I2C & MPU-6050 VERTICAL
// ==============================================================================
void mpu_write_reg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

void set_dlpf(uint8_t mode) {
    dlpf_mode = (mode > 6) ? 6 : mode;
    mpu_write_reg(REG_CONFIG, dlpf_mode);
}

void calibrate_gyro() {
    digitalWrite(PIN_STATUS_LED, HIGH);
    set_rgb(0, 0, 255); // Azul durante calibración
    float sx = 0, sy = 0, sz = 0;
    const int SAMPLES = 150;

    for (int i = 0; i < SAMPLES; i++) {
        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x43);
        Wire.endTransmission(false);
        Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)6);
        if (Wire.available() >= 6) {
            int16_t gx = (Wire.read() << 8) | Wire.read();
            int16_t gy = (Wire.read() << 8) | Wire.read();
            int16_t gz = (Wire.read() << 8) | Wire.read();
            sx += (float)gx / 131.0f;
            sy += (float)gy / 131.0f;
            sz += (float)gz / 131.0f;
        }
        delay(2);
    }
    gyro_offset_x = sx / SAMPLES;
    gyro_offset_y = sy / SAMPLES;
    gyro_offset_z = sz / SAMPLES;

    digitalWrite(PIN_STATUS_LED, LOW);
    last_imu_time_micros = micros();
    yaw = 0.0f;
}

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

void update_imu() {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(REG_ACCEL_XOUT_H);
    Wire.endTransmission(false);
    Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)14);

    if (Wire.available() < 14) return;

    int16_t ax_raw = (Wire.read() << 8) | Wire.read();
    int16_t ay_raw = (Wire.read() << 8) | Wire.read();
    int16_t az_raw = (Wire.read() << 8) | Wire.read();
    Wire.read(); Wire.read(); // Descartar temp
    int16_t gx_raw = (Wire.read() << 8) | Wire.read();
    int16_t gy_raw = (Wire.read() << 8) | Wire.read();
    int16_t gz_raw = (Wire.read() << 8) | Wire.read();

    float ax = (float)ax_raw / 16384.0f;
    float ay = (float)ay_raw / 16384.0f;
    float az = (float)az_raw / 16384.0f;

    float gx = ((float)gx_raw / 131.0f) - gyro_offset_x;
    float gy = ((float)gy_raw / 131.0f) - gyro_offset_y;
    float gz = ((float)gz_raw / 131.0f) - gyro_offset_z;

    unsigned long now_micros = micros();
    float dt = (float)(now_micros - last_imu_time_micros) * 1e-6f;
    last_imu_time_micros = now_micros;
    if (dt > 0.1f) dt = 0.02f;

    // ==========================================================================
    // MATRIZ DE ROTACIÓN PARA MPU VERTICAL (Ay = -1G en reposo)
    // Eje Z: Longitud de la herramienta (inclinación de avance / Pitch con Az)
    // Eje Y: Gravedad vertical hacia abajo (-1G)
    // Eje X: Eje transversal (giro de muñeca / Roll con Ax)
    // ==========================================================================
    float accel_pitch = atan2f(az, -ay) * 57.2957795f;
    float accel_roll  = atan2f(ax, sqrtf(az * az + ay * ay)) * 57.2957795f;

    // Fusión sensorial por Filtro Complementario (96% / 4%)
    pitch = 0.96f * (pitch + gx * dt) + 0.04f * accel_pitch;
    roll  = 0.96f * (roll  + gz * dt) + 0.04f * accel_roll;
    yaw   = yaw + gy * dt; // Yaw gira alrededor del eje vertical Y

    // Convertir a cuaterniones para Godot
    euler_to_quaternion(roll * 0.01745329f, pitch * 0.01745329f, yaw * 0.01745329f);
}

// ==============================================================================
// ACTUALIZACIÓN DE DISTANCIA LÁSER (VL53L1X)
// ==============================================================================
void update_tof() {
    if (distanceSensor.dataReady()) {
        uint16_t dist = distanceSensor.read(false);
        // Descartar lecturas fuera de rango o errores de timeout
        if (dist > 0 && dist < 1500) {
            latest_raw_tof = dist;
            // Si el pulsador físico está en contacto con la chapa, la distancia es estrictamente 0.0 mm
            if (last_stable_button == LOW) {
                current_distance_mm = 0.0f;
            } else {
                float net_gap = (float)dist - dynamic_offset_mm;
                current_distance_mm = (net_gap < 0.0f) ? 0.0f : net_gap;
            }
        }
    }
}

// ==============================================================================
// PULSADOR DE CONTACTO Y TARA
// ==============================================================================
void update_button() {
    int raw = digitalRead(PIN_BUTTON);
    if (raw != last_reading_button) {
        last_debounce_ms = millis();
    }

    if ((millis() - last_debounce_ms) > 25) {
        if (raw != last_stable_button) {
            last_stable_button = raw;
            if (last_stable_button == LOW) {
                // Flanco de bajada: Contacto físico de la punta contra la chapa
                press_start_ms = millis();
                long_press_handled = false;
                button_state_telemetry = 1;
                digitalWrite(PIN_STATUS_LED, HIGH);

                // ¡CALIBRACIÓN DINÁMICA DE CERO EN EL CONTACTO FÍSICO!
                // En el instante de contacto físico la distancia es 0.0 mm absoluta
                current_distance_mm = 0.0f;
                if (latest_raw_tof >= 45 && latest_raw_tof <= 300) {
                    dynamic_offset_mm = (float)latest_raw_tof;
                }

                // Si estábamos en espera, cebamos el arco
                if (!arc_active) {
                    arc_active = true;
                    set_state(STATE_HOMING);
                }
            } else {
                // Flanco de subida: Punta despegada
                button_state_telemetry = 0;
                digitalWrite(PIN_STATUS_LED, LOW);
            }
        }
    }

    // Mientras el pulsador físico esté apretado, fijamos la distancia en 0.0 mm
    if (last_stable_button == LOW) {
        current_distance_mm = 0.0f;
    }

    // Detección de pulsación larga (> 2 segundos) para TARA
    if (last_stable_button == LOW && !long_press_handled) {
        if (millis() - press_start_ms >= 2000) {
            long_press_handled = true;
            yaw = 0.0f; // Restablecer orientación
            // Confirmación visual con destello azul
            set_rgb(0, 0, 255); delay(100);
            set_rgb(0, 0, 0);   delay(100);
            set_rgb(0, 0, 255); delay(100);
        }
    }

    last_reading_button = raw;
}

// ==============================================================================
// EVALUACIÓN DE LA FÍSICA Y TRANSICIÓN DE ESTADOS SMAW
// ==============================================================================
void evaluate_fsm() {
    if (!arc_active) {
        set_state(STATE_IDLE);
        return;
    }

    // 1. Corte de arco por separación excesiva de la punta (> 12.0 mm)
    if (current_distance_mm > 12.0f && last_stable_button == HIGH) {
        arc_active = false;
        set_state(STATE_IDLE);
        return;
    }

    // 2. Electrodo pegado (cortocircuito: punta a <= 0.4 mm O pulsador apretado durante soldadura)
    if ((current_distance_mm <= 0.4f && last_stable_button == LOW) || 
        (last_stable_button == LOW && (millis() - press_start_ms > 250))) {
        set_state(STATE_STICKING);
        return;
    }

    // 3. Salida de Homing al separar la punta a distancia de arco (> 0.8 mm)
    if (current_state == STATE_HOMING) {
        if (current_distance_mm > 0.8f && (millis() - state_enter_ms > 70)) {
            set_state(STATE_WELD_OK);
        }
        return;
    }

    // 4. Evaluación de técnica de soldadura SMAW (Rango pedagógico ampliado):
    // Distancia de arco óptima: 1.0 mm a 6.0 mm (muy tolerante al pulso humano)
    bool dist_ok = (current_distance_mm >= 1.0f && current_distance_mm <= 6.0f);
    // Ángulo de trabajo / Roll óptimo: hasta +/- 25° de desviación
    bool roll_ok = (fabs(roll) < 25.0f);
    // Ángulo de avance / Pitch: entre -5° y +35°
    bool pitch_ok = (pitch >= -5.0f && pitch <= 35.0f);

    if (dist_ok && roll_ok && pitch_ok) {
        set_state(STATE_WELD_OK);
    } else {
        set_state(STATE_WELD_WARN);
    }
}

// ==============================================================================
// STREAMING DE TELEMETRÍA JSON (50 Hz)
// ==============================================================================
void send_telemetry() {
    // Formato estándar compatible directo con DeviceLink (Godot)
    Serial.printf("{\"qw\":%.4f,\"qx\":%.4f,\"qy\":%.4f,\"qz\":%.4f,\"d\":%.1f,\"b\":%d,\"r\":%.1f,\"p\":%.1f,\"y\":%.1f,\"st\":%d,\"dlpf\":%d}\n",
                  qw, qx, qy, qz, current_distance_mm, button_state_telemetry, roll, pitch, yaw, current_state, dlpf_mode);
}

// ==============================================================================
// PARSER DE COMANDOS ENTRANTE DESDE GODOT / CONSOLA
// ==============================================================================
void handle_serial_commands() {
    if (!Serial.available()) return;

    String line = Serial.readStringUntil('\n');
    line.trim();

    if (line.indexOf("CALIBRATE") >= 0 || line == "c" || line == "C") {
        calibrate_gyro();
    } else if (line.indexOf("RESET_YAW") >= 0 || line == "t" || line == "T") {
        yaw = 0.0f;
    } else if (line.length() == 1 && line[0] >= '0' && line[0] <= '6') {
        set_dlpf(line[0] - '0');
    }
}

// ==============================================================================
// SETUP
// ==============================================================================
void setup() {
    Serial.begin(115200);

    // Pines de salida
    pinMode(PIN_STATUS_LED, OUTPUT);
    digitalWrite(PIN_STATUS_LED, LOW);

    // Pin de entrada del pulsador con Pull-Up interno
    pinMode(PIN_BUTTON, INPUT_PULLUP);

    // PWM para LED RGB (5 kHz)
    ledcAttach(PIN_RGB_R, PWM_RGB_FREQ, PWM_RGB_RES);
    ledcAttach(PIN_RGB_G, PWM_RGB_FREQ, PWM_RGB_RES);
    ledcAttach(PIN_RGB_B, PWM_RGB_FREQ, PWM_RGB_RES);

    // PWM para Motor Háptico (1 kHz)
    ledcAttach(PIN_HAPTIC, PWM_HAPTIC_FREQ, PWM_HAPTIC_RES);
    set_motor_duty(0);

    // Test de bienvenida RGB y háptico rápido
    set_rgb(255, 0, 0); delay(150);
    set_rgb(0, 255, 0); delay(150);
    set_rgb(0, 0, 255); delay(150);
    set_rgb(0, 0, 0);

    set_motor_duty(180); delay(60);
    set_motor_duty(0);

    // Inicializar I2C a 400 kHz Fast Mode
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000L);
    delay(100);

    // Inicializar MPU-6050
    mpu_write_reg(REG_PWR_MGMT_1, 0x00); // Salir de sleep
    delay(30);
    set_dlpf(dlpf_mode);
    mpu_online = true;

    // Calibrar giróscopo inicial en reposo
    calibrate_gyro();

    // Inicializar VL53L1X Láser ToF
    distanceSensor.setTimeout(500);
    if (distanceSensor.init()) {
        distanceSensor.setDistanceMode(VL53L1X::Short);
        distanceSensor.setMeasurementTimingBudget(20000); // 20 ms (50 Hz)
        distanceSensor.startContinuous(20);
        tof_online = true;
    } else {
        tof_online = false;
        set_state(STATE_ERROR);
    }

    set_state(STATE_IDLE);
    last_telemetry_ms = millis();
}

// ==============================================================================
// LOOP PRINCIPAL (100 Hz Muestreo / 50 Hz Streaming)
// ==============================================================================
void loop() {
    handle_serial_commands();

    // 1. Lectura de Sensores
    update_imu();
    update_tof();
    update_button();

    // 2. Máquina de Estados SMAW
    evaluate_fsm();

    // 3. Aplicar salidas físicas (LED RGB y Motor Háptico)
    apply_actuators_for_state(current_state);

    // 4. Enviar Telemetría JSON a Godot cada 20 ms (50 Hz)
    unsigned long now = millis();
    if (now - last_telemetry_ms >= 20) {
        last_telemetry_ms = now;
        send_telemetry();
    }

    delay(2);
}
