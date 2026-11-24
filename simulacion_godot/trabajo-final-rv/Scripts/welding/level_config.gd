class_name LevelConfig
extends RefCounted
## Parámetros de cada nivel de dificultad: ayudas visuales y tolerancias.
##
## Las bandas son Vector4(óptimo_min, óptimo_max, límite_min, límite_max):
## dentro de [óptimo_min, óptimo_max] el puntaje es 1.0 y decae linealmente
## hasta 0.0 en los límites. Referencias de los valores: Miller Electric,
## Lincoln Electric, ESAB (técnica CLAMS), AWS D1.1 y fichas técnicas de
## electrodos E6013 Ø3,2 mm (ver docs/investigacion_tecnica_soldadura_smaw.md).

const LEVEL_COUNT := 3
const PASS_GRADE := 6.0
const SEAM_LENGTH_MM := 150.0

var id: int = 1
var display_name: String = ""
var summary: String = ""

# --- Ayudas en pantalla ---
var show_checklist: bool = true
var show_current_hint: bool = true
var show_arc_gauge: bool = true
var show_speed_gauge: bool = true
var show_angle_gauges: bool = true
## Indicadores de color verde/amarillo/rojo (distancia, ángulos y velocidad).
var show_color_guides: bool = true

# --- Bandas de tolerancia ---
var arc_length_band: Vector4    # mm
var speed_band: Vector4         # mm/s
var work_band: Vector4          # ° absolutos (ideal 90°, perpendicular a la chapa)
var travel_band: Vector4        # ° de arrastre (+) o empuje (-)
var current_band: Vector4       # A
var lateral_band: Vector4       # mm de desvío absoluto respecto del eje de la junta
var width_band: Vector4         # mm de ancho de cordón
var penetration_band: Vector4   # mm de penetración

## Multiplicador de la velocidad de consumo del electrodo.
var consumption_scale: float = 1.0


static func create(level: int) -> LevelConfig:
	var c := LevelConfig.new()
	match clampi(level, 1, LEVEL_COUNT):
		1:
			c.id = 1
			c.display_name = "Nivel 1 - Principiante"
			c.summary = "Modo guiado: checklist, indicadores en pantalla y tolerancias amplias."
			c.arc_length_band = Vector4(1.5, 3.5, 0.5, 6.0)
			c.speed_band = Vector4(1.8, 4.5, 0.6, 7.0)
			c.work_band = Vector4(88.0, 92.0, 85.0, 95.0)
			c.travel_band = Vector4(3.0, 20.0, -8.0, 35.0)
			c.current_band = Vector4(95.0, 135.0, 70.0, 160.0)
			c.lateral_band = Vector4(0.0, 1.5, 0.0, 3.5)
			c.width_band = Vector4(4.5, 9.5, 2.5, 13.0)
			c.penetration_band = Vector4(1.8, 5.0, 0.6, 8.0)
			c.consumption_scale = 0.6
		2:
			c.id = 2
			c.display_name = "Nivel 2 - Intermedio"
			c.summary = "Ayudas reducidas (arco y velocidad) y tolerancias medias."
			c.show_current_hint = false
			c.show_angle_gauges = false
			c.arc_length_band = Vector4(1.5, 3.5, 0.8, 5.0)
			c.speed_band = Vector4(2.0, 4.0, 1.0, 5.5)
			c.work_band = Vector4(88.5, 91.5, 86.0, 94.0)
			c.travel_band = Vector4(5.0, 15.0, -3.0, 26.0)
			c.current_band = Vector4(100.0, 130.0, 80.0, 145.0)
			c.lateral_band = Vector4(0.0, 1.0, 0.0, 2.5)
			c.width_band = Vector4(5.0, 8.5, 3.0, 11.0)
			c.penetration_band = Vector4(2.0, 4.5, 0.8, 7.0)
			c.consumption_scale = 1.0
		_:
			c.id = 3
			c.display_name = "Nivel 3 - Avanzado (examen)"
			c.summary = "Sin ayudas: solo señales físicas, sonoras y hápticas. Tolerancias estrictas."
			c.show_checklist = false
			c.show_color_guides = false
			c.show_current_hint = false
			c.show_arc_gauge = false
			c.show_speed_gauge = false
			c.show_angle_gauges = false
			c.arc_length_band = Vector4(2.0, 3.2, 1.0, 4.5)
			c.speed_band = Vector4(2.3, 3.7, 1.5, 4.8)
			c.work_band = Vector4(89.0, 91.0, 87.0, 93.0)
			c.travel_band = Vector4(8.0, 14.0, 0.0, 21.0)
			c.current_band = Vector4(100.0, 125.0, 88.0, 138.0)
			c.lateral_band = Vector4(0.0, 0.5, 0.0, 1.5)
			c.width_band = Vector4(5.5, 8.0, 3.5, 10.0)
			c.penetration_band = Vector4(2.2, 4.0, 1.0, 6.5)
			c.consumption_scale = 1.4
	return c
