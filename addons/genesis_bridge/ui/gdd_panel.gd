@tool
extends PanelContainer

# GDD Panel - Dynamically displays whatever the LLM generates

var current_gdd: Dictionary = {}

@onready var scroll: ScrollContainer
@onready var content_vbox: VBoxContainer

func _ready() -> void:
	_build_ui()
	load_template()

func _build_ui() -> void:
	custom_minimum_size = Vector2(300, 400)
	
	var vbox = VBoxContainer.new()
	vbox.set_anchors_preset(Control.PRESET_FULL_RECT)
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vbox.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(vbox)
	
	# Header
	var title_label = Label.new()
	title_label.text = "Game Design Document"
	title_label.add_theme_font_size_override("font_size", 16)
	vbox.add_child(title_label)
	
	var separator = HSeparator.new()
	vbox.add_child(separator)
	
	# Scrollable content
	scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vbox.add_child(scroll)
	
	content_vbox = VBoxContainer.new()
	content_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(content_vbox)

	# Edit Mode Controls
	var edit_hbox = HBoxContainer.new()
	edit_hbox.alignment = BoxContainer.ALIGNMENT_END
	vbox.add_child(edit_hbox)
	
	edit_btn = Button.new()
	edit_btn.text = "Edit GDD"
	edit_btn.toggle_mode = true
	edit_btn.toggled.connect(_on_edit_toggled)
	edit_hbox.add_child(edit_btn)
	
	save_btn = Button.new()
	save_btn.text = "Save Changes"
	save_btn.disabled = true
	save_btn.pressed.connect(_on_save_pressed)
	edit_hbox.add_child(save_btn)

var edit_mode: bool = false
var editable_fields: Dictionary = {} # Map field name -> Control
var edit_btn: Button
var save_btn: Button

func _on_edit_toggled(toggled: bool):
	edit_mode = toggled
	save_btn.disabled = !edit_mode
	_refresh_display()

func _on_save_pressed():
	# Gather data from editable fields
	var new_gdd = current_gdd.duplicate(true)
	
	for key in editable_fields:
		var control = editable_fields[key]
		if control is TextEdit:
			new_gdd[key] = control.text
		elif control is LineEdit:
			new_gdd[key] = control.text
			
	# Update local and send to backend
	current_gdd = new_gdd
	_refresh_display() # Switch back to view mode? Or stay in edit?
	
	# Find bridge client to send update
	var parent = get_parent()
	while parent:
		if parent.name == "GenesisEngine" and parent.has_method("update_gdd"):
			parent.update_gdd(current_gdd)
			break
		parent = parent.get_parent()
		
	# edit_btn.button_pressed = false # Optional: Exit edit mode on save

func update_gdd(gdd_data: Dictionary) -> void:
	"""Update display with whatever the LLM generated."""
	current_gdd = gdd_data
	_refresh_display()

func _refresh_display() -> void:
	"""Dynamically render all GDD content."""
	# Clear existing content
	for child in content_vbox.get_children():
		child.queue_free()
	editable_fields.clear()
	
	if current_gdd.is_empty():
		var empty_label = Label.new()
		empty_label.text = "No GDD created yet. Start chatting to generate one!"
		content_vbox.add_child(empty_label)
		return
	
	# Helper to decide render mode
	var _render_field = func(label: String, key: String, multiline: bool = true):
		if edit_mode:
			_add_section_header(label)
			var edit
			if multiline:
				edit = TextEdit.new()
				edit.custom_minimum_size.y = 100
				edit.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
			else:
				edit = LineEdit.new()
			
			edit.text = str(current_gdd.get(key, ""))
			content_vbox.add_child(edit)
			editable_fields[key] = edit
		else:
			if current_gdd.has(key) and str(current_gdd[key]) != "":
				_add_section(label, str(current_gdd[key]))

	# Title
	if edit_mode:
		_add_section_header("Title")
		var title_edit = LineEdit.new()
		title_edit.text = current_gdd.get("title", "")
		content_vbox.add_child(title_edit)
		editable_fields["title"] = title_edit
	elif current_gdd.has("title") and current_gdd["title"] != "":
		_add_header(current_gdd["title"])
	
	# Main Fields
	_render_field.call("🎮 Genre", "genre", false)
	_render_field.call("👥 Target Audience", "target_audience", false)
	_render_field.call("🔄 Core Gameplay Loop", "core_loop", true)
	_render_field.call("📖 Story", "story", true)
	_render_field.call("🎨 Theme", "theme", false)
	
	# Mechanics (Complex handling, for now just JSON text edit if in edit mode, or simple display)
	if edit_mode:
		_add_section_header("⚙️ Mechanics (JSON)")
		var mech_edit = TextEdit.new()
		mech_edit.custom_minimum_size.y = 150
		mech_edit.text = JSON.stringify(current_gdd.get("mechanics", []), "\t")
		content_vbox.add_child(mech_edit)
		# Special handling needed to parse back, for now let's skip complex objects in simple edit
		var label = Label.new()
		label.text = "(Complex objects like Mechanics are read-only in this raw editor for now)"
		label.add_theme_color_override("font_color", Color.GRAY)
		content_vbox.add_child(label)
	elif current_gdd.has("mechanics") and current_gdd["mechanics"].size() > 0:
		_add_section_header("⚙️ Mechanics (" + str(current_gdd["mechanics"].size()) + ")")
		for mech in current_gdd["mechanics"]:
			var mech_text = "• " + mech.get("name", "Unnamed")
			if mech.has("complexity_score"):
				mech_text += " [Complexity: " + str(mech["complexity_score"]) + "/10]"
			_add_text(mech_text)
			if mech.has("description") and mech["description"] != "":
				_add_text("  " + mech["description"], true)
	
	# Other Fields
	_render_field.call("🎮 Controls", "controls", true)
	_render_field.call("📈 Progression", "progression", true)
	_render_field.call("🔊 Audio Style", "audio_style", true)
	
	# Lists (Levels, Enemies, Items) - Skip editing for now to keep it simple, or add note
	if not edit_mode:
		if current_gdd.has("levels") and current_gdd["levels"].size() > 0:
			_add_section_header("🗺️ Levels")
			for level in current_gdd["levels"]: _add_text("• " + level)
			
		if current_gdd.has("enemies") and current_gdd["enemies"].size() > 0:
			_add_section_header("👾 Enemies")
			for enemy in current_gdd["enemies"]: _add_text("• " + enemy)

		if current_gdd.has("items") and current_gdd["items"].size() > 0:
			_add_section_header("💎 Items")
			for item in current_gdd["items"]: _add_text("• " + item)

		if current_gdd.has("folder_structure") and current_gdd["folder_structure"].size() > 0:
			_add_section_header("📁 Folder Structure")
			for folder in current_gdd["folder_structure"]: _add_text("• " + folder)

func _add_header(text: String) -> void:
	var label = Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 18)
	label.add_theme_color_override("font_color", Color.CORNFLOWER_BLUE)
	content_vbox.add_child(label)
	_add_spacer(5)

func _add_section_header(text: String) -> void:
	_add_spacer(10)
	var label = Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 14)
	content_vbox.add_child(label)
	_add_spacer(3)

func _add_section(header: String, content: String) -> void:
	_add_section_header(header)
	_add_text(content)

func _add_text(text: String, indent: bool = false) -> void:
	var label = RichTextLabel.new()
	label.bbcode_enabled = true
	label.fit_content = true
	label.scroll_active = false
	label.selection_enabled = true
	label.bbcode_text = text
	label.custom_minimum_size.y = 20
	if indent:
		label.add_theme_constant_override("margin_left", 20)
	content_vbox.add_child(label)

func _add_spacer(height: int) -> void:
	var spacer = Control.new()
	spacer.custom_minimum_size.y = height
	content_vbox.add_child(spacer)

func load_template() -> void:
	"""Load empty template on startup."""
	var template_data = {
		"title": "",
		"genre": "",
		"target_audience": "",
		"core_loop": "",
		"story": "",
		"theme": "",
		"mechanics": [],
		"controls": "",
		"progression": "",
		"art_style": {
			"visual_style": "",
			"color_palette": [],
			"perspective": ""
		},
		"audio_style": "",
		"levels": [],
		"enemies": [],
		"items": [],
		"folder_structure": []
	}
	update_gdd(template_data)

func clear() -> void:
	current_gdd = {}
	_refresh_display()
