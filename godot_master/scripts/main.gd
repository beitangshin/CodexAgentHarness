extends Control

const ApiClient = preload("res://scripts/api_client.gd")
const AgentActor = preload("res://scripts/agent_actor.gd")
const I18n = preload("res://scripts/i18n.gd")
const BG := Color("#09121c")
const SURFACE := Color("#111f2b")
const SURFACE_ALT := Color("#172b38")
const BORDER := Color("#294252")
const TEXT := Color("#eaf5f7")
const MUTED := Color("#91aab8")
const MINT := Color("#62d8bf")
const AMBER := Color("#e4b761")
const RED := Color("#f38587")
const MODES := ["default", "full_access", "bypass"]
const MODE_NAMES := ["沿用 Codex 权限配置", "完整访问 · 按需审批", "Bypass（绕过沙箱与审批）"]
const EFFORTS := ["minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
const STATUS_NAMES := {"starting": "启动中", "working": "工作中", "idle": "空闲",
	"attention": "待处理", "unknown": "未确认", "exited": "已退出", "error": "错误"}

var api: Node
var machines: Array = []
var commands: Array = []
var selected_machine_id := ""
var selected_instance_id := ""
var machine_ids: Array = []
var instance_ids: Array = []
var page := "overview"
var status_busy := false
var master_online := false
var model_catalog: Dictionary = {}
var lookup_intents: Dictionary = {}
var handled_commands: Dictionary = {}
var browser_data: Dictionary = {}
var browser_machine_id := ""
var pending_start_id := ""
var activity_signature := ""
var instance_signature := ""
var machine_signature := ""
var machine_report_labels: Dictionary = {}
var refreshing_controls := false
var configured_instance_id := ""
var configured_machine_id := ""
var recent_signature := ""
var sent_prompt := ""
var language := "zh"
var language_button: Button
var machine_aliases: Dictionary = {}
var rename_machine_id := ""

var pages: Dictionary = {}
var nav_buttons: Dictionary = {}
var status_label: Label
var footer_label: Label
var start_button: Button
var stop_button: Button
var metrics: Array = []
var overview_machines: VBoxContainer
var machines_page_list: VBoxContainer
var machine_picker: OptionButton
var machine_picker_sources: Array[String] = []
var new_paths_by_machine: Dictionary = {}
var path_machine_id := ""
var workbench_subtitle_label: Label
var machine_name_dialog: AcceptDialog
var machine_name_field: LineEdit
var machine_name_error_dialog: AcceptDialog
var instance_scroll: ScrollContainer
var instance_list: VBoxContainer
var instance_title: Label
var instance_meta: Label
var activity_scroll: ScrollContainer
var activity_box: VBoxContainer
var task_input: TextEdit
var send_button: Button
var existing_note: Label
var existing_mode: OptionButton
var existing_model: OptionButton
var existing_effort: OptionButton
var restart_button: Button
var trust_button: Button
var stop_instance_button: Button
var delete_button: Button
var new_path: LineEdit
var new_mode: OptionButton
var new_model: OptionButton
var new_effort: OptionButton
var new_start_button: Button
var browser_panel: VBoxContainer
var browser_path_label: Label
var browser_search: LineEdit
var browser_show_hidden: CheckButton
var browser_list: ItemList
var browser_names: Array = []
var browser_up_button: Button
var browser_choose_button: Button
var recent_box: VBoxContainer
var confirm_dialog: ConfirmationDialog
var confirm_action := ""
var confirm_target_machine_id := ""
var confirm_target_instance_id := ""
var poll_timer: Timer
var tools_dialog: ConfirmationDialog
var tool_fields: Dictionary = {}
var tool_hints: Dictionary = {}
var tool_rows: Dictionary = {}
var tool_intro: Label
var local_tools_checked := false
var tool_dialog_missing_only := false
var tool_file_dialog: FileDialog
var tool_file_kind := ""
var login_dialog: AcceptDialog


func _ready() -> void:
	var settings := ConfigFile.new()
	if settings.load("user://ui_settings.cfg") == OK:
		language = str(settings.get_value("ui", "language", "zh"))
		var stored_aliases: Variant = settings.get_value("ui", "machine_aliases", {})
		if stored_aliases is Dictionary:
			machine_aliases = stored_aliases
	if language != "en":
		language = "zh"
	var system_font := SystemFont.new()
	system_font.font_names = PackedStringArray(["Microsoft YaHei UI", "Segoe UI"])
	var app_theme := Theme.new()
	app_theme.default_font = system_font
	app_theme.default_font_size = 14
	theme = app_theme
	_build_ui()
	_build_machine_name_dialog()
	_build_tool_settings()
	_refresh_language()
	api = ApiClient.new()
	add_child(api)
	api.response.connect(_on_api_response)
	api.load_credentials()
	poll_timer = Timer.new()
	poll_timer.wait_time = 1.0
	poll_timer.autostart = true
	poll_timer.timeout.connect(_poll_status)
	add_child(poll_timer)
	_poll_status()


func _style(color: Color, border: Color = BORDER, radius: int = 12) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = color
	box.border_color = border
	box.border_width_left = 1
	box.border_width_top = 1
	box.border_width_right = 1
	box.border_width_bottom = 1
	box.corner_radius_top_left = radius
	box.corner_radius_top_right = radius
	box.corner_radius_bottom_left = radius
	box.corner_radius_bottom_right = radius
	box.content_margin_left = 16.0
	box.content_margin_top = 14.0
	box.content_margin_right = 16.0
	box.content_margin_bottom = 14.0
	return box


func _panel(color: Color = SURFACE) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _style(color))
	return panel


func _label(value: String, size: int = 14, color: Color = TEXT) -> Label:
	var item := Label.new()
	item.text = value
	item.add_theme_color_override("font_color", color)
	item.add_theme_font_size_override("font_size", size)
	item.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return item


func _button(value: String, accent: bool = false) -> Button:
	var item := Button.new()
	item.text = value
	item.custom_minimum_size = Vector2(0, 38)
	item.focus_mode = Control.FOCUS_NONE
	item.add_theme_color_override("font_color", BG if accent else TEXT)
	item.add_theme_color_override("font_hover_color", BG if accent else TEXT)
	item.add_theme_stylebox_override("normal", _style(MINT if accent else SURFACE_ALT, MINT if accent else BORDER, 9))
	item.add_theme_stylebox_override("hover", _style(Color("#7be7d1") if accent else Color("#203b4b"), MINT, 9))
	item.add_theme_stylebox_override("pressed", _style(Color("#4bc7ae") if accent else Color("#274758"), MINT, 9))
	item.add_theme_stylebox_override("disabled", _style(Color("#21323d"), BORDER, 9))
	return item


func _translate_property(control: Control, property_name: String) -> void:
	var current: String = str(control.get(property_name))
	var source_key := "cah_i18n_source_" + property_name
	var shown_key := "cah_i18n_shown_" + property_name
	var source: String = str(control.get_meta(source_key, current)) if control.has_meta(source_key) else current
	if not control.has_meta(shown_key) or current != str(control.get_meta(shown_key)):
		source = current
	var translated: String = I18n.translate(source, language)
	if current != translated:
		control.set(property_name, translated)
	control.set_meta(source_key, source)
	control.set_meta(shown_key, translated)


func _apply_language(node: Node) -> void:
	if (node is Label or node is Button) and not node.get_meta("cah_no_translate", false):
		_translate_property(node, "text")
	if node is LineEdit or node is TextEdit:
		_translate_property(node, "placeholder_text")
	if node is OptionButton:
		for index in node.item_count:
			var current: String = node.get_item_text(index)
			var key := "cah_i18n_option_%d" % index
			var shown := "cah_i18n_option_shown_%d" % index
			var source: String = str(node.get_meta(key, current)) if node.has_meta(key) else current
			if not node.has_meta(shown) or current != str(node.get_meta(shown)):
				source = current
			var translated: String = I18n.translate(source, language)
			if current != translated:
				node.set_item_text(index, translated)
			node.set_meta(key, source)
			node.set_meta(shown, translated)
	for child in node.get_children():
		_apply_language(child)


func _refresh_language(node: Node = null) -> void:
	var target: Node = self if node == null else node
	_apply_language(target)
	confirm_dialog.title = I18n.translate("确认操作", language)
	confirm_dialog.get_ok_button().text = "确认" if language == "zh" else "Confirm"
	confirm_dialog.get_cancel_button().text = "取消" if language == "zh" else "Cancel"
	tools_dialog.title = I18n.translate("本机程序配置", language)
	tools_dialog.get_ok_button().text = "保存配置" if language == "zh" else "Save settings"
	tools_dialog.get_cancel_button().text = "取消" if language == "zh" else "Cancel"
	login_dialog.title = I18n.translate("网页登录信息", language)
	login_dialog.get_ok_button().text = "关闭" if language == "zh" else "Close"
	if is_instance_valid(machine_name_dialog):
		machine_name_dialog.title = I18n.translate("重命名机器", language)
		machine_name_dialog.dialog_text = I18n.translate("输入机器在中控界面中的自定义名称。留空可恢复主机名。", language)
		machine_name_dialog.get_ok_button().text = "保存" if language == "zh" else "Save"
	if is_instance_valid(machine_name_field):
		machine_name_field.placeholder_text = I18n.translate("机器名称", language)
		machine_name_field.set_meta("cah_i18n_source_placeholder_text", "机器名称")
		machine_name_field.set_meta("cah_i18n_shown_placeholder_text", I18n.translate("机器名称", language))
	if is_instance_valid(machine_name_error_dialog):
		machine_name_error_dialog.title = I18n.translate("保存失败", language)
		machine_name_error_dialog.get_ok_button().text = "关闭" if language == "zh" else "Close"
	if confirm_action == "stop":
		confirm_dialog.dialog_text = I18n.translate("停止当前 Codex 实例？", language)
	elif confirm_action == "delete":
		confirm_dialog.dialog_text = I18n.translate("删除此实例的本地历史记录？该操作无法撤销。", language)
	elif confirm_action == "trust_project":
		_set_trust_confirmation_text()


func _data_label(value: String, size: int = 14, color: Color = TEXT) -> Label:
	var item := _label(value, size, color)
	item.set_meta("cah_no_translate", true)
	return item


func _toggle_language() -> void:
	language = "en" if language == "zh" else "zh"
	var settings := ConfigFile.new()
	settings.load("user://ui_settings.cfg")
	settings.set_value("ui", "language", language)
	settings.save("user://ui_settings.cfg")
	language_button.text = "中文 / English"
	_render_workbench_summary()
	_render_instances()
	_refresh_instance_controls()
	_render_activity()
	_render_recent()
	_refresh_language()


func _build_machine_name_dialog() -> void:
	machine_name_dialog = AcceptDialog.new()
	machine_name_dialog.title = I18n.translate("重命名机器", language)
	machine_name_dialog.dialog_text = I18n.translate("输入机器在中控界面中的自定义名称。留空可恢复主机名。", language)
	machine_name_field = LineEdit.new()
	machine_name_field.placeholder_text = I18n.translate("机器名称", language)
	machine_name_field.custom_minimum_size = Vector2(420, 40)
	machine_name_dialog.add_child(machine_name_field)
	machine_name_dialog.confirmed.connect(_save_machine_name)
	add_child(machine_name_dialog)
	machine_name_error_dialog = AcceptDialog.new()
	machine_name_error_dialog.title = I18n.translate("保存失败", language)
	add_child(machine_name_error_dialog)


func _machine_display_name(machine: Dictionary) -> String:
	var machine_id := str(machine.get("machine_id", ""))
	var alias := str(machine_aliases.get(machine_id, "")).strip_edges()
	return alias if not alias.is_empty() else str(machine.get("hostname", "未知机器"))


func _sync_new_path_machine() -> void:
	if not is_instance_valid(new_path) or path_machine_id == selected_machine_id:
		return
	if not path_machine_id.is_empty():
		new_paths_by_machine[path_machine_id] = new_path.text.strip_edges()
	path_machine_id = selected_machine_id
	if path_machine_id.is_empty():
		new_path.text = ""
		return
	var selected_path := str(new_paths_by_machine.get(path_machine_id, ""))
	if not new_paths_by_machine.has(path_machine_id):
		for instance in _selected_machine().get("instances", []):
			var cwd := str(instance.get("cwd", "")).strip_edges()
			if not cwd.is_empty():
				selected_path = cwd
				break
		new_paths_by_machine[path_machine_id] = selected_path
	new_path.text = selected_path


func _open_machine_name_dialog(machine_id: String) -> void:
	rename_machine_id = machine_id
	machine_name_field.text = str(machine_aliases.get(machine_id, ""))
	machine_name_dialog.popup_centered()
	machine_name_field.grab_focus()


func _save_machine_name() -> void:
	var alias := machine_name_field.text.strip_edges()
	var updated_aliases: Dictionary = machine_aliases.duplicate()
	if alias.is_empty():
		updated_aliases.erase(rename_machine_id)
	else:
		updated_aliases[rename_machine_id] = alias
	var settings := ConfigFile.new()
	settings.load("user://ui_settings.cfg")
	settings.set_value("ui", "machine_aliases", updated_aliases)
	var result := settings.save("user://ui_settings.cfg")
	if result != OK:
		machine_name_error_dialog.dialog_text = "%s: %s" % [I18n.translate("保存失败", language), error_string(result)]
		machine_name_error_dialog.popup_centered()
		return
	machine_aliases = updated_aliases
	machine_signature = ""
	_render_machines()
	_update_machine_picker()
	_sync_new_path_machine()
	_render_workbench_summary()
	_refresh_language()


func _option() -> OptionButton:
	var item := OptionButton.new()
	item.custom_minimum_size = Vector2(0, 39)
	item.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item.add_theme_color_override("font_color", TEXT)
	item.add_theme_stylebox_override("normal", _style(SURFACE_ALT, BORDER, 8))
	item.add_theme_stylebox_override("hover", _style(Color("#203b4b"), MINT, 8))
	item.add_theme_stylebox_override("pressed", _style(Color("#203b4b"), MINT, 8))
	return item


func _field(placeholder: String) -> LineEdit:
	var item := LineEdit.new()
	item.placeholder_text = placeholder
	item.custom_minimum_size = Vector2(0, 38)
	item.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item.add_theme_color_override("font_color", TEXT)
	item.add_theme_color_override("font_placeholder_color", MUTED)
	item.add_theme_stylebox_override("normal", _style(Color("#0d1b26"), BORDER, 8))
	item.add_theme_stylebox_override("focus", _style(Color("#0d1b26"), MINT, 8))
	return item


func _gap(height: float = 10.0) -> Control:
	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(0, height)
	return spacer


func _grow() -> Control:
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return spacer


func _clear(container: Node) -> void:
	for child in container.get_children():
		container.remove_child(child)
		child.queue_free()


func _build_ui() -> void:
	var shell := HBoxContainer.new()
	shell.add_theme_constant_override("separation", 0)
	add_child(shell)
	shell.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build_sidebar(shell)
	var main := VBoxContainer.new()
	main.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	main.add_theme_constant_override("separation", 0)
	shell.add_child(main)
	_build_header(main)
	var page_margin := MarginContainer.new()
	page_margin.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page_margin.add_theme_constant_override("margin_left", 22)
	page_margin.add_theme_constant_override("margin_right", 22)
	page_margin.add_theme_constant_override("margin_top", 18)
	page_margin.add_theme_constant_override("margin_bottom", 18)
	main.add_child(page_margin)
	var page_host := Control.new()
	page_host.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	page_host.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page_margin.add_child(page_host)
	_build_overview(page_host)
	_build_workbench(page_host)
	_build_machines(page_host)
	_show_page("overview")
	confirm_dialog = ConfirmationDialog.new()
	confirm_dialog.title = "确认操作"
	confirm_dialog.confirmed.connect(_on_confirmed)
	add_child(confirm_dialog)
	login_dialog = AcceptDialog.new()
	login_dialog.title = "网页登录信息"
	add_child(login_dialog)


func _build_tool_settings() -> void:
	tools_dialog = ConfirmationDialog.new()
	tools_dialog.title = "本机程序配置"
	tools_dialog.confirmed.connect(_save_tool_settings)
	add_child(tools_dialog)
	tools_dialog.get_ok_button().text = "保存配置"
	var content := VBoxContainer.new()
	content.custom_minimum_size = Vector2(820, 0)
	content.add_theme_constant_override("separation", 8)
	tools_dialog.add_child(content)
	tool_intro = _label("已自动搜索本机程序；你可以修改搜索结果或手动选择路径。", 12, MUTED)
	content.add_child(tool_intro)
	for entry in [["codex", "Codex CLI"], ["terminal", "终端程序"], ["ssh", "SSH 客户端"]]:
		var kind: String = entry[0]
		var group := VBoxContainer.new()
		content.add_child(group)
		tool_rows[kind] = group
		group.add_child(_label(entry[1], 13))
		var row := HBoxContainer.new()
		group.add_child(row)
		var field := LineEdit.new()
		field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(field)
		tool_fields[kind] = field
		var browse := _button("浏览…")
		browse.pressed.connect(_browse_tool.bind(kind))
		row.add_child(browse)
		var hint := _label("建议搜索位置：", 11, MUTED)
		hint.custom_minimum_size.y = 42
		group.add_child(hint)
		tool_hints[kind] = hint
	tool_file_dialog = FileDialog.new()
	tool_file_dialog.access = FileDialog.ACCESS_FILESYSTEM
	tool_file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	tool_file_dialog.file_selected.connect(_tool_file_selected)
	add_child(tool_file_dialog)


func _open_tool_settings() -> void:
	if not master_online:
		_toast("请先启动 Master，再配置本机程序。", true)
		return
	api.request_json("local_tools_get", "/api/local-tools")


func _browse_tool(kind: String) -> void:
	tool_file_kind = kind
	tool_file_dialog.popup_centered(Vector2i(900, 600))


func _tool_file_selected(path: String) -> void:
	if tool_fields.has(tool_file_kind):
		tool_fields[tool_file_kind].text = path


func _save_tool_settings() -> void:
	var values := {}
	for kind in tool_fields:
		values[kind] = tool_fields[kind].text.strip_edges()
	api.request_json("local_tools_put", "/api/local-tools", HTTPClient.METHOD_PUT, values)


func _build_sidebar(shell: HBoxContainer) -> void:
	var panel := _panel(Color("#0d1b27"))
	panel.custom_minimum_size.x = 224
	shell.add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 9)
	panel.add_child(column)
	column.add_child(_label("C  CodexAgentHarness", 17, MINT))
	column.add_child(_label("DESKTOP CONTROL", 11, MUTED))
	language_button = _button("中文 / English")
	language_button.pressed.connect(_toggle_language)
	column.add_child(language_button)
	column.add_child(_gap(24))
	for entry in [["overview", "◫  运行总览"], ["workbench", "▤  实例工作台"], ["machines", "⌘  机器列表"]]:
		var key: String = entry[0]
		var button := _button(entry[1])
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.pressed.connect(_show_page.bind(key))
		column.add_child(button)
		nav_buttons[key] = button
	var tools_button := _button("⚙  本机程序配置")
	tools_button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	tools_button.pressed.connect(_open_tool_settings)
	column.add_child(tools_button)
	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(spacer)
	column.add_child(_label("Master + 本机 Slave", 12, MINT))
	column.add_child(_label("所有连接均使用本机回环地址", 11, MUTED))


func _build_header(main: VBoxContainer) -> void:
	var panel := _panel(Color("#0c1823"))
	panel.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	main.add_child(panel)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	panel.add_child(row)
	var heading := VBoxContainer.new()
	heading.custom_minimum_size.x = 330
	var title := _label("CodexAgentHarness", 19, TEXT)
	title.autowrap_mode = TextServer.AUTOWRAP_OFF
	heading.add_child(title)
	var subtitle := _label("本机 Master · 多机器 Codex 工作台", 11, MUTED)
	subtitle.autowrap_mode = TextServer.AUTOWRAP_OFF
	heading.add_child(subtitle)
	row.add_child(heading)
	row.add_child(_grow())
	status_label = _label("检查连接中…", 12, AMBER)
	status_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	status_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(status_label)
	start_button = _button("启动 Master", true)
	start_button.pressed.connect(_start_master)
	row.add_child(start_button)
	stop_button = _button("停止 Master")
	stop_button.pressed.connect(_stop_master)
	row.add_child(stop_button)
	var browser_button := _button("浏览器打开")
	browser_button.pressed.connect(func(): OS.shell_open(ApiClient.BASE_URL))
	row.add_child(browser_button)
	var login_button := _button("登录信息")
	login_button.pressed.connect(_show_login_info)
	row.add_child(login_button)
	footer_label = _label("", 11, MUTED)
	main.add_child(footer_label)


func _build_overview(host: Control) -> void:
	var page_root := VBoxContainer.new()
	page_root.add_theme_constant_override("separation", 15)
	host.add_child(page_root)
	page_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	pages["overview"] = page_root
	page_root.add_child(_label("运行总览", 28))
	page_root.add_child(_label("集中查看机器、实例和需要处理的任务。", 13, MUTED))
	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	page_root.add_child(cards)
	for title in ["在线机器", "受管实例", "工作中", "需要处理"]:
		var card := _panel()
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		cards.add_child(card)
		var content := VBoxContainer.new()
		card.add_child(content)
		content.add_child(_label(title, 12, MUTED))
		var number := _label("—", 29, MINT)
		content.add_child(number)
		metrics.append(number)
	page_root.add_child(_label("已接入机器", 18))
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page_root.add_child(scroll)
	overview_machines = VBoxContainer.new()
	overview_machines.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	overview_machines.add_theme_constant_override("separation", 9)
	scroll.add_child(overview_machines)


func _build_machines(host: Control) -> void:
	var page_root := VBoxContainer.new()
	page_root.add_theme_constant_override("separation", 14)
	host.add_child(page_root)
	page_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	pages["machines"] = page_root
	page_root.add_child(_label("机器列表", 28))
	page_root.add_child(_label("选择一台机器进入实例工作台。", 13, MUTED))
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page_root.add_child(scroll)
	machines_page_list = VBoxContainer.new()
	machines_page_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	machines_page_list.add_theme_constant_override("separation", 9)
	scroll.add_child(machines_page_list)


func _build_workbench(host: Control) -> void:
	var page_root := VBoxContainer.new()
	page_root.add_theme_constant_override("separation", 14)
	host.add_child(page_root)
	page_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	pages["workbench"] = page_root
	var header := HBoxContainer.new()
	page_root.add_child(header)
	var intro := VBoxContainer.new()
	intro.custom_minimum_size.x = 360
	var workbench_title := _label("实例工作台", 28)
	workbench_title.autowrap_mode = TextServer.AUTOWRAP_OFF
	intro.add_child(workbench_title)
	workbench_subtitle_label = _label("实时活动、任务、审批与实例设置。", 12, MUTED)
	workbench_subtitle_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	intro.add_child(workbench_subtitle_label)
	header.add_child(intro)
	header.add_child(_grow())
	machine_picker = _option()
	machine_picker.custom_minimum_size.x = 250
	machine_picker.size_flags_horizontal = Control.SIZE_SHRINK_END
	machine_picker.item_selected.connect(_on_machine_selected)
	header.add_child(machine_picker)
	var reload := _button("刷新")
	reload.pressed.connect(_poll_status)
	header.add_child(reload)
	var columns := HBoxContainer.new()
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	columns.add_theme_constant_override("separation", 12)
	page_root.add_child(columns)
	_build_instance_column(columns)
	_build_activity_column(columns)
	_build_inspector_column(columns)


func _build_instance_column(columns: HBoxContainer) -> void:
	var panel := _panel()
	panel.custom_minimum_size.x = 232
	columns.add_child(panel)
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	panel.add_child(content)
	content.add_child(_label("Codex 实例", 16))
	instance_scroll = ScrollContainer.new()
	instance_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content.add_child(instance_scroll)
	instance_list = VBoxContainer.new()
	instance_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	instance_list.add_theme_constant_override("separation", 8)
	instance_scroll.add_child(instance_list)
	content.add_child(_label("外部 CLI 只读显示；受管实例可互动。", 11, MUTED))


func _build_activity_column(columns: HBoxContainer) -> void:
	var panel := _panel()
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	columns.add_child(panel)
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	panel.add_child(content)
	instance_title = _label("选择一个实例", 20)
	content.add_child(instance_title)
	instance_meta = _label("", 12, MUTED)
	content.add_child(instance_meta)
	activity_scroll = ScrollContainer.new()
	activity_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content.add_child(activity_scroll)
	activity_box = VBoxContainer.new()
	activity_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	activity_box.add_theme_constant_override("separation", 9)
	activity_scroll.add_child(activity_box)
	content.add_child(_label("继续对话", 13))
	task_input = TextEdit.new()
	task_input.custom_minimum_size.y = 90
	task_input.placeholder_text = "输入任务。Ctrl+Enter 发送。"
	task_input.add_theme_color_override("font_color", TEXT)
	task_input.add_theme_color_override("font_placeholder_color", MUTED)
	task_input.add_theme_stylebox_override("normal", _style(Color("#0d1b26"), BORDER, 8))
	task_input.add_theme_stylebox_override("focus", _style(Color("#0d1b26"), MINT, 8))
	task_input.gui_input.connect(_task_key_input)
	content.add_child(task_input)
	var row := HBoxContainer.new()
	content.add_child(row)
	row.add_child(_grow())
	send_button = _button("下达任务", true)
	send_button.pressed.connect(_send_task)
	row.add_child(send_button)


func _build_inspector_column(columns: HBoxContainer) -> void:
	var panel := _panel()
	panel.custom_minimum_size = Vector2(316, 0)
	columns.add_child(panel)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panel.add_child(scroll)
	var content := VBoxContainer.new()
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_theme_constant_override("separation", 9)
	scroll.add_child(content)
	content.add_child(_label("实例管理", 17))
	existing_note = _label("选择受管实例以调整配置。", 12, MUTED)
	content.add_child(existing_note)
	content.add_child(_label("权限", 12, MUTED))
	existing_mode = _option()
	_fill_modes(existing_mode)
	existing_mode.tooltip_text = "不覆盖权限选项，沿用目标机器当前 Codex 配置。"
	content.add_child(existing_mode)
	content.add_child(_label("模型", 12, MUTED))
	existing_model = _option()
	existing_model.tooltip_text = "不指定模型 ID，沿用目标机器 Codex 配置中的模型。"
	content.add_child(existing_model)
	content.add_child(_label("推理力度", 12, MUTED))
	existing_effort = _option()
	existing_effort.tooltip_text = "不指定推理力度，由 Codex 或所选模型采用默认值。"
	content.add_child(existing_effort)
	var actions := HBoxContainer.new()
	content.add_child(actions)
	restart_button = _button("应用并重启", true)
	restart_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	restart_button.pressed.connect(_restart_instance)
	actions.add_child(restart_button)
	stop_instance_button = _button("停止")
	stop_instance_button.pressed.connect(_confirm_stop)
	actions.add_child(stop_instance_button)
	delete_button = _button("删除历史")
	delete_button.pressed.connect(_confirm_delete)
	content.add_child(delete_button)
	trust_button = _button("信任此目录并重启")
	trust_button.pressed.connect(_confirm_trust_project)
	content.add_child(trust_button)
	content.add_child(_label("Codex 会保存所选目录的信任。之后从该目录启动的会话也会使用此设置；项目配置和钩子可能自动运行。", 11, MUTED))
	content.add_child(HSeparator.new())
	content.add_child(_label("启动新实例", 17))
	new_path = _field("目标机器上的工作目录")
	content.add_child(new_path)
	var browse_row := HBoxContainer.new()
	content.add_child(browse_row)
	var browse_button := _button("浏览目标文件夹")
	browse_button.pressed.connect(_open_browser)
	browse_row.add_child(browse_button)
	var catalog_button := _button("读取模型列表")
	catalog_button.pressed.connect(_request_models)
	browse_row.add_child(catalog_button)
	new_mode = _option()
	_fill_modes(new_mode)
	new_mode.tooltip_text = "不覆盖权限选项，沿用目标机器当前 Codex 配置。"
	content.add_child(new_mode)
	new_model = _option()
	new_model.tooltip_text = "不指定模型 ID，沿用目标机器 Codex 配置中的模型。"
	content.add_child(new_model)
	new_effort = _option()
	new_effort.tooltip_text = "不指定推理力度，由 Codex 或所选模型采用默认值。"
	content.add_child(new_effort)
	new_start_button = _button("启动 Codex", true)
	new_start_button.pressed.connect(_start_instance)
	content.add_child(new_start_button)
	browser_panel = VBoxContainer.new()
	browser_panel.visible = false
	browser_panel.add_theme_constant_override("separation", 7)
	content.add_child(browser_panel)
	browser_panel.add_child(HSeparator.new())
	browser_path_label = _label("", 12, MUTED)
	browser_panel.add_child(browser_path_label)
	browser_search = _field("筛选目录")
	browser_search.text_changed.connect(_filter_browser)
	browser_panel.add_child(browser_search)
	browser_show_hidden = CheckButton.new()
	browser_show_hidden.text = "显示 . 开头的隐藏文件夹"
	browser_show_hidden.button_pressed = false
	browser_show_hidden.toggled.connect(func(_enabled: bool): _filter_browser(browser_search.text))
	browser_panel.add_child(browser_show_hidden)
	browser_list = ItemList.new()
	browser_list.custom_minimum_size.y = 150
	browser_list.add_theme_stylebox_override("panel", _style(Color("#0d1b26"), BORDER, 8))
	browser_list.add_theme_stylebox_override("selected", _style(Color("#1c403b"), MINT, 8))
	browser_list.item_activated.connect(_enter_browser_item)
	browser_panel.add_child(browser_list)
	var browser_actions := HBoxContainer.new()
	browser_panel.add_child(browser_actions)
	browser_up_button = _button("上一级")
	browser_up_button.pressed.connect(_browse_up)
	browser_actions.add_child(browser_up_button)
	browser_choose_button = _button("使用此目录", true)
	browser_choose_button.pressed.connect(_choose_browser_path)
	browser_actions.add_child(browser_choose_button)
	content.add_child(HSeparator.new())
	content.add_child(_label("最近操作", 16))
	recent_box = VBoxContainer.new()
	content.add_child(recent_box)
	_fill_model_options(existing_model, "")
	_fill_model_options(new_model, "")
	_fill_effort_options(existing_effort, "")
	_fill_effort_options(new_effort, "")


func _fill_modes(option: OptionButton) -> void:
	for name in MODE_NAMES:
		option.add_item(name)


func _fill_model_options(option: OptionButton, selected: String) -> void:
	option.clear()
	option.add_item("沿用 Codex 配置模型")
	option.set_item_metadata(0, "")
	var seen: Dictionary = {"": true}
	var models: Array = model_catalog.get(selected_machine_id, [])
	for model in models:
		var model_id := str(model.get("id", ""))
		if model_id.is_empty() or seen.has(model_id):
			continue
		option.add_item(str(model.get("name", model_id)))
		option.set_item_metadata(option.item_count - 1, model_id)
		seen[model_id] = true
	if not selected.is_empty() and not seen.has(selected):
		option.add_item(selected)
		option.set_item_metadata(option.item_count - 1, selected)
	for index in option.item_count:
		if str(option.get_item_metadata(index)) == selected:
			option.select(index)
			break


func _fill_effort_options(option: OptionButton, selected: String) -> void:
	option.clear()
	option.add_item("沿用模型默认推理力度")
	option.set_item_metadata(0, "")
	for effort in EFFORTS:
		option.add_item(effort)
		option.set_item_metadata(option.item_count - 1, effort)
	for index in option.item_count:
		if str(option.get_item_metadata(index)) == selected:
			option.select(index)
			break


func _selected_metadata(option: OptionButton) -> String:
	if option.selected < 0:
		return ""
	return str(option.get_item_metadata(option.selected))


func _nullable_choice(option: OptionButton) -> Variant:
	var value := _selected_metadata(option)
	return null if value.is_empty() else value


func _first_text(values: Array) -> String:
	for value in values:
		if value != null and not str(value).is_empty():
			return str(value)
	return ""


func _show_page(next_page: String) -> void:
	page = next_page
	for key in pages:
		pages[key].visible = key == next_page
	for key in nav_buttons:
		nav_buttons[key].modulate = MINT if key == next_page else TEXT


func _poll_status() -> void:
	if status_busy:
		return
	status_busy = true
	api.request_json("status", "/api/status")


func _on_api_response(kind: String, ok: bool, data: Dictionary, message: String) -> void:
	if kind == "local_tools_get" or kind == "local_tools_auto":
		if not ok:
			if kind == "local_tools_get":
				_toast("本机程序读取失败：" + message, true)
			return
		tool_dialog_missing_only = kind == "local_tools_auto"
		var missing_tools: Array = data.get("missing", [])
		if tool_dialog_missing_only and not ("codex" in missing_tools or "terminal" in missing_tools):
			return
		tool_intro.text = "自动搜索未找到以下程序，请手动选择。" if tool_dialog_missing_only else "已自动搜索本机程序；你可以修改搜索结果或手动选择路径。"
		for tool_kind in tool_fields:
			tool_fields[tool_kind].text = str(data.get("configured", {}).get(tool_kind, ""))
			tool_hints[tool_kind].text = "建议搜索位置：" + " · ".join(data.get("suggestions", {}).get(tool_kind, []))
			tool_rows[tool_kind].visible = not tool_dialog_missing_only or tool_kind in missing_tools and tool_kind != "ssh"
		tools_dialog.popup_centered(Vector2i(900, 520))
		_refresh_language(tools_dialog)
		return
	if kind == "local_tools_put":
		_toast("本机程序已保存" if ok else "保存失败：" + message, not ok)
		if not ok:
			tools_dialog.popup_centered(Vector2i(900, 520))
		return
	if kind == "status":
		status_busy = false
		master_online = ok
		status_label.text = "● Master 运行中" if ok else "● Master 未连接"
		status_label.add_theme_color_override("font_color", MINT if ok else AMBER)
		start_button.disabled = ok
		stop_button.disabled = not ok
		if ok:
			if not local_tools_checked:
				local_tools_checked = true
				api.request_json("local_tools_auto", "/api/local-tools")
			machines = data.get("machines", [])
			commands = data.get("commands", [])
			_render_status()
		else:
			for machine in machines:
				machine["online"] = false
			_render_status()
			footer_label.text = message
		return
	if not ok:
		_toast("操作失败：" + message, true)
		return
	if kind.begins_with("command:"):
		var action := kind.trim_prefix("command:")
		if action == "task" and task_input.text.strip_edges() == sent_prompt:
			task_input.clear()
			sent_prompt = ""
		if action in ["browse", "models"]:
			lookup_intents[str(data.get("id", ""))] = {"action": action,
				"machine_id": str(data.get("machine_id", ""))}
		_toast("命令已排队：" + action)
		_poll_status()


func _render_status() -> void:
	var online_count := 0
	var managed_count := 0
	var working_count := 0
	var attention_count := 0
	for machine in machines:
		if machine.get("online", false):
			online_count += 1
		for instance in machine.get("instances", []):
			if instance.get("managed", true):
				managed_count += 1
			if instance.get("status") == "working":
				working_count += 1
			if instance.get("status") == "attention":
				attention_count += 1
	for index in metrics.size():
		metrics[index].text = str([online_count, managed_count, working_count, attention_count][index])
	footer_label.text = "每 1 秒同步 · %d 台机器 · %s" % [machines.size(), Time.get_time_string_from_system()]
	_render_machines()
	_update_machine_picker()
	_sync_new_path_machine()
	_render_workbench_summary()
	_render_instances()
	_render_activity()
	_render_recent()
	_process_command_results()
	_refresh_language()


func _render_machines() -> void:
	var signature := JSON.stringify(machines.map(func(machine):
		return [machine.get("machine_id"), machine.get("hostname"), machine.get("online"),
			machine.get("cli_process_count"), machine.get("instances", []).map(func(instance):
				return [instance.get("id"), instance.get("project"), instance.get("status"), instance.get("pid")])]))
	if signature == machine_signature:
		_update_report_clocks()
		return
	machine_signature = signature
	machine_report_labels.clear()
	for target in [overview_machines, machines_page_list]:
		_clear(target)
		for machine in machines:
			var machine_id := str(machine.get("machine_id", ""))
			var card := _panel()
			card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			target.add_child(card)
			var row := HBoxContainer.new()
			row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			row.add_theme_constant_override("separation", 20)
			card.add_child(row)
			var details := VBoxContainer.new()
			details.custom_minimum_size.x = 340
			details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			details.add_theme_constant_override("separation", 4)
			row.add_child(details)
			var name_label := _data_label(_machine_display_name(machine), 17)
			name_label.autowrap_mode = TextServer.AUTOWRAP_OFF
			details.add_child(name_label)
			var counts := _label("%s · %d 个 CLI 进程 · %d 个实例" % [machine.get("platform", ""),
				int(machine.get("cli_process_count", 0)), machine.get("instances", []).size()], 12, MUTED)
			counts.autowrap_mode = TextServer.AUTOWRAP_OFF
			details.add_child(counts)
			if machine.get("instances", []).is_empty():
				details.add_child(_label("暂无 Codex 实例", 11, MUTED))
			else:
				var strip := ScrollContainer.new()
				strip.custom_minimum_size.y = 99
				strip.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
				details.add_child(strip)
				var chips := HBoxContainer.new()
				chips.add_theme_constant_override("separation", 7)
				strip.add_child(chips)
				for instance in machine.get("instances", []):
					var instance_id := str(instance.get("id", ""))
					var chip := Button.new()
					chip.custom_minimum_size = Vector2(214, 88)
					chip.tooltip_text = str(instance.get("cwd", ""))
					chip.add_theme_stylebox_override("normal", _style(Color("#13232e"), BORDER, 8))
					chip.add_theme_stylebox_override("hover", _style(Color("#1c353b"), MINT, 8))
					chip.pressed.connect(_open_machine.bind(machine_id, instance_id))
					chips.add_child(chip)
					var chip_body := HBoxContainer.new()
					chip_body.mouse_filter = Control.MOUSE_FILTER_IGNORE
					chip.add_child(chip_body)
					chip_body.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
					var actor := AgentActor.new()
					chip_body.add_child(actor)
					actor.configure(instance_id, str(instance.get("status", "unknown")), machine.get("online", false))
					var chip_labels := VBoxContainer.new()
					chip_labels.mouse_filter = Control.MOUSE_FILTER_IGNORE
					chip_labels.size_flags_horizontal = Control.SIZE_EXPAND_FILL
					chip_labels.add_theme_constant_override("separation", 4)
					chip_body.add_child(chip_labels)
					chip_labels.add_child(_data_label(str(instance.get("project", "Codex")), 11))
					var state_name: String = str(STATUS_NAMES.get(str(instance.get("status", "unknown")), "未确认")) \
						if machine.get("online", false) else "离线"
					chip_labels.add_child(_label(state_name, 10, MUTED))
			var last_report := _label("最近上报：" + _report_clock(machine), 11, MUTED)
			last_report.autowrap_mode = TextServer.AUTOWRAP_OFF
			details.add_child(last_report)
			if not machine_report_labels.has(machine_id):
				machine_report_labels[machine_id] = []
			machine_report_labels[machine_id].append(last_report)
			var right := VBoxContainer.new()
			right.custom_minimum_size.x = 130
			right.add_theme_constant_override("separation", 9)
			row.add_child(right)
			var connection := _label("● 在线" if machine.get("online", false) else "● 离线", 12,
				MINT if machine.get("online", false) else RED)
			connection.autowrap_mode = TextServer.AUTOWRAP_OFF
			right.add_child(connection)
			var open_button := _button("打开工作台")
			open_button.pressed.connect(_open_machine.bind(machine_id))
			right.add_child(open_button)
			var rename_button := _button("重命名")
			rename_button.pressed.connect(_open_machine_name_dialog.bind(machine_id))
			right.add_child(rename_button)


func _report_clock(machine: Dictionary) -> String:
	var stamp := str(machine.get("received_at", ""))
	return stamp.substr(11, 8) + " UTC" if stamp.length() >= 19 else "尚未收到"


func _update_report_clocks() -> void:
	for machine in machines:
		var machine_id := str(machine.get("machine_id", ""))
		for label in machine_report_labels.get(machine_id, []):
			label.text = "最近上报：" + _report_clock(machine)


func _render_workbench_summary() -> void:
	var machine := _selected_machine()
	if machine.is_empty():
		workbench_subtitle_label.text = "选择机器后查看实例状态与活动。"
		return
	workbench_subtitle_label.text = "%s · %s · 最近上报 %s · %d 个实例" % [
		_machine_display_name(machine), "在线" if machine.get("online", false) else "离线",
		_report_clock(machine), machine.get("instances", []).size()]


func _update_machine_picker() -> void:
	var ids: Array = machines.map(func(machine): return str(machine.get("machine_id", "")))
	if ids == machine_ids:
		for index in machines.size():
			var title := "%s · %s" % [_machine_display_name(machines[index]),
				"在线" if machines[index].get("online", false) else "离线"]
			if index >= machine_picker_sources.size() or machine_picker_sources[index] != title:
				if index >= machine_picker_sources.size():
					machine_picker_sources.append(title)
				else:
					machine_picker_sources[index] = title
				machine_picker.set_item_text(index, title)
		return
	machine_ids = ids
	machine_picker_sources.clear()
	if not selected_machine_id in ids:
		selected_machine_id = ids[0] if not ids.is_empty() else ""
		selected_instance_id = ""
	machine_picker.clear()
	for machine in machines:
		var title := "%s · %s" % [_machine_display_name(machine),
			"在线" if machine.get("online", false) else "离线"]
		machine_picker.add_item(title)
		machine_picker_sources.append(title)
		machine_picker.set_item_metadata(machine_picker.item_count - 1, machine.get("machine_id", ""))
	for index in machine_picker.item_count:
		if str(machine_picker.get_item_metadata(index)) == selected_machine_id:
			machine_picker.select(index)
			break


func _open_machine(machine_id: String, instance_id: String = "") -> void:
	selected_machine_id = machine_id
	selected_instance_id = instance_id
	_update_machine_picker()
	_sync_new_path_machine()
	for index in machine_picker.item_count:
		if str(machine_picker.get_item_metadata(index)) == machine_id:
			machine_picker.select(index)
			break
	instance_signature = ""
	activity_signature = ""
	_render_workbench_summary()
	_render_instances()
	_render_activity()
	_show_page("workbench")
	_request_models()
	_refresh_language()


func _on_machine_selected(index: int) -> void:
	selected_machine_id = str(machine_picker.get_item_metadata(index))
	selected_instance_id = ""
	_sync_new_path_machine()
	instance_signature = ""
	activity_signature = ""
	_render_workbench_summary()
	_render_instances()
	_render_activity()
	_request_models()
	_refresh_language()


func _selected_machine() -> Dictionary:
	for machine in machines:
		if machine.get("machine_id") == selected_machine_id:
			return machine
	return {}


func _selected_instance() -> Dictionary:
	for instance in _selected_machine().get("instances", []):
		if instance.get("id") == selected_instance_id:
			return instance
	return {}


func _render_instances() -> void:
	var items: Array = _selected_machine().get("instances", [])
	var online: bool = _selected_machine().get("online", false)
	var ids: Array = items.map(func(item): return str(item.get("id", "")))
	var state_rows: Array = items.map(func(item):
		return [item.get("id"), item.get("project"), item.get("status"), item.get("pid"),
			item.get("active_model"), item.get("active_reasoning_effort"),
			item.get("interaction_ready"), item.get("launch_mode"), item.get("trust_project"), item.get("error")])
	var signature := JSON.stringify([online, selected_instance_id, state_rows])
	if signature == instance_signature:
		return
	instance_ids = ids
	if not selected_instance_id in ids:
		selected_instance_id = ids[0] if not ids.is_empty() else ""
	instance_signature = JSON.stringify([online, selected_instance_id, state_rows])
	var previous_scroll := instance_scroll.scroll_vertical
	_clear(instance_list)
	for item in items:
		var id := str(item.get("id", ""))
		var row := Button.new()
		row.custom_minimum_size.y = 94
		row.focus_mode = Control.FOCUS_ALL
		row.tooltip_text = "PID %s · %s" % [_first_text([item.get("pid"), "—"]), item.get("cwd", "")]
		row.add_theme_stylebox_override("normal", _style(Color("#1b3435") if id == selected_instance_id else Color("#13232e"),
			MINT if id == selected_instance_id else BORDER, 9))
		row.add_theme_stylebox_override("hover", _style(Color("#213a3d"), MINT, 9))
		row.add_theme_stylebox_override("pressed", _style(Color("#24423d"), MINT, 9))
		row.pressed.connect(_select_instance.bind(id))
		instance_list.add_child(row)
		var margin := MarginContainer.new()
		margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
		row.add_child(margin)
		margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		margin.add_theme_constant_override("margin_left", 8)
		margin.add_theme_constant_override("margin_right", 8)
		margin.add_theme_constant_override("margin_top", 5)
		margin.add_theme_constant_override("margin_bottom", 5)
		var body := HBoxContainer.new()
		body.mouse_filter = Control.MOUSE_FILTER_IGNORE
		body.add_theme_constant_override("separation", 4)
		margin.add_child(body)
		var actor := AgentActor.new()
		body.add_child(actor)
		actor.configure(id, str(item.get("status", "unknown")), online)
		var labels := VBoxContainer.new()
		labels.mouse_filter = Control.MOUSE_FILTER_IGNORE
		labels.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		labels.add_theme_constant_override("separation", 4)
		body.add_child(labels)
		var title := _data_label(str(item.get("project", "Codex")), 12)
		title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		labels.add_child(title)
		var status := str(item.get("status", "unknown"))
		var visible_status: String = str(STATUS_NAMES.get(status, "未确认")) if online else "离线"
		var status_color := MINT if status == "working" and online else AMBER if status == "attention" and online else MUTED
		labels.add_child(_label("● " + visible_status, 11, status_color))
		labels.add_child(_label("PID " + _first_text([item.get("pid"), "—"]), 10, MUTED))
	instance_scroll.set_deferred("scroll_vertical", previous_scroll)
	_refresh_instance_controls()


func _select_instance(id: String) -> void:
	selected_instance_id = id
	instance_signature = ""
	_render_instances()
	activity_signature = ""
	_refresh_instance_controls()
	_render_activity()
	_refresh_language()


func _refresh_instance_controls() -> void:
	var item := _selected_instance()
	var managed: bool = not item.is_empty() and item.get("managed", true)
	restart_button.disabled = not managed
	trust_button.disabled = not managed or not _selected_machine().get("online", false) \
		or item.get("status") == "starting"
	trust_button.text = "重新写入目录信任并重启" if item.get("trust_project", false) else "信任此目录并重启"
	stop_instance_button.disabled = not managed or item.get("status") in ["exited", "error"]
	delete_button.disabled = not managed or item.get("status") not in ["exited", "error"]
	send_button.disabled = not managed or not item.get("interaction_ready", false)
	if item.is_empty():
		configured_instance_id = ""
		existing_note.text = "选择受管实例以调整配置。"
		return
	existing_note.text = "PID %s · %s / %s" % [_first_text([item.get("pid"), "—"]),
		_first_text([item.get("active_model"), item.get("model"), "模型未确认"]),
		_first_text([item.get("active_reasoning_effort"), item.get("reasoning_effort"), "力度未确认"])]
	if configured_instance_id == selected_instance_id and configured_machine_id == selected_machine_id:
		return
	configured_instance_id = selected_instance_id
	configured_machine_id = selected_machine_id
	var mode := str(item.get("launch_mode", "default"))
	existing_mode.select(maxi(0, MODES.find(mode)))
	_fill_model_options(existing_model, _first_text([item.get("model")]))
	_fill_effort_options(existing_effort, _first_text([item.get("reasoning_effort")]))


func _render_activity() -> void:
	var item := _selected_instance()
	if item.is_empty():
		if instance_title.has_meta("cah_no_translate"):
			instance_title.remove_meta("cah_no_translate")
		instance_title.text = "选择一个实例"
	else:
		instance_title.set_meta("cah_no_translate", true)
		instance_title.text = str(item.get("project", "Codex"))
	var instance_status := I18n.status_label(str(item.get("status", "unknown")), language)
	instance_meta.text = "PID %s · %s · %s / %s" % [_first_text([item.get("pid"), "—"]),
		instance_status, _first_text([item.get("active_model"), item.get("model"), "模型未确认"]),
		_first_text([item.get("active_reasoning_effort"), item.get("reasoning_effort"), "力度未确认"])] if not item.is_empty() else ""
	var activity: Array = item.get("activity", [])
	var approvals: Array = item.get("pending_approvals", [])
	var signature := JSON.stringify([selected_instance_id, _selected_machine().get("online", false), activity, approvals,
		item.get("live_text", ""), item.get("error"), item.get("interaction_ready")])
	if signature == activity_signature:
		return
	activity_signature = signature
	var previous_scroll := activity_scroll.scroll_vertical
	var scrollbar := activity_scroll.get_v_scroll_bar()
	var follow_bottom := previous_scroll + activity_scroll.size.y >= scrollbar.max_value - 80.0
	_clear(activity_box)
	if item.is_empty():
		activity_box.add_child(_label("选择左侧实例查看状态和对话。", 13, MUTED))
		return
	activity_box.add_child(_data_label(str(item.get("cwd", "")), 12, MUTED))
	if not _first_text([item.get("error")]).is_empty():
		activity_box.add_child(_label("启动错误：" + str(item.get("error")), 12, RED))
	if item.get("managed", true) and not item.get("interaction_ready", false) \
			and item.get("status") not in ["exited", "error"]:
		activity_box.add_child(_label("Codex 进程已启动，但会话尚未就绪。若终端显示 Folder access，请在右侧确认“信任此目录并重启”；登录等其他提示仍需在目标终端处理。", 12, AMBER))
	if not _selected_machine().get("online", false):
		activity_box.add_child(_label("机器已离线；下面显示的是最后一次上报的快照。", 12, AMBER))
	if not item.get("managed", true):
		activity_box.add_child(_label("这是外部启动的 CLI，仅显示进程状态。", 12, AMBER))
	for approval in approvals:
		var approval_id := str(approval.get("id", ""))
		var card := _panel(Color("#302925"))
		activity_box.add_child(card)
		var body := VBoxContainer.new()
		card.add_child(body)
		body.add_child(_label("等待审批 · %s" % approval.get("kind", ""), 13, AMBER))
		body.add_child(_data_label(str(approval.get("reason", "")), 12))
		body.add_child(_data_label(str(approval.get("command", "")), 12, MUTED))
		var row := HBoxContainer.new()
		body.add_child(row)
		var allow := _button("允许本次", true)
		allow.pressed.connect(_send_approval.bind(approval_id, "accept"))
		row.add_child(allow)
		if "acceptForSession" in approval.get("available_decisions", []):
			var session := _button("本会话允许")
			session.pressed.connect(_send_approval.bind(approval_id, "acceptForSession"))
			row.add_child(session)
		var reject := _button("拒绝")
		reject.pressed.connect(_send_approval.bind(approval_id, "decline"))
		row.add_child(reject)
	for event in activity:
		var kind := str(event.get("kind", "event"))
		var from_user := kind in ["user", "task", "用户"]
		var event_card := _panel(Color("#19372f") if from_user else SURFACE_ALT)
		activity_box.add_child(event_card)
		var event_content := VBoxContainer.new()
		event_card.add_child(event_content)
		event_content.add_child(_label(kind.to_upper(), 11, MINT if from_user else MUTED))
		event_content.add_child(_data_label(str(event.get("text", "")), 13))
	if activity.is_empty() and approvals.is_empty():
		activity_box.add_child(_label("已收到实例状态；当前快照没有可显示的对话内容。", 13, MUTED))
	var live_text := str(item.get("live_text", ""))
	if not live_text.is_empty():
		var live_card := _panel(Color("#182735"))
		activity_box.add_child(live_card)
		var live_body := VBoxContainer.new()
		live_card.add_child(live_body)
		live_body.add_child(_label("实时输出", 12, MINT))
		live_body.add_child(_data_label(live_text, 12))
	if follow_bottom:
		call_deferred("_scroll_activity_down")
	else:
		activity_scroll.set_deferred("scroll_vertical", previous_scroll)


func _scroll_activity_down() -> void:
	activity_scroll.scroll_vertical = int(activity_scroll.get_v_scroll_bar().max_value)


func _render_recent() -> void:
	var current: Array = commands.filter(func(command):
		return command.get("machine_id") == selected_machine_id)
	var signature := JSON.stringify([selected_machine_id, language, current.slice(maxi(0, current.size() - 5))])
	if signature == recent_signature:
		return
	recent_signature = signature
	_clear(recent_box)
	var shown := 0
	for index in range(commands.size() - 1, -1, -1):
		var command: Dictionary = commands[index]
		if command.get("machine_id") != selected_machine_id:
			continue
		recent_box.add_child(_data_label("%s · %s · %s" % [
			I18n.command_label(str(command.get("action", "")), language),
			I18n.command_label(str(command.get("status", "")), language), command.get("message", "")], 11,
			RED if command.get("status") == "failed" else MUTED))
		shown += 1
		if shown >= 5:
			break


func _process_command_results() -> void:
	for command in commands:
		var command_id := str(command.get("id", ""))
		if not lookup_intents.has(command_id) or command.get("status") not in ["succeeded", "failed"]:
			continue
		var intent: Dictionary = lookup_intents[command_id]
		lookup_intents.erase(command_id)
		if command.get("status") == "failed":
			var action_label := I18n.command_label(str(intent.get("action", "")), language)
			var failure_text := "%s failed: %s" % [action_label, command.get("message", "")]
			if language == "zh":
				failure_text = "%s 失败：%s" % [action_label, command.get("message", "")]
			_toast(failure_text, true)
			continue
		if intent.get("action") == "browse" and intent.get("machine_id") == selected_machine_id:
			browser_data = command.get("data") if command.get("data") is Dictionary else {}
			_show_browser_data()
		if intent.get("action") == "models":
			var result: Dictionary = command.get("data") if command.get("data") is Dictionary else {}
			var machine_id := str(intent.get("machine_id", ""))
			model_catalog[machine_id] = result.get("models", [])
			if machine_id == selected_machine_id:
				var existing := _selected_metadata(existing_model)
				var newest := _selected_metadata(new_model)
				_fill_model_options(existing_model, existing)
				_fill_model_options(new_model, newest)
				_toast("已读取 %d 个可用模型" % model_catalog[machine_id].size())


func _send_command(action: String, extras: Dictionary = {}) -> void:
	if selected_machine_id.is_empty():
		_toast("请先选择机器", true)
		return
	var payload := {"machine_id": selected_machine_id, "action": action}
	for key in extras:
		payload[key] = extras[key]
	api.request_json("command:" + action, "/api/commands", HTTPClient.METHOD_POST, payload)


func _task_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo \
			and event.keycode == KEY_ENTER and event.ctrl_pressed:
		_send_task()
		get_viewport().set_input_as_handled()


func _send_task() -> void:
	var prompt := task_input.text.strip_edges()
	if prompt.is_empty():
		return
	sent_prompt = prompt
	_send_command("task", {"instance_id": selected_instance_id, "prompt": prompt})


func _send_approval(approval_id: String, decision: String) -> void:
	_send_command("approval", {"instance_id": selected_instance_id,
		"approval_id": approval_id, "decision": decision})


func _restart_instance() -> void:
	if selected_instance_id.is_empty():
		return
	_send_command("restart", {"instance_id": selected_instance_id,
		"mode": MODES[existing_mode.selected], "model": _nullable_choice(existing_model),
		"effort": _nullable_choice(existing_effort)})


func _confirm_stop() -> void:
	confirm_action = "stop"
	confirm_target_machine_id = selected_machine_id
	confirm_target_instance_id = selected_instance_id
	confirm_dialog.dialog_text = I18n.translate("停止当前 Codex 实例？", language)
	confirm_dialog.popup_centered()


func _confirm_delete() -> void:
	confirm_action = "delete"
	confirm_target_machine_id = selected_machine_id
	confirm_target_instance_id = selected_instance_id
	confirm_dialog.dialog_text = I18n.translate("删除此实例的本地历史记录？该操作无法撤销。", language)
	confirm_dialog.popup_centered()


func _confirm_trust_project() -> void:
	var item := _selected_instance()
	if item.is_empty() or not item.get("managed", true):
		return
	confirm_action = "trust_project"
	confirm_target_machine_id = selected_machine_id
	confirm_target_instance_id = selected_instance_id
	_set_trust_confirmation_text()
	confirm_dialog.popup_centered()


func _set_trust_confirmation_text() -> void:
	var item := _selected_instance()
	if item.is_empty():
		return
	if language == "en":
		confirm_dialog.dialog_text = "Trust this folder on the target machine and restart Codex?\n\n%s\n\nCodex saves trust in the target user's settings. Future sessions from this folder inherit it. Project settings and hooks may run automatically. Continue only if you trust this folder." % str(item.get("cwd", ""))
	else:
		confirm_dialog.dialog_text = "信任目标机器上的目录并重启 Codex？\n\n%s\n\nCodex 会把信任写入该机器的用户配置；以后从此目录启动的会话也会使用。项目配置和钩子可能自动运行。仅在你信任该目录时继续。" % str(item.get("cwd", ""))


func _on_confirmed() -> void:
	if confirm_target_machine_id != selected_machine_id or confirm_target_instance_id != selected_instance_id:
		_toast("选中的实例已变化，请重新确认。", true)
		return
	if confirm_action in ["stop", "delete"] and not selected_instance_id.is_empty():
		_send_command(confirm_action, {"instance_id": selected_instance_id})
	elif confirm_action == "trust_project" and not selected_instance_id.is_empty():
		_send_command("trust_project", {"instance_id": selected_instance_id,
			"mode": MODES[existing_mode.selected], "model": _nullable_choice(existing_model),
			"effort": _nullable_choice(existing_effort)})


func _start_instance() -> void:
	var path := new_path.text.strip_edges()
	if path.is_empty():
		_toast("请先选择工作目录", true)
		return
	_send_command("start", {"cwd": path, "mode": MODES[new_mode.selected],
		"model": _nullable_choice(new_model), "effort": _nullable_choice(new_effort)})


func _request_models() -> void:
	if selected_machine_id.is_empty() or not _selected_machine().get("online", false):
		return
	_send_command("models")


func _open_browser() -> void:
	if selected_machine_id.is_empty():
		_toast("请先选择目标机器", true)
		return
	browser_machine_id = selected_machine_id
	browser_panel.visible = true
	_browse_to(new_path.text.strip_edges())


func _browse_to(path: String) -> void:
	var args := {"cwd": path} if not path.is_empty() else {}
	_send_command("browse", args)


func _show_browser_data() -> void:
	browser_panel.visible = true
	browser_path_label.text = str(browser_data.get("path", ""))
	browser_names = browser_data.get("directories", [])
	browser_up_button.disabled = browser_data.get("parent") == null
	_filter_browser(browser_search.text)


func _filter_browser(filter_text: String) -> void:
	browser_list.clear()
	for name in browser_names:
		if str(name).begins_with(".") and not browser_show_hidden.button_pressed:
			continue
		if filter_text.is_empty() or filter_text.to_lower() in str(name).to_lower():
			browser_list.add_item("📁  " + str(name))
			browser_list.set_item_metadata(browser_list.item_count - 1, str(name))


func _enter_browser_item(index: int) -> void:
	var directory := str(browser_list.get_item_metadata(index))
	_browse_to(str(browser_data.get("path", "")).path_join(directory))


func _browse_up() -> void:
	if browser_data.get("parent") != null:
		_browse_to(str(browser_data.get("parent")))


func _choose_browser_path() -> void:
	new_path.text = str(browser_data.get("path", ""))
	browser_panel.visible = false


func _start_master() -> void:
	_run_master_action(false)


func _stop_master() -> void:
	_run_master_action(true)


func _run_master_action(stop: bool) -> void:
	var file_name := "codex-agent-harness-master.exe" if OS.has_feature("windows") else "codex-agent-harness-master"
	var backend := OS.get_executable_path().get_base_dir().path_join("backend").path_join(file_name)
	var executable := backend
	var args := PackedStringArray(["--stop"] if stop else [])
	if not FileAccess.file_exists(backend):
		# Source checkout: the packaged app never needs Python or these scripts.
		var repo_root := ProjectSettings.globalize_path("res://project.godot").get_base_dir().get_base_dir()
		if OS.has_feature("windows"):
			var script := repo_root.path_join("scripts").path_join("stop_master.ps1" if stop else "start_master.ps1")
			if not FileAccess.file_exists(script):
				_toast("找不到脚本：" + script, true)
				return
			executable = "powershell.exe"
			args = PackedStringArray(["-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script])
		else:
			executable = "python3"
			args = PackedStringArray(["-m", "codex_agent_harness.master"])
			if stop:
				args.append("--stop")
	var pid := OS.create_process(executable, args, false)
	if pid < 0:
		_toast("无法启动 Master 程序", true)
	else:
		_toast("已执行 Master 操作 · PID %d" % pid)
		get_tree().create_timer(1.5).timeout.connect(_poll_status)


func _show_login_info() -> void:
	var profile := OS.get_environment("USERPROFILE") if OS.has_feature("windows") else OS.get_environment("HOME")
	var file := FileAccess.open(profile.path_join(".codex-agent-harness").path_join("master-credentials.json"), FileAccess.READ)
	if file == null:
		_toast("请先启动 Master 以生成登录信息。", true)
		return
	var data: Variant = JSON.parse_string(file.get_as_text())
	if not data is Dictionary:
		_toast("登录信息文件无效。", true)
		return
	if language == "en":
		login_dialog.dialog_text = "Web username: %s\nWeb password: %s" % [data.get("DASHBOARD_USER", ""), data.get("DASHBOARD_PASSWORD", "")]
	else:
		login_dialog.dialog_text = "网页登录用户：%s\n网页登录密码：%s" % [data.get("DASHBOARD_USER", ""), data.get("DASHBOARD_PASSWORD", "")]
	login_dialog.popup_centered()


func _toast(message: String, error: bool = false) -> void:
	footer_label.text = message
	footer_label.add_theme_color_override("font_color", RED if error else MINT)
	_apply_language(footer_label)
