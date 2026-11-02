extends Control

## A small, self-contained status scene. Each instance uses its own stable phase.

var instance_id := ""
var state := "unknown"
var phase := 0.0
var redraw_elapsed := 0.0


func _ready() -> void:
	custom_minimum_size = Vector2(98, 78)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_process(false)


func configure(id: String, new_state: String, online: bool) -> void:
	instance_id = id
	state = new_state if online else "offline"
	phase = float(posmod(id.hash(), 1000)) / 97.0
	set_process(state in ["working", "idle", "attention", "starting"])
	queue_redraw()


func _process(delta: float) -> void:
	if not is_visible_in_tree():
		return
	redraw_elapsed += delta
	if redraw_elapsed >= 1.0 / 15.0:
		redraw_elapsed = 0.0
		queue_redraw()


func _draw() -> void:
	var clock := float(Time.get_ticks_msec()) / 1000.0 + phase
	var active := state not in ["offline", "exited", "error"]
	var muted := Color("#607988") if not active else Color("#5cd1b9")
	var skin := Color("#ad998c") if not active else Color("#e8b48d")
	var shirt := Color("#566b77") if not active else Color("#4dbea8")
	var hair := Color("#26333b")
	var motion := sin(clock * 2.1) * 1.2 if state == "idle" else 0.0
	var is_idle := state == "idle"

	# Floor, chair, desk, and a small monitor provide the same scene in every state.
	draw_line(Vector2(6, 71), Vector2(94, 71), Color("#385160"), 1.5)
	draw_rect(Rect2(15, 38, 5, 30), Color("#35505a"))
	draw_rect(Rect2(18, 56, 30, 5), Color("#426270"))
	draw_line(Vector2(34, 61), Vector2(34, 71), Color("#426270"), 3.0)
	draw_rect(Rect2(48, 53, 46, 4), Color("#52727b"))
	draw_line(Vector2(54, 57), Vector2(54, 71), Color("#426270"), 3.0)
	draw_line(Vector2(90, 57), Vector2(90, 71), Color("#426270"), 3.0)
	draw_rect(Rect2(64, 24, 28, 27), Color("#253c49"))
	draw_rect(Rect2(67, 27, 22, 20), Color("#142934"))
	draw_line(Vector2(70, 32), Vector2(81, 32), muted, 2.0)
	draw_line(Vector2(70, 37), Vector2(85, 37), muted.darkened(0.3), 2.0)
	draw_line(Vector2(78, 51), Vector2(78, 54), Color("#52727b"), 2.0)
	draw_rect(Rect2(57, 53, 19, 2), Color("#253c49"))

	if is_idle:
		# Reclining with hands behind the head; a slowly drifting bubble marks rest.
		draw_colored_polygon(PackedVector2Array([Vector2(16, 40), Vector2(27, 35),
			Vector2(46, 51), Vector2(43, 61), Vector2(21, 55)]), shirt)
		draw_line(Vector2(39, 54), Vector2(50, 63), Color("#263c48"), 6.0)
		draw_line(Vector2(50, 63), Vector2(57, 65), Color("#263c48"), 5.0)
		draw_line(Vector2(22, 41), Vector2(17, 23), skin, 4.0)
		draw_line(Vector2(17, 23), Vector2(28, 20), skin, 4.0)
		draw_line(Vector2(34, 38), Vector2(39, 23), skin, 4.0)
		draw_line(Vector2(39, 23), Vector2(28, 20), skin, 4.0)
		draw_circle(Vector2(27, 24 + motion), 10.0, skin)
		draw_arc(Vector2(27, 21 + motion), 9.0, PI, TAU, 12, hair, 4.0)
		draw_arc(Vector2(29, 27 + motion), 3.0, 0.0, PI, 8, hair, 1.2)
		var bubble_y := 15.0 + sin(clock * 1.5) * 3.0
		draw_circle(Vector2(47, bubble_y + 10), 2.0, muted)
		draw_circle(Vector2(54, bubble_y + 4), 3.0, muted)
		draw_line(Vector2(61, bubble_y - 5), Vector2(68, bubble_y - 5), muted, 2.0)
		draw_line(Vector2(68, bubble_y - 5), Vector2(61, bubble_y + 1), muted, 2.0)
		draw_line(Vector2(61, bubble_y + 1), Vector2(68, bubble_y + 1), muted, 2.0)
	else:
		var lean := sin(clock * 8.0) * 0.9 if state == "working" else 0.0
		draw_colored_polygon(PackedVector2Array([Vector2(24, 38), Vector2(43, 36),
			Vector2(51 + lean, 54), Vector2(27, 60)]), shirt)
		draw_line(Vector2(38, 58), Vector2(47, 68), Color("#263c48"), 6.0)
		draw_circle(Vector2(35 + lean, 27), 10.0, skin)
		draw_arc(Vector2(35 + lean, 24), 9.0, PI, TAU, 12, hair, 4.0)
		draw_circle(Vector2(39 + lean, 27), 1.1, hair)
		var hand_y := 51.0 + sin(clock * 13.0) * 2.0 if state == "working" else 51.0
		draw_line(Vector2(43, 42), Vector2(57, hand_y), skin, 4.5)
		draw_circle(Vector2(58, hand_y), 2.4, skin)
		if state == "working":
			draw_circle(Vector2(75, 30 + sin(clock * 3.0) * 2.0), 1.5, Color("#8de6d2"))
		elif state == "attention":
			draw_line(Vector2(49, 39), Vector2(54, 19), skin, 4.0)
			draw_circle(Vector2(54, 18), 2.7, skin)
			draw_line(Vector2(54, 6), Vector2(54, 12), Color("#e4b761"), 3.0)
			draw_circle(Vector2(54, 15), 1.7, Color("#e4b761"))
		elif state == "starting":
			draw_arc(Vector2(78, 37), 6.0, clock * 4.0, clock * 4.0 + PI, 12, Color("#8de6d2"), 2.0)

	if not active:
		draw_line(Vector2(71, 39), Vector2(84, 39), Color("#607988"), 2.0)
