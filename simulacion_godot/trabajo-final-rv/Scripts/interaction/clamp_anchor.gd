class_name ClampAnchor
extends Interactable
## Punto de la mesa donde se engancha la pinza de masa.
## Solo es interactuable cuando el jugador sostiene la pinza.

## Marcador (Marker3D) con la pose que adopta la pinza al engancharse.
@export var clamp_position: Marker3D


func can_interact(interactor: PlayerInteractor) -> bool:
	return enabled and interactor.held is GroundClamp


func interact(interactor: PlayerInteractor) -> void:
	var clamp := interactor.held as GroundClamp
	if clamp == null or clamp_position == null:
		return
	interactor.release_held()
	clamp.attach_to(self, clamp_position)
	super.interact(interactor)
