extends Node
## Estado global de la aplicación (autoload "Game"): nivel elegido, último
## informe y cambios de escena.

const MENU_SCENE := "res://Scenes/MainMenu.tscn"
const EXERCISE_SCENE := "res://Scenes/Main_scene.tscn"

var selected_level: int = 1
var last_report: Dictionary = {}


func start_level(level: int) -> void:
	selected_level = clampi(level, 1, LevelConfig.LEVEL_COUNT)
	last_report = {}
	get_tree().paused = false
	get_tree().change_scene_to_file(EXERCISE_SCENE)


func go_to_menu() -> void:
	get_tree().paused = false
	DeviceLink.stop_haptics()
	get_tree().change_scene_to_file(MENU_SCENE)


func quit_game() -> void:
	DeviceLink.stop_haptics()
	get_tree().quit()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		DeviceLink.stop_haptics()
