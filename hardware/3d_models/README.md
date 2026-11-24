# Modelos 3D CAD — Portaelectrodo SMAW Sensorizado v3.1 (ArcSim_VR)

Diseño paramétrico generado con **CadQuery / OpenCASCADE** (`generate_holder_cad.py`). Exporta sólidos **`.STEP`** editables (para Solid Edge) y mallas **`.STL`** para impresión 3D.

- Qué cambió respecto de la v2.2 y por qué: [`../CAMBIOS_v3.md`](../CAMBIOS_v3.md)
- Cómo armarlo: [`../GUIA_ENSAMBLE.md`](../GUIA_ENSAMBLE.md)
- Versión anterior respaldada en `v2.2_backup/`.

## Resumen v3.1

- **Largo total 250 mm, mango Ø54** (Z −108 a +142): cada mitad se imprime en la Ender 3 V2 rotada 45° en Z.
- **Sensor VL53L0X** (módulo GY-530 o similar) en el pod `03a`, con la varilla de **60 mm**.
- **Motor vibrador Ø27 mm × 23 mm**: cuerpo en la mitad izquierda, desbalance en la derecha.
- **Circuito MOSFET** soldado al aire en el ducto delantero; **canal superior** de 18 × 5,3 mm para 10 cables AWG 28–30.
- Orificio de la cola Ø5,4 mm para el cable USB-C que alimenta al ESP32 (51,6 × 28,5 mm, medidas reales).
- **LED RGB KY-016** en la cara superior del guarda-mano (17 mm de espesor), salida Ø6,4 mm; GPIO 26 (R) y GPIO 27 (G).
- Verificación automática de interferencias al correr el script.

## Archivos

### `step/` (abrir en Solid Edge)
| Archivo | Contenido |
|---|---|
| `00_ensamble_completo.step` | carcasa, pod ToF, varilla 60 mm y soporte ArUco |
| `00b_ensamble_con_componentes.step` | lo anterior + envolventes de ESP32, ficha USB-C, motor, circuito MOSFET, cables, LED KY-016, MPU6050 y GY-530 |
| `01_carcasa_derecha.step` / `02_carcasa_izquierda.step` | carcasa partida en X = 0 |
| `03a_modulo_sensor_ToF.step` | pod del VL53L0X |
| `03b_modulo_sensor_HCSR04.step` | pod alternativo para HC-SR04 (sin cambios) |
| `04a_electrodo_60mm.step` / `04b_electrodo_100mm.step` | varillas deslizantes (con VL53L0X usar la de 60 mm) |
| `05_soporte_aruco.step` | soporte desmontable con 3 caras de 36 × 36 mm |

Los archivos `.par` y `.asm` de esa carpeta son de la v2.2 y quedaron desactualizados: reimportá los STEP nuevos.

### `stl/`
Un `.stl` por pieza, ya orientado sobre la cara plana del corte.

### Otros
`generate_holder_cad.py` (generador y verificador), `preview_cad.py` y `preview_cad.png` (cortes con componentes).

## Cotas clave

| Parámetro | Valor (mm) |
|---|---|
| Largo total | 250 (Z −108 a +142) |
| Diámetro del mango | Ø54 (estrías de 1,2 mm de profundidad); collarín Ø56 |
| Cono prensacable | Z −108 a −88; orificio Ø5,4 |
| Bahía ficha USB-C | 17 × 13 × 26 (Z −92 a −66) |
| Bahía ESP32 | 56 × 32, X −13 a +9 (Z −68 a −12) |
| Motor | cuerpo Ø27,75 × 13 (X −13 a 0); desbalance Ø29 × 11,3 (X 0 a +11,3); centro Z = 5, Y = −1 |
| Canal de cables | 18 × 5,3 arriba y 18 × 3,8 abajo, Z −20 a 46 |
| Zona del motor | cavidad libre Z −9,5 a 44; anillo de 1,8 mm alrededor del motor; plataforma maciza de 8 mm en ambas mitades (de Z −11 a 44) y costilla de 3 mm en la derecha |
| Ducto delantero | 14 × 20 (Z 40,5 a 78) |
| Guarda-mano | Z 55 a 72 (17 mm de espesor) |
| LED KY-016 | cavidad 20,4 × 16,4 × 5,5; salida Ø6,4; eje Z = 65,5 |
| Cabezal | Z 72 a 142 (sin cambios) |
| Cavidad ToF | 21 × 14,5; ventana 14 × 14,5; piso 2,2 |
| Separación sensor ↔ electrodo | 24,0 |
| Lente ToF → punta (varilla 60 mm) | 57,2 |
| Recorrido axial de la varilla | 2,5 |

## Tornillería (todo M3)

| Cant. | Largo | Uso |
|---|---|---|
| 2 | 35 | cierre, prensacable |
| 2 | 25 | cierre, zona ESP32 |
| 1 | 25 | cierre, zona motor |
| 2 | 35 | cierre, guarda-mano |
| 1 | 18–20 | perno guía de la colisa |
| 1 | 10–12 | regulación del pulsador |
| 2 | 10 | pod del sensor |
| 2 | 16–20 | MPU6050 |
| 2 | 10–12 | soporte ArUco (opcional) |

Tuercas M3: 7 (cierre) + 1 (colisa) + 2 (MPU6050) + 2 (ArUco, opcional).

## Regenerar

```bash
pip install cadquery trimesh matplotlib
python generate_holder_cad.py   # STEP + STL + verificaciones
python preview_cad.py           # preview_cad.png
```
