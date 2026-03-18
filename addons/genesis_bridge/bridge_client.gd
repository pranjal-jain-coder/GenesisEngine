@tool
extends Node

# BridgeClient handles WebSocket communication between Godot Editor and Python backend.

var socket: WebSocketPeer = null
var connection_url: String = "ws://127.0.0.1:8000/ws"
var is_registered: bool = false
var reconnect_timer: float = 0.0
var reconnect_interval: float = 3.0

# Signal for UI updates
signal message_received(message: Dictionary)
signal connection_changed(connected: bool)

func _ready() -> void:
	print("BridgeClient: Ready and persistent in the editor.")
	_connect_to_server()

func _process(delta: float) -> void:
	if socket == null:
		# Handle reconnection logic
		reconnect_timer += delta
		if reconnect_timer >= reconnect_interval:
			print("BridgeClient: Attempting to reconnect...")
			_connect_to_server()
			reconnect_timer = 0.0
		return
	
	# Poll the WebSocket
	socket.poll()
	var state = socket.get_ready_state()
	
	match state:
		WebSocketPeer.STATE_CONNECTING:
			# Still connecting, wait
			pass
		
		WebSocketPeer.STATE_OPEN:
			# Connection is open
			if not is_registered:
				_send_registration()

			# Process at most 32 packets per frame to avoid stalling the editor
			var packets_this_frame = 0
			while socket.get_available_packet_count() > 0 and packets_this_frame < 32:
				var packet = socket.get_packet()
				var message = packet.get_string_from_utf8()
				_handle_incoming_message(message)
				packets_this_frame += 1
		
		WebSocketPeer.STATE_CLOSING:
			print("BridgeClient: Connection is closing...")
		
		WebSocketPeer.STATE_CLOSED:
			var code = socket.get_close_code()
			var reason = socket.get_close_reason()
			print("BridgeClient: Connection closed. Code: %d, Reason: %s" % [code, reason])
			is_registered = false
			socket = null
			reconnect_timer = 0.0

func _connect_to_server() -> void:
	socket = WebSocketPeer.new()
	var err = socket.connect_to_url(connection_url)
	if err != OK:
		print("BridgeClient: Failed to connect to %s. Error: %d" % [connection_url, err])
		socket = null
		return
	print("BridgeClient: Connecting to %s..." % connection_url)

func _send_registration() -> void:
	var project_path = ProjectSettings.globalize_path("res://")
	var registration_data = {
		"type": "register",
		"project_path": project_path
	}
	var json_string = JSON.stringify(registration_data)
	var err = socket.send_text(json_string)
	if err == OK:
		is_registered = true
		print("BridgeClient: Sent registration message with project_path: %s" % project_path)
	else:
		print("BridgeClient: Failed to send registration message. Error: %d" % err)

func _handle_incoming_message(message: String) -> void:
	print("BridgeClient: Received message: %s" % message)
	var json = JSON.new()
	var parse_result = json.parse(message)
	if parse_result != OK:
		print("BridgeClient: Failed to parse JSON. Error: %s" % json.get_error_message())
		return
	
	var data = json.get_data()
	if typeof(data) != TYPE_DICTIONARY:
		print("BridgeClient: Received data is not a dictionary.")
		return
	
	# Check if it's a JSON-RPC response (has "result" or "error" field)
	if data.has("result") or data.has("error"):
		print("BridgeClient: Received JSON-RPC response: %s" % str(data))
		# If this is the registration confirmation, request the saved project state
		if data.has("result") and typeof(data["result"]) == TYPE_DICTIONARY and data["result"].get("status") == "connected":
			_request_project_state()
		return
	
	# Check if it's a command (has "method" field)
	if data.has("method"):
		_handle_command(data)
	elif data.has("type"):
		# Check for known types to forward to UI
		var type = data["type"]
		if type in ["chat_response", "task_list", "status", "task_started", "task_completed", "error", "task_history", "project_reverted", "asset_review_request", "gdd_update", "task_verification_request"]:
			# Forward these directly to the UI
			message_received.emit(data)
		else:
			print("BridgeClient: Received message of unknown type: %s" % type)
	else:
		print("BridgeClient: Received message with unknown format (no 'method', 'result', or 'error' field)")

func _request_project_state() -> void:
	"""Request the current project state (GDD + tasks) from the backend."""
	send_message({
		"type": "chat",
		"mode": "execution",
		"action": "get_project_state"
	})

func send_event(event_name: String, data: Dictionary) -> void:
	"""Send an event message to the Python backend."""
	if socket == null or socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
		# Not connected, skip sending
		return
	
	var event_message = {
		"type": "event",
		"event": event_name,
		"data": data
	}
	
	var json_string = JSON.stringify(event_message)
	var err = socket.send_text(json_string)
	if err != OK:
		print("BridgeClient: Failed to send event '%s'. Error: %d" % [event_name, err])
	else:
		print("BridgeClient: Sent event '%s': %s" % [event_name, str(data)])

func send_chat_message(mode: String, message: String) -> void:
	"""Send a chat message to the backend AI agent."""
	if socket == null or socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
		print("BridgeClient: Cannot send chat - not connected")
		message_received.emit({"error": "Not connected to backend"})
		return
	
	var chat_message = {
		"type": "chat",
		"mode": mode,
		"message": message
	}
	
	var json_string = JSON.stringify(chat_message)
	var err = socket.send_text(json_string)
	if err != OK:
		print("BridgeClient: Failed to send chat message. Error: %d" % err)
		message_received.emit({"error": "Failed to send message"})
	else:
		print("BridgeClient: Sent chat message in %s mode: %s" % [mode, message])

func send_message(data: Dictionary) -> void:
	"""Generic method to send any dictionary as JSON."""
	if socket == null or socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
		print("BridgeClient: Cannot send message - not connected")
		message_received.emit({"error": "Not connected to backend"})
		return
		
	var json_string = JSON.stringify(data)
	var err = socket.send_text(json_string)
	if err != OK:
		print("BridgeClient: Failed to send generic message. Error: %d" % err)
		message_received.emit({"error": "Failed to send message"})
	else:
		print("BridgeClient: Sent message: %s" % json_string)


func _handle_command(cmd_dict: Dictionary) -> void:
	print("BridgeClient: Handling command: %s" % str(cmd_dict))
	
	if not cmd_dict.has("method"):
		print("BridgeClient: Error - Command missing 'method' field")
		return
	
	var method = cmd_dict.get("method", "")
	var params = cmd_dict.get("params", {})
	var cmd_id = cmd_dict.get("id", null)
	
	var result = {"success": false, "message": "Unknown method: %s" % method}
	
	match method:
		"create_scene":
			result = _cmd_create_scene(params)
		"write_script":
			result = _cmd_write_script(params)
		"reload_project":
			result = _cmd_reload_project(params)
		"add_node":
			result = _cmd_add_node(params)
		"set_property":
			result = _cmd_set_property(params)
		"attach_script":
			result = _cmd_attach_script(params)
		"read_scene":
			result = _cmd_read_scene(params)
		"save_scene":
			result = _cmd_save_scene(params)
		"open_scene":
			result = _cmd_open_scene(params)
		"instance_scene":
			result = _cmd_instance_scene(params)
		"set_main_scene":
			result = _cmd_set_main_scene(params)
		"scan_filesystem":
			result = _cmd_scan_filesystem(params)
		"set_sprite_texture":
			result = _cmd_set_sprite_texture(params)
		"execute_script":
			result = _cmd_execute_script(params)
		"validate_script":
			result = _cmd_validate_script(params)
		"get_project_files":
			result = _cmd_get_project_files(params)
		"get_input_map":
			result = _cmd_get_input_map(params)
		"node_exists":
			result = _cmd_node_exists(params)
		"test_game":
			result = _cmd_test_game(params)
		"log":
			# Handle server-side logging by forwarding directly to UI
			var msg = params.get("message", "")
			message_received.emit({"type": "log", "message": msg})
			result = {"success": true, "message": "Log received"}
		_:
			print("BridgeClient: Unknown method: %s" % method)
			
	# Send response if ID was provided
	if cmd_id != null:
		var response = {
			"jsonrpc": "2.0",
			"id": cmd_id
		}
		if result.get("success", false):
			response["result"] = result
		else:
			var err_msg = result.get("message", "Unknown error")
			response["error"] = {"code": -32603, "message": err_msg}
			
		send_message(response)
	else:
		# Also send to general message emitter just in case we need it without id
		var err_msg = ""
		if not result.get("success", false):
			err_msg = result.get("message", "")
			
		message_received.emit({
			"type": "command_result",
			"method": method,
			"success": result.get("success", false),
			"error": err_msg
		})

func _ensure_directory_exists(path: String) -> void:
	var base_dir = path.get_base_dir()
	var dir = DirAccess.open("res://")
	if not dir.dir_exists(base_dir):
		print("BridgeClient: Directory %s does not exist, creating..." % base_dir)
		var err = dir.make_dir_recursive(base_dir)
		if err != OK:
			print("BridgeClient: Failed to create directory %s. Error: %d" % [base_dir, err])

func _cmd_create_scene(params: Dictionary) -> Dictionary:
	if not params.has("path") or not params.has("root_type"):
		return {"success": false, "message": "create_scene requires 'path' and 'root_type' parameters"}

	var path = params["path"]
	var root_type = params["root_type"]

	if not ClassDB.class_exists(root_type):
		return {"success": false, "message": "Class '%s' does not exist" % root_type}

	var root_node = ClassDB.instantiate(root_type)
	if root_node == null:
		return {"success": false, "message": "Failed to instantiate class '%s'" % root_type}

	var packed_scene = PackedScene.new()
	var result = packed_scene.pack(root_node)
	if result != OK:
		root_node.free()
		return {"success": false, "message": "Failed to pack scene. Error code: %d" % result}

	_ensure_directory_exists(path)
	var save_result = ResourceSaver.save(packed_scene, path)
	root_node.free()

	if save_result != OK:
		return {"success": false, "message": "Failed to save scene to %s. Error: %d" % [path, save_result]}

	# Open the newly created scene so subsequent add_node / set_property
	# commands target it (they use EditorInterface.get_edited_scene_root()).
	var res_path = path
	if not path.begins_with("res://"):
		res_path = "res://" + path
	EditorInterface.open_scene_from_path(res_path)

	# Defer scan so it runs after this command handler returns and the
	# JSON-RPC response is sent.  Synchronous scan() can trigger @tool
	# script reloads mid-frame → SIGSEGV.
	EditorInterface.get_resource_filesystem().call_deferred("scan")
	return {"success": true, "message": "Successfully created scene at %s" % path}

func _cmd_write_script(params: Dictionary) -> Dictionary:
	if not params.has("path") or not params.has("content"):
		return {"success": false, "message": "write_script requires 'path' and 'content' parameters"}
	
	var path = params["path"]
	var content = params["content"]
	
	var file_path = path
	if not path.begins_with("res://"):
		file_path = ProjectSettings.globalize_path(path)
	
	if path.begins_with("res://"):
		_ensure_directory_exists(path)
	else:
		var base_dir = file_path.get_base_dir()
		if not DirAccess.dir_exists_absolute(base_dir):
			DirAccess.make_dir_recursive_absolute(base_dir)

	var file = FileAccess.open(file_path, FileAccess.WRITE)
	if file == null:
		var error = FileAccess.get_open_error()
		return {"success": false, "message": "Failed to open file %s. Error code: %d" % [file_path, error]}
	
	file.store_string(content)
	file.close()

	# Defer scan — synchronous scan() can trigger @tool script reloads
	# mid-frame → SIGSEGV.
	EditorInterface.get_resource_filesystem().call_deferred("scan")
	return {"success": true, "message": "Successfully wrote script to %s" % path}

func _cmd_reload_project(params: Dictionary) -> Dictionary:
	var edited_scene = EditorInterface.get_edited_scene_root()
	if edited_scene == null:
		return {"success": false, "message": "No scene is currently open"}
	
	var scene_path = edited_scene.scene_file_path
	if scene_path == "":
		return {"success": false, "message": "Current scene has no file path (not saved)"}
	
	EditorInterface.reload_scene_from_path(scene_path)
	return {"success": true, "message": "Successfully reloaded scene from %s" % scene_path}

func _cmd_add_node(params: Dictionary) -> Dictionary:
	if not params.has("parent_path") or not params.has("node_type") or not params.has("node_name"):
		return {"success": false, "message": "add_node requires 'parent_path', 'node_type', and 'node_name'"}

	var parent_path = params["parent_path"]
	var node_type = params["node_type"]
	var node_name = params["node_name"]

	var edited_scene = EditorInterface.get_edited_scene_root()
	if edited_scene == null:
		return {"success": false, "message": "No edited scene root found. Open or create a scene first."}

	var parent_node: Node = null
	if parent_path == ".":
		parent_node = edited_scene
	else:
		parent_node = edited_scene.get_node_or_null(parent_path)

	if parent_node == null:
		return {"success": false, "message": "Parent node '%s' not found. Call read_scene first to verify the scene tree." % parent_path}

	# Guard against duplicates: if a child with this name already exists, skip.
	var existing = parent_node.get_node_or_null(node_name)
	if existing != null:
		return {
			"success": true,
			"message": "Node '%s' already exists at %s — skipped duplicate add." % [node_name, existing.get_path()],
			"already_existed": true
		}

	if not ClassDB.class_exists(node_type):
		return {"success": false, "message": "Class '%s' does not exist in Godot 4. Check the node type name." % node_type}

	var new_node = ClassDB.instantiate(node_type)
	if new_node == null:
		return {"success": false, "message": "Failed to instantiate '%s'" % node_type}

	new_node.name = node_name
	parent_node.add_child(new_node)
	new_node.owner = edited_scene

	return {"success": true, "message": "Successfully added node %s" % new_node.get_path(), "already_existed": false}

func _cmd_node_exists(params: Dictionary) -> Dictionary:
	if not params.has("node_path"):
		return {"success": false, "message": "node_exists requires 'node_path' parameter"}

	var edited_scene = EditorInterface.get_edited_scene_root()
	if edited_scene == null:
		return {"success": false, "message": "No edited scene root found", "exists": false}

	var node_path = params["node_path"]
	var node: Node = null
	if node_path == ".":
		node = edited_scene
	else:
		node = edited_scene.get_node_or_null(node_path)

	var exists = node != null
	var info = {}
	if exists:
		info = {
			"name": node.name,
			"type": node.get_class(),
			"path": str(edited_scene.get_path_to(node)) if node != edited_scene else ".",
			"script": node.get_script().resource_path if node.get_script() else "",
			"child_count": node.get_child_count()
		}

	return {"success": true, "exists": exists, "node": info}

func _cmd_set_property(params: Dictionary) -> Dictionary:
	if not params.has("node_path") or not params.has("property_name") or not params.has("value"):
		return {"success": false, "message": "set_property requires 'node_path', 'property_name', and 'value'"}

	var node_path = params["node_path"]
	var property_name = params["property_name"]
	var value = params["value"]

	var edited_scene = EditorInterface.get_edited_scene_root()
	if edited_scene == null:
		return {"success": false, "message": "No edited scene root found"}

	var node = edited_scene.get_node_or_null(node_path)
	if node == null:
		return {"success": false, "message": "Node '%s' not found" % node_path}

	value = _coerce_property_value(value)

	node.set(property_name, value)
	return {"success": true, "message": "Set %s.%s = %s" % [node_path, property_name, str(value)]}

func _cmd_attach_script(params: Dictionary) -> Dictionary:
	if not params.has("node_path") or not params.has("script_path"):
		return {"success": false, "message": "attach_script requires 'node_path' and 'script_path'"}
		
	var node_path = params["node_path"]
	var script_path = params["script_path"]
	
	var edited_scene = EditorInterface.get_edited_scene_root()
	if edited_scene == null:
		return {"success": false, "message": "No edited scene root found"}
		
	var node = edited_scene.get_node_or_null(node_path)
	if node == null:
		return {"success": false, "message": "Node '%s' not found" % node_path}
		
	var script_res = load(script_path)
	if script_res == null:
		return {"success": false, "message": "Failed to load script '%s'" % script_path}
		
	node.set_script(script_res)
	return {"success": true, "message": "Attached script '%s' to '%s'" % [script_path, node_path]}

func _cmd_read_scene(params: Dictionary) -> Dictionary:
	var edited_scene = EditorInterface.get_edited_scene_root()
	if edited_scene == null:
		return {"success": false, "message": "No edited scene root found"}
	
	var scene_data = _serialize_node(edited_scene, edited_scene)
	return {
		"success": true, 
		"message": "Scene read successfully",
		"scene_tree": scene_data
	}

func _cmd_save_scene(params: Dictionary) -> Dictionary:
	var edited_scene = EditorInterface.get_edited_scene_root()
	if edited_scene == null:
		return {"success": false, "message": "No scene is currently open to save"}

	var scene_path = edited_scene.scene_file_path
	if scene_path == "":
		scene_path = params.get("path", "")
		if scene_path == "":
			return {"success": false, "message": "Scene has no file path and none was provided"}

	var packed = PackedScene.new()
	var pack_result = packed.pack(edited_scene)
	if pack_result != OK:
		return {"success": false, "message": "Failed to pack scene. Error: %d" % pack_result}

	var save_result = ResourceSaver.save(packed, scene_path)
	if save_result != OK:
		return {"success": false, "message": "Failed to save scene to %s. Error: %d" % [scene_path, save_result]}

	EditorInterface.get_resource_filesystem().call_deferred("scan")
	return {"success": true, "message": "Scene saved to %s" % scene_path}

func _cmd_open_scene(params: Dictionary) -> Dictionary:
	if not params.has("path"):
		return {"success": false, "message": "open_scene requires 'path' parameter"}

	var path = params["path"]
	if not path.begins_with("res://"):
		path = "res://" + path

	var fa = FileAccess.open(path, FileAccess.READ)
	if fa == null:
		return {"success": false, "message": "Scene file not found: %s" % path}
	fa.close()

	EditorInterface.open_scene_from_path(path)
	return {"success": true, "message": "Opened scene: %s" % path}

func _cmd_instance_scene(params: Dictionary) -> Dictionary:
	if not params.has("scene_path") or not params.has("parent_path"):
		return {"success": false, "message": "instance_scene requires 'scene_path' and 'parent_path'"}

	var scene_path = params["scene_path"]
	var parent_path = params["parent_path"]
	var node_name = params.get("node_name", "")

	if not scene_path.begins_with("res://"):
		scene_path = "res://" + scene_path

	var edited_scene = EditorInterface.get_edited_scene_root()
	if edited_scene == null:
		return {"success": false, "message": "No edited scene root found"}

	var parent_node: Node = null
	if parent_path == ".":
		parent_node = edited_scene
	else:
		parent_node = edited_scene.get_node_or_null(parent_path)

	if parent_node == null:
		return {"success": false, "message": "Parent node '%s' not found" % parent_path}

	var packed_scene = load(scene_path)
	if packed_scene == null:
		return {"success": false, "message": "Failed to load scene: %s" % scene_path}

	var instance = packed_scene.instantiate()
	if instance == null:
		return {"success": false, "message": "Failed to instantiate scene: %s" % scene_path}

	if node_name != "":
		instance.name = node_name

	# Guard against duplicates: if a child with this name already exists, skip.
	var effective_name = instance.name
	var existing = parent_node.get_node_or_null(effective_name)
	if existing != null:
		instance.free()
		return {
			"success": true,
			"message": "Instance '%s' already exists at %s — skipped duplicate add." % [effective_name, existing.get_path()],
			"already_existed": true
		}

	parent_node.add_child(instance)
	# Only set owner on the instance root, NOT its children.
	# Setting owner recursively on a sub-scene's internal nodes causes Godot
	# to treat them as locally-owned nodes, making their names clash with
	# other nodes in the parent scene and showing 'Load Error' warnings.
	instance.owner = edited_scene

	return {"success": true, "message": "Instanced '%s' as child of '%s'" % [scene_path, parent_path]}

func _cmd_set_main_scene(params: Dictionary) -> Dictionary:
	if not params.has("path"):
		return {"success": false, "message": "set_main_scene requires 'path' parameter"}

	var path = params["path"]
	if not path.begins_with("res://"):
		path = "res://" + path

	ProjectSettings.set_setting("application/run/main_scene", path)
	var save_result = ProjectSettings.save()
	if save_result != OK:
		return {"success": false, "message": "Failed to save project settings. Error: %d" % save_result}

	return {"success": true, "message": "Main scene set to %s" % path}

func _cmd_set_sprite_texture(params: Dictionary) -> Dictionary:
	if not params.has("node_path") or not params.has("image_path"):
		return {"success": false, "message": "set_sprite_texture requires 'node_path' and 'image_path'"}

	var node_path = params["node_path"]
	var image_path = params["image_path"]

	var edited_scene = EditorInterface.get_edited_scene_root()
	if edited_scene == null:
		return {"success": false, "message": "No scene is currently open"}

	var node = edited_scene.get_node_or_null(node_path)
	if node == null:
		return {"success": false, "message": "Node not found: %s" % node_path}

	var texture = load(image_path)
	if texture == null:
		var abs_path = ProjectSettings.globalize_path(image_path)
		if FileAccess.file_exists(abs_path):
			var img = Image.new()
			var load_err = img.load(abs_path)
			if load_err == OK and not img.is_empty():
				texture = ImageTexture.create_from_image(img)
				if texture:
					texture.resource_path = image_path # Ensure serialization uses path

	if texture == null:
		return {"success": false, "message": "Could not load/create texture from '%s'. File may be missing or invalid." % image_path}

	if "texture" in node:
		node.texture = texture
	else:
		return {"success": false, "message": "Node '%s' has no 'texture' property" % node_path}

	return {"success": true, "message": "Set texture on '%s' from '%s'" % [node_path, image_path]}

func _cmd_scan_filesystem(params: Dictionary) -> Dictionary:
	var paths = params.get("paths", [])
	if paths.size() > 0:
		var p_paths = PackedStringArray()
		for p in paths:
			p_paths.append(str(p))
		EditorInterface.get_resource_filesystem().reimport_files(p_paths)
	else:
		EditorInterface.get_resource_filesystem().scan()
	return {"success": true, "message": "Filesystem scan triggered"}

func _cmd_execute_script(params: Dictionary) -> Dictionary:
	if not params.has("code"):
		return {"success": false, "message": "execute_script requires 'code' parameter"}

	var code = params["code"]
	var full_code = "extends Node\n\nfunc run_ai_script(editor, bridge):\n"
	var lines = code.split("\n")
	for line in lines:
		full_code += "\t" + line + "\n"
	
	var script = GDScript.new()
	script.source_code = full_code
	var err = script.reload()
	if err != OK:
		return {"success": false, "message": "GDScript compilation error: " + str(err)}
	
	var script_instance = script.new()
	if script_instance == null:
		return {"success": false, "message": "Failed to instantiate temporary script"}
	
	add_child(script_instance)
	
	var res = "OK"
	if script_instance.has_method("run_ai_script"):
		var exec_res = script_instance.run_ai_script(EditorInterface, self)
		if exec_res != null:
			res = str(exec_res)
	else:
		return {"success": false, "message": "Generated script missing 'run_ai_script' method"}
	
	script_instance.queue_free()
	
	return {
		"success": true, 
		"message": "Script executed successfully",
		"result": res
	}

func _cmd_validate_script(params: Dictionary) -> Dictionary:
	if not params.has("code"):
		return {"success": false, "message": "validate_script requires 'code' parameter"}

	var code = params["code"]
	var script = GDScript.new()
	script.source_code = code
	var err = script.reload(false)
	if err == OK:
		return {"success": true, "message": "Script is valid"}
	else:
		return {"success": false, "message": "GDScript syntax error (error code: %d). Check extends clause, method names, and indentation." % err}

func _cmd_get_project_files(params: Dictionary) -> Dictionary:
	var extensions = params.get("extensions", ["gd", "tscn", "tres", "gdshader"])
	var files: Array = []
	_scan_directory_recursive("res://", extensions, files)
	return {"success": true, "files": files}

func _scan_directory_recursive(path: String, extensions: Array, result: Array, depth: int = 0) -> void:
	if depth > 20:
		return
	var dir = DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var entry = dir.get_next()
	while entry != "":
		if entry.begins_with("."):
			entry = dir.get_next()
			continue
		var full_path = path.path_join(entry)
		if dir.current_is_dir():
			_scan_directory_recursive(full_path, extensions, result, depth + 1)
		else:
			var ext = entry.get_extension().to_lower()
			if ext in extensions:
				result.append(full_path)
		entry = dir.get_next()
	dir.list_dir_end()

func _cmd_get_input_map(params: Dictionary) -> Dictionary:
	var actions = InputMap.get_actions()
	var result = {}
	for action in actions:
		var events: Array = []
		for event in InputMap.action_get_events(action):
			events.append(event.as_text())
		result[str(action)] = events
	return {"success": true, "input_map": result}

func _coerce_property_value(value):
	if typeof(value) == TYPE_STRING:
		var str_val = str(value)
		if str_val.begins_with("res://"):
			var loaded = load(str_val)
			if loaded:
				return loaded
			var ext = str_val.get_extension().to_lower()
			if ext in ["png", "jpg", "jpeg", "webp", "bmp"]:
				var abs_path = ProjectSettings.globalize_path(str_val)
				var img = Image.new()
				if img.load(abs_path) == OK and not img.is_empty():
					var tex = ImageTexture.create_from_image(img)
					if tex:
						tex.resource_path = str_val
						return tex
		elif ClassDB.class_exists(str_val):
			return ClassDB.instantiate(str_val)
	elif typeof(value) == TYPE_DICTIONARY:
		var d = value
		if d.has("x") and d.has("y"):
			if d.has("z"):
				return Vector3(d["x"], d["y"], d["z"])
			return Vector2(d["x"], d["y"])
	return value

func _serialize_node(node, owner):
	var node_path = "."
	if node != owner:
		node_path = str(owner.get_path_to(node))

	var data = {
		"name": node.name,
		"type": node.get_class(),
		"path": node_path,
		"script": "",
		"children": []
	}

	# Include the attached script path so the AI knows what is already wired up
	var script = node.get_script()
	if script and script.resource_path != "":
		data["script"] = script.resource_path

	for child in node.get_children():
		data["children"].append(_serialize_node(child, owner))
	return data

func _cmd_test_game(params: Dictionary) -> Dictionary:
	if not params.has("scene_path"):
		return {"success": false, "message": "test_game requires 'scene_path' parameter"}
	
	var scene_path = params["scene_path"]
	var abs_path = ProjectSettings.globalize_path("res://")
	# Create a temporary script for the autoload
	var script_code = """extends Node
var timer = 0.0
var target_time = 1.5
var viewport = null
var bridge = null

func _ready():
	viewport = get_viewport()
	# Disable the main loop physically so it renders
	# We rely on _process to take the screenshot

func _process(delta):
	timer += delta
	if timer >= target_time:
		var img = viewport.get_texture().get_image()
		var img_buffer = img.save_png_to_buffer()
		var base64_img = Marshalls.raw_to_base64(img_buffer)
		print("Sending screenshot to bridge...")
		# Find the bridge client
		if bridge == null:
			bridge = Engine.get_main_loop().root.get_node_or_null("BridgeClient")
		
		# Assuming we're in the game, we need to communicate back
		# We'll just write it to a temp file and let the editor read it
		var f = FileAccess.open("res://.temp_screenshot.txt", FileAccess.WRITE)
		if f:
			f.store_string(base64_img)
			f.close()
			
		get_tree().quit()
"""
	# Save the autoload script
	var script_path = "res://.temp_screenshot_runner.gd"
	var fa = FileAccess.open(script_path, FileAccess.WRITE)
	if fa:
		fa.store_string(script_code)
		fa.close()
		
	# Add directly to project settings temporarily
	var autoload_name = "AITester"
	ProjectSettings.set_setting("autoload/" + autoload_name, "*res://.temp_screenshot_runner.gd")
	var prev_main = ProjectSettings.get_setting("application/run/main_scene")
	ProjectSettings.set_setting("application/run/main_scene", scene_path)
	ProjectSettings.save()
	
	# Run the game through the editor
	print("BridgeClient: Running scene for testing: ", scene_path)
	EditorInterface.play_custom_scene(scene_path)
	
	# Wait for the file to be generated
	var attempts = 0
	var found = false
	var base64_data = ""
	
	# We can't actually pause the editor thread easily without freezing the bridge
	# A real implementation would make this async or poll
	# For now, we'll try a simple OS sleep for a maximum of 4 seconds
	# Better yet, return immediately and let the client poll or wait for an event?
	# Let's use OS.delay_msec
	
	while attempts < 40 and not found:
		OS.delay_msec(100) # 100ms
		if FileAccess.file_exists("res://.temp_screenshot.txt"):
			found = true
			var f_in = FileAccess.open("res://.temp_screenshot.txt", FileAccess.READ)
			if f_in:
				base64_data = f_in.get_as_text()
				f_in.close()
			break
		attempts += 1
		
	# Cleanup
	EditorInterface.stop_playing_scene()
	ProjectSettings.set_setting("autoload/" + autoload_name, null)
	ProjectSettings.set_setting("application/run/main_scene", prev_main)
	ProjectSettings.save()
	
	var dir = DirAccess.open("res://")
	if dir.file_exists(".temp_screenshot_runner.gd"):
		dir.remove(".temp_screenshot_runner.gd")
	if dir.file_exists(".temp_screenshot.txt"):
		dir.remove(".temp_screenshot.txt")
		
	if found and base64_data != "":
		return {
			"success": true,
			"message": "Screenshot captured",
			"image_data": "data:image/png;base64," + base64_data
		}
	else:
		return {
			"success": false,
			"message": "Failed to capture screenshot - timed out waiting for game"
		}

func _exit_tree() -> void:
	if socket != null and socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		socket.close(1000, "Plugin exiting")
		print("BridgeClient: WebSocket connection closed.")
