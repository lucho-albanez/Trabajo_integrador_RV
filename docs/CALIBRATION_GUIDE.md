# Guía de Calibración y Ajuste de Sensores - ArcSim_VR

Esta guía describe el protocolo de calibración y verificación metrológica del hardware háptico de la herramienta de soldadura SMAW.

---

## 1. Calibración del Sensor Inercial (IMU MPU6050)

El MPU6050 integra un acelerómetro de 3 ejes (referencia gravitatoria) y un giroscopio de 3 ejes (velocidad angular). Debido a tolerancias de fabricación y esfuerzos mecánicos de soldadura del chip, cada unidad presenta un sesgo de cero (*bias*) que debe ser compensado.

### Procedimiento de Calibración de Cero (Offsets)

1. **Condición Inicial de Reposo:**
   - Colocar la pinza porta-electrodo sobre una superficie plana y nivelada (mesa de trabajo).
   - Asegurarse de que no existan vibraciones mecánicas ni corrientes de aire durante el proceso.
2. **Disparo de la Calibración:**
   - **Opción A (Desde el simulador Godot):** Presionar la tecla `[C]` en el teclado.
   - **Opción B (Por comando Serie/UDP):** Enviar la trama JSON `{"cmd":"CALIBRATE"}\n`.
   - **Opción C (Al encender):** El firmware ejecuta automáticamente un muestreo de 250 lecturas durante el primer segundo de encendido (el LED integrado en el pin GPIO 2 permanecerá encendido durante este intervalo).
3. **Muestreo Estadístico:**
   - El firmware adquiere $N = 400$ muestras a 200 Hz.
   - Calcula el promedio de sesgo del giroscopio ($\Delta G_x, \Delta G_y, \Delta G_z$) y del acelerómetro ($\Delta A_x, \Delta A_y, \Delta A_z - 1g$).
   - Los valores calculados se restan dinámicamente en cada ciclo de la tarea FreeRTOS.
4. **Recentrado de Azimut (Yaw):**
   - Dado que el sensor MPU6050 no cuenta con magnetómetro (para no verse afectado por los campos electromagnéticos de la soldadura real), el eje Yaw se integra numéricamente a partir de $G_z$.
   - Para eliminar cualquier desviación acumulada a lo largo del tiempo, apuntar la antorcha directamente hacia el centro de la probeta de soldadura y presionar la tecla `[R]` en Godot o enviar `{"cmd":"RESET_YAW"}\n`.

---

## 2. Calibración del Sensor de Distancia y Offset Mecánico

En un proceso SMAW real, la distancia del arco entre la punta metálica del electrodo y la chapa oscila entre **1.5 mm y 3.5 mm**. 
El sensor ultrasónico no puede ubicarse en la punta misma (chocaría con la chapa y entraría en su zona ciega de $<20\text{ mm}$), por lo que se instala en el lomo de la pinza, con un **offset longitudinal mecánico hacia atrás**.

```text
       [ SENSOR ULTRASÓNICO ] ---> Mide distancia acústica d_sensor
       | <--- Offset L_0 ---> |
==============================[ MORDAZA ]==============================
                                         \
                                          \  Varilla de Electrodo (L_e)
                                           \
                                            * PUNTA (d_punta = 2 a 3 mm)
---------------------------------------------------------------------- [CHAPA]
```

### Medición de Parámetros Físicos

1. **Medir el Offset de Montaje ($L_{offset}$):**
   - Con un calibre, medir la distancia longitudinal desde la cara frontal del transductor ultrasónico hasta el eje central de apriete de la mordaza de la pinza (típicamente $L_{offset} \approx 60.0\text{ mm}$).
   - Configurar este valor en `firmware/include/Config.h`:
     ```cpp
     #define SENSOR_MOUNT_OFFSET_MM 60.0f
     ```
2. **Medir la Longitud Expuesta del Electrodo ($L_{electrodo}$):**
   - Medir la varilla desde la mordaza hasta la punta libre (típicamente $200.0\text{ mm}$ para un electrodo nuevo).
   - Configurar en `Config.h`:
     ```cpp
     #define DEFAULT_ELECTRODE_LENGTH_MM 200.0f
     ```

### Ecuación de Corrección Geométrica en Tiempo Real

La distancia real calculada entre la punta del electrodo y la chapa se obtiene mediante:
$$d_{punta} = d_{sensor} - (L_{electrodo} - L_{offset}) \cdot \cos(\theta_{pitch})$$

Donde $\theta_{pitch}$ es el ángulo de inclinación vertical provisto en tiempo real por el MPU6050.

### Procedimiento de Prueba de Contacto de Cero (Zero Test)

1. Apoyar manualmente la punta del electrodo sobre la chapa de soldadura.
2. Observar la lectura en el HUD de Godot o en el monitor serie (`"d": X.X`).
3. La lectura debe situarse en **$0.0\text{ mm} \pm 0.5\text{ mm}$**.
4. Si la lectura difiere:
   - Si marca un valor positivo (ej. $+3.0\text{ mm}$ estando en contacto): aumentar `SENSOR_MOUNT_OFFSET_MM` en esa misma cantidad.
   - Si marca valor negativo o saturado en 0 antes de tocar: reducir `SENSOR_MOUNT_OFFSET_MM`.

---

## 3. Migración Futura a Sensor ToF Láser (VL53L0X)

Cuando se disponga del sensor láser de tiempo de vuelo I2C (VL53L0X / VL53L1X):
1. Conectar las líneas `SDA` y `SCL` del sensor en paralelo al bus I2C (GPIO 21 y GPIO 22).
2. Alimentar el módulo con `3.3V` y `GND`.
3. En `firmware/src/main.cpp`, cambiar la asignación del puntero polimórfico:
   ```cpp
   // static UltrasonicDistanceSensor ultrasonic(PIN_US_TRIG, PIN_US_ECHO, SENSOR_MOUNT_OFFSET_MM);
   static ToFDistanceSensor tofSensor(0x29, SENSOR_MOUNT_OFFSET_MM);
   static IDistanceSensor* activeDistanceSensor = &tofSensor;
   ```
4. El sistema compilará y operará de forma transparente, eliminando el cono acústico y logrando precisión milimétrica directa.

---

## 4. Seguimiento óptico ArUco: posición de la punta (pose 6D + pivote)

La cámara ve el ArUco del soporte (ID 0), que está unos 10 cm por encima de la punta. `tools/test_vision_table.py` (con `tools/tool_tracking.py`) calcula la punta así:

1. Pose de la cámara respecto de la mesa con los 4 marcadores de la plantilla A4.
2. Pose 6D (rotación + traslación) del ArUco de la herramienta con sus 4 esquinas.
3. La punta es un punto **fijo** en el sistema del marcador: `punta = R·p + t`. Si `p` es correcto, inclinar la herramienta no mueve la punta.
4. `p` se mide con la **calibración de pivote**: punta quieta, herramienta inclinada, y se resuelve `R_i·p + t_i = q` por mínimos cuadrados.

No usa el IMU ni el brazo L para la posición. El cordón por defecto es el de la plantilla (0 a 150 mm).

### Procedimiento

1. Ejecutar `probar_mesa.bat` con el ESP32 conectado. El HUD debe mostrar Mesa 4/4 y Herramienta DETECTADA.
2. `[C]` calibra el giroscopio (herramienta quieta) y `[T]` tara el yaw.
3. **`[P]`:** apoyar la punta en la hoja y dejarla **quieta**; inclinar la herramienta hacia adelante/atrás y hacia los costados durante 5–10 s; `[P]` otra vez. Se acepta con residuo de pocos mm.
4. Verificar: la línea azul cae sobre el cordón impreso, la cruz "PUNTA" está sobre el electrodo (z ≈ 0 apoyada) y "Punta" no se mueve al inclinar.

Repetir el pivote solo si cambia el soporte ArUco. Mover la cámara o la plantilla no lo invalida.

### Teclas

| Tecla | Acción |
| :--- | :--- |
| `[C]` / `[T]` | Calibrar gyro / tara de yaw |
| `[P]` | Iniciar / terminar el pivote |
| `[ESPACIO]` / `[F]` | Cordón propio (opcional): inicio / fin |
| `[R]` | Volver al cordón de la plantilla |

### Opcionales

- `"tool_marker_mm"` en `tool_config.json`: lado del cuadrado negro del ArUco de la herramienta (36 por defecto); el pivote lo corrige si está mal.
- `python tools/calibrar_camara.py`: mide focal y distorsión de la webcam (`camera_intrinsics.json`).
- Si el IMU está conectado durante el pivote, se calibra una fusión cámara + IMU que reduce el temblor; solo se activa si mejora el residuo.

### Prueba sin hardware

```bash
python tools/test_tool_tracking.py
```
