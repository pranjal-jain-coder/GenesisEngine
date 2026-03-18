@tool
extends PanelContainer

var task_data: Dictionary = {}

var status_icon: TextureRect
var description_label: Label
var description_edit: LineEdit
var status_colors = {
	"PENDING": Color.GRAY,
	"IN_PROGRESS": Color.CORNFLOWER_BLUE,
	"COMPLETED": Color.GREEN,
	"FAILED": Color.RED
}

func _ready():
	var hbox = HBoxContainer.new()
	add_child(hbox)
	
	status_icon = TextureRect.new()
	status_icon.custom_minimum_size = Vector2(16, 16)
	status_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	hbox.add_child(status_icon)
	
	description_label = Label.new()
	description_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	description_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	description_label.mouse_filter = Control.MOUSE_FILTER_PASS
	description_label.gui_input.connect(_on_description_gui_input)
	hbox.add_child(description_label)
	
	# In-place editor (hidden by default)
	description_edit = LineEdit.new()
	description_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	description_edit.visible = false
	description_edit.text_submitted.connect(_on_edit_submitted)
	description_edit.focus_exited.connect(_on_edit_cancelled)
	hbox.add_child(description_edit)
	
	# Add some margin
	var margin = MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 5)
	margin.add_theme_constant_override("margin_right", 5)
	margin.add_theme_constant_override("margin_top", 5)
	margin.add_theme_constant_override("margin_bottom", 5)
	
	remove_child(hbox)
	margin.add_child(hbox)
	add_child(margin)

func setup(data: Dictionary):
	task_data = data
	description_label.text = data.get("description", "Unknown Task")
	description_label.tooltip_text = "Double-click to edit"
	description_edit.text = data.get("description", "")
	set_status(data.get("status", "PENDING"))

func set_status(status: String):
	status = status.to_upper()
	
	# Try to get editor icons if in editor
	var icon_name = "Stop" # Default
	var color = Color.GRAY
	
	match status:
		"PENDING":
			icon_name = "GuiRadioUnchecked"
			color = Color.GRAY
		"IN_PROGRESS":
			icon_name = "ArrowRight"
			color = Color.CORNFLOWER_BLUE
		"COMPLETED":
			icon_name = "StatusSuccess"
			color = Color.GREEN
		"FAILED":
			icon_name = "StatusError"
			color = Color.RED
	
	# Attempt to load icon from theme if available, else fallback
	if Engine.is_editor_hint():
		# This might fail if not in the tree yet, but usually okay
		# We can use a trick to get the base control's theme
		if has_theme_icon(icon_name, "EditorIcons"):
			status_icon.texture = get_theme_icon(icon_name, "EditorIcons")
	
	status_icon.modulate = color
	
	if status == "COMPLETED":
		description_label.modulate = Color(1, 1, 1, 0.5)
	elif status == "IN_PROGRESS":
		description_label.modulate = Color.WHITE
	else:
		description_label.modulate = Color.WHITE

func _on_description_gui_input(event: InputEvent):
	if event is InputEventMouseButton and event.double_click and event.button_index == MOUSE_BUTTON_LEFT:
		_start_editing()

func _start_editing():
	description_label.visible = false
	description_edit.visible = true
	description_edit.text = task_data.get("description", "")
	description_edit.grab_focus()
	description_edit.select_all()

func _on_edit_submitted(new_text: String):
	if new_text != task_data.get("description", ""):
		task_data["description"] = new_text # Optimistic update
		description_label.text = new_text
		_submit_update(new_text)
	
	_stop_editing()

func _on_edit_cancelled():
	_stop_editing()

func _stop_editing():
	description_edit.visible = false
	description_label.visible = true

func _submit_update(new_description: String):
	# Find bridge client by traversing up
	var parent = get_parent()
	while parent:
		if parent.name == "GenesisEngine" and parent.has_method("update_task"):
			parent.update_task(task_data.get("id"), new_description)
			break
		parent = parent.get_parent()
		if not parent:
			print("TaskItem: Could not find GenesisEngine root")
