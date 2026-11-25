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
bool session_active = false;

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

// Filtros avanzados ToF: Mediana de 5 muestras + Pasa-bajos EMA + Banda muerta
#define TOF_MEDIAN_SIZE 5
float tof_buf[TOF_MEDIAN_SIZE] = {0.0f};
uint8_t tof_buf_idx = 0;
bool tof_buf_filled = false;
float smoothed_tof_mm = 0.0f;

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
// ==============================================================================
// CONFIGURACIÓN DINÁMICA DE LA HERRAMIENTA (MODIFICABLE POR SERIAL DESDE GUI)
// ==============================================================================
struct DynamicConfig {
    uint8_t idle_r = 255, idle_g = 40, idle_b = 0;        // Naranja cálido
    uint8_t homing_r = 0, homing_g = 50, homing_b = 255;   // Azul contacto
    uint8_t weld_ok_r = 0, weld_ok_g = 255, weld_ok_b = 0; // Verde óptimo
    uint8_t weld_warn_r = 255, weld_warn_g = 0, weld_warn_b = 0; // Rojo advertencia
    uint8_t sticking_r = 255, sticking_g = 0, sticking_b = 0;    // Rojo pegado

    uint8_t duty_homing = 200;    // ~78%
    uint8_t duty_weld_ok = 70;    // ~28%
    uint8_t duty_weld_warn = 125; // ~49%
    uint8_t duty_sticking = 255;  // 100%

    float stick_gap_mm = 0.4f;
    float extinguish_gap_mm = 12.0f;
    float reignite_gap_mm = 4.5f;
    float opt_min_gap_mm = 1.0f;
    float opt_max_gap_mm = 6.0f;
} g_cfg;

// ==============================================================================
// TEMPORIZADORES DE OVERRIDE PARA PRUEBAS MANUALES (DESDE GUI O COMANDOS)
// ==============================================================================
unsigned long test_override_led_until_ms = 0;
unsigned long test_override_haptic_until_ms = 0;

void set_rgb(uint8_t r, uint8_t g, uint8_t b) {
    ledcWrite(PIN_RGB_R, r);
    ledcWrite(PIN_RGB_G, g);
    ledcWrite(PIN_RGB_B, b);
}

void set_motor_duty(uint8_t duty) {
    ledcWrite(PIN_HAPTIC, duty);
}

void apply_led_for_state(SystemState state) {
    unsigned long now = millis();
    switch (state) {
        case STATE_IDLE:
            set_rgb(g_cfg.idle_r, g_cfg.idle_g, g_cfg.idle_b);
            break;
        case STATE_HOMING:
            set_rgb(g_cfg.homing_r, g_cfg.homing_g, g_cfg.homing_b);
            break;
        case STATE_WELD_OK:
            set_rgb(g_cfg.weld_ok_r, g_cfg.weld_ok_g, g_cfg.weld_ok_b);
            break;
        case STATE_WELD_WARN:
            set_rgb(g_cfg.weld_warn_r, g_cfg.weld_warn_g, g_cfg.weld_warn_b);
            break;
        case STATE_STICKING:
            set_rgb(g_cfg.sticking_r, g_cfg.sticking_g, g_cfg.sticking_b);
            break;
        case STATE_ERROR:
            if ((now / 500) % 2 == 0) {
                set_rgb(255, 0, 0);
            } else {
                set_rgb(0, 0, 0);
            }
            break;
    }
}

void apply_haptic_for_state(SystemState state) {
    unsigned long now = millis();
    unsigned long elapsed = now - state_enter_ms;
    switch (state) {
        case STATE_IDLE:
            set_motor_duty(0);
            break;
        case STATE_HOMING:
            if (elapsed <= 70) {
                set_motor_duty(g_cfg.duty_homing);
            } else {
                set_motor_duty(0);
            }
            break;
        case STATE_WELD_OK:
            set_motor_duty(g_cfg.duty_weld_ok);
            break;
        case STATE_WELD_WARN:
            if (now - haptic_pattern_ms > (haptic_toggle ? 120 : 90)) {
                haptic_pattern_ms = now;
                haptic_toggle = !haptic_toggle;
                set_motor_duty(haptic_toggle ? g_cfg.duty_weld_warn : 0);
            }
            break;
        case STATE_STICKING:
            set_motor_duty(g_cfg.duty_sticking);
            break;
        case STATE_ERROR:
            set_motor_duty(0);
            break;
    }
}

void apply_actuators_for_state(SystemState state) {
    unsigned long now = millis();
    if (now >= test_override_led_until_ms) {
        apply_led_for_state(state);
    }
    if (now >= test_override_haptic_until_ms) {
        apply_haptic_for_state(state);
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
        uint8_t status = distanceSensor.ranging_data.range_status;

        // Descartar lecturas con error óptico o fuera de rango físico razonable (< 1200 mm)
        // status 0: Rango válido, status 7: Wraparound
        if (dist > 10 && dist < 1200 && (status == 0 || status == 7)) {
            latest_raw_tof = dist;

            // Si el pulsador físico está en contacto con la chapa, la distancia es estrictamente 0.0 mm
            if (last_stable_button == LOW) {
                current_distance_mm = 0.0f;
                smoothed_tof_mm = 0.0f;
            } else {
                float net_gap = (float)dist - dynamic_offset_mm;
                if (net_gap < 0.0f) net_gap = 0.0f;

                // 1. Filtro de Mediana (elimina picos repentinos y reflexiones parásitas)
                tof_buf[tof_buf_idx] = net_gap;
                tof_buf_idx = (tof_buf_idx + 1) % TOF_MEDIAN_SIZE;
                if (tof_buf_idx == 0) tof_buf_filled = true;

                float median_gap = net_gap;
                if (tof_buf_filled) {
                    float s[TOF_MEDIAN_SIZE];
                    for (int i = 0; i < TOF_MEDIAN_SIZE; i++) s[i] = tof_buf[i];
                    for (int i = 0; i < TOF_MEDIAN_SIZE - 1; i++) {
                        for (int j = i + 1; j < TOF_MEDIAN_SIZE; j++) {
                            if (s[i] > s[j]) {
                                float tmp = s[i];
                                s[i] = s[j];
                                s[j] = tmp;
                            }
                        }
                    }
                    median_gap = s[TOF_MEDIAN_SIZE / 2];
                }

                // 2. Filtro Pasa-Bajos Exponencial (EMA: 70% inercia / 30% nueva muestra)
                if (smoothed_tof_mm <= 0.01f && median_gap > 0.0f) {
                    smoothed_tof_mm = median_gap;
                } else {
                    smoothed_tof_mm = 0.70f * smoothed_tof_mm + 0.30f * median_gap;
                }

                // 3. Banda Muerta (Deadband de 0.25 mm) para eliminar temblor cuántico del último decimal
                if (fabs(smoothed_tof_mm - current_distance_mm) >= 0.25f) {
                    current_distance_mm = smoothed_tof_mm;
                }
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

                // Si la sesión no ha comenzado, este primer contacto es el cebado / homing
                if (!session_active) {
                    session_active = true;
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

    // Detección de pulsación larga (> 2 segundos) para TARA y REINICIO DE SESIÓN
    if (last_stable_button == LOW && !long_press_handled) {
        if (millis() - press_start_ms >= 2000) {
            long_press_handled = true;
            yaw = 0.0f; // Restablecer orientación
            session_active = false;
            arc_active = false;
            set_state(STATE_IDLE);
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
    // Si la sesión no está activa (aún no se hizo homing inicial), permanecemos en IDLE
    if (!session_active) {
        set_state(STATE_IDLE);
        return;
    }

    // 1. Condición de electrodo pegado (STICKING):
    // Si la punta toca físicamente la chapa (botón apretado) o distancia ToF <= stick_gap
    if (last_stable_button == LOW || current_distance_mm <= g_cfg.stick_gap_mm) {
        // En el instante justo del homing permitimos el pulso táctil inicial de cebado (~80ms)
        if (current_state == STATE_HOMING && (millis() - state_enter_ms <= 80)) {
            return;
        }
        set_state(STATE_STICKING);
        return;
    }

    // 2. Si estábamos en STATE_STICKING y el operario despega la punta (> stick_gap):
    // El arco se restablece automáticamente
    if (current_state == STATE_STICKING) {
        arc_active = true;
    }

    // 3. Salida de STATE_HOMING al despegar la punta:
    if (current_state == STATE_HOMING) {
        if (current_distance_mm > g_cfg.stick_gap_mm && (millis() - state_enter_ms > 70)) {
            arc_active = true;
            if (current_distance_mm <= g_cfg.opt_max_gap_mm) {
                set_state(STATE_WELD_OK);
            } else {
                set_state(STATE_WELD_WARN);
            }
        }
        return;
    }

    // 4. Si el arco se había extinguido por distancia excesiva:
    if (!arc_active) {
        // Reencendido automático por proximidad (sin requerir pulsar de nuevo)
        if (current_distance_mm <= g_cfg.reignite_gap_mm && current_distance_mm > g_cfg.stick_gap_mm) {
            arc_active = true;
        } else {
            set_state(STATE_IDLE);
            return;
        }
    }

    // 5. Corte de arco por separación excesiva (> extinguish_gap)
    if (current_distance_mm > g_cfg.extinguish_gap_mm) {
        arc_active = false;
        set_state(STATE_IDLE);
        return;
    }

    // 6. Evaluación de técnica de soldadura SMAW durante arco encendido:
    bool dist_ok = (current_distance_mm >= g_cfg.opt_min_gap_mm && current_distance_mm <= g_cfg.opt_max_gap_mm);
    bool roll_ok = (fabs(roll) < 25.0f);
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
// HELPERS NATIVOS DE PARSEO (CERO DEPENDENCIAS EXTERNAS)
// ==============================================================================
static int extract_int(const String& s, const char* key, int def_val) {
    int idx = s.indexOf(key);
    if (idx < 0) return def_val;
    int colon = s.indexOf(':', idx);
    if (colon < 0) return def_val;
    return s.substring(colon + 1).toInt();
}

static float extract_float(const String& s, const char* key, float def_val) {
    int idx = s.indexOf(key);
    if (idx < 0) return def_val;
    int colon = s.indexOf(':', idx);
    if (colon < 0) return def_val;
    return s.substring(colon + 1).toFloat();
}

static void extract_rgb(const String& s, const char* key, uint8_t& r, uint8_t& g, uint8_t& b) {
    int idx = s.indexOf(key);
    if (idx < 0) return;
    int b1 = s.indexOf('[', idx);
    int b2 = s.indexOf(']', b1);
    if (b1 >= 0 && b2 > b1) {
        String sub = s.substring(b1 + 1, b2);
        int c1 = sub.indexOf(',');
        int c2 = sub.indexOf(',', c1 + 1);
        if (c1 > 0 && c2 > c1) {
            r = (uint8_t)constrain(sub.substring(0, c1).toInt(), 0, 255);
            g = (uint8_t)constrain(sub.substring(c1 + 1, c2).toInt(), 0, 255);
            b = (uint8_t)constrain(sub.substring(c2 + 1).toInt(), 0, 255);
        }
    }
}

// ==============================================================================
// PARSER DE COMANDOS ENTRANTE DESDE GODOT / CONSOLA / GUI
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
    } else if (line.indexOf("TEST_ACTUATOR") >= 0) {
        uint8_t r = (uint8_t)constrain(extract_int(line, "\"r\"", 0), 0, 255);
        uint8_t g = (uint8_t)constrain(extract_int(line, "\"g\"", 0), 0, 255);
        uint8_t b = (uint8_t)constrain(extract_int(line, "\"b\"", 0), 0, 255);
        int ms = extract_int(line, "\"ms\"", 2500); // Duración de prueba visual en ms (por defecto 2.5 s)
        set_rgb(r, g, b);
        test_override_led_until_ms = millis() + ms;
        Serial.printf("{\"ack\":\"TEST_ACTUATOR\",\"r\":%d,\"g\":%d,\"b\":%d,\"ms\":%d}\n", r, g, b, ms);
    } else if (line.indexOf("SET_HAPTIC") >= 0) {
        int duty = extract_int(line, "\"val\"", 0);
        int ms = extract_int(line, "\"ms\"", 0);
        if (ms > 0) {
            // Comando de prueba explícito desde GUI con temporizador en ms
            set_motor_duty((uint8_t)constrain(duty, 0, 255));
            test_override_haptic_until_ms = millis() + ms;
            Serial.printf("{\"ack\":\"SET_HAPTIC\",\"val\":%d,\"ms\":%d}\n", duty, ms);
        } else {
            // Streaming continuo desde el simulador Godot
            if (session_active && duty > 0) {
                set_motor_duty((uint8_t)constrain(duty, 0, 255));
                test_override_haptic_until_ms = millis() + 150; // ventana activa de 150 ms
            } else {
                test_override_haptic_until_ms = 0;
                set_motor_duty(0);
            }
        }
    } else if (line.indexOf("RESET") >= 0 || line.indexOf("END_SESSION") >= 0) {
        session_active = false;
        arc_active = false;
        test_override_haptic_until_ms = 0;
        set_motor_duty(0);
        set_state(STATE_IDLE);
        Serial.println("{\"ack\":\"SESSION_RESET\"}");
    } else if (line.indexOf("CONFIG") >= 0) {
        extract_rgb(line, "\"idle\"", g_cfg.idle_r, g_cfg.idle_g, g_cfg.idle_b);
        extract_rgb(line, "\"homing\"", g_cfg.homing_r, g_cfg.homing_g, g_cfg.homing_b);
        extract_rgb(line, "\"weld_optimal\"", g_cfg.weld_ok_r, g_cfg.weld_ok_g, g_cfg.weld_ok_b);
        extract_rgb(line, "\"weld_warning\"", g_cfg.weld_warn_r, g_cfg.weld_warn_g, g_cfg.weld_warn_b);
        extract_rgb(line, "\"sticking\"", g_cfg.sticking_r, g_cfg.sticking_g, g_cfg.sticking_b);

        if (line.indexOf("\"stick_gap\"") >= 0) g_cfg.stick_gap_mm = extract_float(line, "\"stick_gap\"", g_cfg.stick_gap_mm);
        if (line.indexOf("\"extinguish_gap\"") >= 0) g_cfg.extinguish_gap_mm = extract_float(line, "\"extinguish_gap\"", g_cfg.extinguish_gap_mm);
        if (line.indexOf("\"reignite_gap\"") >= 0) g_cfg.reignite_gap_mm = extract_float(line, "\"reignite_gap\"", g_cfg.reignite_gap_mm);
        if (line.indexOf("\"optimal_min\"") >= 0) g_cfg.opt_min_gap_mm = extract_float(line, "\"optimal_min\"", g_cfg.opt_min_gap_mm);
        if (line.indexOf("\"optimal_max\"") >= 0) g_cfg.opt_max_gap_mm = extract_float(line, "\"optimal_max\"", g_cfg.opt_max_gap_mm);

        int h_hom = extract_int(line, "\"homing\"", -1);
        if (h_hom >= 0 && line.indexOf("\"haptic_intensity_pct\"") >= 0) g_cfg.duty_homing = (uint8_t)(constrain(h_hom, 0, 100) * 2.55f);
        int h_weld = extract_int(line, "\"weld_optimal\"", -1);
        if (h_weld >= 0 && line.indexOf("\"haptic_intensity_pct\"") >= 0) g_cfg.duty_weld_ok = (uint8_t)(constrain(h_weld, 0, 100) * 2.55f);
        int h_warn = extract_int(line, "\"weld_warning\"", -1);
        if (h_warn >= 0 && line.indexOf("\"haptic_intensity_pct\"") >= 0) g_cfg.duty_weld_warn = (uint8_t)(constrain(h_warn, 0, 100) * 2.55f);
        int h_stk = extract_int(line, "\"sticking\"", -1);
        if (h_stk >= 0 && line.indexOf("\"haptic_intensity_pct\"") >= 0) g_cfg.duty_sticking = (uint8_t)(constrain(h_stk, 0, 100) * 2.55f);

        Serial.println("{\"ack\":\"CONFIG_APPLIED\"}");
    }
}

// ==============================================================================
// SETUP
// ==============================================================================
void setup() {
    Serial.begin(115200);
    Serial.setTimeout(5);

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
        distanceSensor.setMeasurementTimingBudget(40000); // 40 ms (mayor integración de fotones y menor dispersión)
        distanceSensor.startContinuous(40);
        tof_online = true;
    } else {
        tof_online = false;
        set_state(STATE_ERROR);
    }

    session_active = false;
    arc_active = false;
    test_override_haptic_until_ms = 0;
    set_motor_duty(0);
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
