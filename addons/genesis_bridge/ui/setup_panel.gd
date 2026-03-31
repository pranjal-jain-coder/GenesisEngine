@tool
extends VBoxContainer

## Emitted when the user clicks "Install & Start".
## python_path: the Python executable path entered by the user
## api_key: the Gemini API key entered by the user
signal install_requested(python_path: String, api_key: String)

var _status_label: Label
var _python_field: LineEdit
var _api_key_field: LineEdit
var _install_btn: Button
var _progress_label: Label

func _ready() -> void:
	_build_ui()


func _build_ui() -> void:
	# ── Header ──────────────────────────────────────────────────────────────
	var title = Label.new()
	title.text = "Genesis Engine — First-Time Setup"
	title.add_theme_font_size_override("font_size", 14)
	add_child(title)

	_status_label = Label.new()
	_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status_label.add_theme_color_override("font_color", Color(1, 0.8, 0.4))
	add_child(_status_label)

	add_child(_separator())

	# ── Gemini API Key ───────────────────────────────────────────────────────
	var key_label = Label.new()
	key_label.text = "Gemini API Key"
	add_child(key_label)

	_api_key_field = LineEdit.new()
	_api_key_field.placeholder_text = "AIza…"
	_api_key_field.secret = true
	_api_key_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	# Pre-fill from EditorSettings if already saved
	var settings = EditorInterface.get_editor_settings()
	if settings.has_setting("genesis_bridge/gemini_api_key"):
		_api_key_field.text = settings.get_setting("genesis_bridge/gemini_api_key")
	add_child(_api_key_field)

	var key_hint = Label.new()
	key_hint.text = "Get a free key at aistudio.google.com"
	key_hint.add_theme_font_size_override("font_size", 10)
	key_hint.add_theme_color_override("font_color", Color(0.6, 0.6, 0.6))
	add_child(key_hint)

	add_child(_separator())

	# ── Python path ──────────────────────────────────────────────────────────
	var py_label = Label.new()
	py_label.text = "Python 3 Executable"
	add_child(py_label)

	var py_row = HBoxContainer.new()
	add_child(py_row)

	_python_field = LineEdit.new()
	_python_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if settings.has_setting("genesis_bridge/python_executable_path"):
		_python_field.text = settings.get_setting("genesis_bridge/python_executable_path")
	else:
		_python_field.text = _autodetect_python()
	py_row.add_child(_python_field)

	var detect_btn = Button.new()
	detect_btn.text = "Auto-detect"
	detect_btn.pressed.connect(_on_autodetect_pressed)
	py_row.add_child(detect_btn)

	var py_hint = Label.new()
	py_hint.text = "Requires Python 3.10+. A .venv will be created inside the plugin folder."
	py_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	py_hint.add_theme_font_size_override("font_size", 10)
	py_hint.add_theme_color_override("font_color", Color(0.6, 0.6, 0.6))
	add_child(py_hint)

	add_child(_separator())

	# ── Install button ───────────────────────────────────────────────────────
	_install_btn = Button.new()
	_install_btn.text = "Install & Start Backend"
	_install_btn.pressed.connect(_on_install_pressed)
	add_child(_install_btn)

	_progress_label = Label.new()
	_progress_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_progress_label.add_theme_color_override("font_color", Color(0.4, 1, 0.6))
	_progress_label.visible = false
	add_child(_progress_label)


# ── Public API ───────────────────────────────────────────────────────────────

func set_status(text: String) -> void:
	_status_label.text = text


func set_progress(text: String) -> void:
	if text.is_empty():
		_progress_label.visible = false
		_install_btn.disabled = false
	else:
		_progress_label.text = text
		_progress_label.visible = true
		_install_btn.disabled = true


# ── Internal helpers ─────────────────────────────────────────────────────────

func _autodetect_python() -> String:
	for candidate in ["python3", "python", "py"]:
		var output: Array = []
		if OS.execute(candidate, ["--version"], output) == 0:
			return candidate
	return "python3"


func _on_autodetect_pressed() -> void:
	_python_field.text = _autodetect_python()


func _on_install_pressed() -> void:
	var api_key = _api_key_field.text.strip_edges()
	var python_path = _python_field.text.strip_edges()

	if api_key.is_empty():
		set_status("Please enter your Gemini API key.")
		return
	if python_path.is_empty():
		set_status("Please enter the Python 3 executable path.")
		return

	set_progress("Installing dependencies — this may take a few minutes…")
	install_requested.emit(python_path, api_key)


func _separator() -> HSeparator:
	return HSeparator.new()
