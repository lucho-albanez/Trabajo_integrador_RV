class_name UIManager
extends CanvasLayer

## ==============================================================================
## UIManager.gd - Interfaz Gráfica de Telemetría y Feedback del Operario
## ==============================================================================

@export_group("Referencias")
@export var serial_manager: SerialManager
@export var arc_simulator: ArcSimulator
@export var weld_bead_generator: WeldBeadGenerator
@export var status_label: Label
@export var distance_label: Label
@export var angle_label: Label
@export var speed_label: Label
@export var score_bar: ProgressBar
@export var score_label: Label
@export var alert_label: Label

func _ready() -> void:
	if serial_manager:
		serial_manager.connection_status_changed.connect(_on_connection_changed)
	if arc_simulator:
		arc_simulator.arc_quality_updated.connect(_on_quality_updated)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.is_pressed():
		if event.is_action_pressed("reset_yaw") and serial_manager:
			serial_manager.send_reset_yaw_command()
		elif event.is_action_pressed("calibrate_imu") and serial_manager:
			serial_manager.send_calibrate_command()
		elif event.keycode == KEY_SPACE and weld_bead_generator:
			weld_bead_generator.clear_bead()

func _on_connection_changed(is_connected: bool) -> void:
	if status_label:
		if is_connected:
			status_label.text = "HARDWARE CONECTADO (100 Hz)"
			status_label.modulate = Color.GREEN
		else:
			status_label.text = "DESCONECTADO (ESPERANDO ESP32)"
			status_label.modulate = Color.RED

func _on_quality_updated(score: float, metrics: Dictionary) -> void:
	var dist = metrics.get("distance_mm", 0.0)
	var angle = metrics.get("travel_angle_deg", 0.0)
	var speed = metrics.get("speed_mm_s", 0.0)
	var is_stuck = metrics.get("is_stuck", false)

	if distance_label:
		distance_label.text = "Longitud de Arco: %.1f mm" % dist
		if dist >= 1.5 and dist <= 3.5:
			distance_label.modulate = Color.GREEN
		elif dist <= 0.8:
			distance_label.modulate = Color.RED
		else:
			distance_label.modulate = Color.YELLOW

	if angle_label:
		angle_label.text = "Ángulo de Avance: %.1f° (Obj: 15°-20°)" % angle
		if angle >= 12.0 and angle <= 22.0:
			angle_label.modulate = Color.GREEN
		else:
			angle_label.modulate = Color.ORANGE

	if speed_label:
		speed_label.text = "Velocidad: %.1f mm/s (Obj: 3-6 mm/s)" % speed
		if speed >= 2.5 and speed <= 6.5:
			speed_label.modulate = Color.GREEN
		else:
			speed_label.modulate = Color.ORANGE

	if score_bar:
		score_bar.value = score
	if score_label:
		score_label.text = "Calidad: %d%%" % int(score)

	if alert_label:
		if is_stuck:
			alert_label.text = "¡ALERTA: ELECTRODO PEGADO (CORTOCIRCUITO)!"
			alert_label.visible = true
			alert_label.modulate = Color.RED
		elif dist > 5.0 and dist < 20.0:
			alert_label.text = "AVISO: ARCO DEMASIADO LARGO"
			alert_label.visible = true
			alert_label.modulate = Color.YELLOW
		else:
			alert_label.visible = false
