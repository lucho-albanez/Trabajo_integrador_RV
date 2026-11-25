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
    uint8_t weld_caution_r = 255, weld_caution_g = 170, weld_caution_b = 0; // Amarillo (cerca del limite)
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

    // true: el arco solo arranca tras apoyar la punta y presionar el pulsador (homing).
    // false: el arco arranca solo al acercar la punta a la distancia de encendido.
    bool homing_required = false;
} g_cfg;

// ==============================================================================
// TEMPORIZADORES DE OVERRIDE PARA PRUEBAS MANUALES (DESDE GUI O COMANDOS)
// ==============================================================================
#define FIRMWARE_VERSION "2026-11-25a"

unsigned long test_override_led_until_ms = 0;
unsigned long test_override_haptic_until_ms = 0;   // prueba manual (GUI / diagnóstico)
uint8_t test_haptic_duty = 0;
unsigned long host_haptic_until_ms = 0;            // streaming del simulador (Godot)
uint8_t host_haptic_duty = 0;
unsigned long host_armed_until_ms = 0;             // Godot con un arco en curso (ejercicio de soldadura)
unsigned long haptic_mute_until_ms = 0;            // silencio pedido (calibraciones)
uint8_t motor_out = 0;                             // duty que realmente sale por el pin (telemetría "h")
bool motor_pwm_ok = false;

void set_rgb(uint8_t r, uint8_t g, uint8_t b) {
    ledcWrite(PIN_RGB_R, r);
    ledcWrite(PIN_RGB_G, g);
    ledcWrite(PIN_RGB_B, b);
}

void set_motor_duty(uint8_t duty) {
    motor_out = duty;
    if (!ledcWrite(PIN_HAPTIC, duty)) {
        motor_pwm_ok = false;
    }
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

// Duty que pide la FSM propia del firmware para el estado actual
uint8_t local_haptic_duty(SystemState state) {
    unsigned long now = millis();
    unsigned long elapsed = now - state_enter_ms;
    switch (state) {
        case STATE_HOMING:
            return (elapsed <= 120) ? g_cfg.duty_homing : 0;
        case STATE_WELD_OK:
            return g_cfg.duty_weld_ok;
        case STATE_WELD_WARN:
            if (now - haptic_pattern_ms > (haptic_toggle ? 120 : 90)) {
                haptic_pattern_ms = now;
                haptic_toggle = !haptic_toggle;
            }
            return haptic_toggle ? g_cfg.duty_weld_warn : 0;
        case STATE_STICKING:
            return g_cfg.duty_sticking;
        default:
            return 0;
    }
}

// Prioridad del motor:
//   1. Prueba manual (GUI / diagnóstico) mientras dure.
//   2. Electrodo pegado detectado por el propio firmware (pulsador o ToF): siempre vibra, aunque
//      Godot no mande nada o mande 0 (así funcionaba antes y no depende de la PC).
//   3. Simulador (Godot) mientras siga mandando SET_HAPTIC.
//   4. FSM propia del firmware (sin Godot abierto).
void apply_motor() {
    unsigned long now = millis();
    uint8_t duty;
    if (now < test_override_haptic_until_ms) {
        duty = test_haptic_duty;                       // prueba manual (GUI / diagnóstico)
    } else if (now < haptic_mute_until_ms) {
        duty = 0;                                      // calibración en curso: motor quieto
    } else if (now < host_armed_until_ms) {
        // Soldando en Godot con el arco encendido: manda Godot y, si el firmware detecta el
        // electrodo pegado (pulsador o ToF), vibra al máximo sin esperar a la PC.
        duty = (current_state == STATE_STICKING) ? max(g_cfg.duty_sticking, host_haptic_duty) : host_haptic_duty;
    } else if (now < host_haptic_until_ms) {
        duty = host_haptic_duty;                       // Godot abierto pero sin arco (normalmente 0)
    } else {
        // Sin simulación activa (calibración de pivote, menú, Godot cerrado): el motor no vibra.
        // Antes la FSM local vibraba al apoyar la punta (pulsador = "pegado") y molestaba al calibrar.
        duty = 0;
    }
    if (duty != motor_out) set_motor_duty(duty);
}

void apply_actuators_for_state(SystemState state) {
    unsigned long now = millis();
    if (now >= test_override_led_until_ms) {
        apply_led_for_state(state);
    }
    apply_motor();
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
    // La vibración del motor arruina el promedio del giroscopio: apagarlo antes de medir.
    set_motor_duty(0);
    delay(150);
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
    haptic_mute_until_ms = millis() + 1000;
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
    // Si la sesión no está activa (aún no se hizo homing inicial), permanecemos en IDLE,
    // salvo que el homing esté desactivado: entonces el arco arranca solo al acercar la punta.
    if (!session_active) {
        if (!g_cfg.homing_required && tof_online &&
            current_distance_mm > g_cfg.stick_gap_mm && current_distance_mm <= g_cfg.reignite_gap_mm) {
            session_active = true;
            arc_active = true;
            set_state(STATE_HOMING);   // pulso corto de "cebado" y pasa a soldadura
        } else {
            set_state(STATE_IDLE);
        }
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
    Serial.printf("{\"qw\":%.4f,\"qx\":%.4f,\"qy\":%.4f,\"qz\":%.4f,\"d\":%.1f,\"b\":%d,\"r\":%.1f,\"p\":%.1f,\"y\":%.1f,\"st\":%d,\"dlpf\":%d,\"h\":%d}\n",
                  qw, qx, qy, qz, current_distance_mm, button_state_telemetry, roll, pitch, yaw, current_state, dlpf_mode, motor_out);
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
// Devuelve el texto del objeto JSON que sigue a `key` ("{...}", con llaves balanceadas) o "".
// Sirve para buscar "homing" dentro de "haptic_intensity_pct" y no dentro de "led_colors",
// que también tiene una clave "homing".
static String extract_section(const String& s, const char* key) {
    int idx = s.indexOf(key);
    if (idx < 0) return String("");
    int start = s.indexOf('{', idx);
    if (start < 0) return String("");
    int depth = 0;
    for (int i = start; i < (int)s.length(); i++) {
        char c = s[i];
        if (c == '{') depth++;
        else if (c == '}') {
            depth--;
            if (depth == 0) return s.substring(start, i + 1);
        }
    }
    return String("");
}

static String extract_cmd(const String& s) {
    int idx = s.indexOf("\"cmd\"");
    if (idx < 0) return String("");
    int colon = s.indexOf(':', idx);
    int q1 = s.indexOf('"', colon + 1);
    int q2 = s.indexOf('"', q1 + 1);
    if (colon < 0 || q1 < 0 || q2 < 0) return String("");
    return s.substring(q1 + 1, q2);
}

static bool extract_bool(const String& s, const char* key, bool def_val) {
    int idx = s.indexOf(key);
    if (idx < 0) return def_val;
    int colon = s.indexOf(':', idx);
    if (colon < 0) return def_val;
    String v = s.substring(colon + 1, colon + 8);
    v.trim();
    if (v.startsWith("true") || v.startsWith("1")) return true;
    if (v.startsWith("false") || v.startsWith("0")) return false;
    return def_val;
}

// Ventana durante la cual manda el simulador (Godot reenvía cada <= 250 ms). Si Godot deja de
// enviar, a los 500 ms el firmware vuelve a manejar el LED y el motor con su propia FSM.
#define HOST_CONTROL_WINDOW_MS 500

static void apply_config(const String& line) {
    String led = extract_section(line, "\"led_colors\"");
    if (led.length() > 0) {
        extract_rgb(led, "\"idle\"", g_cfg.idle_r, g_cfg.idle_g, g_cfg.idle_b);
        extract_rgb(led, "\"homing\"", g_cfg.homing_r, g_cfg.homing_g, g_cfg.homing_b);
        extract_rgb(led, "\"weld_optimal\"", g_cfg.weld_ok_r, g_cfg.weld_ok_g, g_cfg.weld_ok_b);
        extract_rgb(led, "\"weld_caution\"", g_cfg.weld_caution_r, g_cfg.weld_caution_g, g_cfg.weld_caution_b);
        extract_rgb(led, "\"weld_warning\"", g_cfg.weld_warn_r, g_cfg.weld_warn_g, g_cfg.weld_warn_b);
        extract_rgb(led, "\"sticking\"", g_cfg.sticking_r, g_cfg.sticking_g, g_cfg.sticking_b);
    }

    String tof = extract_section(line, "\"tof_limits_mm\"");
    if (tof.length() > 0) {
        g_cfg.stick_gap_mm = extract_float(tof, "\"stick_gap\"", g_cfg.stick_gap_mm);
        g_cfg.extinguish_gap_mm = extract_float(tof, "\"extinguish_gap\"", g_cfg.extinguish_gap_mm);
        g_cfg.reignite_gap_mm = extract_float(tof, "\"reignite_gap\"", g_cfg.reignite_gap_mm);
        g_cfg.opt_min_gap_mm = extract_float(tof, "\"optimal_min\"", g_cfg.opt_min_gap_mm);
        g_cfg.opt_max_gap_mm = extract_float(tof, "\"optimal_max\"", g_cfg.opt_max_gap_mm);
    }

    // Antes se buscaba "homing", "sticking"... en TODO el mensaje y se encontraba primero la
    // clave de led_colors ("[0, 50, 255]" -> toInt() = 0): todas las intensidades quedaban en 0
    // y el motor nunca vibraba. Ahora se busca solo dentro de "haptic_intensity_pct".
    String hap = extract_section(line, "\"haptic_intensity_pct\"");
    if (hap.length() > 0) {
        int v;
        v = extract_int(hap, "\"homing\"", -1);       if (v >= 0) g_cfg.duty_homing = (uint8_t)(constrain(v, 0, 100) * 2.55f);
        v = extract_int(hap, "\"weld_optimal\"", -1); if (v >= 0) g_cfg.duty_weld_ok = (uint8_t)(constrain(v, 0, 100) * 2.55f);
        v = extract_int(hap, "\"weld_warning\"", -1); if (v >= 0) g_cfg.duty_weld_warn = (uint8_t)(constrain(v, 0, 100) * 2.55f);
        v = extract_int(hap, "\"sticking\"", -1);     if (v >= 0) g_cfg.duty_sticking = (uint8_t)(constrain(v, 0, 100) * 2.55f);
    }

    if (line.indexOf("\"homing_required\"") >= 0) {
        g_cfg.homing_required = extract_bool(line, "\"homing_required\"", g_cfg.homing_required);
    }

    Serial.printf("{\"ack\":\"CONFIG_APPLIED\",\"duty\":[%d,%d,%d,%d],\"homing_required\":%d}\n",
                  g_cfg.duty_homing, g_cfg.duty_weld_ok, g_cfg.duty_weld_warn, g_cfg.duty_sticking,
                  g_cfg.homing_required ? 1 : 0);
}

static void handle_command_line(String line) {
    line.trim();
    if (line.length() == 0) return;
    String cmd = extract_cmd(line);
    unsigned long now = millis();

    // Comandos de una letra desde un monitor serie
    if (cmd.length() == 0) {
        if (line == "c" || line == "C" || line == "CALIBRATE") { calibrate_gyro(); return; }
        if (line == "t" || line == "T" || line == "RESET_YAW") { yaw = 0.0f; return; }
        if (line.length() == 1 && line[0] >= '0' && line[0] <= '6') { set_dlpf(line[0] - '0'); return; }
        return;
    }

    if (cmd == "CALIBRATE") {
        calibrate_gyro();
    } else if (cmd == "RESET_YAW") {
        yaw = 0.0f;
    } else if (cmd == "PING") {
        Serial.printf("{\"ack\":\"PONG\",\"fw\":\"%s\",\"pwm_ok\":%d,\"h\":%d,\"duty\":[%d,%d,%d,%d],\"st\":%d,\"session\":%d,\"homing_required\":%d}\n",
                      FIRMWARE_VERSION, motor_pwm_ok ? 1 : 0, motor_out, g_cfg.duty_homing, g_cfg.duty_weld_ok,
                      g_cfg.duty_weld_warn, g_cfg.duty_sticking, current_state, session_active ? 1 : 0,
                      g_cfg.homing_required ? 1 : 0);
    } else if (cmd == "TEST_ACTUATOR") {
        uint8_t r = (uint8_t)constrain(extract_int(line, "\"r\"", 0), 0, 255);
        uint8_t g = (uint8_t)constrain(extract_int(line, "\"g\"", 0), 0, 255);
        uint8_t b = (uint8_t)constrain(extract_int(line, "\"b\"", 0), 0, 255);
        int ms = extract_int(line, "\"ms\"", 2500);
        set_rgb(r, g, b);
        test_override_led_until_ms = now + ms;
        Serial.printf("{\"ack\":\"TEST_ACTUATOR\",\"r\":%d,\"g\":%d,\"b\":%d,\"ms\":%d}\n", r, g, b, ms);
    } else if (cmd == "SET_LED") {
        // Color decidido por el simulador según las tolerancias del nivel (verde/amarillo/rojo)
        uint8_t r = (uint8_t)constrain(extract_int(line, "\"r\"", 0), 0, 255);
        uint8_t g = (uint8_t)constrain(extract_int(line, "\"g\"", 0), 0, 255);
        uint8_t b = (uint8_t)constrain(extract_int(line, "\"b\"", 0), 0, 255);
        set_rgb(r, g, b);
        test_override_led_until_ms = now + HOST_CONTROL_WINDOW_MS;
    } else if (cmd == "SET_HAPTIC") {
        int duty = constrain(extract_int(line, "\"val\"", 0), 0, 255);
        int ms = extract_int(line, "\"ms\"", 0);
        if (ms > 0) {
            // Prueba manual desde la GUI / diagnóstico
            test_haptic_duty = (uint8_t)duty;
            test_override_haptic_until_ms = now + ms;
            set_motor_duty((uint8_t)duty);
            Serial.printf("{\"ack\":\"SET_HAPTIC\",\"val\":%d,\"ms\":%d,\"pwm_ok\":%d}\n", duty, ms, motor_pwm_ok ? 1 : 0);
        } else {
            // Streaming desde Godot (no depende de que el firmware haya visto el homing)
            host_haptic_duty = (uint8_t)duty;
            host_haptic_until_ms = now + HOST_CONTROL_WINDOW_MS;
            if (extract_int(line, "\"arm\"", 0) == 1) {
                host_armed_until_ms = now + HOST_CONTROL_WINDOW_MS;   // hay un arco en curso
            } else {
                host_armed_until_ms = 0;
            }
        }
    } else if (cmd == "HAPTIC_MUTE") {
        int ms = constrain(extract_int(line, "\"ms\"", 1000), 0, 30000);
        haptic_mute_until_ms = now + ms;
        set_motor_duty(0);
    } else if (cmd == "SET_HOMING") {
        g_cfg.homing_required = extract_bool(line, "\"enabled\"", g_cfg.homing_required);
        Serial.printf("{\"ack\":\"SET_HOMING\",\"homing_required\":%d}\n", g_cfg.homing_required ? 1 : 0);
    } else if (cmd == "RESET" || cmd == "END_SESSION") {
        session_active = false;
        arc_active = false;
        test_override_haptic_until_ms = 0;
        host_haptic_until_ms = 0;
        set_motor_duty(0);
        set_state(STATE_IDLE);
        Serial.println("{\"ack\":\"SESSION_RESET\"}");
    } else if (cmd == "CONFIG") {
        apply_config(line);
    }
}

void handle_serial_commands() {
    // Procesa todas las líneas pendientes (Godot puede mandar LED + motor en el mismo ciclo)
    for (int n = 0; n < 8 && Serial.available(); n++) {
        String line = Serial.readStringUntil('\n');
        handle_command_line(line);
    }
}

// ==============================================================================
// SETUP
// ==============================================================================
void setup() {
    Serial.setRxBufferSize(2048);   // el comando CONFIG mide ~700 bytes (el buffer por defecto es 256)
    Serial.begin(115200);
    Serial.setTimeout(20);

    // Pines de salida
    pinMode(PIN_STATUS_LED, OUTPUT);
    digitalWrite(PIN_STATUS_LED, LOW);

    // Pin de entrada del pulsador con Pull-Up interno
    pinMode(PIN_BUTTON, INPUT_PULLUP);

    // PWM con canales fijos: los canales LEDC comparten timer de a pares (0-1, 2-3, 4-5...).
    // El LED usa los canales 0, 1 y 2 (5 kHz) y el motor el 4, con un timer propio a 1 kHz,
    // para que una frecuencia no le pise la otra.
    ledcAttachChannel(PIN_RGB_R, PWM_RGB_FREQ, PWM_RGB_RES, 0);
    ledcAttachChannel(PIN_RGB_G, PWM_RGB_FREQ, PWM_RGB_RES, 1);
    ledcAttachChannel(PIN_RGB_B, PWM_RGB_FREQ, PWM_RGB_RES, 2);
    motor_pwm_ok = ledcAttachChannel(PIN_HAPTIC, PWM_HAPTIC_FREQ, PWM_HAPTIC_RES, 4);
    if (!motor_pwm_ok) {
        // Respaldo: asignación automática de canal (como el firmware que funcionaba)
        motor_pwm_ok = ledcAttach(PIN_HAPTIC, PWM_HAPTIC_FREQ, PWM_HAPTIC_RES);
    }
    set_motor_duty(0);

    // Test de bienvenida RGB y háptico rápido
    set_rgb(255, 0, 0); delay(150);
    set_rgb(0, 255, 0); delay(150);
    set_rgb(0, 0, 255); delay(150);
    set_rgb(0, 0, 0);

    // Prueba de motor al encender: 100 % durante 300 ms (se tiene que sentir; si no se siente,
    // el problema es de hardware: MOSFET, diodo, alimentación de 5 V o cableado).
    set_motor_duty(220); delay(250);
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
    host_haptic_until_ms = 0;
    set_motor_duty(0);
    set_state(STATE_IDLE);
    last_telemetry_ms = millis();
    Serial.printf("{\"ack\":\"BOOT\",\"fw\":\"%s\",\"pwm_ok\":%d}\n", FIRMWARE_VERSION, motor_pwm_ok ? 1 : 0);
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
