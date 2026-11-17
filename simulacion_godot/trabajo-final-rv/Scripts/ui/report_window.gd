class_name ReportWindow
extends CanvasLayer
## Ventana con el informe de desempeño al terminar el ejercicio:
## nota 1-10, puntaje por categoría, penalizaciones, diagnóstico y métricas.

signal retry_requested
signal next_requested
signal menu_requested

const COLOR_OK := Color(0.35, 0.9, 0.5)
const COLOR_WARN := Color(1.0, 0.8, 0.25)
const COLOR_BAD := Color(1.0, 0.4, 0.35)

var _root: Control
var _content: VBoxContainer
var _next_button: Button


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	layer = 30
	add_to_group("report_window")
	_build()
	visible = false


func show_report(report: Dictionary, has_next_level: bool) -> void:
	_populate(report)
	_next_button.visible = has_next_level and bool(report.get("passed", false))
	visible = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _build() -> void:
	_root = ColorRect.new()
	(_root as ColorRect).color = Color(0.0, 0.0, 0.0, 0.8)
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_root)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 36)
	_root.add_child(margin)

	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.09, 0.1, 0.12, 0.98)
	style.set_corner_radius_all(10)
	style.set_content_margin_all(18.0)
	panel.add_theme_stylebox_override("panel", style)
	margin.add_child(panel)

	var outer := VBoxContainer.new()
	outer.add_theme_constant_override("separation", 10)
	panel.add_child(outer)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	outer.add_child(scroll)
	_content = VBoxContainer.new()
	_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_content.add_theme_constant_override("separation", 8)
	scroll.add_child(_content)

	var buttons := HBoxContainer.new()
	buttons.alignment = BoxContainer.ALIGNMENT_CENTER
	buttons.add_theme_constant_override("separation", 14)
	outer.add_child(buttons)
	_add_button(buttons, "Reintentar", func() -> void: retry_requested.emit())
	_next_button = _add_button(buttons, "Siguiente nivel", func() -> void: next_requested.emit())
	_add_button(buttons, "Menú principal", func() -> void: menu_requested.emit())


func _add_button(parent: Control, text: String, action: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(190.0, 44.0)
	b.pressed.connect(action)
	parent.add_child(b)
	return b


func _populate(report: Dictionary) -> void:
	for child in _content.get_children():
		_content.remove_child(child)
		child.queue_free()

	var grade: float = report["grade"]
	var passed: bool = report["passed"]
	var grade_color := COLOR_OK if passed else COLOR_BAD

	_text("INFORME DE DESEMPEÑO - %s" % String(report["level_name"]), 20, Color(0.8, 0.85, 0.95))
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 24)
	_content.add_child(head)
	var big := Label.new()
	big.text = "%.1f / 10" % grade
	big.add_theme_font_size_override("font_size", 56)
	big.add_theme_color_override("font_color", grade_color)
	head.add_child(big)
	var verdict := VBoxContainer.new()
	verdict.alignment = BoxContainer.ALIGNMENT_CENTER
	head.add_child(verdict)
	var lbl := Label.new()
	lbl.text = String(report["grade_label"]).to_upper()
	lbl.add_theme_font_size_override("font_size", 26)
	lbl.add_theme_color_override("font_color", grade_color)
	verdict.add_child(lbl)
	var pass_lbl := Label.new()
	pass_lbl.text = ("APROBADO" if passed else "NO APROBADO") + " (mínimo %.1f)" % LevelConfig.PASS_GRADE
	verdict.add_child(pass_lbl)

	_separator()
	_text("Evaluación por criterio", 18, Color.WHITE)
	var cats: Array = report["categories"]
	for c in cats:
		_category_row(c)

	var penalties: Array = report["penalties"]
	if not penalties.is_empty():
		_separator()
		_text("Penalizaciones", 18, Color.WHITE)
		for p in penalties:
			var pd: Dictionary = p
			_text("-%.1f  %s" % [float(pd["points"]), String(pd["label"])], 14, COLOR_BAD)

	_separator()
	_text("Diagnóstico y recomendaciones", 18, Color.WHITE)
	var diags: Array = report["diagnostics"]
	for d in diags:
		var dd: Dictionary = d
		var sev: String = dd["severity"]
		var color := COLOR_OK
		var mark := "OK"
		if sev == "bad":
			color = COLOR_BAD
			mark = "!!"
		elif sev == "warn":
			color = COLOR_WARN
			mark = "!"
		_text("[%s] %s" % [mark, String(dd["text"])], 14, color)

	_separator()
	_text("Métricas de la pasada", 18, Color.WHITE)
	var s: Dictionary = report["stats"]
	var lines := [
		"Duración del ejercicio: %.0f s (arco encendido %.0f s)" % [float(s["duration_s"]), float(s["arc_time_s"])],
		"Cordón: %.0f mm depositados, %.0f %% de la junta" % [float(s["bead_length_mm"]), float(s["coverage_pct"])],
		"Velocidad media: %.1f mm/s  |  Arco medio: %.1f mm" % [float(s["avg_speed_mm_s"]), float(s["avg_arc_length_mm"])],
		"Ancho medio: %.1f mm  |  Penetración media: %.1f mm  |  Mordedura máx.: %.1f mm" % [
			float(s["avg_width_mm"]), float(s["avg_penetration_mm"]), float(s["max_undercut_mm"])],
		"Corriente: %.0f A  |  Electrodo consumido: %.0f mm" % [float(s["current_a"]), float(s["electrode_used_mm"])],
		"Electrodo pegado: %d  |  Arco apagado: %d  |  Interrupciones del cordón: %d" % [
			int(s["stick_events"]), int(s["out_events"]), int(s.get("interruptions", 0))],
	]
	for line in lines:
		_text(String(line), 14, Color(0.85, 0.85, 0.85))


func _category_row(c: Dictionary) -> void:
	var score: float = c["score"]
	var color := COLOR_OK if score >= 0.75 else (COLOR_WARN if score >= 0.45 else COLOR_BAD)
	var row := VBoxContainer.new()
	_content.add_child(row)
	var top := HBoxContainer.new()
	row.add_child(top)
	var name_lbl := Label.new()
	name_lbl.text = "%s  (peso %.0f)" % [String(c["label"]), float(c["weight"])]
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(name_lbl)
	var pct := Label.new()
	pct.text = "%.0f %%" % (score * 100.0)
	pct.add_theme_color_override("font_color", color)
	top.add_child(pct)
	var bar := ProgressBar.new()
	bar.show_percentage = false
	bar.min_value = 0.0
	bar.max_value = 100.0
	bar.value = score * 100.0
	bar.custom_minimum_size = Vector2(0.0, 8.0)
	bar.add_theme_stylebox_override("fill", _fill_style(color))
	row.add_child(bar)
	var detail := Label.new()
	detail.text = String(c["detail"])
	detail.add_theme_font_size_override("font_size", 12)
	detail.add_theme_color_override("font_color", Color(0.65, 0.65, 0.7))
	row.add_child(detail)


func _fill_style(color: Color) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(3)
	return sb


func _text(text: String, size: int, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	_content.add_child(l)
	return l


func _separator() -> void:
	_content.add_child(HSeparator.new())
