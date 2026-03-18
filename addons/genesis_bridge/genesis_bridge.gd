@tool
extends EditorPlugin

# This script handles the lifecycle of the GenesisBridge plugin in the Godot Editor.

const BridgeClient = preload("res://addons/genesis_bridge/bridge_client.gd")
const ChatDock = preload("res://addons/genesis_bridge/ui/chat_dock.gd")
var bridge_client_instance: Node = null
var chat_dock_instance: Control = null

func _enter_tree() -> void:
	# Add a custom child node to the Editor's main interface to stay persistent.
	bridge_client_instance = BridgeClient.new()
	bridge_client_instance.name = "BridgeClient"
	get_editor_interface().get_base_control().add_child(bridge_client_instance)
	
	# Connect to selection changed signal
	var selection = get_editor_interface().get_selection()
	selection.selection_changed.connect(_on_selection_changed)
	
	# Create and add chat dock
	chat_dock_instance = ChatDock.new()
	chat_dock_instance.name = "GenesisEngine"
	chat_dock_instance.set_bridge_client(bridge_client_instance)
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, chat_dock_instance)
	
	print("GenesisBridge: Plugin entered tree and BridgeClient added.")

func _exit_tree() -> void:
	# Disconnect selection signal
	var selection = get_editor_interface().get_selection()
	if selection.selection_changed.is_connected(_on_selection_changed):
		selection.selection_changed.disconnect(_on_selection_changed)
	
	# Remove chat dock
	if chat_dock_instance:
		remove_control_from_docks(chat_dock_instance)
		chat_dock_instance.queue_free()
		chat_dock_instance = null
	
	# Clean up the BridgeClient node when the plugin is disabled.
	if bridge_client_instance:
		bridge_client_instance.queue_free()
		bridge_client_instance = null
	print("GenesisBridge: Plugin exited tree and BridgeClient removed.")

func _on_selection_changed() -> void:
	var selection = get_editor_interface().get_selection()
	var selected_nodes = selection.get_selected_nodes()
	
	if selected_nodes.size() == 0:
		# No selection, send empty data
		bridge_client_instance.send_event("selection_changed", {})
		return
	
	# Get the first selected node
	var node = selected_nodes[0]
	var selection_data = {
		"name": node.name,
		"type": node.get_class(),
		"scene_file_path": "",
		"script_path": ""
	}
	
	# Get scene file path if available
	if node.scene_file_path != "":
		selection_data["scene_file_path"] = node.scene_file_path
	
	# Get script path if attached
	var script = node.get_script()
	if script != null:
		selection_data["script_path"] = script.resource_path
	
	# Send selection event to backend
	bridge_client_instance.send_event("selection_changed", selection_data)
