/**
 * @file main.cpp
 * @brief Laboratorio de Pruebas del Pulsador de Contacto / Homing / Cebado
 * @project ArcSim_VR - Simulador de Soldadura SMAW
 *
 * Conexión del Pulsador (Pin D4):
 *   - Un terminal del pulsador -> Pin D4 (GPIO 4) de la ESP32
 *   - El otro terminal del pulsador -> Pin GND de la ESP32
 *   *(¡No se necesita ninguna resistencia externa! Usamos la resistencia PULL-UP interna de la ESP32)*
 *
 * Funcionalidad probada:
 *   1. Detección digital limpia con Filtro Antirrebote (Debounce de 25 ms).
 *   2. Detección de flancos: Toque inicial (Strike / Cebado) y Separación.
 *   3. Medición precisa del tiempo de contacto (en milisegundos).
 *   4. Distinción de eventos:
 *      - Toque rápido (< 500 ms): "Strike" / Raspado de cebado / Homing de contacto.
 *      - Mantener presionado (> 2000 ms): Función Tara / Reset de orientación a cero.
 */

#include <Arduino.h>

// ==============================================================================
// CONFIGURACIÓN DE PINES
// ==============================================================================
#define PIN_BUTTON       4    // Pin D4 (GPIO 4) con INPUT_PULLUP
#define PIN_STATUS_LED   2    // LED azul integrado en la placa ESP32 (testeo visual)

// Parámetros de Antirrebote (Debounce)
#define DEBOUNCE_DELAY_MS 25  // 25 ms de inmunidad a rebotes mecánicos

// Variables de estado del pulsador
bool last_stable_state = HIGH;      // En reposo con PULLUP está en HIGH (3.3V)
bool last_reading = HIGH;
unsigned long last_debounce_time = 0;
unsigned long press_start_time = 0;
unsigned int touch_counter = 0;
bool long_press_triggered = false;

// ==============================================================================
// SETUP
// ==============================================================================
void setup() {
    Serial.begin(115200);

    // Configurar el pin con la resistencia PULL-UP interna de la ESP32
    pinMode(PIN_BUTTON, INPUT_PULLUP);
    pinMode(PIN_STATUS_LED, OUTPUT);
    digitalWrite(PIN_STATUS_LED, LOW);

    Serial.println("\n============================================================");
    Serial.println("  ArcSim_VR - Laboratorio de Pulsador de Contacto / Homing");
    Serial.println("============================================================");
    Serial.println("Conexión:");
    Serial.println("  - Terminal 1 del pulsador -> Pin D4 (GPIO 4)");
    Serial.println("  - Terminal 2 del pulsador -> Pin GND");
    Serial.println("------------------------------------------------------------");
    Serial.println("Esperando contacto físico...");
    Serial.println("  * Toca la punta contra la chapa para simular el cebado.");
    Serial.println("  * Mantén presionado 2 segundos para simular TARA / Reset.");
    Serial.println("============================================================\n");
}

// ==============================================================================
// LOOP PRINCIPAL
// ==============================================================================
void loop() {
    int raw_reading = digitalRead(PIN_BUTTON);

    // 1. Filtro de rebotes por software
    if (raw_reading != last_reading) {
        last_debounce_time = millis();
    }

    if ((millis() - last_debounce_time) > DEBOUNCE_DELAY_MS) {
        // La lectura ha sido estable por más de DEBOUNCE_DELAY_MS
        if (raw_reading != last_stable_state) {
            last_stable_state = raw_reading;

            // FLANCO DE BAJADA: Pulsador presionado (Contacto físico con la pieza)
            if (last_stable_state == LOW) {
                press_start_time = millis();
                touch_counter++;
                long_press_triggered = false;
                digitalWrite(PIN_STATUS_LED, HIGH); // Enciende el LED azul de la ESP32

                Serial.printf("\n[CONTACTO #%u DETECTADO] -> La punta toco la probeta!\n", touch_counter);
                Serial.println("  >>> Estado de simulacion: HOMING / CEBADO DE ARCO INICIADO <<<");
            }
            // FLANCO DE SUBIDA: Pulsador liberado (El electrodo se despego de la chapa)
            else {
                unsigned long duration = millis() - press_start_time;
                digitalWrite(PIN_STATUS_LED, LOW); // Apaga el LED azul

                Serial.printf("[CONTACTO LIBERADO] -> Duracion del contacto: %lu ms\n", duration);

                if (!long_press_triggered) {
                    if (duration < 300) {
                        Serial.println("  * Accion: Golpe seco (Strike rapido de inicio de arco)");
                    } else {
                        Serial.println("  * Accion: Contacto sostenido (Electrodo apoyado)");
                    }
                }
                Serial.println("------------------------------------------------------------");
            }
        }
    }

    // 2. Detección de pulsación larga (> 2 segundos) para calibración / tara en caliente
    if (last_stable_state == LOW && !long_press_triggered) {
        if ((millis() - press_start_time) >= 2000) {
            long_press_triggered = true;
            Serial.println("\n  **********************************************************");
            Serial.println("  [EVENTO TARA / RESET] Pulsacion sostenida de 2 segundos!");
            Serial.println("  >>> Restableciendo origen espacial (Zero Orientation) <<<");
            Serial.println("  **********************************************************\n");
            
            // Destello rápido del LED de la placa para confirmar la tara
            for (int i = 0; i < 3; i++) {
                digitalWrite(PIN_STATUS_LED, LOW); delay(50);
                digitalWrite(PIN_STATUS_LED, HIGH); delay(50);
            }
        }
    }

    last_reading = raw_reading;
    delay(5);
}
