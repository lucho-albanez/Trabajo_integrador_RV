class_name ExerciseController
extends Node
## Orquesta el ejercicio de soldadura: preparación del equipo, calibración,
## soldadura (arco, cordón, consumo del electrodo, retroalimentación) e informe.
##
## Fases:  SETUP -> CALIBRATING -> WELDING -> FINISHED
##
## Es el único lugar que conecta la herramienta (DeviceLink) con el mundo
## virtual: calcula la pose del portaelectrodo a partir de la orientación, la
## distancia y el desplazamiento medidos, y alimenta el simulador del arco, el
## evaluador, el cordón, los efectos y la háptica.

signal state_changed(new_state: int)
signal exercise_finished(report: Dictionary)

enum State { SETUP, CALIBRATING, WELDING, FINISHED }

const SPEED_SMOOTH_TAU_S := 0.25
const SPEED_VALID_AFTER_S := 0.5
const NOMINAL_SPEED_MM_S := 3.0
## Transparencia del portaelectrodo durante la calibración y la soldadura (0 opaco, 1 invisible).
const HOLDER_GHOST_TRANSPARENCY := 0.85
const CALIBRATION_TIME_S := 3.0
const VISUAL_GAP_MAX_MM := 30.0
const END_MARGIN_MM := 1.0

@export var player: Player
@export var machine: WeldingMachine
@export var ground_clamp: GroundClamp
@export var holder: ElectrodeHolder
@export var spot: WeldingSpot
@export var coupon: Coupon
## Anclaje de la mesa de trabajo donde se conecta la pinza de masa.
@export var clamp_anchor: ClampAnchor
@export var hud: Hud
@export var report_window: ReportWindow
## Cable del portaelectrodo: se oculta mientras se suelda para no tapar la vista de la junta.
@export var electrode_cable: Node3D

var state: int = State.SETUP
var level: LevelConfig
var arc: ArcSimulator
var evaluator: WeldEvaluator
var recorder: SessionRecorder
var report: Dictionary = {}

var _haptics: HapticController
var _vfx: ArcVFX
## Preparación guiada: los pasos 1 a 5 se ejecutan con las teclas numéricas, en orden.
var sequence: SetupSequence
var _s_mm: float = 0.0
var _v_mm: float = 0.0
var _speed_smooth: float = 0.0
var _angles: Vector2 = Vector2.ZERO
var _away_dir: Vector3 = Vector3.FORWARD
var _weld_time: float = 0.0
var _electrode_used_mm: float = 0.0
var _current_a: float = 0.0
var _was_mask_violation: bool = false
var _last_depleted_msg_msec: int = 0
var _last_width: float = 0.0
var _last_pen: float = 0.0
var _prev_trigger_edge: bool = false
var _homing_done: bool = false
var _home_up: Vector3 = Vector3.UP
var _home_marker_pos: Vector2 = Vector2.ZERO


func _ready() -> void:
	level = LevelConfig.create(Game.selected_level)
	coupon.seam_length_mm = LevelConfig.SEAM_LENGTH_MM
	coupon.bead.reset(LevelConfig.SEAM_LENGTH_MM)

	evaluator = WeldEvaluator.new()
	recorder = SessionRecorder.new()
	arc = ArcSimulator.new()
	arc.name = "ArcSimulator"
	add_child(arc)
	arc.state_changed.connect(_on_arc_state_changed)
	arc.strike_failed.connect(_on_strike_failed)

	_haptics = HapticController.new()
	_haptics.name = "HapticController"
	add_child(_haptics)
	_haptics.setup(arc)

	_vfx = ArcVFX.new()
	_vfx.name = "ArcVFX"
	add_child(_vfx)

	sequence = SetupSequence.new()
	sequence.name = "SetupSequence"
	add_child(sequence)
	sequence.setup(player, machine, ground_clamp, holder, clamp_anchor, level, start_exercise)
	sequence.notice.connect(func(text: String, seconds: float) -> void: hud.show_message(text, seconds))
	player.interactor.set_active(false)  # no se interactúa a mano: todo va por la secuencia

	hud.setup(level)
	coupon.set_guide_visible(level.show_color_guides)
	hud.pause_requested.connect(_set_paused.bind(true))
	hud.resume_requested.connect(_set_paused.bind(false))
	hud.restart_requested.connect(func() -> void: Game.start_level(level.id))
	hud.menu_requested.connect(Game.go_to_menu)
	report_window.retry_requested.connect(func() -> void: Game.start_level(level.id))
	report_window.next_requested.connect(func() -> void: Game.start_level(level.id + 1))
	report_window.menu_requested.connect(Game.go_to_menu)

	ground_clamp.clamped_changed.connect(func(c: bool) -> void: spot.set_active(c))
	spot.set_active(ground_clamp.is_clamped)
	DeviceLink.connection_changed.connect(_on_link_changed)
	DeviceLink.sim_capture = false

	var flat := spot.look_target.global_position - spot.stand_point.global_position
	flat.y = 0.0
	_away_dir = flat.normalized() if flat.length() > 0.001 else Vector3.FORWARD

	_set_state(State.SETUP)
	hud.show_message("%s - preparación guiada: presioná los números 1 a 5 en orden." % level.display_name, 5.0)


func _exit_tree() -> void:
	DeviceLink.sim_capture = false
	DeviceLink.test_trigger = false
	DeviceLink.stop_haptics()
	get_tree().paused = false


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

func _unhandled_input(event: InputEvent) -> void:
	if get_tree().paused:
		return
	if event.is_action_pressed("toggle_input_source"):
		DeviceLink.cycle_input_mode()
		hud.show_message("Fuente de entrada: " + DeviceLink.source_name(), 2.0)
	elif event.is_action_pressed("calibrate"):
		DeviceLink.tare_pose()
		hud.show_message("Pose neutra recalibrada", 1.5)
	elif event.is_action_pressed("reset_yaw"):
		DeviceLink.reset_yaw()
		hud.show_message("Orientación (yaw) reiniciada", 1.5)
	elif event.is_action_pressed("replace_electrode"):
		_try_replace_electrode()
	elif state == State.SETUP and _handle_setup_input(event):
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("finish_exercise") and state == State.WELDING:
		finish_exercise()


## Teclas 1-5: pasos de la preparación. Rueda del mouse: amperaje (paso 4).
func _handle_setup_input(event: InputEvent) -> bool:
	for i in range(1, SetupSequence.LAST_STEP + 1):
		if event.is_action_pressed("step_%d" % i):
			sequence.request(i)
			return true
	if event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
		var button := (event as InputEventMouseButton).button_index
		if button == MOUSE_BUTTON_WHEEL_UP:
			return sequence.adjust_amperage(1)
		if button == MOUSE_BUTTON_WHEEL_DOWN:
			return sequence.adjust_amperage(-1)
	return false


func _set_paused(paused: bool) -> void:
	if state == State.FINISHED:
		return
	get_tree().paused = paused
	hud.show_pause(paused)
	if paused:
		DeviceLink.sim_capture = false
		DeviceLink.stop_haptics()
		player.capture_mouse(false)
	else:
		DeviceLink.sim_capture = state == State.WELDING
		player.capture_mouse(true)


func _on_link_changed(connected: bool) -> void:
	hud.show_message("Herramienta física conectada" if connected else "Herramienta física desconectada", 2.5)


# ---------------------------------------------------------------------------
# Estados
# ---------------------------------------------------------------------------

## Vuelve el portaelectrodo casi transparente (solo se insinúa la silueta) para
## que el mango no tape la junta. El electrodo en la punta también se atenúa menos.
func _set_holder_ghost(on: bool) -> void:
	if holder == null:
		return
	for n in holder.find_children("*", "GeometryInstance3D", true, false):
		var g := n as GeometryInstance3D
		if g == null or g is CPUParticles3D or g is GPUParticles3D:
			continue
		if g.name == &"Electrode":  # el electrodo siempre se ve sólido
			continue
		g.transparency = HOLDER_GHOST_TRANSPARENCY if on else 0.0
		g.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF if on else GeometryInstance3D.SHADOW_CASTING_SETTING_ON


func _set_state(new_state: int) -> void:
	state = new_state
	if electrode_cable != null:
		electrode_cable.visible = state != State.CALIBRATING and state != State.WELDING
	_set_holder_ghost(state == State.CALIBRATING or state == State.WELDING)
	match state:
		State.SETUP:
			hud.set_phase("1/3  Preparación del equipo")
			hud.set_checklist_visible(true)
			hud.set_gauges_visible(false)
			hud.set_crosshair_visible(true)
			hud.set_crosshair_visible(false)
			hud.set_help("Teclas 1 a 5: pasos en orden  |  Rueda: amperaje (paso 4)  |  Q careta  |  Esc pausa")
		State.CALIBRATING:
			hud.set_phase("2/3  Calibración")
			hud.set_checklist_visible(false)
			hud.set_crosshair_visible(false)
			hud.set_prompt("")
			hud.set_help("")
			hud.set_guides_visible(true)
			hud.set_live_visible(true)
		State.WELDING:
			hud.set_phase("3/3  Soldadura")
			hud.set_gauges_visible(true)
			hud.set_guides_visible(true)
			coupon.set_guide_visible(level.show_color_guides)
			hud.set_help("Q careta  |  clic izq. / gatillo: arco  |  mouse: avanzar  |  rueda: distancia  |  A/D W/S: ángulos  |  R electrodo  |  T recalibrar  |  Enter terminar")
		State.FINISHED:
			hud.set_phase("Ejercicio finalizado")
			hud.set_gauges_visible(false)
			hud.set_guides_visible(false)
			hud.set_live_visible(false)
			hud.set_help("")
	state_changed.emit(state)


## Devuelve los requisitos que faltan para comenzar (vacío si está todo listo).
func missing_requirements() -> Array[String]:
	var missing: Array[String] = []
	if not machine.is_on:
		missing.append("Encender la máquina de soldar")
	if not ground_clamp.is_clamped:
		missing.append("Conectar la pinza de masa a la mesa")
	if not holder.is_held:
		missing.append("Tomar el portaelectrodo")
	return missing


func start_exercise() -> void:
	if state != State.SETUP:
		return
	var missing := missing_requirements()
	if not missing.is_empty():
		hud.show_message("Falta: " + missing[0], 2.5)
		return
	_run_calibration()


func _run_calibration() -> void:
	_set_state(State.CALIBRATING)
	_current_a = float(machine.current_amperage)
	var tween := player.enter_station(spot)
	await tween.finished
	if DeviceLink.uses_hardware() and DeviceLink.hardware_connected:
		await _wait_for_neutral_pose()
	else:
		hud.show_message("Sostené la herramienta quieta en posición neutra (perpendicular a la chapa)...", CALIBRATION_TIME_S + 0.5)
		await get_tree().create_timer(CALIBRATION_TIME_S).timeout
		DeviceLink.tare_pose()
	_begin_welding()


## Tara automática robusta: en vez de tarar a los 3 s (con la herramienta quizás acostada sobre
## la mesa), espera a que el operario la tome y la sostenga quieta en la pose neutra.
##  - Con una pose neutra recordada (de la última tara): la inclinación tiene que estar a menos
##    de NEUTRAL_TOL_DEG de esa pose y quieta NEUTRAL_HOLD_S.
##  - La primera vez (sin pose recordada): tiene que haberse levantado de donde estaba y quedar
##    quieta NEUTRAL_HOLD_S.
##  - En cualquier momento se puede tarar a mano con la tecla de recalibrar (T).
const NEUTRAL_TOL_DEG := 25.0
const NEUTRAL_HOLD_S := 0.8
const PICKUP_DEG := 20.0
## Sin pose recordada: si no se detecta que levantaste la herramienta, se acepta igual la pose
## en la que está, quieta, después de este tiempo (por si ya la tenías en la mano).
const NEUTRAL_FIRST_ACCEPT_S := 4.0
## Tiempo máximo de espera: pasado esto se toma la pose actual y se sigue (nunca se queda trabado).
const NEUTRAL_TIMEOUT_S := 10.0

func _wait_for_neutral_pose() -> void:
	var start_g := DeviceLink.gravity_imu()
	var start_tares := DeviceLink.tare_count
	var moved := false
	var msg_timer := 0.0
	var elapsed := 0.0
	while true:
		await get_tree().process_frame
		var dt := get_process_delta_time()
		elapsed += dt
		if DeviceLink.tare_count != start_tares:
			return                                   # tara manual (T): listo
		if not DeviceLink.hardware_connected:
			DeviceLink.tare_pose()
			return
		var g := DeviceLink.gravity_imu()
		if not moved and rad_to_deg(g.angle_to(start_g)) > PICKUP_DEG:
			moved = true
		var err := DeviceLink.neutral_tilt_error_deg()
		var in_pose: bool
		if DeviceLink.has_neutral:
			in_pose = err < NEUTRAL_TOL_DEG
		else:
			in_pose = moved or elapsed >= NEUTRAL_FIRST_ACCEPT_S
		var still := DeviceLink.still_time()
		if in_pose and still >= NEUTRAL_HOLD_S:
			DeviceLink.tare_pose()
			hud.show_message("Pose neutra tomada. ¡Listo para soldar!", 2.0)
			return
		if elapsed >= NEUTRAL_TIMEOUT_S:
			DeviceLink.tare_pose()
			hud.show_message("Pose neutra tomada por tiempo. Si no es la correcta, presioná T en la posición neutra.", 3.0)
			return
		msg_timer -= dt
		if msg_timer <= 0.0:
			msg_timer = 0.4
			var txt := "Sostené la herramienta en posición neutra (perpendicular a la chapa)"
			if DeviceLink.has_neutral and err >= NEUTRAL_TOL_DEG:
				txt += "\nInclinación: faltan %.0f° para la pose neutra" % (err - NEUTRAL_TOL_DEG)
			elif in_pose:
				txt += "\nMantené quieta... %.1f s" % maxf(NEUTRAL_HOLD_S - still, 0.0)
			hud.show_message(txt + "\n(o presioná T para tarar ahora)  [%d s]" % int(ceil(NEUTRAL_TIMEOUT_S - elapsed)), 0.6)


func _begin_welding() -> void:
	evaluator.setup(level, _current_a)
	recorder.setup(level, _current_a)
	_homing_done = false
	_home_up = Vector3.UP
	_home_marker_pos = Vector2.ZERO
	arc.reset()
	DeviceLink.send_command({"cmd": "RESET"})
	DeviceLink.stop_haptics()
	_s_mm = 0.0
	_v_mm = 0.0
	_speed_smooth = 0.0
	_weld_time = 0.0
	_electrode_used_mm = 0.0
	holder.top_level = true
	DeviceLink.consume_travel_mm()  # descarta el movimiento acumulado
	DeviceLink.sim_capture = true
	_set_state(State.WELDING)
	_place_holder(0.0)
	if DeviceLink.homing_required:
		hud.show_message("Bajá la careta (Q), apoyá la punta en el inicio del cordón (punto de homing) para iniciar.", 6.0)
	else:
		hud.show_message("Bajá la careta (Q) y acercá la punta al inicio del cordón: el arco se enciende solo.", 6.0)


func finish_exercise() -> void:
	if state != State.WELDING:
		return
	_homing_done = false
	arc.force_off("finished")
	_apply_feedback(false, 0.0)
	DeviceLink.sim_capture = false
	DeviceLink.test_trigger = false
	DeviceLink.send_command({"cmd": "RESET"})
	DeviceLink.stop_haptics()
	player.mask_hud.set_arc(false)
	player.mask_hud.set_down(false)

	report = evaluator.finalize({
		"coverage": coupon.bead.coverage(),
		"bead_length_mm": coupon.bead.length_mm(),
		"electrode_used_mm": _electrode_used_mm,
		"duration_s": _weld_time,
	})
	(report["stats"] as Dictionary)["interruptions"] = coupon.bead.interruptions()
	Game.last_report = report
	_set_state(State.FINISHED)
	report_window.show_report(report, level.id < LevelConfig.LEVEL_COUNT, recorder)
	exercise_finished.emit(report)


# ---------------------------------------------------------------------------
# Bucle principal
# ---------------------------------------------------------------------------

func _process(_delta: float) -> void:
	match state:
		State.SETUP:
			_update_setup_ui()
		State.CALIBRATING:
			_update_calibration_ui()
		State.WELDING:
			_update_welding_ui()


func _physics_process(delta: float) -> void:
	if state == State.WELDING:
		_step_welding(delta)


func _update_setup_ui() -> void:
	hud.set_checklist(sequence.get_items(), "Preparación (teclas 1 a 5)")
	hud.set_prompt(sequence.get_prompt())
	hud.set_amperage(float(machine.current_amperage), machine.is_on)
	hud.set_electrode(holder.remaining_fraction(), holder.length_mm, holder.electrodes_used)
	hud.set_progress(0.0, 0.0)


## Durante la calibración se muestran en vivo los valores actuales e ideales
## para que el operario posicione y oriente la herramienta antes de cebar el arco.
func _update_calibration_ui() -> void:
	_angles = WeldGeometry.angles_from_up(DeviceLink.get_tool_up())
	var gap := DeviceLink.get_arc_gap_mm()
	var tiles := _guide_tiles(gap)
	hud.update_guides(tiles)
	_update_tool_led(tiles)
	hud.set_guides_title("CALIBRACIÓN: posicioná y orientá la herramienta")
	hud.update_live("CALIBRACIÓN: posicioná y orientá la herramienta", tiles)


func _update_welding_ui() -> void:
	var gap := DeviceLink.get_arc_gap_mm()
	hud.update_gauges(gap if is_finite(gap) else 0.0, is_finite(gap), _speed_smooth, 90.0 + _angles.x, _angles.y)
	hud.set_amperage(_current_a, true)
	hud.set_electrode(holder.remaining_fraction(), holder.length_mm, holder.electrodes_used)
	hud.set_progress(clampf(_s_mm / coupon.seam_length_mm, 0.0, 1.0), coupon.bead.coverage())

	var tiles := _guide_tiles(gap)
	hud.update_guides(tiles)
	_update_tool_led(tiles)
	hud.set_live_visible(arc.state == ArcSimulator.State.OFF and level.show_color_guides)
	if arc.state == ArcSimulator.State.OFF:
		var all_ok: bool = true
		for t in tiles:
			var d: Dictionary = t
			var is_pose: bool = d["key"] == "gap" or d["key"] == "work" or d["key"] == "travel"
			if is_pose and int(d["state"]) == 2:
				all_ok = false
		if all_ok:
			var ready_msg := "POSICIÓN CORRECTA: podés cebar el arco" if DeviceLink.homing_required \
				else "POSICIÓN CORRECTA: acercá la punta y el arco se enciende solo"
			hud.set_guides_title(ready_msg, Hud.COLOR_OK)
			hud.update_live(ready_msg, tiles)
		else:
			hud.set_guides_title("PRE-ARCO: corregí la posición hasta ver verde")
			hud.update_live("PRE-ARCO: corregí la posición hasta ver verde", tiles)
	else:
		hud.set_guides_title("SOLDADURA EN CURSO")

	match arc.state:
		ArcSimulator.State.ARCING:
			match arc.zone:
				ArcSimulator.Zone.SHORT:
					hud.set_arc_state("ARCO CORTO", Hud.COLOR_WARN)
				ArcSimulator.Zone.LONG:
					hud.set_arc_state("ARCO LARGO", Hud.COLOR_WARN)
				_:
					hud.set_arc_state("ARCO ESTABLE", Hud.COLOR_OK)
		ArcSimulator.State.STUCK:
			hud.set_arc_state("ELECTRODO PEGADO", Hud.COLOR_BAD)
		ArcSimulator.State.OUT:
			hud.set_arc_state("ARCO APAGADO", Hud.COLOR_BAD)
		_:
			hud.set_arc_state("Sin arco", Hud.COLOR_PENDING)

	if _s_mm >= coupon.seam_length_mm - END_MARGIN_MM:
		hud.set_prompt("Llegaste al final de la junta - [Enter] para terminar")
	elif holder.is_depleted():
		hud.set_prompt("Electrodo agotado - [R] para colocar uno nuevo")
	else:
		hud.set_prompt("")


## LED de la herramienta con los mismos márgenes que los indicadores del HUD (bandas del nivel):
## verde = todo óptimo, amarillo = algo en zona tolerable, rojo = algo fuera de límites.
## Se evalúan distancia, ángulo de trabajo, ángulo de avance y velocidad (esta última solo con
## arco encendido). Electrodo pegado = color de "sticking".
func _update_tool_led(tiles: Array) -> void:
	var worst := 0
	for t in tiles:
		var d: Dictionary = t
		var k: String = d["key"]
		if k == "gap" or k == "work" or k == "travel" or k == "speed":
			var st: int = d["state"]
			if st != 3:
				worst = maxi(worst, st)
	var key: String = ["weld_optimal", "weld_caution", "weld_warning"][worst]
	if state == State.WELDING and arc.state == ArcSimulator.State.STUCK:
		key = "sticking"
	DeviceLink.send_led(DeviceLink.led_color(key))


## Estado de un valor frente a una banda: 0 óptimo, 1 tolerable, 2 fuera de límites.
static func _band_state(x: float, band: Vector4) -> int:
	if x >= band.x and x <= band.y:
		return 0
	if x >= band.z and x <= band.w:
		return 1
	return 2


func _detail(actual: String, band: Vector4, unit: String, decimals: int) -> String:
	var fmt := "%." + str(decimals) + "f"
	return ("Actual: " + fmt + " %s  |  Ideal: " + fmt + " %s  (" + fmt + " a " + fmt + ")") % [
		float(actual), unit, SessionRecorder.ideal_of(band), unit, band.x, band.y]


func _guide_tiles(gap: float) -> Array:
	var tiles: Array = []
	var lv := level
	# Distancia punta-chapa
	if is_finite(gap):
		var hint := "Correcta"
		if gap < lv.arc_length_band.x:
			hint = "Alejá la punta"
		elif gap > lv.arc_length_band.y:
			hint = "Acercá la punta"
		tiles.append({"key": "gap", "state": _band_state(gap, lv.arc_length_band), "hint": hint,
			"detail": _detail(str(gap), lv.arc_length_band, "mm", 1)})
	else:
		tiles.append({"key": "gap", "state": 2, "hint": "Sin lectura del sensor",
			"detail": "Ideal: %.1f mm  (%.1f a %.1f)" % [SessionRecorder.ideal_of(lv.arc_length_band), lv.arc_length_band.x, lv.arc_length_band.y]})
	# Ángulo de trabajo (90° ideal perpendicular a la chapa)
	var whint := "Correcto"
	var work_abs := 90.0 + _angles.x
	if work_abs < lv.work_band.z:
		whint = "Inclinar hacia el otro lado"
	elif work_abs > lv.work_band.w:
		whint = "Enderezar el electrodo hacia 90°"
	elif work_abs < lv.work_band.x or work_abs > lv.work_band.y:
		whint = "Aproximar a 90°"
	tiles.append({"key": "work", "state": _band_state(work_abs, lv.work_band), "hint": whint,
		"detail": _detail(str(work_abs), lv.work_band, "°", 0)})
	# Ángulo de avance (arrastre)
	var thint := "Correcto"
	if _angles.y < lv.travel_band.x:
		thint = "Arrastrar más"
	elif _angles.y > lv.travel_band.y:
		thint = "Inclinar menos"
	tiles.append({"key": "travel", "state": _band_state(_angles.y, lv.travel_band), "hint": thint,
		"detail": _detail(str(_angles.y), lv.travel_band, "°", 0)})
	# Trayectoria / Centrado de la punta en la junta
	var path_hint := "Centrado en junta"
	var lat_abs := absf(_v_mm)
	if lat_abs > lv.lateral_band.w:
		path_hint = "¡Desviado de la junta! Centrar punta"
	elif lat_abs > lv.lateral_band.y:
		path_hint = "Leve desvío lateral"
	tiles.append({"key": "path", "state": _band_state(lat_abs, lv.lateral_band), "hint": path_hint,
		"detail": "Desvío: %.1f mm  (máx tol: %.1f mm)" % [lat_abs, lv.lateral_band.y]})
	# Velocidad (solo con el arco encendido)
	if arc.state == ArcSimulator.State.ARCING and arc.time_in_arc >= SPEED_VALID_AFTER_S:
		var shint := "Correcta"
		if _speed_smooth < lv.speed_band.x:
			shint = "Más rápido"
		elif _speed_smooth > lv.speed_band.y:
			shint = "Más lento"
		tiles.append({"key": "speed", "state": _band_state(_speed_smooth, lv.speed_band), "hint": shint,
			"detail": _detail(str(_speed_smooth), lv.speed_band, "mm/s", 1)})
	else:
		tiles.append({"key": "speed", "state": 3, "hint": "Con el arco encendido",
			"detail": "Ideal: %.1f mm/s  (%.1f a %.1f)" % [SessionRecorder.ideal_of(lv.speed_band), lv.speed_band.x, lv.speed_band.y]})
	# Corriente
	var cst := _band_state(_current_a, lv.current_band)
	var chint := "Correcta"
	if _current_a < lv.current_band.x:
		chint = "Corriente baja"
	elif _current_a > lv.current_band.y:
		chint = "Corriente alta"
	tiles.append({"key": "current", "state": cst, "hint": chint,
		"detail": _detail(str(_current_a), lv.current_band, "A", 0)})
	return tiles


func _step_welding(delta: float) -> void:
	_weld_time += delta

	# 1) Lectura de posición de la herramienta.
	var prev_s := _s_mm
	var prev_v := _v_mm

	var trigger := DeviceLink.get_trigger()

	# Sin homing (opción de la GUI): el arco se enciende solo al acercar la punta.
	arc.auto_strike = not DeviceLink.homing_required and not holder.is_depleted()
	if not DeviceLink.homing_required and not _homing_done:
		_homing_done = true
		_home_up = DeviceLink.get_tool_up().normalized()
		_home_marker_pos = DeviceLink.hw_abs_pos_mm
		DeviceLink.consume_travel_mm()

	# ¡HOMING! Al apoyar físicamente la punta en la mesa y pulsar el microswitch
	if DeviceLink.homing_required and trigger and not _prev_trigger_edge and not _homing_done:
		_homing_done = true
		_s_mm = 0.0
		_v_mm = 0.0
		_home_up = DeviceLink.get_tool_up().normalized()
		_home_marker_pos = DeviceLink.hw_abs_pos_mm
		arc.session_active = true
		DeviceLink.consume_travel_mm()
		hud.show_message("¡Homing confirmado en inicio del cordón! Arco activado.", 2.5)
	_prev_trigger_edge = trigger

	if DeviceLink.has_position_tracking and DeviceLink.has_absolute_position:
		# Seguimiento óptico con compensación cinemática 3D directa de la punta
		var target_s := clampf(DeviceLink.hw_abs_pos_mm.x, -coupon.plate_margin_mm, coupon.seam_length_mm + coupon.plate_margin_mm)
		var target_v := clampf(DeviceLink.hw_abs_pos_mm.y, -coupon.plate_half_width_mm, coupon.plate_half_width_mm)
		if arc.state != ArcSimulator.State.STUCK:
			_s_mm = lerpf(_s_mm, target_s, 0.45)
			_v_mm = lerpf(_v_mm, target_v, 0.45)
	else:
		var travel := Vector2.ZERO
		if arc.state != ArcSimulator.State.STUCK:  # pegado a la chapa no se puede avanzar
			travel = DeviceLink.consume_travel_mm()
		else:
			DeviceLink.consume_travel_mm()
		_s_mm = clampf(_s_mm + travel.x, -coupon.plate_margin_mm, coupon.seam_length_mm + coupon.plate_margin_mm)
		_v_mm = clampf(_v_mm + travel.y, -coupon.plate_half_width_mm, coupon.plate_half_width_mm)

	var moved_s := absf(_s_mm - prev_s)
	var inst_speed := moved_s / delta
	_speed_smooth = lerpf(_speed_smooth, inst_speed, 1.0 - exp(-delta / SPEED_SMOOTH_TAU_S))

	var up := DeviceLink.get_tool_up()
	_angles = WeldGeometry.angles_from_up(up)
	var gap := DeviceLink.get_arc_gap_mm()
	var energized := machine.is_on and ground_clamp.is_clamped
	var over_plate := coupon.is_over_plate(_s_mm, _v_mm)

	if holder.is_depleted():
		if trigger and arc.state == ArcSimulator.State.OFF:
			var now := Time.get_ticks_msec()
			if now - _last_depleted_msg_msec > 2000:
				_last_depleted_msg_msec = now
				hud.show_message("Electrodo agotado: presioná R para colocar uno nuevo", 2.5)
		trigger = false

	# 2) Simulación del arco.
	if not _homing_done:
		# Antes de hacer homing: arco apagado y sin vibración
		arc.force_off("waiting_homing")
	else:
		arc.step(delta, trigger, gap, energized, over_plate)
	var arcing := arc.state == ArcSimulator.State.ARCING

	# 3) Proceso de soldadura.
	if arcing:
		_weld_step(delta, prev_s, prev_v, gap)
	_apply_feedback(arcing, gap)

	# 4) Registro para el informe y el CSV.
	recorder.sample(delta, {
		"t": _weld_time, "arc": arcing, "s": _s_mm, "v": _v_mm,
		"speed": _speed_smooth, "gap": gap if is_finite(gap) else 0.0,
		"work": 90.0 + _angles.x, "travel": _angles.y,
		"width": _last_width if arcing else 0.0,
		"penetration": _last_pen if arcing else 0.0,
		"mask": player.mask_hud.is_down,
	})

	# 5) Pose del portaelectrodo virtual.
	_place_holder(gap)


func _weld_step(delta: float, prev_s: float, prev_v: float, gap: float) -> void:
	# Consumo del electrodo (el operario no necesita compensarlo: la punta
	# virtual sigue la distancia medida).
	var burn := WeldPhysics.burn_rate_mm_s(_current_a) * delta * level.consumption_scale
	_electrode_used_mm += holder.consume(burn)
	if holder.is_depleted():
		arc.force_off("depleted")
		hud.show_message("Electrodo agotado: presioná R para colocar uno nuevo", 3.0)
		return

	# Velocidad física: arranca desde un valor nominal para no castigar el cebado.
	var speed_phys := _speed_smooth
	if arc.time_in_arc < SPEED_VALID_AFTER_S:
		speed_phys = lerpf(NOMINAL_SPEED_MM_S, _speed_smooth, arc.time_in_arc / SPEED_VALID_AFTER_S)

	var width := WeldPhysics.bead_width_mm(_current_a, speed_phys, gap)
	var height := WeldPhysics.bead_height_mm(_current_a, speed_phys, width)
	var pen := WeldPhysics.penetration_mm(_current_a, speed_phys, gap, _angles.y)
	var undercut := WeldPhysics.undercut_mm(_current_a, speed_phys)

	_last_width = width
	_last_pen = pen
	evaluator.add_sample(delta, {
		"arc_len": gap,
		"speed": _speed_smooth if arc.time_in_arc >= SPEED_VALID_AFTER_S else -1.0,
		"work": 90.0 + _angles.x,
		"travel": _angles.y,
		"lateral": _v_mm,
		"width": width,
		"height": height,
		"penetration": pen,
		"undercut": undercut,
	})
	var defect := undercut > 1.0 or gap > WeldPhysics.OPTIMAL_GAP_MAX_MM + 1.5
	coupon.bead.deposit_span(prev_s, prev_v, _s_mm, _v_mm, width, height, defect)

	if not player.mask_hud.is_down:
		evaluator.add_safety_time(delta)
		if not _was_mask_violation:
			_was_mask_violation = true
			Events.safety_violation.emit()
			hud.show_message("¡Soldando sin careta! Bajá la careta (Q)", 2.5)
	else:
		_was_mask_violation = false


## Efectos, careta y háptica según el estado del arco.
func _apply_feedback(arcing: bool, gap: float) -> void:
	var stuck := arc.state == ArcSimulator.State.STUCK
	var tip := _tip_global(gap)
	_vfx.global_position = tip + coupon.global_transform.basis.y * 0.004
	_vfx.set_active(arcing, gap if is_finite(gap) else 2.5, _current_a)
	_vfx.set_stuck(stuck)
	player.mask_hud.set_arc(arcing or stuck)
	var work_abs := 90.0 + _angles.x
	var out_of_tolerance := (work_abs < level.work_band.z or work_abs > level.work_band.w) \
		or (_angles.y < level.travel_band.x or _angles.y > level.travel_band.y) \
		or (absf(_v_mm) > level.lateral_band.w)
	_haptics.set_warning(out_of_tolerance)


func _tip_global(gap: float) -> Vector3:
	var h := clampf(gap, 0.0, VISUAL_GAP_MAX_MM) if is_finite(gap) else VISUAL_GAP_MAX_MM
	return coupon.seam_to_global(_s_mm, _v_mm, h)


## Coloca el portaelectrodo para que su punta quede en la posición virtual.
func _place_holder(gap: float) -> void:
	var up_global := coupon.global_transform.basis * DeviceLink.get_tool_up()
	var basis := WeldGeometry.holder_basis(-up_global, _away_dir)
	var tip := _tip_global(gap)
	holder.global_transform = Transform3D(basis, tip - basis * holder.get_tip_local())


func _try_replace_electrode() -> void:
	if not holder.is_held:
		hud.show_message("Tomá el portaelectrodo para cambiar el electrodo", 2.0)
		return
	if state == State.WELDING and arc.state != ArcSimulator.State.OFF:
		return
	if holder.length_mm >= holder.initial_length_mm - 0.5:
		hud.show_message("El electrodo está nuevo", 1.5)
		return
	holder.replace_electrode()
	hud.show_message("Electrodo nuevo colocado (#%d)" % holder.electrodes_used, 2.0)


# ---------------------------------------------------------------------------
# Eventos del arco
# ---------------------------------------------------------------------------

func _on_arc_state_changed(new_state: int, reason: String) -> void:
	match new_state:
		ArcSimulator.State.ARCING:
			_speed_smooth = 0.0
			_was_mask_violation = false
			if reason == "reignited":
				hud.show_message("Arco reencendido.", 1.5)
		ArcSimulator.State.STUCK:
			evaluator.add_stick_event()
			hud.show_message("¡Electrodo pegado! Separá la punta para despegar.", 3.0)
		ArcSimulator.State.OUT:
			evaluator.add_out_event()
			if reason == "too_long":
				hud.show_message("Arco cortado: te alejaste mucho. Acercate a la chapa para reencender.", 3.0)
		ArcSimulator.State.OFF:
			if reason == "freed":
				hud.show_message("Electrodo liberado.", 1.5)


func _on_strike_failed(reason: String) -> void:
	match reason:
		"no_circuit":
			hud.show_message("Sin corriente: encendé la máquina y conectá la pinza de masa", 2.5)
		"off_plate":
			hud.show_message("Apuntá a la probeta para cebar el arco", 2.0)
		"too_far":
			hud.show_message("Muy lejos para cebar: acercate a menos de 4,5 mm", 2.0)
