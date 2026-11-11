# Investigación Técnica y Arquitectura del Simulador de Soldadura SMAW (ArcSim_VR)

Documento técnico elaborado para el Trabajo Integrador de Realidad Virtual.

*(Para el plan de implementación interactivo con feedback, consultar el artefacto asociado).*

---

## 1. Benchmarking de Simuladores de Soldadura en RV/RA: Análisis de SOLDAMATIC

### 1.1 Sistemas Comerciales Líderes
1. **SOLDAMATIC (Seabery - España):** Emplea **Realidad Aumentada (AR)** con visión computacional y cupones de trabajo (*dummies*) con marcadores ópticos. Utiliza antorchas y pinzas portaelectrodo reales instrumentadas.
2. **Lincoln Electric VRTEX® 360 / Mobile:** Utiliza cascos de **Realidad Virtual cerrada (VR)** inmersiva con periféricos con sensores magnéticos/ópticos patentados y réplicas de cupones metálicos plásticos.
3. **Miller AugmentedArc®:** Basado en realidad aumentada de sobremesa con pantalla integrada y cámara frontal.

### 1.2 Funcionamiento Interno de SOLDAMATIC
- **Tecnología HyperReal-SIM™:** Modelo matemático calibrado con laboratorios metalúrgicos internacionales para calcular transferencia de calor ($I, V, v$), tensión superficial del baño fundido y tasa de deposición.
- **Hardware:** Visor AR estéreo sobre máscara real de soldador, cupones con marcadores fiduciales sin oclusión y pinza portaelectrodo con peso real y consumo longitudinal simulado.
- **HUD con Semáforo:** Diana 3D/2D para ángulos de trabajo y avance, barra milimétrica de distancia de arco punta-pieza, y guía luminosa animada (*pacer*) para velocidad de avance.
- **Audio Frecuencial:** Modulación sonora del arco eléctrico según longitud y estabilidad del plasma.
- **Diagnóstico de Defectos (AWS D1.1 / ISO 5817):** Correlación de errores en tiempo real con defectos: porosidad, mordeduras de borde (*undercut*), falta de penetración, inclusiones de escoria y electrodo pegado (*sticking*).

### 1.3 Aportes para ArcSim_VR
1. Adopción del marco de evaluación industrial **C.L.A.M.S.** (Current, Length of arc, Angle, Manipulation, Speed).
2. Dos modos pedagógicos: *Modo Guiado* (con HUD y ayudas visuales) y *Modo Examen* (sin ayudas, solo señales físicas, sonoras y hápticas).
3. Desgaste dinámico del electrodo virtual ($v_{\text{consumo}} \propto I$).
4. Matriz diagnóstica post-soldadura con causas físicas concretas.

---

## 2. Compendio Técnico del Proceso SMAW (Normas AWS D1.1 / A5.1 / A5.5)

### 2.1 Ángulos de Incidencia según Tipo de Junta y Posición
- **Ángulo de Avance (*Travel Angle*):** En SMAW se usa técnica de **arrastre (*Drag*)** con **10° a 20°** respecto a la perpendicular para mantener la escoria detrás del baño fundido. En vertical ascendente (3G/3F) se utiliza **empuje (*Push*)** de 5° a 15° para sostener la pileta contra la gravedad.
- **Ángulo de Trabajo (*Work Angle*):** Perpendicular al eje del cordón para balancear el aporte térmico.

| Tipo de Junta | Posición AWS | Ángulo de Trabajo (*Work Angle*) | Ángulo de Avance (*Travel Angle*) | Tolerancia Óptima | Tolerancia Aceptable |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A Tope (*Butt Joint*)** | **1G** (Plana) | **90°** (perpendicular) | **10° a 15° Arrastre** (*Drag*) | $\pm 3^\circ$ | $\pm 8^\circ$ |
| **A Tope (*Butt Joint*)** | **2G** (Horizontal) | **90° a 95°** (5° hacia arriba contra gravedad) | **10° a 15° Arrastre** | $\pm 4^\circ$ | $\pm 8^\circ$ |
| **A Tope (*Butt Joint*)** | **3G** (Vertical Ascendente) | **90°** (centrado en ranura) | **5° a 15° Empuje** (*Push*) | $\pm 5^\circ$ | $\pm 10^\circ$ |
| **A Tope (*Butt Joint*)** | **3G** (Vertical Descendente) | **90°** | **15° a 20° Arrastre** (*Drag*) | $\pm 5^\circ$ | $\pm 10^\circ$ |
| **A Tope (*Butt Joint*)** | **4G** (Sobrecabeza) | **90°** | **5° a 10° Arrastre** (muy cerrado) | $\pm 3^\circ$ | $\pm 6^\circ$ |
| **En T / Filete (*Tee / Fillet*)** | **1F** (Plana / Barco) | **90°** respecto a la cuna | **10° a 15° Arrastre** | $\pm 4^\circ$ | $\pm 8^\circ$ |
| **En T / Filete (*Tee / Fillet*)** | **2F** (Horizontal) | **45°** (bisectriz exacta) | **10° a 15° Arrastre** | $\pm 4^\circ$ | $\pm 8^\circ$ |
| **En T / Filete (*Tee / Fillet*)** | **3F** (Vertical Ascendente) | **45°** bisectriz | **5° a 15° Empuje** | $\pm 5^\circ$ | $\pm 10^\circ$ |
| **En T / Filete (*Tee / Fillet*)** | **4F** (Sobrecabeza) | **45°** bisectriz | **5° a 10° Arrastre** | $\pm 4^\circ$ | $\pm 8^\circ$ |
| **A Solape (*Lap Joint*)** | **1F / 2F** | **30° a 40°** desde la base horizontal | **10° a 15° Arrastre** | $\pm 4^\circ$ | $\pm 8^\circ$ |
| **En Esquina (*Corner Joint*)** | **Exterior (1G / 1F)** | **45°** centrado en la arista | **10° a 15° Arrastre** | $\pm 4^\circ$ | $\pm 8^\circ$ |

### 2.2 Longitud de Arco (*Arc Length*)
- **Fórmula:** $L_{\text{arc\_óptima}} \approx 0.8 \times d_{\text{alma}} \text{ a } 1.0 \times d_{\text{alma}}$.
- Para electrodo de 3.2 mm (1/8"): **2.0 mm a 3.5 mm**.
- **Zonas:**
  - Cortocircuito / Pegado: $< 0.8\text{ mm}$ (vibración continua al 100%, tensión $< 12\text{ V}$).
  - Arco óptimo: $1.5\text{ mm} - 3.5\text{ mm}$ (sonido crepitante suave, tensión $22-28\text{ V}$).
  - Arco largo: $3.5\text{ mm} - 5.5\text{ mm}$ (porosidad, salpicaduras violentas, tensión $> 30\text{ V}$).
  - Extinción: $> 6.0\text{ mm}$.

### 2.3 Velocidad de Soldado (*Travel Speed*)
- **Rango típico:** **120 a 240 mm/min** (**2.0 a 4.0 mm/s**). Promedio nominal: **3.0 mm/s**.
- **Regla geométrica:** Ancho del cordón $\approx 1.5 \text{ a } 2.5 \times d_{\text{alma}}$ (5 a 8 mm para 3.2 mm).
- **Exceso ($> 5\text{ mm/s}$):** Mordedura (*undercut*), falta de penetración y poros atrapados.
- **Defecto ($< 1.5\text{ mm/s}$):** Cordón excesivamente ancho y alto, riesgo de perforación (*burn-through*).

### 2.4 Amperaje de la Herramienta
- **Regla empírica:** $35\text{ a } 40\text{ A}$ por milímetro de diámetro de alma (o $1\text{ A}$ por $0.001''$).
- **Valores nominales:**
  - 1.6 mm: 25 - 45 A
  - 2.0 mm: 45 - 70 A
  - 2.5 mm: 60 - 90 A
  - 3.2 mm: **90 - 130 A** (E6013) / **105 - 145 A** (E7018) / **75 - 125 A** (E6010)
  - 4.0 mm: 140 - 180 A (E6013) / 145 - 200 A (E7018)
  - 5.0 mm: 180 - 240 A

### 2.5 Clasificación y Selección de Electrodos según Material Base
1. **Aceros al Carbono / Estructurales Ligeros:**
   - **AWS E6013 (Rutílico):** Arco suave, fácil reencendido, escoria vitrificada separable. Ideal para enseñanza.
   - **AWS E6010 / E6011 (Celulósico):** Alta penetración, para pases de raíz en cañerías y piezas sucias.
2. **Aceros Estructurales Pesados y Recipientes a Presión:**
   - **AWS E7018 (Básico de bajo hidrógeno con polvo de hierro):** Alta tenacidad al impacto (-30 °C). Requiere arco muy corto y estufa a 100-150 °C.
   - **AWS E7024 (Alto rendimiento):** Para pasadas de relleno en posición plana.
3. **Aceros Inoxidables Austeníticos:**
   - **AWS E308L:** Aceros AISI 304 / 304L.
   - **AWS E316L:** Aceros AISI 316 / 316L (resistente a cloruros).
   - **AWS E309L:** Unión disímil acero negro con acero inoxidable.
4. **Fundiciones de Hierro:**
   - **AWS ENi-CI (Níquel puro):** Mecanizable.
   - **AWS ENiFe-CI (Ferro-níquel):** Mayor resistencia mecánica y unión con acero.
5. **Recargues Duros (Hardfacing):**
   - Electrodos de carburos de cromo (55 - 62 HRC) para piezas expuestas a abrasión severa.
