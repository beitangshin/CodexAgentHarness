extends SceneTree


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var scene: PackedScene = load("res://scenes/Main.tscn")
	if scene == null:
		_fail("main scene did not load")
		return
	var main: Control = scene.instantiate()
	root.add_child(main)
	main.call("_on_api_response", "local_tools_auto", true,
		{"configured": {"codex": "", "terminal": "/usr/bin/xterm", "ssh": ""},
		 "missing": ["codex", "ssh"], "suggestions": {"codex": [], "terminal": [], "ssh": []}}, "")
	var tool_rows: Dictionary = main.get("tool_rows")
	if not tool_rows["codex"].visible or tool_rows["terminal"].visible or tool_rows["ssh"].visible:
		_fail("automatic program prompt did not show only missing launch tools")
		return
	main.get("tools_dialog").hide()
	var instance := {"id": "instance-one", "project": "sample", "cwd": "C:/sample",
		"status": "idle", "pid": 1234, "managed": true, "interaction_ready": true,
		"launch_mode": "default", "activity": [], "pending_approvals": [], "live_text": ""}
	var one := {"machine_id": "one", "hostname": "Laptop", "platform": "windows",
		"online": true, "cli_process_count": 1, "instances": [instance]}
	var two := {"machine_id": "two", "hostname": "VDI", "platform": "linux",
		"online": true, "cli_process_count": 0, "instances": []}
	main.set("machines", [one, two])
	main.call("_render_status")
	var picker: OptionButton = main.get("machine_picker")
	var mode: OptionButton = main.get("existing_mode")
	var new_path: LineEdit = main.get("new_path")
	mode.select(2)
	new_path.text = "C:/unsent-project"
	instance["status"] = "working"
	main.call("_render_status")
	if main.get("selected_machine_id") != "one" or picker.selected != 0:
		_fail("selected machine changed during refresh")
		return
	if mode.selected != 2 or new_path.text != "C:/unsent-project":
		_fail("dropdown or typed path changed during refresh")
		return
	var second := instance.duplicate(true)
	second["id"] = "instance-two"
	second["project"] = "second-project"
	second["status"] = "idle"
	one["instances"] = [instance, second]
	main.call("_render_status")
	var rows: VBoxContainer = main.get("instance_list")
	if rows.get_child_count() != 2:
		_fail("each CLI should have its own animated card")
		return
	var first_actor: Control = rows.get_child(0).get_child(0).get_child(0).get_child(0)
	var second_actor: Control = rows.get_child(1).get_child(0).get_child(0).get_child(0)
	if first_actor.get("state") != "working" or second_actor.get("state") != "idle":
		_fail("instance animation did not follow its own status")
		return
	rows.get_child(1).pressed.emit()
	if main.get("selected_instance_id") != "instance-two":
		_fail("animated instance card did not select its CLI")
		return
	main.set("selected_machine_id", "two")
	picker.select(1)
	main.call("_render_status")
	if main.get("selected_machine_id") != "two" or picker.selected != 1:
		_fail("selected VDI was not preserved")
		return
	main.set("browser_names", [".git", ".cache", "project", "scripts"])
	main.call("_filter_browser", "")
	var folders: ItemList = main.get("browser_list")
	if folders.item_count != 2:
		_fail("hidden folders were shown by default")
		return
	var show_hidden: CheckButton = main.get("browser_show_hidden")
	show_hidden.button_pressed = true
	if folders.item_count != 4:
		_fail("hidden folder toggle did not reveal folders")
		return
	main.set("language", "en")
	main.call("_apply_language", main)
	var nav: Dictionary = main.get("nav_buttons")
	if not str(nav["overview"].text).contains("Overview") or mode.get_item_text(0) != "Codex default":
		_fail("English UI did not translate navigation and permissions: nav=%s mode=%s" % [nav["overview"].text, mode.get_item_text(0)])
		return
	if new_path.text != "C:/unsent-project" or picker.selected != 1:
		_fail("language switch changed a path or selected machine")
		return
	main.set("language", "zh")
	main.call("_apply_language", main)
	if not str(nav["overview"].text).contains("运行总览") or mode.get_item_text(0) != "Codex 默认":
		_fail("Chinese UI was not restored")
		return
	main.call("_on_api_response", "local_tools_get", true,
		{"configured": {"codex": "C:/tools/codex.exe", "terminal": "windows-console", "ssh": "C:/tools/ssh.exe"},
		 "suggestions": {"codex": ["C:/tools/codex.exe"], "terminal": ["windows-console"], "ssh": ["C:/tools/ssh.exe"]}}, "")
	var configured: Dictionary = main.get("tool_fields")
	if configured["codex"].text != "C:/tools/codex.exe" or configured["terminal"].text != "windows-console":
		_fail("local program settings did not populate from Master")
		return
	print("UI_SMOKE_OK")
	quit(0)


func _fail(reason: String) -> void:
	printerr("UI_SMOKE_FAILED: " + reason)
	quit(1)
