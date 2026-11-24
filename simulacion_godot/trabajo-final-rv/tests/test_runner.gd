extends Node
## Pruebas automáticas (sin ventana):
##   godot --headless --fixed-fps 60 res://tests/test_runner.tscn
## Devuelve código de salida 1 si alguna verificación falla.

var _failures: int = 0
var _checks: int = 0


func _ready() -> void:
	_run()


func _check(cond: bool, msg: String) -> void:
	_checks += 1
	if cond:
		print("  ok   ", msg)
	else:
		_failures += 1
		printerr("  FAIL ", msg)


func _run() -> void:
	print("== Lógica pura ==")
	_test_geometry()
	_test_physics()
	_test_arc()
	_test_evaluator()

	print("== Escenas ==")
	_test_scenes_load()

	print("== Enlace con la herramienta (UDP) ==")
	await _test_device_link()

	print("== Ejercicio completo (simulado) ==")
	await _test_setup_sequence()
	await _test_exercise_flow()

	print("== Resultado: %d verificaciones, %d fallos ==" % [_checks, _failures])
	get_tree().quit(1 if _failures > 0 else 0)


# ---------------------------------------------------------------------------

func _test_geometry() -> void:
	var up := WeldGeometry.up_from_angles(7.0, 12.0)
	var a := WeldGeometry.angles_from_up(up)
	_check(absf(a.x - 7.0) < 0.01 and absf(a.y - 12.0) < 0.01, "ángulos de trabajo/avance: ida y vuelta")
	_check(absf(WeldGeometry.angles_from_up(Vector3.UP).x) < 0.001, "vertical = 0° de desvío")
	var drag := WeldGeometry.angles_from_up(Vector3(-0.2, 1.0, 0.0))
	_check(drag.y > 0.0, "portaelectrodo atrás de la punta = arrastre positivo")
	var band := Vector4(1.5, 3.5, 0.5, 6.0)
	_check(WeldGeometry.band_score(2.0, band) == 1.0, "banda: dentro del óptimo = 1")
	_check(WeldGeometry.band_score(0.5, band) == 0.0 and WeldGeometry.band_score(6.0, band) == 0.0, "banda: en los límites = 0")
	_check(absf(WeldGeometry.band_score(1.0, band) - 0.5) < 0.001, "banda: interpolación lineal")
	var basis := WeldGeometry.holder_basis(Vector3(0.0, -1.0, 0.0), Vector3(0.0, 0.0, -1.0))
	_check(absf(basis.determinant() - 1.0) < 0.001 and absf(basis.x.dot(basis.y)) < 0.001, "base del portaelectrodo ortonormal")
	_check(basis.y.is_equal_approx(Vector3(0.0, -1.0, 0.0)), "portaelectrodo: +Y hacia la punta")


func _test_physics() -> void:
	var w := WeldPhysics.bead_width_mm(110.0, 3.0, 2.5)
	_check(w > 6.0 and w < 8.5, "ancho nominal ~7 mm (%.2f)" % w)
	var h := WeldPhysics.bead_height_mm(110.0, 3.0, w)
	_check(h > 1.5 and h < 3.5, "altura nominal ~2-3 mm (%.2f)" % h)
	var p := WeldPhysics.penetration_mm(110.0, 3.0, 2.5, 10.0)
	_check(p > 1.5 and p < 3.0, "penetración nominal ~2 mm (%.2f)" % p)
	var burn := WeldPhysics.burn_rate_mm_s(110.0)
	_check(burn > 3.5 and burn < 4.5, "consumo de varilla ~4 mm/s (%.2f)" % burn)
	_check(WeldPhysics.bead_width_mm(110.0, 1.0, 2.5) > WeldPhysics.bead_width_mm(110.0, 6.0, 2.5), "más lento = cordón más ancho")
	_check(WeldPhysics.undercut_mm(110.0, 8.0) > 1.0, "avance muy rápido produce mordedura")


func _test_arc() -> void:
	var arc := ArcSimulator.new()
	arc.step(0.016, false, 2.5, true, true)
	arc.step(0.016, true, 2.5, true, true)
	_check(arc.state == ArcSimulator.State.ARCING, "cebado con gatillo y distancia correcta")
	arc.step(0.016, true, 2.5, true, true)
	_check(arc.zone == ArcSimulator.Zone.OPTIMAL, "zona óptima a 2,5 mm")
	for i in range(40):
		arc.step(0.016, true, 0.3, true, true)
	_check(arc.state == ArcSimulator.State.STUCK, "electrodo pegado tras >0,35 s a <0,8 mm")
	arc.step(0.016, true, 3.0, true, true)
	_check(arc.state == ArcSimulator.State.OFF, "electrodo liberado al alejarse")
	arc.step(0.016, true, 3.0, true, true)
	_check(arc.state == ArcSimulator.State.OFF, "no recebar sin soltar el gatillo")
	arc.step(0.016, false, 3.0, true, true)
	arc.step(0.016, true, 3.0, true, true)
	_check(arc.state == ArcSimulator.State.ARCING, "recebado tras soltar el gatillo")
	for i in range(20):
		arc.step(0.016, true, 8.0, true, true)
	_check(arc.state == ArcSimulator.State.OUT, "arco apagado por distancia excesiva")
	arc.step(0.016, false, 3.0, true, true)
	arc.step(0.016, true, 3.0, true, true)
	_check(arc.state == ArcSimulator.State.ARCING, "recebado luego de apagarse")
	arc.step(0.016, true, 3.0, false, true)
	_check(arc.state == ArcSimulator.State.OFF, "sin circuito el arco se corta")
	var failed: Array[String] = []
	arc.strike_failed.connect(func(r: String) -> void: failed.append(r))
	arc.step(0.016, false, 3.0, true, true)
	arc.step(0.016, true, 9.0, true, true)
	_check(failed == ["too_far"], "no ceba más allá de 4,5 mm")
	arc.free()


func _feed(ev: WeldEvaluator, seconds: float, d: Dictionary) -> void:
	var t := 0.0
	while t < seconds:
		ev.add_sample(0.02, d)
		t += 0.02


func _test_evaluator() -> void:
	var good := {"arc_len": 2.5, "speed": 3.0, "work": 0.0, "travel": 10.0, "lateral": 0.2,
		"width": 6.8, "height": 2.3, "penetration": 3.0, "undercut": 0.0}
	for lvl in range(1, LevelConfig.LEVEL_COUNT + 1):
		var ev := WeldEvaluator.new()
		ev.setup(LevelConfig.create(lvl), 112.0)
		_feed(ev, 50.0, good)
		var r := ev.finalize({"coverage": 1.0, "bead_length_mm": 150.0, "electrode_used_mm": 200.0, "duration_s": 55.0})
		_check(float(r["grade"]) >= 9.5, "nivel %d: técnica ideal >= 9.5 (%.1f)" % [lvl, float(r["grade"])])
		_check(bool(r["passed"]), "nivel %d: técnica ideal aprueba" % lvl)

	var bad := {"arc_len": 6.5, "speed": 8.0, "work": 25.0, "travel": -6.0, "lateral": 5.0,
		"width": 12.0, "height": 1.0, "penetration": 0.4, "undercut": 1.6}
	var ev_bad := WeldEvaluator.new()
	ev_bad.setup(LevelConfig.create(2), 170.0)
	_feed(ev_bad, 10.0, bad)
	ev_bad.add_stick_event()
	ev_bad.add_out_event()
	ev_bad.add_safety_time(3.0)
	var rb := ev_bad.finalize({"coverage": 0.3, "bead_length_mm": 45.0, "electrode_used_mm": 50.0, "duration_s": 20.0})
	_check(float(rb["grade"]) <= 3.0 and not bool(rb["passed"]), "técnica mala: nota baja (%.1f) y no aprueba" % float(rb["grade"]))
	_check((rb["diagnostics"] as Array).size() >= 5, "técnica mala: genera diagnósticos")
	_check((rb["penalties"] as Array).size() == 3, "técnica mala: 3 penalizaciones")

	var ev_none := WeldEvaluator.new()
	ev_none.setup(LevelConfig.create(1), 100.0)
	var rn := ev_none.finalize({"coverage": 0.0})
	_check(float(rn["grade"]) == 1.0, "sin soldadura: nota 1.0")

	var ev_part := WeldEvaluator.new()
	ev_part.setup(LevelConfig.create(1), 112.0)
	_feed(ev_part, 20.0, good)
	var rp := ev_part.finalize({"coverage": 0.4})
	_check(float(rp["grade"]) <= WeldEvaluator.INCOMPLETE_GRADE_CAP, "cordón incompleto: nota limitada (%.1f)" % float(rp["grade"]))
	var weights := 0.0
	for c in WeldEvaluator.CATEGORIES:
		weights += float(c["weight"])
	_check(is_equal_approx(weights, 100.0), "los pesos de las categorías suman 100")


func _test_scenes_load() -> void:
	for path in [
		"res://Scenes/MainMenu.tscn", "res://Scenes/Main_scene.tscn", "res://Scenes/Player.tscn",
		"res://Scenes/Table.tscn", "res://Scenes/Coupon.tscn", "res://Scenes/WeldingSpot.tscn",
		"res://Scenes/electrode_holder.tscn", "res://Scenes/ground_clamp.tscn", "res://Scenes/welding_machine.tscn",
	]:
		var res := load(path)
		_check(res is PackedScene, "carga " + path)
		if res is PackedScene:
			var inst := (res as PackedScene).instantiate()
			_check(inst != null, "instancia " + path)
			if inst != null:
				inst.free()


# ---------------------------------------------------------------------------

func _test_device_link() -> void:
	var tx := PacketPeerUDP.new()
	tx.set_dest_address("127.0.0.1", DeviceLink.LISTEN_PORT)
	DeviceLink.input_mode = DeviceLink.InputMode.AUTO
	var pkt := func(q: Quaternion, dist: float, btn: int) -> void:
		var d := {"qw": q.w, "qx": q.x, "qy": q.y, "qz": q.z, "d": dist, "b": btn, "t": 0}
		tx.put_packet(JSON.stringify(d).to_utf8_buffer())
	for i in range(8):
		pkt.call(Quaternion.IDENTITY, 25.0, 0)
		await get_tree().physics_frame
		await get_tree().physics_frame
	_check(DeviceLink.hardware_connected, "se detecta la herramienta al recibir paquetes")
	_check(DeviceLink.uses_hardware(), "modo AUTO pasa a hardware")
	DeviceLink.tare_pose()
	for i in range(8):
		pkt.call(Quaternion.IDENTITY, 25.0, 1)
		await get_tree().physics_frame
		await get_tree().physics_frame
	_check(DeviceLink.get_tool_up().is_equal_approx(Vector3.UP), "pose neutra tras tarar: electrodo vertical")
	_check(absf(DeviceLink.get_arc_gap_mm() - 25.0) < 0.01, "distancia leída del paquete")
	_check(DeviceLink.get_trigger(), "botón del arco leído del paquete")
	var tilt := Quaternion(Vector3(1.0, 0.0, 0.0), deg_to_rad(20.0))
	for i in range(60):
		pkt.call(tilt, 25.0, 0)
		await get_tree().physics_frame
	var ang := rad_to_deg(Vector3.UP.angle_to(DeviceLink.get_tool_up()))
	_check(absf(ang - 20.0) < 1.0, "inclinación de 20° reflejada en el vector del electrodo (%.1f°)" % ang)
	# Paquetes basura no deben romper nada.
	tx.put_packet("esto no es json".to_utf8_buffer())
	tx.put_packet("{\"qw\": \"x\"}".to_utf8_buffer())
	tx.put_packet(PackedByteArray([0xff, 0xfe, 0x00]))
	await get_tree().physics_frame
	await get_tree().physics_frame
	_check(true, "paquetes inválidos ignorados sin errores")
	# Pérdida de señal (el enlace usa el reloj real, no el de los cuadros).
	OS.delay_msec(700)
	for i in range(4):
		await get_tree().physics_frame
	_check(not DeviceLink.hardware_connected, "se detecta la pérdida de señal")
	_check(not DeviceLink.uses_hardware(), "sin señal vuelve al modo simulado")
	tx.close()


# ---------------------------------------------------------------------------

func _spawn_exercise(level: int) -> Node:
	Game.selected_level = level
	var scene := (load("res://Scenes/Main_scene.tscn") as PackedScene).instantiate()
	get_tree().root.add_child(scene)
	await get_tree().physics_frame
	await get_tree().physics_frame
	return scene


func _prepare_and_start(scene: Node) -> ExerciseController:
	var ctrl := scene.get_node("ExerciseController") as ExerciseController
	var player := scene.get_node("Player") as Player
	var machine := scene.get_node("WeldingMachine") as WeldingMachine
	var clamp := scene.get_node("GroundClamp") as GroundClamp
	var holder := scene.get_node("ElectrodeHolder") as ElectrodeHolder
	var table := scene.get_node("TableWork") as Node
	var spot := scene.get_node("WeldingSpot") as WeldingSpot

	_check(ctrl.state == ExerciseController.State.SETUP, "arranca en la fase de preparación")
	_check(not ctrl.missing_requirements().is_empty(), "faltan requisitos al inicio")

	machine.toggle_power()
	machine.adjust_amperage(1)
	_check(machine.is_on, "la máquina enciende")

	# Un anclaje o el spot nunca deben poder agarrarse con las manos vacías.
	var anchor := table.get_node("ClampAnchorLeft") as ClampAnchor
	_check(not anchor.can_interact(player.interactor), "el anclaje no es interactuable sin la pinza")
	player.interactor.pick_up(clamp)
	_check(player.interactor.held == clamp, "se agarra la pinza")
	_check(anchor.can_interact(player.interactor), "el anclaje es interactuable con la pinza en mano")
	anchor.interact(player.interactor)
	await get_tree().physics_frame
	_check(clamp.is_clamped and player.interactor.held == null, "la pinza queda enganchada a la mesa")
	_check(spot.is_active, "aparece la marca amarilla al conectar la pinza")

	player.interactor.pick_up(holder)
	_check(holder.is_held, "se agarra el portaelectrodo")
	player.global_position = spot.global_position
	for i in range(4):
		await get_tree().physics_frame
	_check(spot.contains(player), "el jugador está sobre la marca")
	_check(ctrl.missing_requirements().is_empty(), "requisitos completos")

	ctrl.start_exercise()
	_check(ctrl.state == ExerciseController.State.CALIBRATING, "comienza la calibración")
	_check(ctrl.electrode_cable != null and not ctrl.electrode_cable.visible, "el cable se oculta al calibrar")
	var guard := 0
	while ctrl.state != ExerciseController.State.WELDING and guard < 600:
		guard += 1
		await get_tree().physics_frame
	_check(ctrl.state == ExerciseController.State.WELDING, "pasa a la fase de soldadura (%d cuadros)" % guard)
	_check(not ctrl.electrode_cable.visible, "el cable sigue oculto durante la soldadura")
	return ctrl


func _drive(ctrl: ExerciseController, frames: int, speed_mm_s: float, gap: float, work: float, travel: float, lateral_mm_s: float = 0.0) -> void:
	DeviceLink.set_sim_state(work, travel, gap)
	for i in range(frames):
		DeviceLink.add_sim_travel(Vector2(speed_mm_s / 60.0, lateral_mm_s / 60.0))
		await get_tree().physics_frame


func _run_scenario(level: int, speed: float, gap: float, work: float, travel: float, mask_down: bool, label: String) -> Dictionary:
	var scene := await _spawn_exercise(level)
	var ctrl := await _prepare_and_start(scene)
	var player := scene.get_node("Player") as Player
	var holder := ctrl.holder
	var coupon := scene.get_node("Coupon") as Coupon
	player.mask_hud.set_down(mask_down)
	DeviceLink.set_sim_state(work, travel, gap)
	DeviceLink.test_trigger = true
	var len_before := holder.length_mm
	var frames := int(coupon.seam_length_mm / speed * 60.0) + 30
	# Cebado correcto a 3 mm y luego la técnica del escenario.
	await _drive(ctrl, 20, 0.0, 3.0, work, travel)
	await _drive(ctrl, frames, speed, gap, work, travel)
	_check(ctrl.arc.state != ArcSimulator.State.OFF or label != "ideal", "[%s] el arco sigue encendido al final de la pasada" % label)
	var consumed := len_before - holder.length_mm
	if label == "ideal":
		_check(consumed > 20.0, "[%s] el electrodo se consumió (%.0f mm)" % [label, consumed])
		_check(coupon.bead.coverage() > 0.9, "[%s] el cordón cubre la junta (%.0f %%)" % [label, coupon.bead.coverage() * 100.0])
		_check(coupon.bead.mesh != null, "[%s] se generó la malla del cordón" % label)
	DeviceLink.test_trigger = false
	ctrl.finish_exercise()
	_check(ctrl.state == ExerciseController.State.FINISHED, "[%s] el ejercicio termina" % label)
	var report := ctrl.report
	print("     [%s] nota %.1f (%s)  cobertura %.0f %%  electrodo %.0f mm" % [
		label, float(report["grade"]), String(report["grade_label"]),
		float((report["stats"] as Dictionary)["coverage_pct"]), consumed])
	if label == "ideal":
		var rec := ctrl.recorder
		_check(rec.rows.size() > 100, "[%s] se registró la serie temporal (%d filas)" % [label, rec.rows.size()])
		var path := rec.export_csv(report, "/tmp/csv_test")
		_check(path != "" and FileAccess.file_exists(path), "[%s] se exporta el CSV (%s)" % [label, path])
		var txt := FileAccess.get_file_as_string(path)
		_check(txt.contains("sep=;") and txt.contains("tiempo_s;arco_encendido") and txt.contains("# CRITERIOS"), "[%s] el CSV tiene resumen y serie" % label)
		_check(txt.contains("velocidad_ideal_mm_s") and txt.contains(","), "[%s] el CSV usa decimales con coma" % label)
		var win := ctrl.report_window
		_check(win.visible, "[%s] se muestra la ventana del informe" % label)
		var charts := win.find_children("*", "SeriesChart", true, false)
		_check(charts.size() == 6, "[%s] el informe tiene 6 gráficos" % label)
	scene.queue_free()
	await get_tree().physics_frame
	await get_tree().physics_frame
	return report


func _wait_sequence_idle(seq: SetupSequence, max_frames: int = 900) -> void:
	var guard := 0
	while seq.busy and guard < max_frames:
		guard += 1
		await get_tree().physics_frame


func _test_setup_sequence() -> void:
	print("-- Preparación guiada (secuencia 1-5) --")
	var scene := await _spawn_exercise(1)
	var ctrl := scene.get_node("ExerciseController") as ExerciseController
	var seq := ctrl.sequence
	var player := scene.get_node("Player") as Player
	var machine := scene.get_node("WeldingMachine") as WeldingMachine
	var clamp := scene.get_node("GroundClamp") as GroundClamp
	var holder := scene.get_node("ElectrodeHolder") as ElectrodeHolder
	var start_pos := player.global_position

	# El jugador ya no se mueve con el teclado: no hay acciones de movimiento.
	for a in ["left", "right", "forward", "back", "jump", "crouch", "start_exercise"]:
		_check(not InputMap.has_action(a), "no existe la acción de movimiento libre '%s'" % a)
	for i in range(1, 6):
		_check(InputMap.has_action("step_%d" % i), "existe la acción step_%d" % i)

	# Saltear pasos está prohibido.
	for bad in [2, 3, 4, 5]:
		seq.request(bad)
		_check(seq.next_step == 1 and not seq.busy, "no se puede ejecutar el paso %d antes del 1" % bad)
	_check(not clamp.is_clamped and not holder.is_held and not machine.is_on, "ningún paso se ejecutó")
	_check(player.global_position.is_equal_approx(start_pos), "el jugador no se movió")

	# Paso 1.
	seq.request(1)
	_check(seq.busy, "el paso 1 deja la secuencia ocupada")
	seq.request(2)
	_check(seq.next_step == 1, "mientras hay una tarea en curso se ignoran otros pasos")
	await _wait_sequence_idle(seq)
	_check(clamp.is_clamped and seq.next_step == 2, "paso 1: pinza de masa conectada")
	seq.request(1)
	_check(seq.next_step == 2, "repetir el paso 1 no retrocede ni repite")
	seq.request(3)
	_check(seq.next_step == 2 and not machine.is_on, "no se salta del 2 al 3")

	# Paso 2 y 3.
	seq.request(2)
	await _wait_sequence_idle(seq)
	_check(holder.is_held and seq.next_step == 3, "paso 2: portaelectrodo en mano")
	seq.request(3)
	await _wait_sequence_idle(seq)
	_check(machine.is_on and seq.next_step == 4, "paso 3: máquina encendida")

	# Paso 4: la rueda solo funciona después de mirar la máquina.
	var amps0 := machine.current_amperage
	_check(not seq.adjust_amperage(1) and machine.current_amperage == amps0, "la rueda no regula antes del paso 4")
	seq.request(4)
	await _wait_sequence_idle(seq)
	_check(seq.amperage_mode and seq.next_step == 5, "paso 4: mirando la máquina, modo amperaje")
	_check(seq.adjust_amperage(1) and machine.current_amperage == amps0 + machine.amperage_step, "la rueda sube el amperaje")
	# Con amperaje fuera de rango, el paso 5 se bloquea (nivel con ayudas).
	machine.current_amperage = 60
	seq.request(5)
	_check(ctrl.state == ExerciseController.State.SETUP and not seq.busy, "amperaje fuera de rango: el paso 5 se bloquea")
	machine.current_amperage = 110
	seq.request(5)
	_check(seq.busy, "con amperaje correcto el paso 5 arranca")
	var guard := 0
	while ctrl.state != ExerciseController.State.WELDING and guard < 900:
		guard += 1
		await get_tree().physics_frame
	_check(ctrl.state == ExerciseController.State.WELDING, "tras el paso 5 se calibra y se pasa a soldar")
	_check(player.mode == Player.Mode.STATION, "el operario queda posicionado en la mesa de trabajo")
	scene.queue_free()
	await get_tree().physics_frame
	await get_tree().physics_frame


func _test_exercise_flow() -> void:
	# Orientación de la pantalla: el avance va de izquierda a derecha y el desvío
	# transversal positivo hacia abajo.
	var scene := await _spawn_exercise(2)
	var ctrl := await _prepare_and_start(scene)
	var player := scene.get_node("Player") as Player
	var coupon := scene.get_node("Coupon") as Coupon
	await get_tree().physics_frame
	var cam := player.camera
	var p0 := cam.unproject_position(coupon.seam_to_global(0.0, 0.0))
	var p1 := cam.unproject_position(coupon.seam_to_global(150.0, 0.0))
	var pv := cam.unproject_position(coupon.seam_to_global(75.0, 20.0))
	var pc := cam.unproject_position(coupon.seam_to_global(75.0, 0.0))
	_check(p1.x > p0.x + 50.0, "el avance de la junta va de izquierda a derecha (%.0f -> %.0f px)" % [p0.x, p1.x])
	_check(pv.y > pc.y, "desvío transversal positivo = hacia abajo en pantalla")
	var viewport_w := player.get_viewport().get_visible_rect().size.x
	_check(p0.x > 0.0 and p1.x < viewport_w, "la junta completa entra en pantalla (%.0f..%.0f de %.0f)" % [p0.x, p1.x, viewport_w])
	_check(not cam.is_position_behind(coupon.seam_to_global(75.0, 0.0)), "la probeta está frente a la cámara")

	# Eventos: pegado y arco apagado.
	player.mask_hud.set_down(true)
	DeviceLink.set_sim_state(0.0, 10.0, 2.5)
	DeviceLink.test_trigger = true
	await _drive(ctrl, 30, 0.0, 2.5, 0.0, 10.0)
	_check(ctrl.arc.state == ArcSimulator.State.ARCING, "el arco ceba en la fase de soldadura")
	await _drive(ctrl, 45, 0.0, 0.3, 0.0, 10.0)
	_check(ctrl.arc.state == ArcSimulator.State.STUCK, "evento: electrodo pegado")
	DeviceLink.test_trigger = false
	await _drive(ctrl, 5, 0.0, 3.0, 0.0, 10.0)
	_check(ctrl.arc.state == ArcSimulator.State.OFF, "se libera el electrodo al alejarse")
	DeviceLink.test_trigger = true
	await _drive(ctrl, 5, 0.0, 3.0, 0.0, 10.0)
	DeviceLink.test_trigger = false
	await _drive(ctrl, 3, 0.0, 3.0, 0.0, 10.0)
	DeviceLink.test_trigger = true
	await _drive(ctrl, 5, 0.0, 3.0, 0.0, 10.0)
	_check(ctrl.arc.state == ArcSimulator.State.ARCING, "recebado correcto")
	await _drive(ctrl, 30, 0.0, 8.0, 0.0, 10.0)
	_check(ctrl.arc.state == ArcSimulator.State.OUT, "evento: arco apagado por distancia")
	# Consumo total del electrodo y reemplazo.
	DeviceLink.test_trigger = false
	await _drive(ctrl, 3, 0.0, 3.0, 0.0, 10.0)
	var holder := ctrl.holder
	holder.consume(1000.0)
	_check(holder.is_depleted(), "el electrodo se agota")
	DeviceLink.test_trigger = true
	await _drive(ctrl, 5, 0.0, 3.0, 0.0, 10.0)
	_check(ctrl.arc.state == ArcSimulator.State.OFF, "con el electrodo agotado no se puede cebar")
	DeviceLink.test_trigger = false
	ctrl._try_replace_electrode()
	_check(not holder.is_depleted() and holder.electrodes_used == 2, "se reemplaza el electrodo")
	ctrl.finish_exercise()
	_check(float(ctrl.report["grade"]) < 6.0, "pasada interrumpida: no aprueba (%.1f)" % float(ctrl.report["grade"]))
	scene.queue_free()
	await get_tree().physics_frame
	await get_tree().physics_frame

	# Pasadas completas.
	var good := await _run_scenario(2, 3.0, 2.5, 0.0, 10.0, true, "ideal")
	_check(float(good["grade"]) >= 8.5 and bool(good["passed"]), "pasada ideal: nota alta (%.1f)" % float(good["grade"]))
	var bad := await _run_scenario(2, 8.0, 5.5, 22.0, -5.0, false, "mala")
	_check(float(bad["grade"]) < float(good["grade"]) - 3.0, "pasada mala: nota mucho menor (%.1f)" % float(bad["grade"]))
	_check(float((bad["stats"] as Dictionary)["safety_s"]) > 0.0, "soldar sin careta queda registrado")
	var l3 := await _run_scenario(3, 3.0, 2.5, 0.0, 11.0, true, "nivel3")
	_check(float(l3["grade"]) >= 8.0, "nivel 3 con buena técnica aprueba (%.1f)" % float(l3["grade"]))
	var slow := await _run_scenario(1, 1.0, 2.5, 0.0, 10.0, true, "lenta")
	print("     lenta: nota %.1f" % float(slow["grade"]))
