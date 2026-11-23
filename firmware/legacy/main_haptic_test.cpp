/**
 * @file main.cpp
 * @brief Laboratorio de Pruebas del Motor de Vibración Háptico (MOSFET IRFZ44N)
 * @project ArcSim_VR - Simulador de Soldadura SMAW
 *
 * Conexión del actuador háptico (GPIO 25):
 *   - Pin D25 de la ESP32 -> Resistencia de 1k -> Gate (Pata 1 del IRFZ44N)
 *   - Resistencia de 10k entre Gate (Pata 1) y GND (Pull-Down)
 *   - Cable NEGRO del motor -> Drain (Pata 2 / Centro del IRFZ44N)
 *   - Pata 3 (Source del IRFZ44N) -> GND de la ESP32
 *   - Cable ROJO del motor -> Pin VIN de la ESP32 (+5V de USB)
 *
 * Modos de vibración para la simulación:
 *   [0] APAGADO           -> Motor en reposo
 *   [1] CEBADO (STRIKE)   -> Pulso seco de impacto (60 ms al 80%)
 *   [2] ARCO ÓPTIMO       -> Zumbido sutil y parejo (~30% de potencia)
 *   [3] ARCO LARGO        -> Pulsos intermitentes de advertencia
 *   [4] ELECTRODO PEGADO  -> Vibración violenta y continua (100% de potencia)
 *   [5] RAMPA DE POTENCIA -> Barrido suave de 0% a 100% para calibrar inercia
 *   [A] AUTO-DEMO         -> Secuencia realista completa de soldadura
 */

#include <Arduino.h>

// ==============================================================================
// CONFIGURACIÓN DE PINES Y PWM
// ==============================================================================
#define PIN_HAPTIC       25    // Pin D25 de la ESP32 (GPIO 25)
#define HAPTIC_PWM_FREQ  1000  // 1 kHz (frecuencia ideal para motores DC de vibración)
#define HAPTIC_PWM_RES   8     // Resolución de 8 bits (valores de 0 a 255)

// Modos hápticos disponibles
enum HapticMode {
    HAPTIC_OFF,
    HAPTIC_TOUCH_STRIKE,  // Contacto inicial / raspado del electrodo
    HAPTIC_OPTIMAL_ARC,   // Arco estable ardiendo (zumbido continuo suave)
    HAPTIC_LONG_ARC,      // Arco alargado (advertencia pulsante)
    HAPTIC_STICKING,      // Electrodo pegado a la chapa (cortocircuito violento)
    HAPTIC_RAMP_TEST      // Prueba de calibración de inercia
};

HapticMode current_mode = HAPTIC_OFF;
uint8_t current_duty = 0;

// Variables de temporización no bloqueante
unsigned long mode_start_ms = 0;
unsigned long last_pattern_ms = 0;
bool pattern_toggle = false;

// Variables para el modo Auto-Demo
bool auto_demo_mode = false;
unsigned long last_demo_switch_ms = 0;

// ==============================================================================
// FUNCIONES DE CONTROL PWM
// ==============================================================================
void set_motor_duty(uint8_t duty) {
    current_duty = duty;
    ledcWrite(PIN_HAPTIC, duty);
}

void print_menu() {
    Serial.println("\n============================================================");
    Serial.println("  ArcSim_VR - Laboratorio de Feedback Háptico (IRFZ44N)");
    Serial.println("============================================================");
    Serial.println("Escribe el comando en la consola y presiona Enter:");
    Serial.println("  '0' : APAGAR motor");
    Serial.println("  '1' : Golpe de CEBADO / RASPADO (Impacto seco de 60 ms)");
    Serial.println("  '2' : ARCO ÓPTIMO (Zumbido parejo y suave ~30%)");
    Serial.println("  '3' : ARCO LARGO (Pulsos intermitentes de advertencia)");
    Serial.println("  '4' : ELECTRODO PEGADO (Vibración violenta al 100%)");
    Serial.println("  '5' : RAMPA SUAVE (Sube de 0% a 100% para ver sensibilidad)");
    Serial.println("  'a' : Activar / Pausar AUTO-DEMO de soldadura");
    Serial.println("============================================================\n");
}

void set_haptic_mode(HapticMode mode) {
    current_mode = mode;
    mode_start_ms = millis();
    last_pattern_ms = millis();
    pattern_toggle = false;

    switch (current_mode) {
        case HAPTIC_OFF:
            set_motor_duty(0);
            Serial.println(">>> Modo: [APAGADO] (0% PWM)");
            break;

        case HAPTIC_TOUCH_STRIKE:
            // Pulso seco inicial al 80%
            set_motor_duty(200);
            Serial.println(">>> Modo: [CEBADO / STRIKE] - Golpe seco inicial");
            break;

        case HAPTIC_OPTIMAL_ARC:
            // ~30% de potencia: zumbido suave que simula el flujo de plasma
            set_motor_duty(75);
            Serial.println(">>> Modo: [ARCO ÓPTIMO] - Zumbido suave y continuo (30%)");
            break;

        case HAPTIC_LONG_ARC:
            // Comienza encendido para el patrón intermitente
            set_motor_duty(120);
            pattern_toggle = true;
            Serial.println(">>> Modo: [ARCO LARGO] - Pulsos intermitentes de aviso");
            break;

        case HAPTIC_STICKING:
            // 100% de potencia: sacudida violenta que avisa al alumno que se pegó la varilla
            set_motor_duty(255);
            Serial.println(">>> Modo: [ELECTRODO PEGADO] - Cortocircuito al 100%!");
            break;

        case HAPTIC_RAMP_TEST:
            set_motor_duty(0);
            Serial.println(">>> Modo: [RAMPA DE CALIBRACIÓN] - Incrementando de 0 a 255...");
            break;
    }
}

// ==============================================================================
// SETUP
// ==============================================================================
void setup() {
    Serial.begin(115200);

    // Configurar canal PWM en GPIO 25 (ESP32 Arduino Core 3.x)
    ledcAttach(PIN_HAPTIC, HAPTIC_PWM_FREQ, HAPTIC_PWM_RES);
    set_motor_duty(0);

    // Test de bienvenida: 2 pulsos cortos para confirmar que el motor responde
    set_motor_duty(180); delay(80);
    set_motor_duty(0);   delay(80);
    set_motor_duty(180); delay(80);
    set_motor_duty(0);

    print_menu();
}

// ==============================================================================
// LOOP PRINCIPAL
// ==============================================================================
void loop() {
    // 1. Escuchar comandos por monitor serie
    if (Serial.available()) {
        char cmd = Serial.read();
        auto_demo_mode = false; // El comando manual desactiva el demo

        if (cmd == '0') set_haptic_mode(HAPTIC_OFF);
        else if (cmd == '1') set_haptic_mode(HAPTIC_TOUCH_STRIKE);
        else if (cmd == '2') set_haptic_mode(HAPTIC_OPTIMAL_ARC);
        else if (cmd == '3') set_haptic_mode(HAPTIC_LONG_ARC);
        else if (cmd == '4') set_haptic_mode(HAPTIC_STICKING);
        else if (cmd == '5') set_haptic_mode(HAPTIC_RAMP_TEST);
        else if (cmd == 'a' || cmd == 'A') {
            auto_demo_mode = !auto_demo_mode;
            Serial.printf(">>> Modo AUTO-DEMO: %s\n", auto_demo_mode ? "ACTIVADO" : "PAUSADO");
            last_demo_switch_ms = millis();
            if (auto_demo_mode) set_haptic_mode(HAPTIC_TOUCH_STRIKE);
        }
    }

    unsigned long now = millis();

    // 2. Gestión de patrones temporizados
    switch (current_mode) {
        case HAPTIC_TOUCH_STRIKE:
            // El golpe de raspado dura exactamente 70 ms y se apaga solo
            if (now - mode_start_ms > 70) {
                set_haptic_mode(HAPTIC_OFF);
            }
            break;

        case HAPTIC_LONG_ARC:
            // Patrón pulsante: 120 ms ON, 90 ms OFF
            if (pattern_toggle && (now - last_pattern_ms > 120)) {
                set_motor_duty(0);
                pattern_toggle = false;
                last_pattern_ms = now;
            } else if (!pattern_toggle && (now - last_pattern_ms > 90)) {
                set_motor_duty(120);
                pattern_toggle = true;
                last_pattern_ms = now;
            }
            break;

        case HAPTIC_RAMP_TEST:
            // Incrementa el ciclo de trabajo de 0 a 255 en 5 segundos
            {
                unsigned long elapsed = now - mode_start_ms;
                if (elapsed <= 5000) {
                    uint8_t ramp_duty = (elapsed * 255) / 5000;
                    set_motor_duty(ramp_duty);
                    static unsigned long last_print = 0;
                    if (now - last_print > 400) {
                        last_print = now;
                        Serial.printf("  Potencia actual: %3d / 255  (%2d %%)\n", 
                                      ramp_duty, (ramp_duty * 100) / 255);
                    }
                } else {
                    Serial.println(">>> Rampa finalizada. Motor apagado.");
                    set_haptic_mode(HAPTIC_OFF);
                }
            }
            break;

        default:
            break;
    }

    // 3. Gestión del modo Auto-Demo (recorre el ciclo típico de soldar)
    if (auto_demo_mode) {
        if (current_mode == HAPTIC_OFF && (now - last_demo_switch_ms > 2000)) {
            last_demo_switch_ms = now;
            set_haptic_mode(HAPTIC_TOUCH_STRIKE); // 1. Raspado
        } else if (current_mode == HAPTIC_OFF && (now - mode_start_ms > 100) && (now - last_demo_switch_ms > 500)) {
            // Luego del strike, pasa a arco estable
            set_haptic_mode(HAPTIC_OPTIMAL_ARC);
            last_demo_switch_ms = now;
        } else if (current_mode == HAPTIC_OPTIMAL_ARC && (now - last_demo_switch_ms > 3500)) {
            // El usuario aleja mucho la herramienta
            set_haptic_mode(HAPTIC_LONG_ARC);
            last_demo_switch_ms = now;
        } else if (current_mode == HAPTIC_LONG_ARC && (now - last_demo_switch_ms > 3000)) {
            // El usuario baja demasiado y se pega el electrodo
            set_haptic_mode(HAPTIC_STICKING);
            last_demo_switch_ms = now;
        } else if (current_mode == HAPTIC_STICKING && (now - last_demo_switch_ms > 2500)) {
            // Despega el electrodo y vuelve a reposo
            set_haptic_mode(HAPTIC_OFF);
            last_demo_switch_ms = now;
        }
    }

    delay(10);
}
