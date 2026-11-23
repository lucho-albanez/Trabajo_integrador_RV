/**
 * @file main.cpp
 * @brief Laboratorio y Control del Módulo LED RGB (HW-479)
 * @project ArcSim_VR
 *
 * Módulo HW-479 (Cátodo Común):
 *   - Pin (-) -> GND de la ESP32
 *   - Pin (R) -> Pin D16 (GPIO 16)
 *   - Pin (G) -> Pin D17 (GPIO 17)
 *   - Pin (B) -> Pin D19 (GPIO 19)
 *
 * Implementa la Máquina de Estados de iluminación para ArcSim VR:
 *   [1] ESTADO INACTIVO / ESPERA   -> Naranja cálido continuo
 *   [2] SOLDADURA ÓPTIMA           -> Verde puro continuo
 *   [3] ADVERTENCIA DE TÉCNICA     -> Rojo sólido continuo
 *   [4] HOMING / CALIBRACIÓN       -> Azul continuo
 *   [5] ERROR CRÍTICO DEL SISTEMA  -> Rojo parpadeando a 1 Hz (500 ms ON / 500 ms OFF)
 *   [A] AUTO-DEMO                  -> Cicla los estados automáticamente
 */

#include <Arduino.h>

// ==============================================================================
// ASIGNACIÓN DE PINES (ESP32)
// ==============================================================================
#define PIN_RGB_R    16
#define PIN_RGB_G    17
#define PIN_RGB_B    19

// Frecuencia y resolución PWM (Hardware LEDC ESP32 Core 3.x)
#define PWM_FREQ     5000 // 5 kHz (mezcla de color 100% pura y sin parpadeo)
#define PWM_RES      8    // 8 bits de resolución (valores de 0 a 255)

// ==============================================================================
// DEFINICIÓN DE ESTADOS DEL SISTEMA
// ==============================================================================
enum SystemState {
    STATE_IDLE,       // Inactivo / Standby (Naranja)
    STATE_WELD_OK,    // Soldadura óptima (Verde)
    STATE_WELD_WARN,  // Error de técnica: distancia/ángulo (Rojo)
    STATE_HOMING,     // Homing / Cebado inicial (Azul)
    STATE_ERROR       // Falla crítica de sensor o enlace (Rojo 1 Hz)
};

SystemState current_state = STATE_IDLE;
bool auto_demo_mode = false;
unsigned long last_demo_switch_ms = 0;
unsigned long last_blink_ms = 0;
bool blink_toggle = false;

// ==============================================================================
// CONTROL DE COLOR RGB
// ==============================================================================
// El módulo HW-479 es Cátodo Común: 255 es brillo máximo, 0 es apagado
void set_rgb(uint8_t r, uint8_t g, uint8_t b) {
    ledcWrite(PIN_RGB_R, r);
    ledcWrite(PIN_RGB_G, g);
    ledcWrite(PIN_RGB_B, b);
}

void apply_state_color(SystemState state) {
    switch (state) {
        case STATE_IDLE:
            // Naranja cálido: El ojo humano es muy sensible al verde,
            // por lo que R=255 y G=40 logran un naranja puro de soldador.
            set_rgb(255, 40, 0);
            break;

        case STATE_WELD_OK:
            // Verde intenso (técnica de arco correcta)
            set_rgb(0, 255, 0);
            break;

        case STATE_WELD_WARN:
            // Rojo sólido (advertencia: arco alargado, mal ángulo o velocidad)
            set_rgb(255, 0, 0);
            break;

        case STATE_HOMING:
            // Azul brillante (contacto de la punta / calibración inicial)
            set_rgb(0, 50, 255);
            break;

        case STATE_ERROR:
            // Parpadeo a 1 Hz gestionado en loop()
            break;
    }
}

void print_menu() {
    Serial.println("\n=======================================================");
    Serial.println("  ArcSim_VR - Control de Estados LED RGB (HW-479)");
    Serial.println("=======================================================");
    Serial.println("Presiona una tecla en la consola y da Enter:");
    Serial.println("  '1' : Estado INACTIVO      -> LED Naranja (Standby / Tracking)");
    Serial.println("  '2' : SOLDADURA ÓPTIMA     -> LED Verde (Técnica perfecta)");
    Serial.println("  '3' : ADVERTENCIA TÉCNICA  -> LED Rojo sólido (Mala postura/distancia)");
    Serial.println("  '4' : HOMING / CEBADO      -> LED Azul (Punta toca la pieza)");
    Serial.println("  '5' : ERROR DEL SISTEMA    -> LED Rojo parpadeando a 1 Hz");
    Serial.println("  'a' : Activar / Pausar Modo AUTO-DEMO (simula una soldadura)");
    Serial.println("=======================================================\n");
}

void set_system_state(SystemState new_state) {
    current_state = new_state;
    blink_toggle = true;
    last_blink_ms = millis();
    apply_state_color(current_state);

    const char* nombres[] = {
        "[INACTIVO] -> Naranja (Listo para soldar / Standby)",
        "[SOLDADURA OPTIMA] -> Verde (Arco estable, distancia y ángulo correctos)",
        "[ADVERTENCIA] -> Rojo solido (Error de tecnica del alumno)",
        "[HOMING / CEBADO] -> Azul (Contacto fisico inicial)",
        "[ERROR CRITICO] -> Rojo parpadeando a 1 Hz"
    };
    Serial.printf(">>> Estado cambiado a: %s\n", nombres[current_state]);
}

// ==============================================================================
// SETUP
// ==============================================================================
void setup() {
    Serial.begin(115200);

    // Configurar canales PWM con el nuevo motor LEDC de Arduino Core 3.x
    ledcAttach(PIN_RGB_R, PWM_FREQ, PWM_RES);
    ledcAttach(PIN_RGB_G, PWM_FREQ, PWM_RES);
    ledcAttach(PIN_RGB_B, PWM_FREQ, PWM_RES);

    // Test de inicio rápido: R -> G -> B para confirmar conexiones
    set_rgb(255, 0, 0); delay(250);
    set_rgb(0, 255, 0); delay(250);
    set_rgb(0, 0, 255); delay(250);

    // Arrancamos en Estado Inactivo (Naranja)
    set_system_state(STATE_IDLE);

    print_menu();
}

// ==============================================================================
// LOOP PRINCIPAL
// ==============================================================================
void loop() {
    // 1. Escuchar comandos serie del usuario
    if (Serial.available()) {
        char cmd = Serial.read();
        auto_demo_mode = false; // Desactivar demo si el usuario toma el control manual

        if (cmd == '1') set_system_state(STATE_IDLE);
        else if (cmd == '2') set_system_state(STATE_WELD_OK);
        else if (cmd == '3') set_system_state(STATE_WELD_WARN);
        else if (cmd == '4') set_system_state(STATE_HOMING);
        else if (cmd == '5') set_system_state(STATE_ERROR);
        else if (cmd == 'a' || cmd == 'A') {
            auto_demo_mode = !auto_demo_mode;
            Serial.printf(">>> Modo AUTO-DEMO: %s\n", auto_demo_mode ? "ACTIVADO" : "PAUSADO");
            last_demo_switch_ms = millis();
        }
    }

    // 2. Gestión del parpadeo a 1 Hz en caso de ESTADO_ERROR (500 ms ON / 500 ms OFF)
    if (current_state == STATE_ERROR) {
        unsigned long now = millis();
        if (now - last_blink_ms >= 500) {
            last_blink_ms = now;
            blink_toggle = !blink_toggle;
            if (blink_toggle) {
                set_rgb(255, 0, 0); // Rojo encendido
            } else {
                set_rgb(0, 0, 0);   // Apagado
            }
        }
    }

    // 3. Modo Auto-Demo (muestra la secuencia típica de una soldadura real)
    if (auto_demo_mode) {
        unsigned long now = millis();
        if (now - last_demo_switch_ms >= 3000) { // cambia cada 3 segundos
            last_demo_switch_ms = now;
            if (current_state == STATE_IDLE) set_system_state(STATE_HOMING);
            else if (current_state == STATE_HOMING) set_system_state(STATE_WELD_OK);
            else if (current_state == STATE_WELD_OK) set_system_state(STATE_WELD_WARN);
            else if (current_state == STATE_WELD_WARN) set_system_state(STATE_ERROR);
            else set_system_state(STATE_IDLE);
        }
    }

    delay(10);
}
