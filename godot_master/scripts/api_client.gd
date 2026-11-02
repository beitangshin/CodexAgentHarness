extends Node

signal response(kind: String, ok: bool, data: Dictionary, message: String)

const BASE_URL := "http://127.0.0.1:8000"
var auth_header := ""


func load_credentials() -> bool:
	var profile := OS.get_environment("USERPROFILE") if OS.has_feature("windows") else OS.get_environment("HOME")
	if profile.is_empty():
		return false
	var path := profile.path_join(".codex-agent-harness").path_join("master-credentials.json")
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return false
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		return false
	var username := str(parsed.get("DASHBOARD_USER", ""))
	var password := str(parsed.get("DASHBOARD_PASSWORD", ""))
	if username.is_empty() or password.is_empty():
		return false
	auth_header = "Authorization: Basic " + Marshalls.utf8_to_base64(username + ":" + password)
	return true


func request_json(kind: String, path: String, method: int = HTTPClient.METHOD_GET, payload: Dictionary = {}) -> void:
	if auth_header.is_empty() and not load_credentials():
		response.emit(kind, false, {}, "缺少本机 Master 凭据文件")
		return
	var request_node := HTTPRequest.new()
	request_node.timeout = 8.0
	add_child(request_node)
	request_node.request_completed.connect(_completed.bind(kind, request_node))
	var headers := PackedStringArray([auth_header, "Accept: application/json"])
	var body := ""
	if method != HTTPClient.METHOD_GET:
		headers.append("Content-Type: application/json")
		body = JSON.stringify(payload)
	var error := request_node.request(BASE_URL + path, headers, method, body)
	if error != OK:
		request_node.queue_free()
		response.emit(kind, false, {}, "请求无法启动 (%d)" % error)


func _completed(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray,
		kind: String, request_node: HTTPRequest) -> void:
	request_node.queue_free()
	if result != HTTPRequest.RESULT_SUCCESS:
		response.emit(kind, false, {}, "无法连接 Master (%d)" % result)
		return
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	var data: Dictionary = parsed if parsed is Dictionary else {}
	if code < 200 or code >= 300:
		var detail := str(data.get("detail", "HTTP %d" % code))
		response.emit(kind, false, data, detail)
		return
	response.emit(kind, true, data, "")
