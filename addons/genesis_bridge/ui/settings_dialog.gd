@tool
extends Window

## Emitted when the user clicks "Save & Restart".
## genesis_bridge.gd listens to this to rewrite .env and restart the backend.
signal settings_saved

const IMAGE_PROVIDERS       := ["local", "gemini"]
const IMAGE_PROVIDER_LABELS := ["Local Diffusers (Stable Diffusion)", "Gemini (Imagen API)"]

const DEFAULT_MODEL := "gemini-3.1-flash-lite-preview"

const _PROVIDER_HINTS := [
	# local
	"Generates images on your own machine using Stable Diffusion.\n" +
	"torch and diffusers are NOT included in the standard install — run:\n" +
	"  pip install torch diffusers transformers accelerate\n" +
	"inside the plugin's .venv after the main install completes.\n" +
	"Fast with a CUDA GPU; very slow on CPU.",

	# gemini
	"Uses Google's Imagen API — no extra packages needed.\n" +
	"Requires your API key to have Imagen access enabled\n" +
	"(available on paid Google AI Studio tiers).",
]

var _api_key_field: LineEdit
var _model_flash_field: LineEdit
var _model_lite_field: LineEdit
var _image_provider_btn: OptionButton
var _provider_hint_label: Label
var _imagen_model_section: VBoxContainer
var _imagen_model_field: LineEdit
var _daily_limit_spin: SpinBox
var _rate_limit_spin: SpinBox
var _python_field: LineEdit


func _ready() -> void:
	title = "Genesis Engine Settings"
	min_size = Vector2(500, 560)
	unresizable = false
	close_requested.connect(hide)
	_build_ui()


func _build_ui() -> void:
	var margin = MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 14)
	margin.add_theme_constant_override("margin_right", 14)
	margin.add_theme_constant_override("margin_top", 12)
	margin.add_theme_constant_override("margin_bottom", 12)
	add_child(margin)

	var outer = VBoxContainer.new()
	margin.add_child(outer)

	var scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	outer.add_child(scroll)

	var form = VBoxContainer.new()
	form.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	form.add_theme_constant_override("separation", 4)
	scroll.add_child(form)

	# ── API & Authentication ─────────────────────────────────────────────────
	form.add_child(_section("API & Authentication"))

	form.add_child(_label("Gemini API Key"))
	var key_row = HBoxContainer.new()
	form.add_child(key_row)
	_api_key_field = LineEdit.new()
	_api_key_field.placeholder_text = "AIzaSy…"
	_api_key_field.secret = true
	_api_key_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	key_row.add_child(_api_key_field)
	var show_btn = Button.new()
	show_btn.text = "Show"
	show_btn.toggle_mode = true
	show_btn.toggled.connect(func(on): _api_key_field.secret = not on)
	key_row.add_child(show_btn)
	form.add_child(_hint(
		"Create a free key at aistudio.google.com → Get API key.\n" +
		"The key is stored in Godot's editor settings, never committed to git."
	))

	form.add_child(_gap())
	form.add_child(HSeparator.new())
	form.add_child(_gap())

	# ── Models ───────────────────────────────────────────────────────────────
	form.add_child(_section("AI Models"))
	form.add_child(_hint(
		"Enter any Gemini model ID. Find current IDs at:\n" +
		"aistudio.google.com → Model dropdown, or ai.google.dev/gemini-api/docs/models\n" +
		"Both fields can use the same model — the split allows using a faster/cheaper\n" +
		"model for code writing while a smarter one plans and reviews."
	))
	form.add_child(_gap())

	form.add_child(_label("Orchestrator model  —  used for planning, reviewing, and coordinating agents"))
	_model_flash_field = LineEdit.new()
	_model_flash_field.placeholder_text = DEFAULT_MODEL
	_model_flash_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	form.add_child(_model_flash_field)

	form.add_child(_gap())
	form.add_child(_label("Coder model  —  used for writing GDScript and executing each task"))
	_model_lite_field = LineEdit.new()
	_model_lite_field.placeholder_text = DEFAULT_MODEL
	_model_lite_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	form.add_child(_model_lite_field)

	form.add_child(_gap())
	form.add_child(HSeparator.new())
	form.add_child(_gap())

	# ── Image Generation ─────────────────────────────────────────────────────
	form.add_child(_section("Image Generation"))

	form.add_child(_label("Provider"))
	_image_provider_btn = OptionButton.new()
	for lbl in IMAGE_PROVIDER_LABELS:
		_image_provider_btn.add_item(lbl)
	_image_provider_btn.item_selected.connect(_on_provider_changed)
	form.add_child(_image_provider_btn)

	_provider_hint_label = _hint("")
	form.add_child(_provider_hint_label)

	# Imagen model — only shown when provider = gemini
	_imagen_model_section = VBoxContainer.new()
	_imagen_model_section.add_theme_constant_override("separation", 2)
	form.add_child(_imagen_model_section)
	_imagen_model_section.add_child(_gap())
	_imagen_model_section.add_child(_label("Imagen model ID"))
	_imagen_model_field = LineEdit.new()
	_imagen_model_field.placeholder_text = "imagen-4.0-fast-generate-001"
	_imagen_model_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_imagen_model_section.add_child(_imagen_model_field)
	_imagen_model_section.add_child(_hint(
		"Find available Imagen model IDs at cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images"
	))

	form.add_child(_gap())
	form.add_child(HSeparator.new())
	form.add_child(_gap())

	# ── Rate Limiting ────────────────────────────────────────────────────────
	form.add_child(_section("Rate Limiting"))
	form.add_child(_hint(
		"The backend tracks usage and pauses generation when limits are reached,\n" +
		"preventing unexpected charges on paid tiers.\n" +
		"Free tier: ~500 requests/day, 15 requests/minute."
	))
	form.add_child(_gap())

	var row1 = HBoxContainer.new()
	form.add_child(row1)
	var daily_lbl = _label("Daily call limit")
	daily_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row1.add_child(daily_lbl)
	_daily_limit_spin = _spinbox(1, 100_000, 50)
	_daily_limit_spin.custom_minimum_size.x = 120
	row1.add_child(_daily_limit_spin)

	var row2 = HBoxContainer.new()
	form.add_child(row2)
	var rate_lbl = _label("Requests per minute per key")
	rate_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row2.add_child(rate_lbl)
	_rate_limit_spin = _spinbox(1, 1000, 1)
	_rate_limit_spin.custom_minimum_size.x = 120
	row2.add_child(_rate_limit_spin)

	form.add_child(_gap())
	form.add_child(HSeparator.new())
	form.add_child(_gap())

	# ── Backend ──────────────────────────────────────────────────────────────
	form.add_child(_section("Backend"))
	form.add_child(_label("Python 3 executable"))
	var py_row = HBoxContainer.new()
	form.add_child(py_row)
	_python_field = LineEdit.new()
	_python_field.placeholder_text = "python3"
	_python_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	py_row.add_child(_python_field)
	var detect_btn = Button.new()
	detect_btn.text = "Auto-detect"
	detect_btn.pressed.connect(_on_autodetect_pressed)
	py_row.add_child(detect_btn)
	form.add_child(_hint(
		"Path to Python 3.10+ — either 'python3' (if on your PATH) or a full path\n" +
		"like /usr/bin/python3.11.  Changing this does not reinstall the .venv;\n" +
		"delete addons/genesis_bridge/backend/.venv and use the Setup panel to reinstall."
	))

	# ── Buttons ──────────────────────────────────────────────────────────────
	outer.add_child(_gap())
	outer.add_child(HSeparator.new())

	var btn_row = HBoxContainer.new()
	btn_row.alignment = BoxContainer.ALIGNMENT_END
	btn_row.add_theme_constant_override("separation", 8)
	outer.add_child(btn_row)

	var cancel_btn = Button.new()
	cancel_btn.text = "Cancel"
	cancel_btn.pressed.connect(hide)
	btn_row.add_child(cancel_btn)

	var save_btn = Button.new()
	save_btn.text = "Save & Restart Backend"
	save_btn.pressed.connect(_on_save_pressed)
	btn_row.add_child(save_btn)


# ── Public ───────────────────────────────────────────────────────────────────

## Fill all fields from current EditorSettings before calling popup_centered().
func load_settings() -> void:
	var s = EditorInterface.get_editor_settings()

	_api_key_field.text      = s.get_setting("genesis_bridge/gemini_api_key")
	_model_flash_field.text  = s.get_setting("genesis_bridge/model_flash")
	_model_lite_field.text   = s.get_setting("genesis_bridge/model_lite")
	_daily_limit_spin.value  = float(s.get_setting("genesis_bridge/gemini_daily_limit"))
	_rate_limit_spin.value   = float(s.get_setting("genesis_bridge/gemini_rate_limit"))
	_python_field.text       = s.get_setting("genesis_bridge/python_executable_path")
	_imagen_model_field.text = s.get_setting("genesis_bridge/imagen_model")

	var provider: String = s.get_setting("genesis_bridge/image_provider")
	var idx := IMAGE_PROVIDERS.find(provider)
	_image_provider_btn.selected = max(idx, 0)
	_on_provider_changed(max(idx, 0))


# ── Internal ─────────────────────────────────────────────────────────────────

func _on_provider_changed(index: int) -> void:
	_provider_hint_label.text = _PROVIDER_HINTS[index]
	_imagen_model_section.visible = (IMAGE_PROVIDERS[index] == "gemini")


func _on_autodetect_pressed() -> void:
	for candidate in ["python3", "python", "py"]:
		if OS.execute(candidate, ["--version"], []) == 0:
			_python_field.text = candidate
			return


func _on_save_pressed() -> void:
	var api_key = _api_key_field.text.strip_edges()
	if api_key.is_empty():
		_api_key_field.placeholder_text = "⚠ API key is required!"
		return

	# Use placeholder (default) when field is left blank
	var flash = _model_flash_field.text.strip_edges()
	if flash.is_empty():
		flash = DEFAULT_MODEL
	var lite = _model_lite_field.text.strip_edges()
	if lite.is_empty():
		lite = DEFAULT_MODEL

	var s = EditorInterface.get_editor_settings()
	s.set_setting("genesis_bridge/gemini_api_key",         api_key)
	s.set_setting("genesis_bridge/model_flash",            flash)
	s.set_setting("genesis_bridge/model_lite",             lite)
	s.set_setting("genesis_bridge/image_provider",         IMAGE_PROVIDERS[_image_provider_btn.selected])
	s.set_setting("genesis_bridge/imagen_model",           _imagen_model_field.text.strip_edges())
	s.set_setting("genesis_bridge/gemini_daily_limit",     int(_daily_limit_spin.value))
	s.set_setting("genesis_bridge/gemini_rate_limit",      int(_rate_limit_spin.value))
	s.set_setting("genesis_bridge/python_executable_path", _python_field.text.strip_edges())

	hide()
	settings_saved.emit()


# ── Widget helpers ────────────────────────────────────────────────────────────

func _section(text: String) -> Label:
	var lbl = Label.new()
	lbl.text = text
	lbl.add_theme_font_size_override("font_size", 12)
	lbl.add_theme_color_override("font_color", Color(0.55, 0.78, 1.0))
	return lbl


func _label(text: String) -> Label:
	var lbl = Label.new()
	lbl.text = text
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return lbl


func _hint(text: String) -> Label:
	var lbl = Label.new()
	lbl.text = text
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.add_theme_font_size_override("font_size", 10)
	lbl.add_theme_color_override("font_color", Color(0.52, 0.52, 0.52))
	return lbl


func _gap() -> Control:
	var c = Control.new()
	c.custom_minimum_size.y = 4
	return c


func _spinbox(min_v: float, max_v: float, step_v: float) -> SpinBox:
	var sb = SpinBox.new()
	sb.min_value = min_v
	sb.max_value = max_v
	sb.step = step_v
	sb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return sb
