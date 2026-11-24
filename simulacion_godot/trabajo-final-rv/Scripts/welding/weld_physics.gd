class_name WeldPhysics
extends RefCounted
## Modelo físico simplificado del proceso SMAW (electrodo E6013 Ø3,2 mm, DCEP).
##
## Son aproximaciones de ingeniería calibradas para que, con los parámetros
## nominales (110 A, arco de 2,5 mm, 3 mm/s), el cordón resulte de ~7 mm de
## ancho, ~2,3 mm de altura y ~2 mm de penetración, valores típicos de
## práctica en chapa de 10 mm. No pretende ser un modelo metalúrgico.

const ELECTRODE_DIAMETER_MM := 3.2
const ELECTRODE_LENGTH_MM := 350.0
const ELECTRODE_STUB_MM := 50.0     # colilla que no se puede consumir
const PLATE_THICKNESS_MM := 10.0

const STICK_GAP_MM := 0.8           # por debajo: cortocircuito / electrodo pegado
const OPTIMAL_GAP_MIN_MM := 1.5
const OPTIMAL_GAP_MAX_MM := 3.5
const EXTINGUISH_GAP_MM := 6.0      # por encima: el arco se apaga

const MIN_SPEED_MM_S := 0.3         # evita divisiones por cero


## Tensión de arco aproximada [V]: sube con la corriente y con la longitud de arco.
static func arc_voltage(current_a: float, arc_len_mm: float) -> float:
	return 18.0 + 0.04 * current_a + 1.2 * arc_len_mm


## Aporte térmico [J/mm] con rendimiento térmico del 80 %.
static func heat_input_j_mm(current_a: float, speed_mm_s: float, arc_len_mm: float) -> float:
	var v := maxf(speed_mm_s, MIN_SPEED_MM_S)
	return 0.8 * arc_voltage(current_a, arc_len_mm) * current_a / v


## Tasa de deposición de metal [mm³/s].
static func deposition_rate_mm3_s(current_a: float) -> float:
	return 0.29 * current_a


## Velocidad de consumo de la varilla [mm/s] (≈ 4 mm/s a 110 A).
static func burn_rate_mm_s(current_a: float) -> float:
	var core_area := PI * 0.25 * ELECTRODE_DIAMETER_MM * ELECTRODE_DIAMETER_MM
	return deposition_rate_mm3_s(current_a) / core_area


static func bead_width_mm(current_a: float, speed_mm_s: float, arc_len_mm: float) -> float:
	var w := 0.2565 * sqrt(heat_input_j_mm(current_a, speed_mm_s, arc_len_mm))
	# Un arco largo ensancha y aplana el baño.
	w *= 1.0 + 0.04 * maxf(arc_len_mm - OPTIMAL_GAP_MAX_MM, 0.0)
	return clampf(w, 2.0, 16.0)


static func bead_height_mm(current_a: float, speed_mm_s: float, width_mm: float) -> float:
	var area := deposition_rate_mm3_s(current_a) / maxf(speed_mm_s, MIN_SPEED_MM_S)
	return clampf(area / (0.667 * maxf(width_mm, 0.5)), 0.3, 6.0)


## Penetración [mm]. El arrastre (drag) aumenta la penetración y el empuje (push) la reduce.
static func penetration_mm(current_a: float, speed_mm_s: float, arc_len_mm: float, drag_deg: float) -> float:
	var v := maxf(speed_mm_s, MIN_SPEED_MM_S)
	var p := 2.0 * (current_a / 110.0) * sqrt(3.0 / v)
	p *= clampf(1.0 - 0.10 * (arc_len_mm - 2.5), 0.5, 1.1)
	p *= clampf(1.0 + 0.015 * (clampf(drag_deg, -15.0, 25.0) - 10.0), 0.85, 1.2)
	return clampf(p, 0.0, 9.0)


## Profundidad estimada de mordedura (undercut) [mm]. AWS D1.1 admite hasta 1 mm.
static func undercut_mm(current_a: float, speed_mm_s: float) -> float:
	var u := maxf(speed_mm_s - 4.5, 0.0) * 0.3 + maxf(current_a - 135.0, 0.0) * 0.015
	return clampf(u, 0.0, 2.0)
