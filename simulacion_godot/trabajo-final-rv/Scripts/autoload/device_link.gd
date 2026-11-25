extends Node
## Enlace con la herramienta física (autoload "DeviceLink").
##
## Abstrae el origen de los datos de la herramienta para el resto del
## simulador. Hay dos fuentes intercambiables:
##   * HARDWARE: telemetría JSON del ESP32 por UDP (puerto 4242). El ESP32 se
##     conecta por USB y tools/serial_bridge.py reenvía las tramas a Godot.
##   * SIMULADA: teclado y mouse (para desarrollar y probar sin la herramienta).
##
## Protocolo (ver README.md, sección 8):
##   ESP32 -> Godot  {"qw","qx","qy","qz","d","b","t",...}   d = distancia punta-chapa [mm]
##                   campos opcionales de seguimiento de posición: "dx","dy" [mm]
##   Godot -> ESP32  {"cmd":"CALIBRATE"} | {"cmd":"RESET_YAW"} | {"cmd":"PING"}
##                   {"cmd":"SET_HAPTIC","val":0-255,"m":0|1}
##                   {"cmd":"SET_LED","r":0-255,"g":0-255,"b":0-255}
##
## La orientación se expresa como el versor "up" (de la punta al portaelectrodo)
## en el marco de la probeta, relativo a una pose neutra calibrada con tare_pose().

signal connection_changed(connected: bool)

enum InputMode { AUTO, SIMULATED, HARDWARE }

const LISTEN_PORT := 4242
const COMMAND_PORT := 4243
const COMMAND_HOST := "127.0.0.1"
const TIMEOUT_S := 0.5
const BIND_RETRY_S := 3.0
const HAPTIC_MIN_INTERVAL_S := 1.0 / 30.0
const HAPTIC_KEEPALIVE_S := 0.25
const LED_MIN_INTERVAL_S := 1.0 / 20.0
const LED_KEEPALIVE_S := 0.2          # el firmware suelta el control a los 500 ms sin mensajes
const CONFIG_POLL_S := 1.0            # relectura de tool_config.json (cambios desde la GUI)
const TOOL_CONFIG_PATH := "res://tool_config.json"

# Valores de la simulación por teclado y mouse.
const SIM_MOUSE_MM_PER_PX := 0.12
const SIM_GAP_STEP_MM := 0.25
const SIM_GAP_MAX_MM := 15.0
const SIM_ANGLE_RATE_DEG_S := 30.0

# --- Configuración ---
var input_mode: int = InputMode.AUTO
## Cantidad de motores hápticos presentes en la herramienta (1 o 2).
var haptic_motor_count: int = 1
## Escala y desplazamiento de la distancia medida (virtual = medida * escala + offset).
## Con escala < 1 se amplía el rango útil del sensor (ver docs/CALIBRATION_GUIDE.md).
var distance_scale: float = 1.0
var distance_offset_mm: float = 0.0
## Rotación del marco del IMU (Z arriba) al marco de la probeta (Y arriba, X = avance).
var imu_to_probe: Basis = Basis(Vector3(1, 0, 0), Vector3(0, 0, -1), Vector3(0, 1, 0))
## Suavizado de la orientación (1/s). Más alto = más rápido y más ruidoso.
var orientation_smoothing: float = 30.0

# --- Estado de la conexión ---
var hardware_connected: bool = false
var packet_rate_hz: float = 0.0
var packets_received: int = 0
var has_position_tracking: bool = false

# --- Entrada simulada ---
## Cuando es true, el teclado y el mouse manejan la herramienta simulada.
var sim_capture: bool = false
## Gatillo forzado por código (pruebas automáticas y demos).
var test_trigger: bool = false

var _udp: PacketPeerUDP
var _udp_out: PacketPeerUDP = PacketPeerUDP.new()
var _bound: bool = false
var _bind_timer: float = 0.0
var _last_sender: String = COMMAND_HOST
var _last_packet_msec: int = -100000
var _rate_counter: int = 0
var _rate_timer: float = 0.0

# Telemetría decodificada
var _hw_basis: Basis = Basis.IDENTITY
var _hw_ref_basis: Basis = Basis.IDENTITY
var _hw_has_orientation: bool = false
var _hw_up: Vector3 = Vector3.UP
var _hw_gap_mm: float = 99.0
var _hw_gap_valid: bool = false
var _hw_gap_msec: int = 0
var _hw_trigger: bool = false
var _hw_travel: Vector2 = Vector2.ZERO
var has_absolute_position: bool = false
var hw_abs_pos_mm: Vector2 = Vector2.ZERO
var _tare_pending: bool = false
var _tare_delay: float = 0.0

# Estado simulado
var _sim_work_deg: float = 0.0
var _sim_travel_deg: float = 0.0
var _sim_gap_mm: float = 8.0
var _sim_travel: Vector2 = Vector2.ZERO

# Háptica
var _haptic_last: Array[int] = [-1, -1]
var _haptic_last_msec: Array[int] = [0, 0]
var _haptic_armed: bool = false

# Pose neutra recordada (para la tara automática al empezar a soldar)
const NEUTRAL_POSE_PATH := "user://pose_neutra.json"
const STILL_DEG_S := 12.0                   # por debajo de esto la herramienta se considera quieta
var has_neutral: bool = false
var neutral_gravity: Vector3 = Vector3.ZERO  # vertical vista desde el IMU en la pose neutra
var tare_count: int = 0                      # aumenta en cada tara (manual o automática)
var _hw_q_basis: Basis = Basis.IDENTITY      # orientación cruda del IMU
var _prev_q_basis: Basis = Basis.IDENTITY
var _motion_deg_s: float = 999.0
var _still_time: float = 0.0

var tool_config: Dictionary = {}

## true: el arco solo arranca con el homing (punta apoyada + pulsador).
## false: el arco arranca solo al acercar la punta a la distancia de encendido.
var homing_required: bool = false

## Colores del LED de la herramienta (tool_config.json -> "led_colors").
var led_colors: Dictionary = {
	"weld_optimal": [0, 255, 0],
	"weld_caution": [255, 170, 0],
	"weld_warning": [255, 0, 0],
	"sticking": [255, 0, 0],
}
## Intensidad del motor por situación, 0-100 % (tool_config.json -> "haptic_intensity_pct").
var haptic_pct: Dictionary = {"homing": 78, "weld_optimal": 45, "weld_warning": 60, "sticking": 100}

var _led_last: Array = []
var _led_last_msec: int = 0
var _config_mtime: int = 0
var _config_timer: float = 0.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_try_bind()
	load_tool_config()
	_load_neutral_pose()


func load_tool_config() -> void:
	var path := TOOL_CONFIG_PATH
	if not FileAccess.file_exists(path):
		return
	_config_mtime = FileAccess.get_modified_time(path)
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return
	var json := JSON.new()
	var err := json.parse(file.get_as_text())
	if err == OK and typeof(json.data) == TYPE_DICTIONARY:
		tool_config = json.data
		_apply_tool_config()
		print("DeviceLink: Configuracion de herramienta cargada desde tool_config.json")


## Relee tool_config.json si cambió (por ejemplo, al tocar el botón de homing en la GUI).
func _poll_tool_config(delta: float) -> void:
	_config_timer -= delta
	if _config_timer > 0.0:
		return
	_config_timer = CONFIG_POLL_S
	if not FileAccess.file_exists(TOOL_CONFIG_PATH):
		return
	var mt := FileAccess.get_modified_time(TOOL_CONFIG_PATH)
	if mt != _config_mtime:
		var before := homing_required
		load_tool_config()
		if before != homing_required:
			print("DeviceLink: homing %s" % ("ACTIVADO (pulsador)" if homing_required else "DESACTIVADO (arco automático)"))


func _apply_tool_config() -> void:
	if tool_config.has("homing_required"):
		homing_required = bool(tool_config["homing_required"])
	if tool_config.has("led_colors") and typeof(tool_config["led_colors"]) == TYPE_DICTIONARY:
		var lc: Dictionary = tool_config["led_colors"]
		for k in lc:
			if typeof(lc[k]) == TYPE_ARRAY and (lc[k] as Array).size() == 3:
				led_colors[k] = lc[k]
	if tool_config.has("haptic_intensity_pct") and typeof(tool_config["haptic_intensity_pct"]) == TYPE_DICTIONARY:
		var hp: Dictionary = tool_config["haptic_intensity_pct"]
		for k in hp:
			haptic_pct[k] = float(hp[k])
	if tool_config.has("tof_limits_mm"):
		var limits: Dictionary = tool_config["tof_limits_mm"]
		if limits.has("stick_gap"):
			WeldPhysics.STICK_GAP_MM = float(limits["stick_gap"])
		if limits.has("extinguish_gap"):
			WeldPhysics.EXTINGUISH_GAP_MM = float(limits["extinguish_gap"])
		if limits.has("optimal_min"):
			WeldPhysics.OPTIMAL_GAP_MIN_MM = float(limits["optimal_min"])
		if limits.has("optimal_max"):
			WeldPhysics.OPTIMAL_GAP_MAX_MM = float(limits["optimal_max"])
		if limits.has("reignite_gap"):
			WeldPhysics.REIGNITE_GAP_MM = float(limits["reignite_gap"])
	if tool_config.has("tool_tip_lever_mm"):
		WeldPhysics.TOOL_TIP_LEVER_MM = float(tool_config["tool_tip_lever_mm"])
		print("DeviceLink: Brazo cinematico punta-marcador configurado en %.1f mm" % WeldPhysics.TOOL_TIP_LEVER_MM)
		print("DeviceLink: Limites ToF actualizados -> Optimo: [%.1f - %.1f] mm, Pegado: <= %.1f mm, Extincion: >= %.1f mm, Reencendido: <= %.1f mm" % [
			WeldPhysics.OPTIMAL_GAP_MIN_MM, WeldPhysics.OPTIMAL_GAP_MAX_MM,
			WeldPhysics.STICK_GAP_MM, WeldPhysics.EXTINGUISH_GAP_MM, WeldPhysics.REIGNITE_GAP_MM
		])


func _exit_tree() -> void:
	stop_haptics()
	if _udp != null:
		_udp.close()


func _process(delta: float) -> void:
	_bind_timer -= delta
	if not _bound and _bind_timer <= 0.0:
		_try_bind()
	_poll_udp()
	_update_connection(delta)
	_update_tare(delta)
	_update_sim_keys(delta)
	_smooth_orientation(delta)
	_poll_tool_config(delta)
	_update_stillness(delta)


func _input(event: InputEvent) -> void:
	if not sim_capture or Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	if event is InputEventMouseMotion:
		var m := event as InputEventMouseMotion
		_sim_travel += m.relative * SIM_MOUSE_MM_PER_PX
	elif event is InputEventMouseButton:
		var b := event as InputEventMouseButton
		if b.pressed and b.button_index == MOUSE_BUTTON_WHEEL_UP:
			_sim_gap_mm = minf(_sim_gap_mm + SIM_GAP_STEP_MM, SIM_GAP_MAX_MM)
		elif b.pressed and b.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_sim_gap_mm = maxf(_sim_gap_mm - SIM_GAP_STEP_MM, 0.0)


# ---------------------------------------------------------------------------
# API de lectura (la usa el controlador del ejercicio)
# ---------------------------------------------------------------------------

## true si la herramienta física es la fuente activa de orientación/distancia/gatillo.
func uses_hardware() -> bool:
	match input_mode:
		InputMode.SIMULATED:
			return false
		InputMode.HARDWARE:
			return true
		_:
			return hardware_connected


func get_tool_up() -> Vector3:
	if uses_hardware():
		return _hw_up
	return WeldGeometry.up_from_angles(_sim_work_deg, _sim_travel_deg)


## Distancia punta-chapa virtual [mm]. INF si no hay lectura válida.
func get_arc_gap_mm() -> float:
	if uses_hardware():
		return _hw_gap_mm if _hw_gap_valid else INF
	return _sim_gap_mm


func get_trigger() -> bool:
	if test_trigger:
		return true
	if uses_hardware() and hardware_connected:
		# En modo AUTO el clic izquierdo también sirve (útil para pruebas).
		return _hw_trigger or (sim_capture and Input.is_action_pressed("arc_trigger"))
	return sim_capture and Input.is_action_pressed("arc_trigger")


## Desplazamiento de la punta [mm] desde la última llamada (x = avance, y = transversal).
## Si el hardware no informa posición, se usa el mouse (modo híbrido).
func consume_travel_mm() -> Vector2:
	var t := _sim_travel
	_sim_travel = Vector2.ZERO
	if uses_hardware() and has_position_tracking:
		t = _hw_travel
		_hw_travel = Vector2.ZERO
	else:
		_hw_travel = Vector2.ZERO
	return t


## Fija el estado simulado desde código (pruebas automáticas y demos).
func set_sim_state(work_deg: float, travel_deg: float, gap_mm: float) -> void:
	_sim_work_deg = work_deg
	_sim_travel_deg = travel_deg
	_sim_gap_mm = gap_mm


## Suma un desplazamiento simulado [mm] (x = avance, y = transversal).
func add_sim_travel(delta_mm: Vector2) -> void:
	_sim_travel += delta_mm


func source_name() -> String:
	if uses_hardware():
		return "HARDWARE" if hardware_connected else "HARDWARE (sin señal)"
	return "SIMULADO"


## Texto de estado para mostrar en el HUD.
func status_text() -> String:
	if hardware_connected:
		return "Herramienta: CONECTADA (%d Hz)" % roundi(packet_rate_hz)
	if input_mode == InputMode.HARDWARE:
		return "Herramienta: SIN SEÑAL"
	return "Herramienta: simulada (teclado y mouse)"


func set_input_mode(mode: int) -> void:
	input_mode = clampi(mode, InputMode.AUTO, InputMode.HARDWARE)


## Cicla AUTO -> SIMULATED -> HARDWARE.
func cycle_input_mode() -> void:
	set_input_mode((input_mode + 1) % 3)


# ---------------------------------------------------------------------------
# Calibración
# ---------------------------------------------------------------------------

## Define la pose actual como pose neutra (electrodo perpendicular a la chapa).
func tare_pose() -> void:
	_sim_work_deg = 0.0
	_sim_travel_deg = 0.0
	tare_count += 1
	if _hw_has_orientation:
		_hw_ref_basis = _hw_basis
		_hw_up = Vector3.UP
		_save_neutral_pose()
	else:
		_tare_pending = true


## Vertical (arriba) vista desde el IMU. Depende solo de la inclinación (pitch/roll, que el
## acelerómetro mide sin deriva), no del yaw: sirve para reconocer la pose neutra entre sesiones.
func gravity_imu() -> Vector3:
	return (_hw_q_basis.transposed() * Vector3(0, 0, 1)).normalized()


## Ángulo [°] entre la inclinación actual y la pose neutra recordada (INF si no hay).
func neutral_tilt_error_deg() -> float:
	if not has_neutral or not _hw_has_orientation:
		return INF
	return rad_to_deg(gravity_imu().angle_to(neutral_gravity))


## Segundos que la herramienta lleva quieta.
func still_time() -> float:
	return _still_time if hardware_connected else 0.0


func _update_stillness(delta: float) -> void:
	if not _hw_has_orientation or delta <= 0.0:
		_still_time = 0.0
		return
	var d := rad_to_deg((_prev_q_basis.inverse() * _hw_q_basis).get_rotation_quaternion().get_angle())
	_prev_q_basis = _hw_q_basis
	_motion_deg_s = lerpf(_motion_deg_s, d / delta, 0.3)
	_still_time = _still_time + delta if _motion_deg_s < STILL_DEG_S else 0.0


func _save_neutral_pose() -> void:
	neutral_gravity = gravity_imu()
	has_neutral = true
	var f := FileAccess.open(NEUTRAL_POSE_PATH, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify({"g": [neutral_gravity.x, neutral_gravity.y, neutral_gravity.z]}))


func _load_neutral_pose() -> void:
	if not FileAccess.file_exists(NEUTRAL_POSE_PATH):
		return
	var f := FileAccess.open(NEUTRAL_POSE_PATH, FileAccess.READ)
	if f == null:
		return
	var d = JSON.parse_string(f.get_as_text())
	if typeof(d) == TYPE_DICTIONARY and d.has("g") and (d["g"] as Array).size() == 3:
		var g: Array = d["g"]
		neutral_gravity = Vector3(float(g[0]), float(g[1]), float(g[2])).normalized()
		has_neutral = neutral_gravity.length() > 0.5


## Calibra los offsets del IMU en el ESP32 (herramienta quieta) y retara.
func calibrate_imu() -> void:
	send_command({"cmd": "HAPTIC_MUTE", "ms": 3000})
	send_command({"cmd": "CALIBRATE"})
	_tare_delay = 1.5


## Pone el yaw del ESP32 en cero y retara.
func reset_yaw() -> void:
	send_command({"cmd": "RESET_YAW"})
	_tare_delay = 0.25


func ping() -> void:
	send_command({"cmd": "PING"})


# ---------------------------------------------------------------------------
# Salida: comandos y háptica
# ---------------------------------------------------------------------------

func send_command(cmd: Dictionary) -> void:
	var target := _last_sender if _last_sender != "" else COMMAND_HOST
	var err := _udp_out.set_dest_address(target, COMMAND_PORT)
	if err != OK:
		return
	_udp_out.put_packet((JSON.stringify(cmd) + "\n").to_utf8_buffer())


## Fija la intensidad (0-255) de un motor. Limita la tasa de envío y evita repeticiones.
## armed: true mientras hay un arco en curso en el ejercicio. Solo entonces el firmware puede
## vibrar por su cuenta al detectar el electrodo pegado (fuera de eso, el motor queda quieto,
## por ejemplo al calibrar apoyando la punta).
func send_haptic(motor: int, duty: int, armed: bool = false) -> void:
	if motor < 0 or motor >= mini(haptic_motor_count, 2):
		return
	if not hardware_connected:
		return
	var d := clampi(duty, 0, 255)
	var now := Time.get_ticks_msec()
	var elapsed := (now - _haptic_last_msec[motor]) / 1000.0
	var changed := d != _haptic_last[motor] or (motor == 0 and armed != _haptic_armed)
	if changed and elapsed < HAPTIC_MIN_INTERVAL_S:
		return
	if not changed and elapsed < HAPTIC_KEEPALIVE_S:
		return
	_haptic_last[motor] = d
	_haptic_last_msec[motor] = now
	if motor == 0:
		_haptic_armed = armed
	send_command({"cmd": "SET_HAPTIC", "val": d, "m": motor, "arm": 1 if armed else 0})


## Intensidad 0-255 configurada para una situación ("homing", "weld_optimal", "weld_warning", "sticking").
func haptic_duty(key: String, fallback_pct: float = 50.0) -> int:
	return clampi(roundi(float(haptic_pct.get(key, fallback_pct)) * 2.55), 0, 255)


## Color [r, g, b] configurado para una situación ("weld_optimal", "weld_caution", "weld_warning", "sticking").
func led_color(key: String) -> Array:
	var c: Array = led_colors.get(key, [255, 255, 255])
	return [clampi(int(c[0]), 0, 255), clampi(int(c[1]), 0, 255), clampi(int(c[2]), 0, 255)]


## Fija el color del LED de la herramienta. Limita la tasa de envío y repite cada 200 ms.
func send_led(rgb: Array) -> void:
	if not hardware_connected or rgb.size() != 3:
		return
	var now := Time.get_ticks_msec()
	var elapsed := (now - _led_last_msec) / 1000.0
	var changed := rgb != _led_last
	if changed and elapsed < LED_MIN_INTERVAL_S:
		return
	if not changed and elapsed < LED_KEEPALIVE_S:
		return
	_led_last = rgb.duplicate()
	_led_last_msec = now
	send_command({"cmd": "SET_LED", "r": int(rgb[0]), "g": int(rgb[1]), "b": int(rgb[2])})


func stop_haptics() -> void:
	if not hardware_connected:
		return
	for m in range(mini(haptic_motor_count, 2)):
		_haptic_last[m] = 0
		_haptic_last_msec[m] = Time.get_ticks_msec()
		send_command({"cmd": "SET_HAPTIC", "val": 0, "m": m})


# ---------------------------------------------------------------------------
# Recepción
# ---------------------------------------------------------------------------

func _try_bind() -> void:
	_bind_timer = BIND_RETRY_S
	if _udp != null:
		_udp.close()
	_udp = PacketPeerUDP.new()
	var err := _udp.bind(LISTEN_PORT)
	_bound = err == OK
	if not _bound:
		push_warning("DeviceLink: no se pudo abrir el puerto UDP %d (error %d). Modo simulado." % [LISTEN_PORT, err])


func _poll_udp() -> void:
	if not _bound:
		return
	var guard := 0
	while _udp.get_available_packet_count() > 0 and guard < 200:
		guard += 1
		var raw := _udp.get_packet()
		var err := _udp.get_packet_error()
		if err != OK:
			continue
		var sender := _udp.get_packet_ip()
		if sender != "":
			_last_sender = sender
		if not _is_ascii_text(raw):
			continue  # el protocolo es JSON ASCII: se descarta cualquier otra cosa
		for line in raw.get_string_from_ascii().split("\n", false):
			_handle_line(line.strip_edges())


static func _is_ascii_text(raw: PackedByteArray) -> bool:
	if raw.size() > 1024:
		return false
	for b in raw:
		if b >= 0x80 or (b < 0x20 and b != 0x0A and b != 0x0D and b != 0x09):
			return false
	return true


func _handle_line(line: String) -> void:
	if line.is_empty():
		return
	var json := JSON.new()
	if json.parse(line) != OK or typeof(json.data) != TYPE_DICTIONARY:
		return
	var d: Dictionary = json.data
	if not d.has("d") and not d.has("qw") and not d.has("dx"):
		return  # acks ({"ack":...}) y otros mensajes
	_last_packet_msec = Time.get_ticks_msec()
	packets_received += 1
	_rate_counter += 1

	if d.has("qw") and d.has("qx") and d.has("qy") and d.has("qz"):
		_apply_quaternion(float(d["qw"]), float(d["qx"]), float(d["qy"]), float(d["qz"]))
	if d.has("d"):
		var dist := float(d["d"])
		if is_nan(dist) or dist < 0.0:
			if Time.get_ticks_msec() - _hw_gap_msec > 200:
				_hw_gap_valid = false
		else:
			var target_gap := maxf(dist * distance_scale + distance_offset_mm, 0.0)
			if not _hw_gap_valid:
				_hw_gap_mm = target_gap
			else:
				# Suavizado pasa-bajos del 40% para eliminar micro-fluctuación cuántica del ToF
				_hw_gap_mm = lerpf(_hw_gap_mm, target_gap, 0.40)
			_hw_gap_valid = true
			_hw_gap_msec = Time.get_ticks_msec()
	if d.has("b"):
		_hw_trigger = int(d["b"]) != 0
	if d.has("dx") and d.has("dy"):
		has_position_tracking = true
		_hw_travel += Vector2(float(d["dx"]), float(d["dy"]))
	if d.has("x") and d.has("y"):
		has_position_tracking = true
		has_absolute_position = true
		hw_abs_pos_mm = Vector2(float(d["x"]), float(d["y"]))


func _apply_quaternion(w: float, x: float, y: float, z: float) -> void:
	var q := Quaternion(x, y, z, w)
	if is_nan(q.length_squared()) or q.length_squared() < 0.5:
		return
	q = q.normalized()
	_hw_q_basis = Basis(q)
	# Cambio de base IMU -> probeta (rotación propia: det = +1).
	_hw_basis = imu_to_probe * Basis(q) * imu_to_probe.inverse()
	if not _hw_has_orientation:
		_hw_has_orientation = true
		_hw_ref_basis = _hw_basis
	if _tare_pending:
		_tare_pending = false
		_hw_ref_basis = _hw_basis


func _update_connection(delta: float) -> void:
	var now_connected := (Time.get_ticks_msec() - _last_packet_msec) / 1000.0 < TIMEOUT_S
	if now_connected != hardware_connected:
		hardware_connected = now_connected
		if not now_connected:
			_hw_trigger = false
			has_position_tracking = false
			has_absolute_position = false
			packet_rate_hz = 0.0
			for m in 2:
				_haptic_last[m] = -1
		connection_changed.emit(hardware_connected)
	_rate_timer += delta
	if _rate_timer >= 1.0:
		packet_rate_hz = _rate_counter / _rate_timer if hardware_connected else 0.0
		_rate_counter = 0
		_rate_timer = 0.0


func _update_tare(delta: float) -> void:
	if _tare_delay > 0.0:
		_tare_delay -= delta
		if _tare_delay <= 0.0:
			tare_pose()


func _update_sim_keys(delta: float) -> void:
	if not sim_capture:
		return
	var work_axis := Input.get_axis("tool_tilt_left", "tool_tilt_right")
	var travel_axis := Input.get_axis("tool_tilt_back", "tool_tilt_forward")
	_sim_work_deg = clampf(_sim_work_deg + work_axis * SIM_ANGLE_RATE_DEG_S * delta, -60.0, 60.0)
	_sim_travel_deg = clampf(_sim_travel_deg + travel_axis * SIM_ANGLE_RATE_DEG_S * delta, -45.0, 70.0)


func _smooth_orientation(delta: float) -> void:
	if not _hw_has_orientation:
		return
	var rel := _hw_basis * _hw_ref_basis.inverse()
	var target := (rel * Vector3.UP).normalized()
	var k := 1.0 - exp(-orientation_smoothing * delta)
	_hw_up = _hw_up.slerp(target, k).normalized() if _hw_up.dot(target) > -0.999 else target
