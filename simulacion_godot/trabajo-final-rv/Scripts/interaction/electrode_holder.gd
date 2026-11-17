class_name ElectrodeHolder
extends Pickable
## Portaelectrodo con electrodo consumible (E6013 Ø3,2 x 350 mm).
##
## El electrodo se acorta con el uso; la punta (tip) se desplaza en consecuencia.
## El marco local del portaelectrodo tiene +Y apuntando hacia la punta del
## electrodo y el mango extendido hacia -Z.

signal electrode_changed(length_mm: float)
signal depleted

@export var electrode_mesh: MeshInstance3D
@export var cable_point: Marker3D

## Longitud del electrodo nuevo en mm.
var initial_length_mm: float = WeldPhysics.ELECTRODE_LENGTH_MM
var length_mm: float = WeldPhysics.ELECTRODE_LENGTH_MM
var electrodes_used: int = 1

# Geometría base del electrodo en la escena (coordenadas locales, en metros).
const BASE_Y := 0.00203
const TIP_Z := 0.11914
const MESH_FULL_HEIGHT := 0.35

var _depleted_emitted: bool = false


func _ready() -> void:
	super._ready()
	_update_visual()


func is_depleted() -> bool:
	return length_mm <= WeldPhysics.ELECTRODE_STUB_MM + 0.001


func remaining_fraction() -> float:
	var usable := initial_length_mm - WeldPhysics.ELECTRODE_STUB_MM
	return clampf((length_mm - WeldPhysics.ELECTRODE_STUB_MM) / usable, 0.0, 1.0)


## Posición local de la punta del electrodo.
func get_tip_local() -> Vector3:
	return Vector3(0.0, BASE_Y + length_mm / 1000.0, TIP_Z)


## Consume mm de electrodo. Devuelve los mm realmente consumidos.
func consume(mm: float) -> float:
	if is_depleted():
		return 0.0
	var before := length_mm
	length_mm = maxf(length_mm - maxf(mm, 0.0), WeldPhysics.ELECTRODE_STUB_MM)
	_update_visual()
	electrode_changed.emit(length_mm)
	if is_depleted() and not _depleted_emitted:
		_depleted_emitted = true
		depleted.emit()
	return before - length_mm


## Cambia el electrodo por uno nuevo.
func replace_electrode() -> void:
	length_mm = initial_length_mm
	electrodes_used += 1
	_depleted_emitted = false
	_update_visual()
	electrode_changed.emit(length_mm)


func _update_visual() -> void:
	if electrode_mesh == null:
		return
	var len_m := length_mm / 1000.0
	electrode_mesh.scale = Vector3(1.0, len_m / MESH_FULL_HEIGHT, 1.0)
	electrode_mesh.position = Vector3(0.0, BASE_Y + len_m * 0.5, TIP_Z)
