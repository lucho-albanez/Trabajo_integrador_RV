extends Node3D
## Controlador del Gemelo Digital en Tiempo Real
## Muestra la herramienta 3D rotando exactamente según los datos del MPU-6050

@onready var tool_pivot: Node3D = $ToolPivot
@onready var lbl_status: Label = $UI/Panel/VBox/LblStatus
@onready var lbl_angles: Label = $UI/Panel/VBox/LblAngles
@onready var lbl_trigger: Label = $UI/Panel/VBox/LblTrigger
@onready var lbl_dlpf: Label = $UI/Panel/VBox/LblDlpf
@onready var cam: Camera3D = $CameraPivot/Camera3D
@onready var cam_pivot: Node3D = $CameraPivot

const DLPF_NAMES := [
	"Modo 0 (260 Hz - Sin filtro / Ruido Máximo)",
	"Modo 1 (184 Hz - Filtro muy leve)",
	"Modo 2 (94 Hz - Filtro leve)",
	"Modo 3 (44 Hz - Equilibrado Estándar)",
	"Modo 4 (21 Hz - Filtrado activo)",
	"Modo 5 (10 Hz - Muy Suave / Recomendado SMAW)",
	"Modo 6 (5 Hz - Filtrado Extremo)"
]

var _cam_drag: bool = false

func _ready() -> void:
	# Aseguramos que DeviceLink intente escuchar la herramienta física
	DeviceLink.set_input_mode(DeviceLink.InputMode.HARDWARE)

func _process(_delta: float) -> void:
	if DeviceLink.hardware_connected:
		lbl_status.text = "Hardware: CONECTADO (%.0f Hz)" % DeviceLink.packet_rate_hz
		lbl_status.modulate = Color(0.2, 1.0, 0.3)
	else:
		lbl_status.text = "Hardware: ESPERANDO SEÑAL (Ejecuta iniciar_puente.bat)"
		lbl_status.modulate = Color(1.0, 0.6, 0.2)

	# Actualizar orientación de la herramienta 3D
	if DeviceLink._hw_has_orientation:
		# Aplicamos la base orientada directamente al pivot del modelo 3D
		var rel_basis: Basis = DeviceLink._hw_basis * DeviceLink._hw_ref_basis.inverse()
		tool_pivot.basis = rel_basis

	# Mostrar ángulos calculados
	var angles: Vector2 = WeldGeometry.angles_from_up(DeviceLink.get_tool_up())
	lbl_angles.text = "Ángulo Trabajo: %+.1f°  |  Ángulo Avance: %+.1f°" % [angles.x, angles.y]

	# Mostrar pulsador
	var trig: bool = DeviceLink.get_trigger()
	lbl_trigger.text = "Gatillo SMAW: %s" % ("¡PRESIONADO!" if trig else "LIBRE")
	lbl_trigger.modulate = Color(1.0, 0.2, 0.2) if trig else Color(0.7, 0.8, 0.9)

	# Mostrar estado del Filtro DLPF
	var m: int = clampi(DeviceLink.dlpf_mode, 0, 6)
	lbl_dlpf.text = "Filtro DLPF: %s" % DLPF_NAMES[m]
	if m == 0:
		lbl_dlpf.modulate = Color(1.0, 0.4, 0.4) # Rojo (mucho ruido)
	elif m >= 4:
		lbl_dlpf.modulate = Color(0.4, 0.9, 1.0) # Celeste suave
	else:
		lbl_dlpf.modulate = Color(0.9, 0.9, 0.5) # Amarillo estándar

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey:
		var k := event as InputEventKey
		if k.pressed:
			# Tecla T o Espacio: Calibrar pose neutra (Tare)
			if k.keycode == KEY_T or k.keycode == KEY_SPACE:
				DeviceLink.tare_pose()
			elif k.keycode == KEY_C:
				DeviceLink.calibrate_imu()
			elif k.keycode == KEY_R:
				cam_pivot.rotation = Vector3.ZERO
			# Teclas numéricas 0 al 6: Cambiar filtro DLPF en vivo en el MPU6050
			elif (k.keycode >= KEY_0 and k.keycode <= KEY_6):
				var mode_val := int(k.keycode - KEY_0)
				DeviceLink.set_dlpf(mode_val)
			elif (k.keycode >= KEY_KP_0 and k.keycode <= KEY_KP_6):
				var mode_val := int(k.keycode - KEY_KP_0)
				DeviceLink.set_dlpf(mode_val)

	# Control de cámara orbital con botón derecho del mouse
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_RIGHT:
			_cam_drag = mb.pressed
		elif mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			cam.position.z = maxf(cam.position.z - 0.05, 0.2)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			cam.position.z = minf(cam.position.z + 0.05, 1.5)

	if event is InputEventMouseMotion and _cam_drag:
		var mm := event as InputEventMouseMotion
		cam_pivot.rotate_y(-mm.relative.x * 0.008)
		cam_pivot.rotate_object_local(Vector3.RIGHT, -mm.relative.y * 0.008)
