class_name SessionRecorder
extends RefCounted
## Registra la pasada del operario (a ~20 Hz) junto con los valores ideales
## del nivel, para graficarla en el informe y exportarla a CSV.

const SAMPLE_INTERVAL_S := 0.05
const EXPORT_FOLDER := "SimuladorSoldadura"

## Columnas de la serie temporal: [clave, encabezado CSV].
const COLUMNS: Array[Array] = [
	["t", "tiempo_s"],
	["arc", "arco_encendido"],
	["s", "posicion_avance_mm"],
	["v", "desvio_lateral_mm"],
	["v_ideal", "desvio_ideal_mm"],
	["speed", "velocidad_mm_s"],
	["speed_ideal", "velocidad_ideal_mm_s"],
	["speed_min", "velocidad_ideal_min_mm_s"],
	["speed_max", "velocidad_ideal_max_mm_s"],
	["gap", "distancia_arco_mm"],
	["gap_ideal", "distancia_ideal_mm"],
	["gap_min", "distancia_ideal_min_mm"],
	["gap_max", "distancia_ideal_max_mm"],
	["work", "angulo_trabajo_deg"],
	["work_ideal", "angulo_trabajo_ideal_deg"],
	["work_min", "angulo_trabajo_ideal_min_deg"],
	["work_max", "angulo_trabajo_ideal_max_deg"],
	["travel", "angulo_avance_deg"],
	["travel_ideal", "angulo_avance_ideal_deg"],
	["travel_min", "angulo_avance_ideal_min_deg"],
	["travel_max", "angulo_avance_ideal_max_deg"],
	["current", "corriente_A"],
	["current_ideal", "corriente_ideal_A"],
	["current_min", "corriente_ideal_min_A"],
	["current_max", "corriente_ideal_max_A"],
	["width", "ancho_cordon_mm"],
	["penetration", "penetracion_mm"],
	["mask", "careta_baja"],
]

var level: LevelConfig
var current_a: float = 0.0
var rows: Array[Dictionary] = []

var _timer: float = 0.0


func setup(level_config: LevelConfig, set_current_a: float) -> void:
	level = level_config
	current_a = set_current_a
	rows.clear()
	_timer = 0.0


## Valor ideal (centro de la banda óptima) de un parámetro.
static func ideal_of(band: Vector4) -> float:
	return (band.x + band.y) * 0.5


## Se llama en cada paso de física. d: t, arc (bool), s, v, speed, gap, work,
## travel, width, penetration, mask (bool).
func sample(delta: float, d: Dictionary) -> void:
	_timer += delta
	if _timer < SAMPLE_INTERVAL_S:
		return
	_timer = fmod(_timer, SAMPLE_INTERVAL_S)
	var row := d.duplicate()
	row["arc"] = 1 if bool(d["arc"]) else 0
	row["mask"] = 1 if bool(d["mask"]) else 0
	row["v_ideal"] = 0.0
	row["speed_ideal"] = ideal_of(level.speed_band)
	row["speed_min"] = level.speed_band.x
	row["speed_max"] = level.speed_band.y
	row["gap_ideal"] = ideal_of(level.arc_length_band)
	row["gap_min"] = level.arc_length_band.x
	row["gap_max"] = level.arc_length_band.y
	row["work_ideal"] = ideal_of(level.work_band)
	row["work_min"] = level.work_band.x
	row["work_max"] = level.work_band.y
	row["travel_ideal"] = ideal_of(level.travel_band)
	row["travel_min"] = level.travel_band.x
	row["travel_max"] = level.travel_band.y
	row["current"] = current_a
	row["current_ideal"] = ideal_of(level.current_band)
	row["current_min"] = level.current_band.x
	row["current_max"] = level.current_band.y
	rows.append(row)


## Serie de una columna. Si only_arc, las muestras sin arco valen NAN (cortan la línea).
func series(key: String, only_arc: bool = true) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	for r in rows:
		if only_arc and int(r["arc"]) == 0:
			out.append(NAN)
		else:
			out.append(float(r[key]))
	return out


## Genera el texto CSV (separador ";", decimales con coma, listo para Excel en español).
func to_csv(report: Dictionary) -> String:
	var lines: PackedStringArray = []
	lines.append("sep=;")
	lines.append("# RESUMEN DEL EJERCICIO")
	lines.append("fecha;%s" % Time.get_datetime_string_from_system(false, true))
	lines.append("nivel;%s" % String(report["level_name"]))
	lines.append("nota_final_1_a_10;%s" % _num(float(report["grade"]), 1))
	lines.append("resultado;%s" % ("APROBADO" if bool(report["passed"]) else "NO APROBADO"))
	lines.append("calificacion;%s" % String(report["grade_label"]))
	lines.append("")
	lines.append("# CRITERIOS")
	lines.append("criterio;peso;puntaje_0_a_100;detalle")
	for c in report["categories"]:
		var cd: Dictionary = c
		lines.append("%s;%s;%s;%s" % [_txt(cd["label"]), _num(float(cd["weight"]), 0),
			_num(float(cd["score"]) * 100.0, 0), _txt(cd["detail"])])
	lines.append("")
	lines.append("# PENALIZACIONES")
	lines.append("motivo;puntos")
	for p in report["penalties"]:
		var pd: Dictionary = p
		lines.append("%s;%s" % [_txt(pd["label"]), _num(float(pd["points"]), 1)])
	lines.append("")
	lines.append("# DIAGNOSTICO")
	for d in report["diagnostics"]:
		lines.append(_txt((d as Dictionary)["text"]))
	lines.append("")
	lines.append("# METRICAS")
	var stats: Dictionary = report["stats"]
	var keys := stats.keys()
	keys.sort()
	for k in keys:
		lines.append("%s;%s" % [str(k), _num(float(stats[k]), 2)])
	lines.append("")
	lines.append("# SERIE TEMPORAL (una fila cada %s s)" % _num(SAMPLE_INTERVAL_S, 2))
	var header := PackedStringArray()
	for c in COLUMNS:
		header.append(String(c[1]))
	lines.append(";".join(header))
	for r in rows:
		var cells := PackedStringArray()
		for c in COLUMNS:
			cells.append(_num(float(r[c[0]]), 3))
		lines.append(";".join(cells))
	return "\n".join(lines) + "\n"


## Guarda el CSV (con BOM UTF-8 para que Excel muestre bien las tildes).
## Devuelve la ruta del archivo, o "" si falló.
func export_csv(report: Dictionary, folder_override: String = "") -> String:
	var folder := folder_override
	if folder.is_empty():
		folder = OS.get_system_dir(OS.SYSTEM_DIR_DOCUMENTS).path_join(EXPORT_FOLDER)
	if DirAccess.make_dir_recursive_absolute(folder) != OK and not DirAccess.dir_exists_absolute(folder):
		folder = ProjectSettings.globalize_path("user://")
		DirAccess.make_dir_recursive_absolute(folder)
	var stamp := Time.get_datetime_string_from_system(false, false).replace("-", "").replace(":", "").replace("T", "_").replace(" ", "_")
	var path := folder.path_join("informe_nivel%d_%s.csv" % [int(report["level_id"]), stamp])
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		push_warning("No se pudo escribir " + path)
		return ""
	f.store_buffer(PackedByteArray([0xEF, 0xBB, 0xBF]))
	f.store_string(to_csv(report))
	f.close()
	return path


static func _num(x: float, decimals: int) -> String:
	if is_nan(x) or is_inf(x):
		return ""
	return String.num(x, decimals).replace(".", ",")


static func _txt(v: Variant) -> String:
	return str(v).replace(";", ",").replace("\n", " ")
