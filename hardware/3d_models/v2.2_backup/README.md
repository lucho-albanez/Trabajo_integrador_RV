# Modelos 3D CAD — Portaelectrodo SMAW Sensorizado v2 (ArcSim_VR)

Diseño CAD paramétrico generado en **OpenCASCADE / CadQuery** (`generate_holder_cad.py`), exportado como sólidos B-Rep editables **`.STEP`** (para abrir y modificar en **Solid Edge**) y mallas **`.STL`** orientadas para impresión 3D FDM.

### Novedad principal (v2 — Cebado realista SMAW + Auto-Homing a 0 mm)
- **Sin palanca/gatillo externo:** la varilla impresa en 3D desliza axialmente **2,5 mm** dentro del cabezal, retenida y guiada por un perno M3 frontal que pasa por una **colisa (ranura ovalada)**.
- **Pulsador táctil `6 × 6 mm` fijo en "sándwich":** se cablea afuera de la carcasa y queda aprisionado sin pegamento entre ambas mitades (apoyado en una repisa fija y contra techo macizo).
- **Regulación fina sin calibre:** un tornillo **M3 × 10/12 mm** roscado en la cabeza superior de la varilla permite ajustar al milímetro el punto exacto de disparo contra tu pulsador `6 × 6 mm` (funciona tanto **con** como **sin** el capuchón rojo, para alturas de 5 a 13,5 mm).
- **Doble tope anti-rotura:** al hundirse 2,5 mm, tanto la colisa como el collarín de la varilla hacen tope sólido contra la carcasa, evitando aplastar el pulsador.

---

## 1. Archivos generados

### Carpeta `step/` (Abrir en Solid Edge)
- **`00_ensamble_completo.step`**: Ensamble completo coloreado con todas las piezas en su posición de reposo.
- **`01_carcasa_derecha.step`** / **`02_carcasa_izquierda.step`**: Carcasa dividida en `X = 0` con pines guía, 7 alojamientos M3 (cabeza Allen izquierda / tuerca hexagonal derecha), prensacable trasero USB, bahía ESP32 DevKit v1 (30 o 38 pines), bahía MOSFET/flyback, bolsillo motor vibrador 10 mm bajo la palma, postes para MPU6050 (GY-521), casquillo guía y nicho fijo para el pulsador `6 × 6 mm`.
- **`03a_modulo_sensor_ToF.step`**: Módulo porta-sensor compacto intercambiable para **VL6180X**, **VL53L1X** o **VL53L0X** (centrado en `Z = 104 mm`, a `22 mm` del eje del electrodo).
- **`03b_modulo_sensor_HCSR04.step`**: Módulo adaptador intercambiable para prototipar con el **HC-SR04** (mismos 2 tornillos M3).
- **`04a_electrodo_60mm.step`**: Varilla deslizante impresa de **60 mm expuestos** (recomendada para **`VL6180X`**) con colisa de 2,5 mm, collarín tope, rosca superior M3 de regulación y punta redondeada.
- **`04b_electrodo_100mm.step`**: Varilla deslizante impresa de **100 mm expuestos** (recomendada para **`VL53L1X`** o pruebas con `HC-SR04`).
- **`05_soporte_aruco.step`**: Soporte superior desmontable (2 tornillos M3) con 3 caras planas de `36 × 36 mm` para marcadores ArUco.

### Carpeta `stl/` (Listos para Slicer / Impresión 3D)
Contiene el `.stl` de cada pieza ya orientado para imprimir con mínimos soportes.

---

## 2. Cómo armar y regular el mecanismo de Auto-Homing

1. **Cableá el pulsador `6 × 6 mm` afuera:** soldá 2 cables flexibles a dos patitas opuestas/normalmente abiertas (`GPIO 4` y `GND`), protegé con termocontraíble y doblalos hacia atrás.
2. **Colocá el pulsador en la Mitad Derecha:** apoyalo en su nicho (`Y = +10..+14,2 mm`, botón hacia abajo `-Y`) y pasá los cables por la canaleta trasera hacia la cámara del cabezal. *(Si el capuchón rojo de tu pulsador es más ancho que `Ø5,5 mm`, simplemente sacáselo: el vástago pelado de Ø3,2 mm pasa holgado por el orificio `Ø5,6 mm`).*
3. **Cerrá la carcasa:** colocá el ESP32, motor vibrador, MOSFET y MPU6050, cerrá la Mitad Izquierda y ajustá los 7 tornillos M3.
4. **Regulá el disparo sin calibre:** enroscá un tornillo **M3 × 10 mm** (o `M3 × 12 mm`) en la punta superior de la varilla, meté la varilla en el casquillo y colocá el perno frontal M3 en la colisa (sin apretar la varilla; la punta del tornillo solo entra en la ranura). Apoyá la punta sobre la mesa: girá el tornillo superior de la varilla media vuelta hasta que haga **clic limpio** al hundirse ~1–1,5 mm y suelte solo al levantarla.

---

## 3. Cotas clave y calibración (para `firmware/include/Config.h`)

| Parámetro | Valor exacto (mm) | Notas |
| :--- | :---: | :--- |
| Largo total sin electrodo | `324 mm` | De `Z = -182` (cola prensacable) a `Z = +142` (frente cabezal) |
| Diámetro exterior del mango | `Ø46 mm` | Pared mínima `3.0 mm`, con 8 estrías ergonómicas |
| Bahía ESP32 DevKit v1 | `56.0 × 29.6 × 18.0 mm` | Compatible con 30 pines (`51.5×28.5`) y 38 pines (`55×28`) |
| Cámara ficha USB trasera | `34.0 × 16.0 × 17.0 mm` | Detrás del ESP32 (`Z = -148..-114`) + pasacable `Ø5.4 mm` |
| Bolsillo motor vibrador | `Ø10.6 × 3.6 mm` | En `Z = -134, Y = -12` (zona palma, a `~215 mm` del MPU6050) |
| Cavidad / Montaje MPU6050 (GY-521) | Pared plana `X=+8 mm`, 2× M3 pasantes (`15.6 mm` entre centros) | Tuercas M3 hexagonales en cara externa derecha; admite tornillos largos; pines hacia abajo (`-Y`) |
| Recorrido axial varilla (colisa) | **`2.5 mm`** | Auto-homing al tocar/despegar de la chapa |
| Nicho pulsador táctil `6 × 6 mm` | **`6.4 × 6.4 × 4.0 mm`** | Canaleta trasera angosta `4.0 × 4.5 mm` para los 2 cables soldados |
| Separación lateral sensor ↔ electrodo (`r_z`) | **`24.0 mm`** | Centro sensor `Z = 102 mm`, eje electrodo `Z = 126 mm` |
| Distancia vertical lente ToF → punta (`L`, 60 mm) | **`57.2 mm`** | Lente `Y = -28.8 mm`, punta en reposo `Y = -86.0 mm` |
| Distancia vertical lente ToF → punta (`L`, 100 mm) | **`97.2 mm`** | Lente `Y = -28.8 mm`, punta en reposo `Y = -126.0 mm` |

---

## 4. Tornillería necesaria (todo estándar M3)

- **7× tornillos M3 × 35–45 mm** (cabeza Allen) + **7× tuercas M3**: cierre de las dos mitades.
- **1× tornillo M3 × 18–20 mm** + **1× tuerca M3**: perno guía frontal de la colisa (`Z = 142, Y = -14`).
- **1× tornillo M3 × 10–12 mm**: tornillo de regulación fina roscado en la cabeza superior de la varilla.
- **2× tornillos M3 × 10 mm**: fijación del módulo porta-sensor inferior (`ToF` o `HC-SR04`).
- **2× tornillos M3 × 10–12 mm** + **2× tuercas M3** *(opcional)*: fijación del soporte ArUco superior por las 2 orejas exteriores (`Z = 77` y `Z = 118,5 mm`, acceso 100% libre desde arriba, tuercas cautivas internas).
- **2× tornillos M3 × 16–20 mm** + **2× tuercas M3**: fijación rígida del MPU6050 contra la pared interior derecha (agujeros pasantes abiertos hasta afuera + hexágonos para tuerca en cara externa derecha; admite tornillos más largos sin tope).

---

## 5. Recomendaciones de impresión 3D (FDM)

- **Material:** PLA+ o PETG (**negro mate** recomendado para la varilla del electrodo para evitar reflejos IR).
- **Varilla (`04a` / `04b`):** imprimirla **acostada** (ya viene orientada así en el `.stl`) con **4 perímetros / 50–100% relleno** y capa `0.16 mm`. Dar una pasadita suave con lija fina a la espiga `Ø8 mm` para que caiga libremente por gravedad dentro del casquillo `Ø8,45 mm`.
- **Carcasas (`01` / `02`):** ya vienen apoyadas sobre la cara plana del corte (`X = 0`), capa `0.20 mm`, 3 perímetros, 20–25% relleno.
