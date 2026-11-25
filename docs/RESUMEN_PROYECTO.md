# ArcSim_VR — Resumen general del proyecto

**Simulador de soldadura SMAW con herramienta física sensorizada y gemelo digital en Godot, para capacitación de operarios.**

---

## 1. De qué trata el proyecto

Capacitar a un operario en soldadura por arco manual con electrodo revestido (SMAW) es caro y riesgoso: se consumen electrodos y chapas, hay arco, humo y quemaduras, y el instructor no puede ver con precisión qué hace mal el alumno (¿el arco estaba muy largo? ¿inclinó mal la pinza? ¿avanzó muy rápido?).

**ArcSim_VR** resuelve esto con un sistema mixto físico + virtual:

- El alumno sostiene un **portaelectrodo real** (impreso en 3D) con sensores y un motor de vibración.
- Trabaja sobre una **plantilla impresa** sobre la mesa, que una cámara ve.
- Una **réplica virtual (gemelo digital)** en Godot reproduce en tiempo real lo que hace con la herramienta: dibuja el arco, el cordón de soldadura, el consumo del electrodo, y al final entrega un **informe con nota de 1 a 10**.

No hay corriente ni arco real: todo lo peligroso es virtual, pero la **técnica de manipulación** (distancia, ángulos, velocidad, pulso) es la real.

### Cómo lo encaramos

Dividimos el problema en cuatro capas que se comunican por mensajes simples (JSON sobre UDP/serie), de modo que cada una se puede probar y reemplazar por separado:

```
 HERRAMIENTA FÍSICA ──USB──► PUENTE (Python) ──UDP──► GODOT (gemelo digital)
   ESP32 + IMU + ToF           serial_bridge.py          evaluación + informe
   + pulsador + motor    ◄──────────────────────◄        + háptica de retorno
        ▲                          ▲
        │                          │ UDP
   (impreso 3D, ArUco)      CÁMARA + ArUco (Python/OpenCV)
                            posición de la punta sobre la mesa
```

---

## 2. Hardware (herramienta física)

### Componentes
| Componente | Función |
|---|---|
| **ESP32 DevKit v1** | Cerebro de la herramienta: lee sensores, decide estados, maneja actuadores, transmite por USB |
| **IMU MPU6050** (I²C) | Orientación de la herramienta (ángulos de trabajo y de avance) |
| **Sensor ToF láser VL53L1X** (I²C) | Distancia punta del electrodo ↔ chapa (longitud de arco), con precisión milimétrica |
| **Pulsador en la punta** | Detecta contacto físico (cebado del arco / electrodo pegado) y permite "tara" con pulsación larga |
| **Motor vibrador + MOSFET IRFZ44N** | Retroalimentación háptica (el alumno "siente" el arco) |
| **LED RGB** | Indicador visual de estado en la propia herramienta |
| **Cable USB** | Alimentación y datos; cumple el rol del "cable de soldadura" |

### Diseño mecánico (carpeta `hardware/`)
- **Portaelectrodo de 250 mm** diseñado de forma paramétrica en Python (CadQuery/OpenCASCADE), exportado a **STEP** (editable en Solid Edge) y **STL** (impresión 3D). Cada mitad de la carcasa entra en una Ender 3 V2.
- Aloja ESP32, IMU, sensor ToF, motor, circuito MOSFET y canal de cableado; incluye una **varilla de electrodo** intercambiable (60/100 mm).
- **Soporte desmontable con marcador ArUco** (ID 0) para que la cámara pueda ubicar la herramienta.
- **Plantilla A4 imprimible** con 4 marcadores ArUco de referencia y el cordón dibujado (150 mm), que define el sistema de coordenadas de la mesa.

---

## 3. Firmware (ESP32)

Programado en C++ con **PlatformIO / Arduino**. Un único programa (`firmware/src/main.cpp`) ejecuta un lazo continuo:

1. **Leer sensores**
   - *IMU:* filtro complementario (96 % giroscopio / 4 % acelerómetro) que entrega ángulos y un **cuaternión** de orientación. Se calibra el sesgo del giroscopio al arrancar.
   - *ToF:* filtro de **mediana de 5 muestras + suavizado exponencial + banda muerta**, con un offset que compensa la longitud del electrodo.
   - *Pulsador:* antirrebote, detección de contacto y pulsación larga (2 s) para tarar.
2. **Máquina de estados finita (FSM) del arco**, que reproduce el comportamiento del proceso real:

   | Estado | Significado | LED | Motor |
   |---|---|---|---|
   | IDLE | En espera | Violeta | Apagado |
   | HOMING | Contacto / cebado del arco | Azul | Golpe seco breve |
   | WELD_OK | Arco estable y técnica correcta | Verde | "Ronroneo" suave |
   | WELD_WARN | Distancia o ángulos fuera de rango | Rojo | Pulsos de aviso |
   | STICKING | Electrodo pegado a la chapa | Rojo | Vibración violenta (100 %) |
   | ERROR | Falla de sensor | Rojo parpadeante | — |

   Incluye lógica realista: el arco se apaga si la punta se separa demasiado y se **reenciende automáticamente** al volver a acercarse; un electrodo pegado se libera al despegar.
3. **Actuadores:** aplica color de LED y patrón de vibración según el estado.
4. **Telemetría:** cada 20 ms (**50 Hz**) envía una línea JSON por USB (115200 baud) con cuaternión, ángulos, distancia, estado del pulsador, estado de la FSM y potencia del motor.
5. **Comandos entrantes:** acepta órdenes (`CALIBRATE`, `RESET_YAW`, `SET_HAPTIC`, `SET_LED`, `CONFIG`, `PING`, …) para que Godot o la interfaz de configuración controlen la herramienta. Los umbrales y colores se pueden **reconfigurar sin recompilar**.

> Los programas de prueba individuales (solo ToF, solo motor, solo LED, etc.) quedaron en `firmware/legacy/` como banco de pruebas por subsistema.

---

## 4. Comunicación (puente Python)

`serial_bridge.py` es un puente transparente entre el mundo embebido y Godot:

- **ESP32 → Godot:** lee el puerto serie (auto-detecta el ESP32) y reenvía cada trama JSON por **UDP al puerto 4242**.
- **Godot → ESP32:** recibe comandos por **UDP en el puerto 4243** y los escribe al puerto serie.
- Se **reconecta solo** si se desenchufa el cable y tiene un modo `--mock` que genera telemetría sintética para desarrollar sin hardware.

Se eligió UDP local porque Godot lo maneja de forma nativa y desacopla el simulador del hardware.

---

## 5. Seguimiento por cámara (visión por computadora)

El IMU da *orientación*, pero no *posición* sobre la mesa. Para eso se usa una cámara web y marcadores **ArUco** (carpeta `tools/`):

1. **Pose de la mesa:** los 4 marcadores de la plantilla A4 (posiciones conocidas) definen el plano de trabajo (`solvePnP`).
2. **Pose 6D de la herramienta:** el marcador ArUco del soporte da su rotación y traslación completas.
3. **Calibración de pivote:** la punta del electrodo no es visible, pero es un punto fijo respecto del marcador. Con la punta apoyada quieta se inclina la herramienta en todas direcciones y se resuelve por **mínimos cuadrados** dónde está la punta respecto del marcador. Así, inclinar la herramienta *no* mueve la punta calculada.
4. **Fusión con IMU (opcional):** el IMU aporta la inclinación (más estable que la que estima la cámara con un marcador chico), la cámara aporta posición.
5. El resultado (posición de la punta en mm sobre la mesa) se envía por UDP a Godot junto con la telemetría del ESP32.

Además hay un **Centro de Control (GUI en Tkinter, `arcsim_gui.py`)** para configurar colores de LED, intensidades de vibración, límites del sensor y tolerancias, probar los actuadores en vivo y lanzar todo el sistema. Los `.bat` de la raíz (`iniciar_simulador`, `iniciar_puente`, `probar_camara`, `probar_motor`, …) permiten arrancar cada parte con doble clic.

---

## 6. Simulación en Godot 4.7 (gemelo digital)

### 6.1 Enlace con la herramienta (`DeviceLink`)
Autoload que abstrae el origen de los datos. Hay **dos fuentes intercambiables**:
- **Hardware:** recibe la telemetría por UDP, convierte el cuaternión a una orientación relativa a una **pose neutra** (tara) y suaviza el movimiento.
- **Simulada:** teclado y mouse emulan la herramienta, para desarrollar y probar sin hardware.

También envía de vuelta los comandos de **vibración y LED**.

### 6.2 Entorno virtual e interacción
Un taller 3D en primera persona con máquina de soldar, pinza de masa, portaelectrodo, cable y mesa de trabajo con la probeta. La **preparación del equipo es una secuencia guiada y obligatoriamente ordenada**: conectar la pinza de masa → tomar el portaelectrodo → encender la máquina → regular el amperaje → posicionarse en la mesa. Luego hay una **calibración** de la pose neutra antes de soldar.

### 6.3 Simulación del proceso de soldadura
- **Arco (`ArcSimulator`):** misma lógica de estados que el firmware (apagado / arco / pegado / extinguido) con los mismos umbrales de distancia, de modo que el comportamiento físico y el virtual coinciden.
- **Modelo físico simplificado (`WeldPhysics`):** a partir de corriente, velocidad y longitud de arco calcula tensión de arco, aporte térmico, **ancho, altura y penetración del cordón**, tasa de consumo del electrodo y riesgo de mordedura (undercut). Calibrado para un electrodo E6013 Ø3,2 mm; son aproximaciones de ingeniería, no un modelo metalúrgico.
- **Cordón procedural (`WeldBead`):** malla 3D que se construye sección a sección (cada 1 mm) a lo largo de la junta; cada sección guarda ancho, altura, desvío y temperatura, y el metal **se enfría de incandescente a acero** con el tiempo (shader dedicado).
- **Efectos:** luz y partículas del arco, y la **careta de soldador** con filtro fotosensible (HUD de máscara).
- **Háptica (`HapticController`):** traduce el estado del arco a patrones de vibración: golpe seco al cebar, "ronroneo" parejo con arco óptimo, pulsos rápidos si el arco está muy corto, pulsos lentos si está muy largo, vibración fuerte si el electrodo se pega.

### 6.4 Evaluación pedagógica
- Basada en el método **CLAMS** (Corriente, Longitud de arco, Ángulo, Manipulación, Velocidad) y en la inspección visual de **AWS D1.1**; los rangos se sustentan en la documentación técnica de Miller, Lincoln y ESAB (ver `docs/investigacion_tecnica_soldadura_smaw.md`).
- **Tres niveles de dificultad:**
  1. *Principiante:* checklist, indicadores en pantalla y tolerancias amplias.
  2. *Intermedio:* menos ayudas y tolerancias medias.
  3. *Avanzado (examen):* sin ayudas visuales, solo señales físicas, sonoras y hápticas; tolerancias estrictas.
- **10 criterios ponderados** (suman 100): longitud de arco, velocidad, ángulo de trabajo, ángulo de avance, amperaje, trayectoria, ancho, regularidad, penetración y cobertura. Cada uno decae linealmente fuera de su rango óptimo.
- **Penalizaciones** por electrodo pegado, arco apagado e infracciones de seguridad (por ejemplo, soldar sin la careta puesta).
- **Informe final:** nota 1–10 (aprobado ≥ 6), puntaje por categoría, diagnóstico, gráficos de la pasada contra los valores ideales y **exportación a CSV** para análisis posterior.

### 6.5 Pruebas automáticas
Un conjunto de pruebas en Godot (`tests/test_runner`, ejecutable sin ventana) valida la lógica pura (geometría, física, arco, evaluador), la carga de escenas, el enlace UDP y el flujo completo de un ejercicio simulado.

---

## 7. Flujo de uso completo

1. Conectar el ESP32 por USB y ejecutar el puente (y, si se usa, el seguimiento por cámara).
2. Abrir el simulador y elegir el nivel (1–3).
3. Realizar la preparación guiada del equipo y calibrar la pose neutra.
4. Bajar la careta, cebar el arco con la herramienta y recorrer la junta de 150 mm; el alumno recibe feedback visual, sonoro y háptico en tiempo real.
5. Al terminar, ver el **informe** con nota y diagnóstico, y reintentar, pasar de nivel o exportar los datos.

---

## 8. Estructura del repositorio

```
Trabajo_Integrador_RV/
├── firmware/               Código del ESP32 (PlatformIO) + pruebas por subsistema (legacy/)
├── hardware/
│   ├── 3d_models/          CAD paramétrico, STEP y STL del portaelectrodo
│   └── aruco/              Marcadores y plantilla A4 imprimible
├── tools/                  Visión por computadora, calibración, GUI de configuración
├── simulacion_godot/
│   └── trabajo-final-rv/   Proyecto Godot: escenas, scripts, shaders, tests, puente serie
├── docs/                   Investigación técnica SMAW y guía de calibración
└── *.bat                   Lanzadores de cada parte del sistema
```

---

## 9. Resumen de decisiones de diseño

- **Arquitectura desacoplada** por mensajes JSON/UDP: cada capa se prueba y se reemplaza de forma independiente (incluso el hardware completo por teclado y mouse).
- **Misma lógica de arco en firmware y simulador**, para que lo que se siente en la mano coincida con lo que se ve en pantalla.
- **Fundamento técnico real:** rangos y criterios tomados de normas y fabricantes (CLAMS, AWS D1.1).
- **Sin magnetómetro** a propósito (la soldadura real genera campos que lo perturbarían); la posición la aporta la cámara y la orientación el IMU.
- **Pedagogía progresiva:** de modo guiado a examen sin ayudas, con informe objetivo y exportable.
- **Configurable sin recompilar:** colores, intensidades, umbrales y tolerancias desde la GUI.
