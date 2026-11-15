extends CharacterBody3D

const SPEED = 5.0
const JUMP_VELOCITY = 5.0
# --- Agacharse (Crouch) ---
const CROUCH_SPEED = 2.5
const STANDING_HEIGHT = 2.0
const CROUCH_HEIGHT = 1.0
const CROUCH_TRANSITION_SPEED = 10.0

@onready var collision_shape = $CollisionShape3D
var is_crouching: bool = false
var standing_camera_y: float = 2.0
var crouch_camera_y: float = 1.1

@onready var camera_pivot = $Camerapivot
var mouse_sensitivity = 0.002
@onready var animation_player = $AnimationPlayer
var is_mask_down: bool = false

@onready var interact_ray = $Camerapivot/Camera3D/InteractionRay
@onready var hand_slot = $Camerapivot/Camera3D/HandPoint
@onready var crosshair = $MaskHUD/Crosshair

var held_object: Node3D = null
var current_highlighted: Node3D = null

# Estado del circuito de soldadura
var is_ground_connected: bool = false

# Material de contorno para resaltar objetos interactuables
var outline_material: ShaderMaterial = null


func _ready():
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	$MaskHUD/MaskContainer.position.y = -1100
	
	var shader = load("res://materials/outline.gdshader")
	outline_material = ShaderMaterial.new()
	outline_material.shader = shader
	outline_material.set_shader_parameter("outline_color", Color(1.0, 0.85, 0.0, 1.0))
	outline_material.set_shader_parameter("outline_width", 0.015)
	
	standing_camera_y = camera_pivot.position.y
	crouch_camera_y = standing_camera_y - 0.9

func _input(event):
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * mouse_sensitivity)
		camera_pivot.rotate_x(-event.relative.y * mouse_sensitivity)
		camera_pivot.rotation.x = clampf(camera_pivot.rotation.x, -deg_to_rad(80), deg_to_rad(80))
		
	# Ajustar amperaje con rueda del ratón
	if event is InputEventMouseButton and event.is_pressed():
		if current_highlighted and (current_highlighted.name == "Knob" or current_highlighted.name == "KnobArea"):
			var machine = _find_welding_machine(current_highlighted)
			if machine:
				if event.button_index == MOUSE_BUTTON_WHEEL_UP:
					machine.adjust_amperage(1)
				elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
					machine.adjust_amperage(-1)


func _process(_delta):
	if Input.is_action_just_pressed("quit"):
		get_tree().quit()
	if Input.is_action_just_pressed("toggle_mask"):
		toggle_welding_mask()
	if Input.is_action_just_pressed("interact"):
		handle_interaction()
	
	update_highlight()


# ---------- MÁSCARA DE SOLDADURA ----------

func toggle_welding_mask():
	is_mask_down = !is_mask_down
	if is_mask_down:
		animation_player.play("lower_mask")
	else:
		animation_player.play_backwards("lower_mask")


# ---------- OBTENCIÓN ROBUSTA DEL TARGET INTERACTUABLE ----------

func _get_interactable_target(collider: Object) -> Node3D:
	if collider == null:
		return null
	
	var node = collider as Node
	if node == null:
		return null
		
	# 1. Anclaje de pinza de masa en patas de mesa
	if node.is_in_group("clamp_anchor") or node.name.begins_with("ClampAnchor"):
		return node as Node3D
		
	# 2. Botón de encendido de la máquina (resaltar el botón MeshInstance3D)
	if node.name == "PowerArea":
		return node.get_parent() as Node3D # PowerSwitch
	if node.name == "PowerSwitch":
		return node as Node3D
		
	# 3. Perilla de amperaje (resaltar la perilla MeshInstance3D)
	if node.name == "KnobArea":
		return node.get_parent() as Node3D # Knob
	if node.name == "Knob":
		return node as Node3D

	# 4. Herramientas sueltas o en el entorno (ElectrodeHolder, GroundClamp)
	var current: Node = node
	while current != null and current != get_tree().current_scene:
		if current.is_in_group("interactable"):
			if current is Area3D:
				return current as Node3D
			return current as Node3D
		current = current.get_parent()
		
	return null


func _find_welding_machine(node: Node) -> Node:
	var current: Node = node
	while current != null and current != get_tree().current_scene:
		if current.has_method("toggle_power"):
			return current
		current = current.get_parent()
	return null


# ---------- RESALTADO DE OBJETOS (HIGHLIGHT) ----------

func update_highlight():
	var target: Node3D = null
	
	if interact_ray.is_colliding():
		var collider = interact_ray.get_collider()
		var candidate = _get_interactable_target(collider)
		
		if candidate != null:
			if held_object != null:
				# Si tenemos la pinza en mano, podemos anclarla en la pata de la mesa o usar la máquina
				if held_object.name.begins_with("GroundClamp"):
					if candidate.is_in_group("clamp_anchor") or candidate.name.begins_with("ClampAnchor") or candidate.name in ["PowerSwitch", "Knob"]:
						target = candidate
				else:
					# Si tenemos otra herramienta (portaelectrodo), aún podemos operar la máquina
					if candidate.name in ["PowerSwitch", "Knob"]:
						target = candidate
			else:
				# Si no tenemos nada en mano, interactuamos con todo
				target = candidate
	
	if target != current_highlighted:
		if current_highlighted != null:
			_remove_highlight(current_highlighted)
		if target != null:
			_apply_highlight(target)
		current_highlighted = target
	
	if crosshair:
		if target != null:
			crosshair.color = Color(1.0, 0.9, 0.0, 0.9)
		else:
			crosshair.color = Color(1.0, 1.0, 1.0, 0.6)


func _apply_highlight(obj: Node3D):
	if not is_instance_valid(obj):
		return
	
	# Caso especial para las patas de mesa: resaltar la pata correspondiente
	if obj.name == "ClampAnchorLeft":
		var leg = obj.get_parent().get_node_or_null("MeshInstance3D2")
		if leg:
			_set_overlay_recursive(leg, outline_material)
		return
	elif obj.name == "ClampAnchorRight":
		var leg = obj.get_parent().get_node_or_null("MeshInstance3D3")
		if leg:
			_set_overlay_recursive(leg, outline_material)
		return
		
	_set_overlay_recursive(obj, outline_material)


func _remove_highlight(obj: Node3D):
	if not is_instance_valid(obj):
		return
		
	if obj.name == "ClampAnchorLeft":
		var leg = obj.get_parent().get_node_or_null("MeshInstance3D2")
		if leg:
			_set_overlay_recursive(leg, null)
		return
	elif obj.name == "ClampAnchorRight":
		var leg = obj.get_parent().get_node_or_null("MeshInstance3D3")
		if leg:
			_set_overlay_recursive(leg, null)
		return
		
	_set_overlay_recursive(obj, null)


func _set_overlay_recursive(node: Node, mat: Material):
	if node is MeshInstance3D and node.name != "plano":
		node.material_overlay = mat
	for child in node.get_children():
		_set_overlay_recursive(child, mat)


# ---------- INTERACCIÓN: AGARRAR, SOLTAR O ANCLAR ----------

func handle_interaction():
	var collider = interact_ray.get_collider() if interact_ray.is_colliding() else null
	var target = _get_interactable_target(collider)

	# 1. Botón de encendido de la máquina (incluso con herramienta en mano)
	if target and (target.name == "PowerSwitch" or target.name == "PowerArea"):
		var machine = _find_welding_machine(target)
		if machine:
			machine.toggle_power()
		return

	# 2. Perilla de amperaje (incluso con herramienta en mano)
	if target and (target.name == "Knob" or target.name == "KnobArea"):
		var machine = _find_welding_machine(target)
		if machine:
			machine.adjust_amperage(1)
		return

	# 3. Si tenemos la pinza en mano y apuntamos a la pata de la mesa (ClampAnchor)
	if held_object != null and held_object.name.begins_with("GroundClamp"):
		if target and (target.is_in_group("clamp_anchor") or target.name.begins_with("ClampAnchor")):
			attach_ground_clamp_to_anchor(target)
			return

	# 4. Si tenemos un objeto en mano y apuntamos a otra parte, lo soltamos
	if held_object != null:
		drop_object()
		return

	# 5. Si no tenemos nada en mano y apuntamos a un objeto interactuable (portaelectrodo, pinza)
	if target != null:
		# Si la pinza estaba anclada y la desenganchamos
		if target.name.begins_with("GroundClamp") and is_ground_connected:
			is_ground_connected = false
			print("Pinza de masa desconectada de la mesa.")
		pick_up_object(target)


func attach_ground_clamp_to_anchor(anchor_area: Node3D):
	if held_object == null:
		return
		
	var clamp_obj = held_object
	held_object = null
	
	if current_highlighted != null:
		_remove_highlight(current_highlighted)
		current_highlighted = null
		
	var clamp_pos_marker = anchor_area.get_node_or_null("ClampPosition")
	var target_transform = clamp_pos_marker.global_transform if clamp_pos_marker else anchor_area.global_transform
	
	hand_slot.remove_child(clamp_obj)
	get_tree().current_scene.add_child(clamp_obj)
	
	clamp_obj.global_transform = target_transform
	
	if clamp_obj is RigidBody3D:
		clamp_obj.freeze = true
		for child in clamp_obj.get_children():
			if child is CollisionShape3D:
				child.disabled = false
				
	var area = clamp_obj.get_node_or_null("InteractArea")
	if area:
		area.monitoring = true
		area.monitorable = true
		for child in area.get_children():
			if child is CollisionShape3D:
				child.disabled = false
		
	is_ground_connected = true
	print("¡Pinza de masa anclada exitosamente a la mesa! Circuito de tierra CERRADO.")


func pick_up_object(obj: Node3D):
	if current_highlighted == obj:
		_remove_highlight(obj)
		current_highlighted = null

	var area = obj.get_node_or_null("InteractArea")
	if area:
		area.monitoring = false
		area.monitorable = false

	if obj is RigidBody3D:
		obj.freeze = true
		for child in obj.get_children():
			if child is CollisionShape3D:
				child.disabled = true

	held_object = obj

	var old_parent = obj.get_parent()
	if old_parent:
		old_parent.remove_child(obj)
	hand_slot.add_child(obj)
	obj.position = Vector3.ZERO
	
	if obj.name.begins_with("ElectrodeHolder"):
		obj.rotation_degrees = Vector3(45, 0, 0)
	else:
		obj.rotation = Vector3.ZERO


func drop_object():
	if held_object == null:
		return

	var obj = held_object
	held_object = null

	var drop_pos: Vector3
	if interact_ray.is_colliding():
		drop_pos = interact_ray.get_collision_point() + Vector3(0, 0.15, 0)
	else:
		drop_pos = global_transform.origin + (-global_transform.basis.z * 1.5) + Vector3(0, 0.3, 0)

	hand_slot.remove_child(obj)
	get_tree().current_scene.add_child(obj)

	obj.global_position = drop_pos
	obj.rotation = Vector3.ZERO

	if obj is RigidBody3D:
		for child in obj.get_children():
			if child is CollisionShape3D:
				child.disabled = false
		obj.freeze = false
		obj.linear_velocity = Vector3.ZERO
		obj.angular_velocity = Vector3.ZERO

	var area = obj.get_node_or_null("InteractArea")
	if area:
		area.monitoring = true
		area.monitorable = true
		for child in area.get_children():
			if child is CollisionShape3D:
				child.disabled = false


# ---------- MOVIMIENTO ----------

func _physics_process(delta: float) -> void:
	handle_crouch(delta)

	if not is_on_floor():
		velocity += get_gravity() * delta

	# No permitir saltar si está agachado (opcional pero habitual en FPS)
	if Input.is_action_just_pressed("jump") and is_on_floor() and not is_crouching:
		velocity.y = JUMP_VELOCITY
	# Selección de velocidad según si está agachado o de pie
	var current_speed = CROUCH_SPEED if is_crouching else SPEED
	
	var input_dir := Input.get_vector("left", "right", "forward", "back")
	var direction := (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()
	if direction:
		velocity.x = direction.x * current_speed
		velocity.z = direction.z * current_speed
	else:
		velocity.x = move_toward(velocity.x, 0, current_speed)
		velocity.z = move_toward(velocity.z, 0, current_speed)

	move_and_slide()
	
	

func handle_crouch(delta: float):
	# Si se mantiene presionada la tecla agacharse
	var wants_to_crouch = Input.is_action_pressed("crouch")
	
	# También soporta modo "toggle" si prefieres pulsar una sola vez
	is_crouching = wants_to_crouch
	
	# Interpolar suavemente la altura de la cámara
	var target_cam_y = crouch_camera_y if is_crouching else standing_camera_y
	camera_pivot.position.y = lerp(camera_pivot.position.y, target_cam_y, CROUCH_TRANSITION_SPEED * delta)
	
	# Ajustar el CollisionShape3D para no colisionar con techos bajos
	if collision_shape and collision_shape.shape is CapsuleShape3D:
		var target_col_height = CROUCH_HEIGHT if is_crouching else STANDING_HEIGHT
		collision_shape.shape.height = lerp(collision_shape.shape.height, target_col_height, CROUCH_TRANSITION_SPEED * delta)
		
		var target_col_y = target_col_height / 2.0
		collision_shape.position.y = lerp(collision_shape.position.y, target_col_y, CROUCH_TRANSITION_SPEED * delta)
