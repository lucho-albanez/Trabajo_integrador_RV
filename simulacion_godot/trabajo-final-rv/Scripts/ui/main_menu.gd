class_name MainMenu
extends Control
## Menú principal: selección de nivel, fuente de entrada y salida.

var _status: Label
var _source_button: Button


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	DeviceLink.sim_capture = false
	_build()


func _process(_delta: float) -> void:
	_status.text = DeviceLink.status_text()
	_source_button.text = "Fuente de entrada: %s (cambiar)" % _mode_name()


func _mode_name() -> String:
	match DeviceLink.input_mode:
		DeviceLink.InputMode.SIMULATED:
			return "teclado y mouse"
		DeviceLink.InputMode.HARDWARE:
			return "herramienta física"
		_:
			return "automática"


func _build() -> void:
	var bg := ColorRect.new()
	bg.color = Color(0.07, 0.08, 0.1)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(center)

	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(560.0, 0.0)
	box.add_theme_constant_override("separation", 12)
	center.add_child(box)

	var title := Label.new()
	title.text = "SIMULADOR DE SOLDADURA SMAW"
	title.add_theme_font_size_override("font_size", 36)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(title)
	var sub := Label.new()
	sub.text = "Electrodo revestido E6013 Ø3,2 mm - junta a tope en chapa de 10 mm"
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sub.add_theme_color_override("font_color", Color(0.7, 0.7, 0.75))
	box.add_child(sub)
	box.add_child(HSeparator.new())

	for i in range(1, LevelConfig.LEVEL_COUNT + 1):
		var cfg := LevelConfig.create(i)
		var b := Button.new()
		b.text = "%s\n%s" % [cfg.display_name, cfg.summary]
		b.custom_minimum_size = Vector2(0.0, 64.0)
		b.pressed.connect(_on_level_pressed.bind(i))
		box.add_child(b)

	box.add_child(HSeparator.new())
	_source_button = Button.new()
	_source_button.custom_minimum_size = Vector2(0.0, 40.0)
	_source_button.pressed.connect(func() -> void: DeviceLink.cycle_input_mode())
	box.add_child(_source_button)
	_status = Label.new()
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_status)

	var quit := Button.new()
	quit.text = "Salir"
	quit.custom_minimum_size = Vector2(0.0, 40.0)
	quit.pressed.connect(func() -> void: Game.quit_game())
	box.add_child(quit)

	var help := Label.new()
	help.text = "Controles: WASD mover - mouse mirar - E interactuar - Q careta - C agacharse - Esc pausa"
	help.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	help.add_theme_font_size_override("font_size", 12)
	help.add_theme_color_override("font_color", Color(0.6, 0.6, 0.65))
	box.add_child(help)


func _on_level_pressed(level: int) -> void:
	Game.start_level(level)
