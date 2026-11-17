extends Node
## Bus de señales global (autoload "Events").
## Desacopla emisores y receptores que no deben conocerse entre sí
## (por ejemplo, el controlador del ejercicio y el HUD).

## Mensaje breve para mostrar en pantalla.
signal hud_message(text: String, seconds: float)
## El operario intentó soldar con la careta levantada.
signal safety_violation
