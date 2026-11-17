class_name WeldEvaluator
extends RefCounted
## Evaluador del desempeño del operario.
##
## Acumula muestras mientras el arco está encendido y, al finalizar, produce un
## informe con una nota de 1 a 10. Criterios basados en la técnica CLAMS
## (Current, Length of arc, Angle, Manipulation, Speed; Miller Electric,
## Lincoln Electric, ESAB) y en la inspección visual de AWS D1.1.
##
## Es lógica pura (RefCounted, sin nodos): se puede probar sin escena.

## Categorías evaluadas, en el orden en que se muestran, con su peso (suma = 100).
const CATEGORIES: Array[Dictionary] = [
	{"id": "arc_length", "label": "Longitud de arco", "weight": 15.0},
	{"id": "speed", "label": "Velocidad de avance", "weight": 15.0},
	{"id": "work_angle", "label": "Ángulo de trabajo", "weight": 10.0},
	{"id": "travel_angle", "label": "Ángulo de avance", "weight": 10.0},
	{"id": "current", "label": "Amperaje", "weight": 5.0},
	{"id": "path", "label": "Trayectoria (centrado en la junta)", "weight": 10.0},
	{"id": "width", "label": "Ancho del cordón", "weight": 10.0},
	{"id": "regularity", "label": "Regularidad del cordón", "weight": 10.0},
	{"id": "penetration", "label": "Penetración", "weight": 10.0},
	{"id": "coverage", "label": "Continuidad y cobertura", "weight": 5.0},
]

# Penalizaciones sobre la nota final (en puntos de la escala 1-10).
const PENALTY_STICK := 0.5
const PENALTY_STICK_CAP := 2.0
const PENALTY_OUT := 0.3
const PENALTY_OUT_CAP := 1.2
const PENALTY_SAFETY_PER_S := 0.4
const PENALTY_SAFETY_CAP := 2.5

const MIN_ARC_TIME_S := 2.0         # por debajo no se considera que hubo soldadura
const INCOMPLETE_GRADE_CAP := 4.0   # tope de nota si el cordón cubre menos del 50 %


## Estadística ponderada incremental (algoritmo de West).
class Stat:
	var wsum: float = 0.0
	var mean: float = 0.0
	var _s: float = 0.0

	func add(x: float, w: float) -> void:
		if w <= 0.0:
			return
		wsum += w
		var d := x - mean
		mean += (w / wsum) * d
		_s += w * d * (x - mean)

	func stdev() -> float:
		return sqrt(maxf(_s / wsum, 0.0)) if wsum > 0.0 else 0.0


var level: LevelConfig
var current_a: float = 0.0

var _arc_time: float = 0.0
var _long_arc_time: float = 0.0
var _max_undercut: float = 0.0
var _stick_events: int = 0
var _out_events: int = 0
var _safety_s: float = 0.0

# Medias (ponderadas por tiempo) de las magnitudes medidas.
var _arc: Stat = Stat.new()
var _speed: Stat = Stat.new()
var _work: Stat = Stat.new()
var _travel: Stat = Stat.new()
var _lateral: Stat = Stat.new()
var _width: Stat = Stat.new()
var _height: Stat = Stat.new()
var _pen: Stat = Stat.new()
# Puntajes instantáneos medios por categoría.
var _sc_arc: Stat = Stat.new()
var _sc_speed: Stat = Stat.new()
var _sc_work: Stat = Stat.new()
var _sc_travel: Stat = Stat.new()
var _sc_path: Stat = Stat.new()
var _sc_width: Stat = Stat.new()
var _sc_pen: Stat = Stat.new()


func setup(level_config: LevelConfig, set_current_a: float) -> void:
	level = level_config
	current_a = set_current_a


## Registra una muestra de arco encendido de duración dt (s).
## Claves de d: arc_len, speed (<0 si no es válida), work, travel, lateral,
## width, height, penetration, undercut.
func add_sample(dt: float, d: Dictionary) -> void:
	if dt <= 0.0:
		return
	var arc_len: float = d["arc_len"]
	var work: float = d["work"]
	var travel: float = d["travel"]
	var lateral: float = absf(d["lateral"])
	var width: float = d["width"]
	var pen: float = d["penetration"]

	_arc_time += dt
	if arc_len > WeldPhysics.OPTIMAL_GAP_MAX_MM:
		_long_arc_time += dt
	_max_undercut = maxf(_max_undercut, float(d["undercut"]))

	_arc.add(arc_len, dt)
	_sc_arc.add(WeldGeometry.band_score(arc_len, level.arc_length_band), dt)
	_work.add(work, dt)
	_sc_work.add(WeldGeometry.band_score(work, level.work_band), dt)
	_travel.add(travel, dt)
	_sc_travel.add(WeldGeometry.band_score(travel, level.travel_band), dt)
	_lateral.add(lateral, dt)
	_sc_path.add(WeldGeometry.band_score(lateral, level.lateral_band), dt)
	_width.add(width, dt)
	_sc_width.add(WeldGeometry.band_score(width, level.width_band), dt)
	_height.add(float(d["height"]), dt)
	_pen.add(pen, dt)
	_sc_pen.add(WeldGeometry.band_score(pen, level.penetration_band), dt)

	var speed: float = d["speed"]
	if speed >= 0.0:
		_speed.add(speed, dt)
		_sc_speed.add(WeldGeometry.band_score(speed, level.speed_band), dt)


func add_stick_event() -> void:
	_stick_events += 1


func add_out_event() -> void:
	_out_events += 1


func add_safety_time(dt: float) -> void:
	_safety_s += maxf(dt, 0.0)


func arc_time() -> float:
	return _arc_time


## Puntaje [0..1] en vivo de un parámetro de proceso (para el HUD), sin acumular.
func live_score_arc(arc_len: float) -> float:
	return WeldGeometry.band_score(arc_len, level.arc_length_band)


## Genera el informe final. ctx: coverage (0..1), bead_length_mm,
## electrode_used_mm, duration_s.
func finalize(ctx: Dictionary) -> Dictionary:
	var coverage: float = clampf(float(ctx.get("coverage", 0.0)), 0.0, 1.0)
	var welded := _arc_time >= MIN_ARC_TIME_S

	var scores := {
		"arc_length": _sc_arc.mean if welded else 0.0,
		"speed": _sc_speed.mean if (welded and _sc_speed.wsum > 0.0) else 0.0,
		"work_angle": _sc_work.mean if welded else 0.0,
		"travel_angle": _sc_travel.mean if welded else 0.0,
		"current": WeldGeometry.band_score(current_a, level.current_band),
		"path": _sc_path.mean if welded else 0.0,
		"width": _sc_width.mean if welded else 0.0,
		"regularity": _regularity_score() if welded else 0.0,
		"penetration": _sc_pen.mean if welded else 0.0,
		"coverage": clampf(coverage / 0.95, 0.0, 1.0),
	}
	var details := _category_details(coverage)

	var raw := 0.0
	var categories: Array[Dictionary] = []
	for c in CATEGORIES:
		var id: String = c["id"]
		var weight: float = c["weight"]
		var sc: float = scores[id]
		raw += weight * sc / 100.0
		categories.append({"id": id, "label": c["label"], "weight": weight, "score": sc, "detail": details[id]})

	var penalties: Array[Dictionary] = []
	var penalty_total := 0.0
	if _stick_events > 0:
		var p := minf(_stick_events * PENALTY_STICK, PENALTY_STICK_CAP)
		penalties.append({"label": "Electrodo pegado (%d vez/veces)" % _stick_events, "points": p})
		penalty_total += p
	if _out_events > 0:
		var p := minf(_out_events * PENALTY_OUT, PENALTY_OUT_CAP)
		penalties.append({"label": "Arco apagado por mala técnica (%d vez/veces)" % _out_events, "points": p})
		penalty_total += p
	if _safety_s > 0.05:
		var p := minf(_safety_s * PENALTY_SAFETY_PER_S, PENALTY_SAFETY_CAP)
		penalties.append({"label": "Soldar sin careta (%.1f s)" % _safety_s, "points": p})
		penalty_total += p

	var grade := 1.0 + 9.0 * raw - penalty_total
	if coverage < 0.5:
		grade = minf(grade, INCOMPLETE_GRADE_CAP)
	if not welded:
		grade = 1.0
	grade = snappedf(clampf(grade, 1.0, 10.0), 0.1)

	return {
		"level_id": level.id,
		"level_name": level.display_name,
		"grade": grade,
		"grade_label": grade_label(grade),
		"passed": grade >= LevelConfig.PASS_GRADE,
		"raw_score": raw,
		"categories": categories,
		"penalties": penalties,
		"diagnostics": _diagnostics(coverage, welded),
		"stats": {
			"duration_s": float(ctx.get("duration_s", 0.0)),
			"arc_time_s": _arc_time,
			"bead_length_mm": float(ctx.get("bead_length_mm", 0.0)),
			"coverage_pct": coverage * 100.0,
			"avg_speed_mm_s": _speed.mean,
			"avg_arc_length_mm": _arc.mean,
			"avg_work_deviation_deg": _work.mean,
			"avg_travel_angle_deg": _travel.mean,
			"avg_width_mm": _width.mean,
			"avg_penetration_mm": _pen.mean,
			"max_undercut_mm": _max_undercut,
			"current_a": current_a,
			"electrode_used_mm": float(ctx.get("electrode_used_mm", 0.0)),
			"stick_events": _stick_events,
			"out_events": _out_events,
			"safety_s": _safety_s,
		},
	}


static func grade_label(grade: float) -> String:
	if grade >= 9.0:
		return "Excelente"
	if grade >= 8.0:
		return "Muy bueno"
	if grade >= 7.0:
		return "Bueno"
	if grade >= LevelConfig.PASS_GRADE:
		return "Aprobado"
	if grade >= 4.0:
		return "Insuficiente"
	return "Deficiente"


# ---------------------------------------------------------------------------

## Regularidad: variación del ancho (60 %), de la altura (20 %) y constancia de
## los ángulos de la herramienta (20 %). Un coeficiente de variación del ancho
## <= 8 % es excelente y >= 30 % es nulo.
func _regularity_score() -> float:
	var cv_w := _width.stdev() / maxf(_width.mean, 0.001)
	var cv_h := _height.stdev() / maxf(_height.mean, 0.001)
	var s_w := 1.0 - clampf((cv_w - 0.08) / (0.30 - 0.08), 0.0, 1.0)
	var s_h := 1.0 - clampf((cv_h - 0.08) / (0.35 - 0.08), 0.0, 1.0)
	var ang_sd := maxf(_work.stdev(), _travel.stdev())
	var s_a := 1.0 - clampf((ang_sd - 3.0) / (10.0 - 3.0), 0.0, 1.0)
	return 0.6 * s_w + 0.2 * s_h + 0.2 * s_a


func _band_text(b: Vector4, unit: String) -> String:
	return "%.1f a %.1f %s" % [b.x, b.y, unit]


func _category_details(coverage: float) -> Dictionary:
	var has := _arc_time >= MIN_ARC_TIME_S
	var na := "Sin datos"
	return {
		"arc_length": ("Promedio %.1f mm (objetivo %s)" % [_arc.mean, _band_text(level.arc_length_band, "mm")]) if has else na,
		"speed": ("Promedio %.1f mm/s (objetivo %s)" % [_speed.mean, _band_text(level.speed_band, "mm/s")]) if _speed.wsum > 0.0 else na,
		"work_angle": ("Desvío medio %+.1f° respecto de 90° (tolerancia ±%.0f°)" % [_work.mean, level.work_band.y]) if has else na,
		"travel_angle": ("Promedio %.1f° de arrastre (objetivo %s)" % [_travel.mean, _band_text(level.travel_band, "°")]) if has else na,
		"current": "%.0f A (objetivo %s para E6013 Ø3,2 mm)" % [current_a, _band_text(level.current_band, "A")],
		"path": ("Desvío medio %.1f mm del eje (tolerancia %.1f mm)" % [_lateral.mean, level.lateral_band.y]) if has else na,
		"width": ("Ancho medio %.1f mm (objetivo %s)" % [_width.mean, _band_text(level.width_band, "mm")]) if has else na,
		"regularity": ("Variación del ancho %.0f %%, desvío angular %.1f°" % [
			100.0 * _width.stdev() / maxf(_width.mean, 0.001), maxf(_work.stdev(), _travel.stdev())]) if has else na,
		"penetration": ("Penetración media %.1f mm (objetivo %s)" % [_pen.mean, _band_text(level.penetration_band, "mm")]) if has else na,
		"coverage": "Cordón depositado sobre el %.0f %% de la junta" % (coverage * 100.0),
	}


## Matriz diagnóstica: causa física -> defecto probable -> corrección sugerida.
func _diagnostics(coverage: float, welded: bool) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	if not welded:
		out.append({"severity": "bad", "text": "No se detectó soldadura: encendé el arco (clic izquierdo o gatillo) con el electrodo a 1,5-3,5 mm de la chapa y avanzá por la junta."})
		return out

	# Longitud de arco
	var long_frac := _long_arc_time / maxf(_arc_time, 0.001)
	if _arc.mean > level.arc_length_band.y or long_frac > 0.2:
		out.append({"severity": "bad", "text": "Arco largo (%.0f %% del tiempo): provoca salpicaduras, porosidad y mordeduras. Mantené el arco cercano al diámetro del electrodo (1,5-3,5 mm)." % (long_frac * 100.0)})
	elif _arc.mean < level.arc_length_band.x:
		out.append({"severity": "warn", "text": "Arco demasiado corto: riesgo de pegado del electrodo y cordón alto y angosto. Levantá levemente la herramienta."})
	# Velocidad
	if _speed.wsum > 0.0:
		if _speed.mean > level.speed_band.y:
			out.append({"severity": "bad", "text": "Avance demasiado rápido: cordón angosto con falta de penetración y riesgo de mordeduras (undercut). Reducí la velocidad."})
		elif _speed.mean < level.speed_band.x:
			out.append({"severity": "warn", "text": "Avance demasiado lento: cordón ancho y alto, exceso de aporte térmico e inclusiones de escoria. Avanzá más rápido."})
	# Ángulos
	if absf(_work.mean) > level.work_band.y:
		out.append({"severity": "warn", "text": "Ángulo de trabajo desviado %.0f° de la perpendicular: el aporte de calor queda desbalanceado entre las dos chapas (falta de fusión de un lado)." % _work.mean})
	if _travel.mean < level.travel_band.x:
		out.append({"severity": "warn", "text": "Ángulo de avance insuficiente o en empuje: la escoria se adelanta al baño y hay inclusiones de escoria. Usá arrastre de 5-15°."})
	elif _travel.mean > level.travel_band.y:
		out.append({"severity": "warn", "text": "Ángulo de avance excesivo: el arco pierde dirección y se reduce la protección del baño. Reducí la inclinación."})
	if maxf(_work.stdev(), _travel.stdev()) > 6.0:
		out.append({"severity": "warn", "text": "Los ángulos variaron durante la pasada: mantené la misma inclinación de punta a punta para evitar falta de fusión."})
	# Corriente y penetración
	if current_a < level.current_band.x:
		out.append({"severity": "warn", "text": "Amperaje bajo (%.0f A): arco inestable, electrodo pegajoso y poca penetración." % current_a})
	elif current_a > level.current_band.y:
		out.append({"severity": "warn", "text": "Amperaje alto (%.0f A): sobrecalentamiento del electrodo, salpicaduras y mordeduras." % current_a})
	if _pen.mean < level.penetration_band.x:
		out.append({"severity": "warn", "text": "Penetración insuficiente (%.1f mm): subí el amperaje o reducí la velocidad de avance." % _pen.mean})
	elif _pen.mean >= 0.8 * WeldPhysics.PLATE_THICKNESS_MM:
		out.append({"severity": "bad", "text": "Penetración excesiva: riesgo de perforar la chapa (burn-through). Bajá el amperaje o avanzá más rápido."})
	if _max_undercut > 1.0:
		out.append({"severity": "bad", "text": "Mordedura estimada de %.1f mm: supera el límite de 1 mm de la inspección visual AWS D1.1." % _max_undercut})
	# Trayectoria y regularidad
	if _lateral.mean > level.lateral_band.y:
		out.append({"severity": "warn", "text": "El cordón se desvió %.1f mm del eje de la junta: guiá la punta sobre la raíz." % _lateral.mean})
	if _width.mean > 0.0 and _width.stdev() / _width.mean > 0.2:
		out.append({"severity": "warn", "text": "Ancho irregular del cordón: practicá un avance y una distancia de arco constantes."})
	# Cobertura
	if coverage < 0.9:
		out.append({"severity": "bad", "text": "Cordón incompleto: cubriste solo el %.0f %% de la junta. Soldá de punta a punta sin interrupciones." % (coverage * 100.0)})
	# Eventos
	if _stick_events > 0:
		out.append({"severity": "warn", "text": "El electrodo se pegó %d vez/veces. Cebá con un movimiento rápido y levantá hasta ~2-3 mm." % _stick_events})
	if _out_events > 0:
		out.append({"severity": "warn", "text": "El arco se apagó %d vez/veces por separarte demasiado." % _out_events})
	if _safety_s > 0.05:
		out.append({"severity": "bad", "text": "Soldaste %.1f s sin la careta bajada: la radiación del arco daña la vista. Bajá siempre la careta (Q) antes de cebar." % _safety_s})

	if out.is_empty():
		out.append({"severity": "ok", "text": "Técnica muy pareja: todos los parámetros CLAMS dentro de tolerancia."})
	return out
