class_name Hud
extends CanvasLayer
## Interfaz en pantalla del ejercicio: estado, lista de verificación,
## indicadores de proceso, electrodo, mensajes y menú de pausa.
## Todo se construye por código; el controlador del ejercicio solo llama a esta API.

signal pause_requested
signal resume_requested
signal restart_requested
signal menu_requested

const COLOR_OK := Color(0.35, 0.9, 0.5)
const COLOR_PENDING := Color(0.85, 0.85, 0.85)
const COLOR_WARN := Color(1.0, 0.8, 0.25)
const COLOR_BAD := Color(1.0, 0.35, 0.3)

var level: LevelConfig

var _status_label: Label
var _phase_label: Label
var _checklist_box: VBoxContainer
var _checklist_panel: PanelContainer
var _crosshair: ColorRect
var _prompt_label: Label
var _message_label: Label
var _help_label: Label
var _gauge_panel: PanelContainer
var _arc_gauge: GaugeBar
var _speed_gauge: GaugeBar
var _work_gauge: GaugeBar
var _travel_gauge: GaugeBar
var _arc_state_label: Label
var _current_hint: Label
var _electrode_bar: ProgressBar
var _electrode_label: Label
var _amps_label: Label
var _progress_bar: ProgressBar
var _progress_label: Label
var _guide_panel: PanelContainer
var _guide_frame: Panel
var _guide_frame_style: StyleBoxFlat
var _guide_swatches: Dictionary = {}
var _guide_hints: Dictionary = {}
var _pause_panel: Control
var _message_tween: Tween
var _status_timer: float = 0.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	layer = 25  # por encima de la careta (20): los mensajes deben verse con ella baja
	_build()
	Events.hud_message.connect(show_message)


func setup(level_config: LevelConfig) -> void:
	level = level_config
	_arc_gauge.configure("Longitud de arco", "mm", 0.0, 8.0, level.arc_length_band, 1)
	_speed_gauge.configure("Velocidad de avance", "mm/s", 0.0, 8.0, level.speed_band, 1)
	_work_gauge.configure("Ángulo de trabajo (desvío)", "°", -30.0, 30.0, level.work_band, 0)
	_travel_gauge.configure("Ángulo de avance (arrastre)", "°", -15.0, 45.0, level.travel_band, 0)
	_arc_gauge.visible = level.show_arc_gauge
	_speed_gauge.visible = level.show_speed_gauge
	_work_gauge.visible = level.show_angle_gauges
	_travel_gauge.visible = level.show_angle_gauges
	_current_hint.visible = level.show_current_hint
	if level.show_current_hint:
		_current_hint.text = "Amperaje recomendado: %.0f-%.0f A" % [level.current_band.x, level.current_band.y]
	_gauge_panel.visible = false


func _process(delta: float) -> void:
	_status_timer -= delta
	if _status_timer <= 0.0:
		_status_timer = 0.25
		var level_name := level.display_name if level != null else ""
		_status_label.text = "%s\n%s" % [level_name, DeviceLink.status_text()]


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("pause") and not _pause_panel.visible and not _is_report_open():
		pause_requested.emit()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("pause") and _pause_panel.visible:
		resume_requested.emit()
		get_viewport().set_input_as_handled()


func _is_report_open() -> bool:
	return get_tree().get_nodes_in_group("report_window").any(func(n: Node) -> bool: return (n as CanvasLayer).visible)


# --- API pública ---------------------------------------------------------

func set_phase(text: String) -> void:
	_phase_label.text = text


func set_prompt(text: String) -> void:
	_prompt_label.text = text
	_prompt_label.visible = not text.is_empty()


func set_crosshair_visible(value: bool) -> void:
	_crosshair.visible = value


func set_help(text: String) -> void:
	_help_label.text = text


func show_message(text: String, seconds: float = 3.0) -> void:
	_message_label.text = text
	_message_label.modulate.a = 1.0
	_message_label.visible = true
	if _message_tween != null:
		_message_tween.kill()
	_message_tween = create_tween()
	_message_tween.tween_interval(maxf(seconds, 0.5))
	_message_tween.tween_property(_message_label, "modulate:a", 0.0, 0.5)
	_message_tween.tween_callback(func() -> void: _message_label.visible = false)


## items: Array de {text: String, done: bool}.
func set_checklist(items: Array) -> void:
	for child in _checklist_box.get_children():
		_checklist_box.remove_child(child)
		child.queue_free()
	var title := Label.new()
	title.text = "Preparación del equipo"
	title.add_theme_font_size_override("font_size", 16)
	_checklist_box.add_child(title)
	for item in items:
		var d: Dictionary = item
		var lbl := Label.new()
		var done: bool = d["done"]
		lbl.text = ("[x] " if done else "[  ] ") + String(d["text"])
		lbl.add_theme_color_override("font_color", COLOR_OK if done else COLOR_PENDING)
		_checklist_box.add_child(lbl)


func set_checklist_visible(value: bool) -> void:
	_checklist_panel.visible = value and level != null and level.show_checklist


func set_gauges_visible(value: bool) -> void:
	_gauge_panel.visible = value


func update_gauges(arc_mm: float, arc_valid: bool, speed: float, work: float, travel: float) -> void:
	_arc_gauge.set_value(arc_mm, arc_valid)
	_speed_gauge.set_value(speed)
	_work_gauge.set_value(work)
	_travel_gauge.set_value(travel)


## Colores de estado de los indicadores guiados.
static func state_color(state: int) -> Color:
	match state:
		0:
			return Color(0.2, 0.85, 0.35)
		1:
			return Color(1.0, 0.8, 0.15)
		2:
			return Color(0.95, 0.2, 0.2)
	return Color(0.5, 0.5, 0.55)


func set_guides_visible(value: bool) -> void:
	var on := value and level != null and level.show_color_guides
	_guide_panel.visible = on
	_guide_frame.visible = on


## tiles: Array de {key: String, state: int (0 ok, 1 límite, 2 mal, 3 sin dato), hint: String}.
## El marco toma el color del peor estado.
func update_guides(tiles: Array) -> void:
	var worst := 0
	for t in tiles:
		var d: Dictionary = t
		var key: String = d["key"]
		var st: int = d["state"]
		if _guide_swatches.has(key):
			(_guide_swatches[key] as ColorRect).color = state_color(st)
			(_guide_hints[key] as Label).text = String(d["hint"])
		if st != 3:
			worst = maxi(worst, st)
	_guide_frame_style.border_color = state_color(worst)


func set_arc_state(text: String, color: Color) -> void:
	_arc_state_label.text = text
	_arc_state_label.add_theme_color_override("font_color", color)


func set_electrode(fraction: float, length_mm: float, count: int) -> void:
	_electrode_bar.value = fraction * 100.0
	_electrode_label.text = "Electrodo #%d: %.0f mm" % [count, length_mm]


func set_amperage(amps: float, is_on: bool) -> void:
	_amps_label.text = ("Corriente: %.0f A" % amps) if is_on else "Máquina apagada"


func set_progress(fraction: float, coverage: float) -> void:
	_progress_bar.value = clampf(fraction, 0.0, 1.0) * 100.0
	_progress_label.text = "Avance %.0f %%  -  cordón %.0f %%" % [fraction * 100.0, coverage * 100.0]


func show_pause(value: bool) -> void:
	_pause_panel.visible = value


# --- Construcción --------------------------------------------------------

func _build() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	# Estado (arriba a la izquierda)
	var top_left := _panel(root, Control.PRESET_TOP_LEFT, Vector2(12.0, 12.0))
	var top_box := VBoxContainer.new()
	top_left.add_child(top_box)
	_phase_label = _label(top_box, 18)
	_status_label = _label(top_box, 13)

	# Lista de verificación (izquierda)
	_checklist_panel = _panel(root, Control.PRESET_CENTER_LEFT, Vector2(12.0, -120.0))
	_checklist_box = VBoxContainer.new()
	_checklist_panel.add_child(_checklist_box)

	# Mira y mensajes (centro)
	_crosshair = ColorRect.new()
	_crosshair.color = Color(1.0, 1.0, 1.0, 0.8)
	_crosshair.custom_minimum_size = Vector2(4.0, 4.0)
	_crosshair.size = Vector2(4.0, 4.0)
	_crosshair.set_anchors_preset(Control.PRESET_CENTER)
	_crosshair.offset_left = -2.0
	_crosshair.offset_top = -2.0
	_crosshair.offset_right = 2.0
	_crosshair.offset_bottom = 2.0
	_crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(_crosshair)

	_prompt_label = _centered_label(root, 20, 40.0, Control.PRESET_CENTER)
	_prompt_label.visible = false
	_message_label = _centered_label(root, 24, -200.0, Control.PRESET_CENTER)
	_message_label.visible = false
	_message_label.add_theme_color_override("font_color", COLOR_WARN)

	# Ayuda de controles (abajo, centro)
	_help_label = _centered_label(root, 13, 0.0, Control.PRESET_CENTER_BOTTOM)
	_help_label.offset_top = -34.0
	_help_label.offset_bottom = -8.0
	_help_label.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8, 0.9))

	# Indicadores de proceso (abajo a la izquierda)
	_gauge_panel = _panel(root, Control.PRESET_BOTTOM_LEFT, Vector2(12.0, -270.0))
	var gauge_box := VBoxContainer.new()
	_gauge_panel.add_child(gauge_box)
	_arc_state_label = _label(gauge_box, 18)
	_arc_gauge = GaugeBar.new()
	_speed_gauge = GaugeBar.new()
	_work_gauge = GaugeBar.new()
	_travel_gauge = GaugeBar.new()
	for g in [_arc_gauge, _speed_gauge, _work_gauge, _travel_gauge]:
		gauge_box.add_child(g)
	_current_hint = _label(gauge_box, 13)

	# Electrodo y avance (abajo a la derecha)
	var bottom_right := _panel(root, Control.PRESET_BOTTOM_RIGHT, Vector2(-330.0, -150.0))
	var br_box := VBoxContainer.new()
	br_box.custom_minimum_size = Vector2(300.0, 0.0)
	bottom_right.add_child(br_box)
	_amps_label = _label(br_box, 16)
	_electrode_label = _label(br_box, 13)
	_electrode_bar = _bar(br_box)
	_progress_label = _label(br_box, 13)
	_progress_bar = _bar(br_box)

	_build_guides(root)
	_build_pause(root)


func _build_guides(root: Control) -> void:
	# Marco alrededor del visor: verde/amarillo/rojo según la técnica.
	_guide_frame = Panel.new()
	_guide_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_guide_frame_style = StyleBoxFlat.new()
	_guide_frame_style.bg_color = Color(0, 0, 0, 0)
	_guide_frame_style.set_border_width_all(5)
	_guide_frame_style.set_corner_radius_all(18)
	_guide_frame_style.border_color = state_color(3)
	_guide_frame.add_theme_stylebox_override("panel", _guide_frame_style)
	_guide_frame.anchor_left = 0.27
	_guide_frame.anchor_right = 0.73
	_guide_frame.anchor_top = 0.29
	_guide_frame.anchor_bottom = 0.71
	_guide_frame.visible = false
	root.add_child(_guide_frame)

	_guide_panel = _panel(root, Control.PRESET_CENTER_RIGHT, Vector2(-250.0, -90.0))
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	_guide_panel.add_child(box)
	for entry in [["gap", "Distancia"], ["work", "Áng. de trabajo"], ["travel", "Áng. de avance"], ["speed", "Velocidad"]]:
		var key: String = entry[0]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		box.add_child(row)
		var sw := ColorRect.new()
		sw.custom_minimum_size = Vector2(22.0, 22.0)
		sw.color = state_color(3)
		row.add_child(sw)
		var col := VBoxContainer.new()
		row.add_child(col)
		var title := _label(col, 13)
		title.text = String(entry[1])
		var hint := _label(col, 12)
		hint.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
		_guide_swatches[key] = sw
		_guide_hints[key] = hint
	_guide_panel.visible = false


func _build_pause(root: Control) -> void:
	_pause_panel = ColorRect.new()
	(_pause_panel as ColorRect).color = Color(0.0, 0.0, 0.0, 0.65)
	_pause_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_pause_panel.visible = false
	root.add_child(_pause_panel)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	_pause_panel.add_child(center)
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(320.0, 0.0)
	box.add_theme_constant_override("separation", 12)
	center.add_child(box)
	var title := Label.new()
	title.text = "PAUSA"
	title.add_theme_font_size_override("font_size", 36)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(title)
	_button(box, "Continuar", func() -> void: resume_requested.emit())
	_button(box, "Reiniciar ejercicio", func() -> void: restart_requested.emit())
	_button(box, "Volver al menú", func() -> void: menu_requested.emit())


func _panel(parent: Control, preset: int, offset: Vector2) -> PanelContainer:
	var p := PanelContainer.new()
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.0, 0.0, 0.0, 0.55)
	style.set_corner_radius_all(6)
	style.set_content_margin_all(10.0)
	p.add_theme_stylebox_override("panel", style)
	parent.add_child(p)
	p.set_anchors_preset(preset)
	# Con los anclajes en la esquina/borde elegido, el offset desplaza el panel.
	p.offset_left = offset.x
	p.offset_top = offset.y
	p.grow_horizontal = Control.GROW_DIRECTION_END if offset.x >= 0.0 else Control.GROW_DIRECTION_BEGIN
	p.grow_vertical = Control.GROW_DIRECTION_END if offset.y >= 0.0 else Control.GROW_DIRECTION_BEGIN
	return p


func _label(parent: Control, size: int) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override("font_size", size)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(l)
	return l


func _centered_label(parent: Control, size: int, y_offset: float, preset: int) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_outline_color", Color.BLACK)
	l.add_theme_constant_override("outline_size", 6)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(l)
	l.set_anchors_preset(preset)
	l.offset_left = -450.0
	l.offset_right = 450.0
	l.offset_top = y_offset
	l.offset_bottom = y_offset + size * 1.6
	return l


func _bar(parent: Control) -> ProgressBar:
	var b := ProgressBar.new()
	b.show_percentage = false
	b.custom_minimum_size = Vector2(0.0, 12.0)
	b.min_value = 0.0
	b.max_value = 100.0
	b.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(b)
	return b


func _button(parent: Control, text: String, action: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0.0, 44.0)
	b.pressed.connect(action)
	parent.add_child(b)
	return b
