@tool
extends Control

# Genesis Engine Chat Dock UI
# Provides a chat interface for interacting with AI agents

const GDDPanel = preload("res://addons/genesis_bridge/ui/gdd_panel.gd")
const TaskItem = preload("res://addons/genesis_bridge/ui/task_item.gd")

signal message_sent(mode: String, message: String)

@onready var message_container: VBoxContainer
@onready var scroll_container: ScrollContainer
@onready var input_field: LineEdit
@onready var send_button: Button
@onready var mode_selector: OptionButton
@onready var gdd_panel: Control

var bridge_client: Node = null
var loading_message: PanelContainer = null
var loading_timer: Timer = null
var loading_dots: int = 0
var execution_status_label: Label = null
var execution_loading_base_text: String = ""

# Tracks the current pending asset review so feedback / option selection can be sent
var pending_asset_review: Dictionary = {}

# Reference to the currently open review dialog (if any)
var _review_dialog: Window = null

@onready var execution_ui: VBoxContainer
@onready var task_list: VBoxContainer
@onready var chat_ui_elements: Array[Control] = [] # To toggle visibility
@onready var gen_btn: Button
@onready var exec_btn: Button
@onready var feedback_btn: Button

func _ready() -> void:
	_build_ui()
	
func _build_ui() -> void:
	# Main layout
	var margin = MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 8)
	margin.add_theme_constant_override("margin_right", 8)
	margin.add_theme_constant_override("margin_top", 8)
	margin.add_theme_constant_override("margin_bottom", 8)
	add_child(margin)
	
	var vbox = VBoxContainer.new()
	vbox.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_child(vbox)
	
	# Create split container for chat and GDD panel
	var hsplit = HSplitContainer.new()
	hsplit.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vbox.add_child(hsplit)
	
	# Left side: Chat/Execution interface
	var left_vbox = VBoxContainer.new()
	left_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left_vbox.custom_minimum_size.x = 300
	hsplit.add_child(left_vbox)
	
	# Header with mode selector and status
	var header = HBoxContainer.new()
	left_vbox.add_child(header)
	
	var mode_label = Label.new()
	mode_label.text = "Mode:"
	header.add_child(mode_label)
	
	mode_selector = OptionButton.new()
	mode_selector.add_item("Planning", 0)
	mode_selector.add_item("Execution", 1)
	mode_selector.custom_minimum_size = Vector2(120, 0)
	mode_selector.item_selected.connect(_on_mode_changed)
	header.add_child(mode_selector)
	
	var separator1 = HSeparator.new()
	left_vbox.add_child(separator1)
	
	### CHAT UI ###
	scroll_container = ScrollContainer.new()
	scroll_container.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll_container.follow_focus = true
	left_vbox.add_child(scroll_container)
	chat_ui_elements.append(scroll_container)
	
	message_container = VBoxContainer.new()
	message_container.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll_container.add_child(message_container)
	
	var separator2 = HSeparator.new()
	left_vbox.add_child(separator2)
	chat_ui_elements.append(separator2)
	
	var input_box = HBoxContainer.new()
	left_vbox.add_child(input_box)
	chat_ui_elements.append(input_box)
	
	input_field = LineEdit.new()
	input_field.placeholder_text = "Type your message..."
	input_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input_field.text_submitted.connect(_on_input_submitted)
	input_box.add_child(input_field)
	
	send_button = Button.new()
	send_button.text = "Send"
	send_button.pressed.connect(_on_send_pressed)
	input_box.add_child(send_button)
	
	### EXECUTION UI ###
	execution_ui = VBoxContainer.new()
	execution_ui.size_flags_vertical = Control.SIZE_EXPAND_FILL
	execution_ui.visible = false
	left_vbox.add_child(execution_ui)
	# Move execution_ui up to reuse space
	left_vbox.move_child(execution_ui, left_vbox.get_child_count() - 3) 
	
	var task_scroll = ScrollContainer.new()
	task_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	task_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	execution_ui.add_child(task_scroll)
	
	task_list = VBoxContainer.new()
	task_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	task_scroll.add_child(task_list)
	
	var controls_box = HBoxContainer.new()
	execution_ui.add_child(controls_box)
	
	gen_btn = Button.new()
	gen_btn.text = "Generate Tasks"
	gen_btn.pressed.connect(_on_generate_tasks_pressed)
	controls_box.add_child(gen_btn)
	
	exec_btn = Button.new()
	exec_btn.text = "Start Next Task"
	exec_btn.pressed.connect(_on_execute_next_pressed)
	controls_box.add_child(exec_btn)
	
	feedback_btn = Button.new()
	feedback_btn.text = "Regenerate"
	feedback_btn.pressed.connect(_on_regenerate_pressed)
	feedback_btn.visible = false # Hidden initially
	controls_box.add_child(feedback_btn)

	var add_task_btn = Button.new()
	add_task_btn.text = "+"
	add_task_btn.tooltip_text = "Add New Task"
	add_task_btn.pressed.connect(_on_add_task_pressed)
	controls_box.add_child(add_task_btn)

	var history_btn = Button.new()
	history_btn.text = "History"
	history_btn.pressed.connect(_on_history_pressed)
	controls_box.add_child(history_btn)

	# Execution loading indicator
	var loading_container = MarginContainer.new()
	loading_container.add_theme_constant_override("margin_top", 10)
	loading_container.add_theme_constant_override("margin_bottom", 10)
	execution_ui.add_child(loading_container)
	
	var status_hbox = HBoxContainer.new()
	status_hbox.alignment = BoxContainer.ALIGNMENT_CENTER
	loading_container.add_child(status_hbox)

	var spinner_tex = TextureRect.new()
	if Engine.is_editor_hint() and has_theme_icon("Progress1", "EditorIcons"):
		spinner_tex.texture = get_theme_icon("Progress1", "EditorIcons")
	status_hbox.add_child(spinner_tex)
	
	execution_status_label = Label.new()
	execution_status_label.text = "Working..."
	execution_status_label.add_theme_color_override("font_color", Color.LIGHT_GREEN)
	status_hbox.add_child(execution_status_label)
	
	loading_container.visible = false
	execution_status_label.set_meta("container", loading_container)

	# Add welcome message
	add_system_message("Genesis Engine initialized. Select a mode and start chatting!")
	
	# Right side: GDD Panel
	gdd_panel = GDDPanel.new()
	gdd_panel.custom_minimum_size.x = 300
	hsplit.add_child(gdd_panel)

func set_bridge_client(client: Node) -> void:
	bridge_client = client
	if bridge_client:
		# Connect to bridge client signals if available
		if bridge_client.has_signal("message_received"):
			bridge_client.message_received.connect(_on_message_received)

func _on_send_pressed() -> void:
	_send_message()

func _on_input_submitted(_text: String) -> void:
	_send_message()

func _send_message() -> void:
	var text = input_field.text.strip_edges()
	if text.is_empty():
		return
	
	# Only for planning mode now
	var mode = "planning"
	
	# Display user message
	add_user_message(text)
	
	# Show loading indicator
	_show_loading()
	
	# Send to backend via bridge client
	if bridge_client and bridge_client.has_method("send_chat_message"):
		bridge_client.send_chat_message(mode, text)
	
	# Emit signal
	message_sent.emit(mode, text)
	
	# Clear input
	input_field.text = ""

func _on_mode_changed(index: int) -> void:
	var is_execution = (index == 1)
	
	# Toggle visibility
	for el in chat_ui_elements:
		el.visible = !is_execution
	
	execution_ui.visible = is_execution
	
	if is_execution:
		# Maybe trigger a refresh of tasks if needed, or just show empty state
		pass
	else:
		# Clear messages when switching back to planning provided we want a fresh start or keep history?
		# Original code cleared it. Let's keep it cleared for now.
		for child in message_container.get_children():
			child.queue_free()
			
	var mode_name = "Planning" if index == 0 else "Execution"
	# add_system_message("Switched to %s mode." % mode_name) # No message log in execution mode

### EXECUTION ACTIONS ###

func _set_execution_busy(busy: bool, message: String = ""):
	var buttons = [gen_btn, exec_btn, feedback_btn]
	for btn in buttons:
		if is_instance_valid(btn):
			btn.disabled = busy
			
	if busy:
		_show_loading() # Use existing loading for now, or custom execution message
		# We can customize the loading label text if we expose it
		execution_loading_base_text = message if message != "" else "Generating..."
		if message != "":
			if is_instance_valid(loading_message):
				var loading_label = loading_message.find_child("LoadingLabel", true, false)
				if is_instance_valid(loading_label):
					loading_label.text = message
				
		if is_instance_valid(execution_status_label):
			if execution_status_label.has_meta("container"):
				var container = execution_status_label.get_meta("container")
				if is_instance_valid(container):
					container.visible = true
			execution_status_label.text = execution_loading_base_text
	else:
		_hide_loading()
		if is_instance_valid(execution_status_label):
			if execution_status_label.has_meta("container"):
				var container = execution_status_label.get_meta("container")
				if is_instance_valid(container):
					container.visible = false

func _on_generate_tasks_pressed():
	if bridge_client and bridge_client.has_method("send_message"):
		_set_tasks_loading("Generating Plan...")
		_set_execution_busy(true, "Generating Plan...")
		bridge_client.send_message({
			"type": "chat",
			"mode": "execution",
			"action": "generate_tasks"
		})

func _on_execute_next_pressed():
	if bridge_client and bridge_client.has_method("send_message"):
		_set_execution_busy(true, "Executing Task...")
		bridge_client.send_message({
			"type": "chat",
			"mode": "execution",
			"action": "execute_next_task"
		})

func _on_regenerate_pressed():
	# Simple dialog or just use input field if we wanted to reuse it, but simpler to just popup a dialog
	# For now, let's use a simple confirmation dialog with a line edit
	var dialog = ConfirmationDialog.new()
	dialog.title = "Regenerate Tasks"
	var vbox = VBoxContainer.new()
	dialog.add_child(vbox)
	var label = Label.new()
	label.text = "Enter feedback for regeneration:"
	vbox.add_child(label)
	var line_edit = LineEdit.new()
	line_edit.custom_minimum_size.x = 300
	vbox.add_child(line_edit)
	
	dialog.confirmed.connect(func():
		var feedback = line_edit.text
		if bridge_client and bridge_client.has_method("send_message"):
			bridge_client.send_message({
				"type": "chat",
				"mode": "execution",
				"action": "regenerate_tasks",
				"feedback": feedback
			})
			_set_tasks_loading("Regenerating...")
		dialog.queue_free()
	)
	add_child(dialog)
	dialog.popup_centered()

func _on_history_pressed():
	if bridge_client and bridge_client.has_method("send_message"):
		_set_execution_busy(true, "Fetching History...")
		bridge_client.send_message({
			"type": "chat",
			"mode": "execution",
			"action": "get_task_history"
		})

func _show_history_dialog(commits: Array) -> void:
	var dialog = ConfirmationDialog.new()
	dialog.title = "Task History (Select to Revert)"
	dialog.min_size = Vector2(500, 300)
	
	var item_list = ItemList.new()
	item_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	item_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	dialog.add_child(item_list)
	
	var commit_hashes = []
	for commit in commits:
		var txt = commit.get("message", "Unknown commit")
		item_list.add_item(txt)
		commit_hashes.append(commit.get("hash", ""))
	
	dialog.confirmed.connect(func():
		var selected = item_list.get_selected_items()
		if selected.size() > 0:
			var idx = selected[0]
			var hash_to_revert = commit_hashes[idx]
			if bridge_client and bridge_client.has_method("send_message"):
				_set_execution_busy(true, "Reverting...")
				bridge_client.send_message({
					"type": "chat",
					"mode": "execution",
					"action": "revert_project",
					"commit_hash": hash_to_revert
				})
		dialog.queue_free()
	)
	
	dialog.canceled.connect(func():
		dialog.queue_free()
	)
	
	add_child(dialog)
	dialog.popup_centered()

func update_task(task_id: String, description: String = "", status: String = ""):
	"""Called by TaskItem to update a task."""
	if bridge_client and bridge_client.has_method("send_message"):
		var payload = {
			"type": "chat",
			"mode": "execution",
			"action": "update_task",
			"task_id": task_id
		}
		if description != "":
			payload["description"] = description
		if status != "":
			payload["status"] = status
			
		bridge_client.send_message(payload)

func update_gdd(gdd_data: Dictionary):
	"""Called by GDDPanel to update backend GDD."""
	if bridge_client and bridge_client.has_method("send_message"):
		_set_execution_busy(true, "Updating GDD...") # Added this line
		bridge_client.send_message({
			"type": "chat",
			"mode": "execution",
			"action": "update_gdd",
			"gdd": gdd_data
		})
func _on_add_task_pressed():
	if bridge_client and bridge_client.has_method("send_message"):
		_set_execution_busy(true, "Adding Task...") # Added this line
		bridge_client.send_message({
			"type": "chat",
			"mode": "execution",
			"action": "add_task",
			"description": "New Task"
		})
		# Optimistic UI update or wait for list refresh
		# We'll wait for list refresh to keep it simple and synced
func _set_tasks_loading(msg: String):
	# Clear list and show loading
	for child in task_list.get_children():
		child.queue_free()
	var label = Label.new()
	label.text = msg
	task_list.add_child(label)

func _update_task_list(tasks: Array):
	for child in task_list.get_children():
		child.queue_free()
		
	# Toggle buttons based on task existence
	if tasks.size() > 0:
		gen_btn.visible = false
		feedback_btn.visible = true
	else:
		gen_btn.visible = true
		feedback_btn.visible = false
		
	for task in tasks:
		var item = TaskItem.new()
		task_list.add_child(item)
		item.setup(task)

### MESSAGE HANDLING ###

func add_user_message(text: String) -> void:
	_add_message("You", text, Color.CORNFLOWER_BLUE)

func add_agent_message(text: String) -> void:
	_add_message("Agent", text, Color.LIGHT_GREEN)

func add_system_message(text: String) -> void:
	_add_message("System", text, Color.GRAY)

func add_error_message(text: String) -> void:
	_add_message("Error", text, Color.ORANGE_RED)

func _add_message(sender: String, text: String, color: Color) -> void:
	var message_panel = PanelContainer.new()
	message_container.add_child(message_panel)
	
	var message_vbox = VBoxContainer.new()
	message_panel.add_child(message_vbox)
	
	# Sender label
	var sender_label = Label.new()
	sender_label.text = sender
	sender_label.add_theme_color_override("font_color", color)
	var font = sender_label.get_theme_font("bold_font", "Label")
	if font:
		sender_label.add_theme_font_override("font", font)
	message_vbox.add_child(sender_label)
	
	# Message text
	var message_label = RichTextLabel.new()
	message_label.bbcode_enabled = true
	message_label.fit_content = true
	message_label.scroll_active = false
	message_label.selection_enabled = true
	message_label.context_menu_enabled = true
	# Convert markdown-style formatting to BBCode
	var formatted_text = _convert_markdown_to_bbcode(text)
	message_label.bbcode_text = formatted_text
	message_label.custom_minimum_size.y = 20
	message_vbox.add_child(message_label)
	
	# Auto-scroll to bottom.
	# NOTE: No await here — awaiting in a @tool script suspends the coroutine.
	# If a filesystem scan triggers a script reload mid-await, the resumed
	# continuation accesses freed objects → SIGSEGV (signal 11 crash).
	if is_instance_valid(scroll_container):
		scroll_container.scroll_vertical = int(scroll_container.get_v_scroll_bar().max_value)

func _on_message_received(message: Dictionary) -> void:
	# Handle incoming messages from backend
	var type = message.get("type")
	
	if type == "chat_response":
		# Legacy / Planning mode
		if message.has("content"):
			var content = message["content"]
			if content != "":
				_hide_loading()
				add_agent_message(content)
		elif message.has("error"):
			_hide_loading()
			add_error_message(message["error"])
			
	elif type == "task_list":
		_set_execution_busy(false)
		var task_array = message.get("tasks", [])
		_update_task_list(task_array)
		
		# Auto-switch to execution mode if we just loaded an existing project with tasks
		if task_array.size() > 0 and mode_selector.selected == 0:
			mode_selector.select(1)
			_on_mode_changed(1)
		
	elif type == "task_started":
		# Could highlight specific task
		pass
		
	elif type == "task_completed":
		_set_execution_busy(false)
		_update_task_list(message.get("tasks", []))
		# Rescan filesystem and reload the open scene so the editor reflects
		# newly written .tscn / .gd / asset files without requiring manual Ctrl+R.
		# NOTE: No await here — awaiting in a @tool script suspends the coroutine
		# and can cause SIGSEGV crashes when a filesystem scan triggers a script reload.
		if Engine.is_editor_hint():
			var edited_scene = EditorInterface.get_edited_scene_root()
			var scene_path = ""
			if is_instance_valid(edited_scene):
				scene_path = edited_scene.scene_file_path
			var fs = EditorInterface.get_resource_filesystem()
			fs.scan()
			if scene_path != "":
				fs.filesystem_changed.connect(
					func(): EditorInterface.reload_scene_from_path(scene_path),
					CONNECT_ONE_SHOT
				)

	elif type == "error":
		_set_execution_busy(false)
		add_error_message(message.get("content", "Unknown Error"))
		
	elif type == "task_history":
		_set_execution_busy(false)
		_show_history_dialog(message.get("commits", []))
		
	elif type == "project_reverted":
		_set_execution_busy(false)
		add_system_message(message.get("content", "Project successfully reverted."))
		_update_task_list(message.get("tasks", []))
		# Rescan filesystem and reload open scenes so the editor reflects
		# the reverted files on disk (git reset --hard changed .tscn files etc.)
		# NOTE: No await here — awaiting in a @tool script suspends the coroutine
		# and can cause SIGSEGV crashes when a filesystem scan triggers a script reload.
		if Engine.is_editor_hint():
			var edited_scene = EditorInterface.get_edited_scene_root()
			var scene_path = ""
			if is_instance_valid(edited_scene):
				scene_path = edited_scene.scene_file_path
			var fs = EditorInterface.get_resource_filesystem()
			fs.scan()
			# Reload the open scene once the scan completes. CONNECT_ONE_SHOT
			# auto-disconnects after the first emit so no manual cleanup needed.
			if scene_path != "":
				fs.filesystem_changed.connect(
					func(): EditorInterface.reload_scene_from_path(scene_path),
					CONNECT_ONE_SHOT
				)
		
	elif type == "asset_review_request":
		_set_execution_busy(false)
		pending_asset_review = message
		_show_asset_review_dialog(message)
		
	elif type == "task_verification_request":
		_set_execution_busy(false)
		_show_verification_dialog(message)

	elif type == "log":
		# Live asset pipeline logs and system status
		# If we are in execution mode and loading, update the base text
		if execution_status_label and execution_status_label.is_visible_in_tree():
			execution_loading_base_text = message.get("message", "Working...")
			execution_status_label.text = execution_loading_base_text
		else:
			add_system_message(message.get("message", ""))

	# Handle GDD updates
	if message.has("gdd") or (type == "gdd_update" and message.has("gdd")):
		var gdd_data = message.get("gdd", {})
		if gdd_panel and gdd_panel.has_method("update_gdd"):
			gdd_panel.update_gdd(gdd_data)
			# Do not spam system message on every update if it's frequent/auto, but fine for now
			# add_system_message("GDD updated successfully!")

func _convert_markdown_to_bbcode(text: String) -> String:
	"""Convert common markdown formatting to BBCode."""
	var result = text
	
	# Convert bold: **text** or __text__ to [b]text[/b]
	var bold_regex = RegEx.new()
	bold_regex.compile("\\*\\*(.+?)\\*\\*|__(.+?)__")
	for match in bold_regex.search_all(result):
		var matched_text = match.get_string(1) if match.get_string(1) != "" else match.get_string(2)
		result = result.replace(match.get_string(), "[b]" + matched_text + "[/b]")
	
	# Convert italic: *text* or _text_ to [i]text[/i]
	var italic_regex = RegEx.new()
	italic_regex.compile("\\*(.+?)\\*|_(.+?)_")
	for match in italic_regex.search_all(result):
		var matched_text = match.get_string(1) if match.get_string(1) != "" else match.get_string(2)
		result = result.replace(match.get_string(), "[i]" + matched_text + "[/i]")
	
	# Convert code: `text` to [code]text[/code]
	var code_regex = RegEx.new()
	code_regex.compile("`(.+?)`")
	for match in code_regex.search_all(result):
		result = result.replace(match.get_string(), "[code]" + match.get_string(1) + "[/code]")
	
	# Convert headers: # Header to larger font
	var header_regex = RegEx.new()
	header_regex.compile("^#{1,3}\\s+(.+)$")
	for match in header_regex.search_all(result):
		result = result.replace(match.get_string(), "[font_size=18][b]" + match.get_string(1) + "[/b][/font_size]")
	
	# Convert bullet points: - item or * item
	result = result.replace("\n- ", "\n• ")
	result = result.replace("\n* ", "\n• ")
	
	return result

func _show_loading() -> void:
	"""Show animated loading indicator."""
	if not loading_timer:
		# Create timer for animation if it doesn't exist
		loading_timer = Timer.new()
		loading_timer.wait_time = 0.5
		loading_timer.timeout.connect(_update_loading_animation)
		add_child(loading_timer)
		loading_timer.start()
		loading_dots = 0

	if is_instance_valid(loading_message):
		return  # Already showing

	loading_message = PanelContainer.new()
	message_container.add_child(loading_message)

	var message_vbox = VBoxContainer.new()
	loading_message.add_child(message_vbox)

	# Sender label
	var sender_label = Label.new()
	sender_label.text = "Agent"
	sender_label.add_theme_color_override("font_color", Color.LIGHT_GREEN)
	message_vbox.add_child(sender_label)

	# Loading text
	var loading_label = Label.new()
	loading_label.text = "Generating"
	loading_label.name = "LoadingLabel"
	message_vbox.add_child(loading_label)
	# NOTE: No `await get_tree().process_frame` here — awaiting in a @tool script
	# suspends the coroutine. If a filesystem scan (triggered by write_script or
	# create_scene) causes a script reload mid-await, the resumed continuation
	# accesses freed objects → SIGSEGV (signal 11 crash).

func _hide_loading() -> void:
	"""Hide loading indicator."""
	if is_instance_valid(loading_message):
		loading_message.queue_free()
		loading_message = null

	if is_instance_valid(loading_timer):
		loading_timer.stop()
		loading_timer.queue_free()
		loading_timer = null
	
	loading_dots = 0

func _update_loading_animation() -> void:
	"""Animate the loading dots."""
	loading_dots = (loading_dots + 1) % 4
	var dots = ".".repeat(loading_dots)
	
	if is_instance_valid(loading_message):
		var loading_label = loading_message.find_child("LoadingLabel", true, false)
		if loading_label:
			loading_label.text = "Generating" + dots

	if execution_status_label and execution_status_label.visible:
		execution_status_label.text = execution_loading_base_text + dots


### ASSET REVIEW DIALOG ###

func _show_asset_review_dialog(data: Dictionary) -> void:
	"""Show a popup dialog to review acquired asset options."""
	# Close any existing review dialog before opening a new one.
	# queue_free() is deferred, so without this guard a second exclusive
	# Window can be added while the first is still in the tree → crash.
	if is_instance_valid(_review_dialog):
		_review_dialog.queue_free()
		_review_dialog = null

	var task_id = data.get("task_id", "")
	var asset = data.get("asset", {})
	var asset_name = asset.get("name", "asset")
	var options: Array = asset.get("options", [])

	# Build a single-option array from legacy non-options format
	if options.is_empty():
		var ap = asset.get("asset_path", asset.get("godot_path", ""))
		if ap != "":
			options = [{"asset_path": ap, "godot_path": asset.get("godot_path", ""), "source": asset.get("source", ""), "index": 0}]

	var dialog = Window.new()
	_review_dialog = dialog
	dialog.title = "Review Asset: " + asset_name
	# Cap width so it never exceeds a sane size on smaller monitors
	dialog.min_size = Vector2i(min(480 * max(1, options.size()), 1400), 460)
	# Do NOT set exclusive = true — exclusive embedded Windows inside @tool
	# plugin docks can crash the editor when a second one is created while the
	# first is still alive (queue_free is deferred). Use always_on_top instead.
	dialog.always_on_top = true
	# Add to the editor's root control so it floats above all docks properly
	EditorInterface.get_base_control().add_child(dialog)

	# Handle the window's X / close button so it cleans up properly
	dialog.close_requested.connect(func():
		_review_dialog = null
		pending_asset_review = {}
		dialog.queue_free()
	)

	var root_margin = MarginContainer.new()
	root_margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	root_margin.add_theme_constant_override("margin_left", 12)
	root_margin.add_theme_constant_override("margin_right", 12)
	root_margin.add_theme_constant_override("margin_top", 12)
	root_margin.add_theme_constant_override("margin_bottom", 12)
	dialog.add_child(root_margin)

	var vbox = VBoxContainer.new()
	root_margin.add_child(vbox)

	var title_label = Label.new()
	title_label.text = "Choose an option for \"%s\" or provide feedback to regenerate:" % asset_name
	title_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vbox.add_child(title_label)

	# Options row
	var options_hbox = HBoxContainer.new()
	options_hbox.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vbox.add_child(options_hbox)

	for i in range(options.size()):
		var opt = options[i]
		var opt_vbox = VBoxContainer.new()
		opt_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		options_hbox.add_child(opt_vbox)

		var abs_path = opt.get("asset_path", "")
		var ext = abs_path.get_extension().to_lower() if abs_path != "" else ""
		var is_audio = ext in ["wav", "ogg", "mp3"]

		if is_audio:
			# Audio preview — show filename and a play/stop toggle button
			var audio_name_label = Label.new()
			audio_name_label.text = abs_path.get_file()
			audio_name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			audio_name_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			audio_name_label.custom_minimum_size = Vector2(200, 0)
			audio_name_label.size_flags_vertical = Control.SIZE_EXPAND_FILL
			audio_name_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
			opt_vbox.add_child(audio_name_label)

			var player = AudioStreamPlayer.new()
			opt_vbox.add_child(player)

			# Load audio bytes directly — avoids needing a .import file
			if abs_path != "" and FileAccess.file_exists(abs_path):
				var bytes = FileAccess.get_file_as_bytes(abs_path)
				var stream = null
				if ext == "wav":
					stream = AudioStreamWAV.load_from_buffer(bytes)
				elif ext == "ogg":
					stream = AudioStreamOggVorbis.load_from_buffer(bytes)
				elif ext == "mp3":
					stream = AudioStreamMP3.load_from_buffer(bytes)
				if stream:
					player.stream = stream

			var play_btn = Button.new()
			play_btn.text = "▶  Play"
			play_btn.disabled = player.stream == null
			play_btn.pressed.connect(func():
				if player.playing:
					player.stop()
					play_btn.text = "▶  Play"
				else:
					player.play()
					play_btn.text = "⏹  Stop"
			)
			player.finished.connect(func(): play_btn.text = "▶  Play")
			opt_vbox.add_child(play_btn)
		else:
			# Image preview
			var tex_rect = TextureRect.new()
			tex_rect.custom_minimum_size = Vector2(200, 200)
			tex_rect.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			tex_rect.size_flags_vertical = Control.SIZE_EXPAND_FILL
			tex_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			tex_rect.expand_mode = TextureRect.EXPAND_FIT_WIDTH_PROPORTIONAL

			if abs_path != "" and FileAccess.file_exists(abs_path):
				var img = Image.load_from_file(abs_path)
				if img:
					tex_rect.texture = ImageTexture.create_from_image(img)
			opt_vbox.add_child(tex_rect)

		var source_label = Label.new()
		source_label.text = "Source: " + opt.get("source", "unknown")
		source_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		opt_vbox.add_child(source_label)

		var select_btn = Button.new()
		select_btn.text = "Select" if options.size() > 1 else "Approve"
		var capture_index = i
		select_btn.pressed.connect(func():
			_send_asset_feedback(task_id, "APPROVED", capture_index)
			_review_dialog = null
			pending_asset_review = {}
			dialog.queue_free()
			_set_execution_busy(true, "Continuing task...")
		)
		opt_vbox.add_child(select_btn)

	vbox.add_child(HSeparator.new())

	# Feedback / regenerate row
	var feedback_label = Label.new()
	feedback_label.text = "Or describe what you want instead:"
	vbox.add_child(feedback_label)

	var feedback_hbox = HBoxContainer.new()
	vbox.add_child(feedback_hbox)

	var feedback_input = LineEdit.new()
	feedback_input.placeholder_text = "e.g. make it more colourful, different style..."
	feedback_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	feedback_hbox.add_child(feedback_input)

	var regen_btn = Button.new()
	regen_btn.text = "Regenerate"
	regen_btn.pressed.connect(func():
		var fb = feedback_input.text.strip_edges()
		if fb.is_empty():
			return
		_send_asset_feedback(task_id, fb, -1)
		_review_dialog = null
		pending_asset_review = {}
		dialog.queue_free()
		_set_execution_busy(true, "Regenerating asset...")
	)
	feedback_hbox.add_child(regen_btn)

	dialog.popup_centered()


func _send_asset_feedback(task_id: String, feedback: String, selected_index: int) -> void:
	"""Send asset feedback to the backend."""
	if not bridge_client or not bridge_client.has_method("send_message"):
		return
	var payload = {
		"type": "chat",
		"mode": "execution",
		"action": "asset_feedback",
		"task_id": task_id,
		"feedback": feedback,
	}
	if selected_index >= 0:
		payload["selected_index"] = selected_index
	bridge_client.send_message(payload)

func _show_verification_dialog(data: Dictionary) -> void:
	"""Show a popup dialog asking the user to verify a task."""
	var task_id = data.get("task_id", "")
	var content = data.get("content", "Task finished. Please verify.")
	
	var dialog = ConfirmationDialog.new()
	dialog.title = "Verify Task"
	dialog.ok_button_text = "Task Verified & Working"
	dialog.cancel_button_text = "Report Issue"
	dialog.min_size = Vector2(400, 200)
	
	var vbox = VBoxContainer.new()
	dialog.add_child(vbox)
	
	var msg_label = Label.new()
	msg_label.text = content
	msg_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vbox.add_child(msg_label)
	
	var feedback_input = LineEdit.new()
	feedback_input.placeholder_text = "If something is wrong, describe it here..."
	feedback_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	feedback_input.visible = false
	vbox.add_child(feedback_input)
	
	# Logic to handle verification flow
	# Since ConfirmationDialog only has OK/Cancel, we hijack Cancel for "Report Issue"
	# To do this cleanly, we need a custom dialog or careful signal handling.
	# Let's switch to a custom Window for better control similar to asset review.
	dialog.queue_free()
	
	var win = Window.new()
	win.title = "Verify Task Execution"
	win.min_size = Vector2(500, 250)
	win.always_on_top = true
	EditorInterface.get_base_control().add_child(win)
	
	var margin = MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 20)
	margin.add_theme_constant_override("margin_right", 20)
	margin.add_theme_constant_override("margin_top", 20)
	margin.add_theme_constant_override("margin_bottom", 20)
	win.add_child(margin)
	
	var layout = VBoxContainer.new()
	margin.add_child(layout)
	
	var header = Label.new()
	header.text = "Task Execution Finished"
	header.add_theme_font_size_override("font_size", 18)
	layout.add_child(header)
	
	var desc = Label.new()
	desc.text = content
	desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desc.custom_minimum_size.y = 60
	layout.add_child(desc)
	
	layout.add_child(HSeparator.new())
	
	var q_label = Label.new()
	q_label.text = "Does the game work as expected?"
	layout.add_child(q_label)
	
	var btn_row = HBoxContainer.new()
	layout.add_child(btn_row)
	
	var approve_btn = Button.new()
	approve_btn.text = "✅ Yes, It Works"
	approve_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	approve_btn.custom_minimum_size.y = 40
	approve_btn.pressed.connect(func():
		_send_verification_feedback(task_id, "APPROVED")
		win.queue_free()
	)
	btn_row.add_child(approve_btn)
	
	var reject_btn = Button.new()
	reject_btn.text = "❌ No, Something is Broken"
	reject_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btn_row.add_child(reject_btn)
	
	# Hidden reporting section
	var report_box = VBoxContainer.new()
	report_box.visible = false
	layout.add_child(report_box)
	
	var report_label = Label.new()
	report_label.text = "Describe the issue (system will prioritize a fix immediately):"
	report_box.add_child(report_label)
	
	var issue_edit = LineEdit.new()
	issue_edit.custom_minimum_size.y = 35
	report_box.add_child(issue_edit)
	
	var submit_issue_btn = Button.new()
	submit_issue_btn.text = "Submit Issue & Fix"
	submit_issue_btn.pressed.connect(func():
		var issue = issue_edit.text.strip_edges()
		if issue.is_empty():
			return
		_send_verification_feedback(task_id, issue)
		win.queue_free()
	)
	report_box.add_child(submit_issue_btn)
	
	reject_btn.pressed.connect(func():
		btn_row.visible = false
		report_box.visible = true
		q_label.text = "What went wrong?"
	)
	
	win.close_requested.connect(func(): win.queue_free())
	win.popup_centered()

func _send_verification_feedback(task_id: String, feedback: String) -> void:
	if bridge_client and bridge_client.has_method("send_message"):
		bridge_client.send_message({
			"type": "chat",
			"mode": "execution",
			"action": "task_verification_feedback",
			"task_id": task_id,
			"feedback": feedback
		})
		_set_execution_busy(true, "Processing Verification...")
