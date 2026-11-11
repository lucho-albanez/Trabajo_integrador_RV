class_name SerialManager
extends Node

## ==============================================================================
## SerialManager.gd - Receptor de Telemetría ESP32 para Godot 4.7
## ==============================================================================
## Recibe paquetes de telemetría de alta velocidad vía UDP (desde serial_bridge.py
## por cable USB o directamente por Wi-Fi), los desempaqueta y notifica al simulador.

signal telemetry_received(data: Dictionary)
signal connection_status_changed(is_connected: bool)
signal command_acknowledged(ack_type: String)

@export_group("Configuración de Red")
@export var listen_port: int = 4242
@export var target_command_ip: String = "127.0.0.1"
@export var target_command_port: int = 4243
@export var connection_timeout_seconds: float = 0.5

var _udp_receiver: PacketPeerUDP
var _udp_sender: PacketPeerUDP
var _is_connected: bool = false
var _time_since_last_packet: float = 0.0

# Métricas de rendimiento
var _packet_count: int = 0
var _fps_timer: float = 0.0
var current_packet_rate: float = 0.0

# Último estado recibido
var last_telemetry: Dictionary = {
	"roll": 0.0,
	"pitch": 0.0,
	"yaw": 0.0,
	"quat": Quaternion.IDENTITY,
	"distance_tip_mm": 50.0,
	"raw_distance_mm": 110.0,
	"trigger_pressed": false,
	"haptic_duty": 0,
	"timestamp_ms": 0,
	"sensor_type": 1
}

func _ready() -> void:
	_udp_receiver = PacketPeerUDP.new()
	var err = _udp_receiver.bind(listen_port, "*")
	if err == OK:
		print("[SerialManager] Servidor UDP de telemetría escuchando en puerto: ", listen_port)
	else:
		push_error("[SerialManager] Error al abrir socket UDP en puerto %d: %d" % [listen_port, err])

	_udp_sender = PacketPeerUDP.new()
	_udp_sender.set_dest_address(target_command_ip, target_command_port)

func _physics_process(delta: float) -> void:
	_time_since_last_packet += delta
	_fps_timer += delta

	# Watchdog de conexión
	if _is_connected and _time_since_last_packet > connection_timeout_seconds:
		_is_connected = false
		connection_status_changed.emit(false)
		print("[SerialManager] Conexión con ESP32 perdida (Timeout)")

	# Métricas de tasa de paquetes
	if _fps_timer >= 1.0:
		current_packet_rate = float(_packet_count) / _fps_timer
		_packet_count = 0
		_fps_timer = 0.0

	# Procesar todos los paquetes encolados en el buffer del socket
	while _udp_receiver != null and _udp_receiver.get_available_packet_count() > 0:
		var raw_packet = _udp_receiver.get_packet()
		var json_string = raw_packet.get_string_from_utf8()
		_parse_json_packet(json_string)

func _parse_json_packet(json_text: String) -> void:
	if json_text.is_empty():
		return

	var json = JSON.new()
	var error = json.parse(json_text)
	if error != OK:
		return

	var data = json.data
	if typeof(data) != TYPE_DICTIONARY:
		return

	# Respuesta o confirmación de comando (ACK)
	if data.has("ack"):
		command_acknowledged.emit(data["ack"])
		return
	if data.has("pong"):
		return

	# Paquete de telemetría
	if data.has("r") and data.has("p") and data.has("y"):
		_time_since_last_packet = 0.0
		_packet_count += 1

		if not _is_connected:
			_is_connected = true
			connection_status_changed.emit(true)
			print("[SerialManager] Conexión establecida con la herramienta ESP32!")

		var r: float = float(data.get("r", 0.0))
		var p: float = float(data.get("p", 0.0))
		var y: float = float(data.get("y", 0.0))

		var qw: float = float(data.get("qw", 1.0))
		var qx: float = float(data.get("qx", 0.0))
		var qy: float = float(data.get("qy", 0.0))
		var qz: float = float(data.get("qz", 0.0))

		# Cuaternión normalizado para rotación 3D pura sin deformaciones
		var quat = Quaternion(qx, qy, qz, qw).normalized()

		last_telemetry["roll"] = r
		last_telemetry["pitch"] = p
		last_telemetry["yaw"] = y
		last_telemetry["quat"] = quat
		last_telemetry["distance_tip_mm"] = float(data.get("d", -1.0))
		last_telemetry["trigger_pressed"] = bool(data.get("b", 0) == 1)
		last_telemetry["haptic_duty"] = int(data.get("h", 0))
		last_telemetry["timestamp_ms"] = int(data.get("t", 0))
		last_telemetry["sensor_type"] = int(data.get("st", 1))

		telemetry_received.emit(last_telemetry)

## ==============================================================================
## COMANDOS DE CONTROL HACIA EL ESP32
## ==============================================================================

## Solicita calibración en reposo de offsets de giroscopio y acelerómetro
func send_calibrate_command() -> void:
	_send_json_command({"cmd": "CALIBRATE"})
	print("[SerialManager] Enviado comando de calibración al ESP32...")

## Resetea el ángulo de azimut/yaw a cero frente a la mesa de trabajo
func send_reset_yaw_command() -> void:
	_send_json_command({"cmd": "RESET_YAW"})
	print("[SerialManager] Recentrado de Yaw solicitado al ESP32...")

## Envía intensidad háptica forzada desde el motor de física de Godot (0 a 255)
func send_haptic_override(duty: int) -> void:
	var clamped_duty = clampi(duty, 0, 255)
	_send_json_command({"cmd": "SET_HAPTIC", "val": clamped_duty})

func _send_json_command(dict: Dictionary) -> void:
	if _udp_sender == null:
		return
	var text = JSON.stringify(dict)
	var bytes = text.to_utf8_buffer()
	_udp_sender.put_packet(bytes)
