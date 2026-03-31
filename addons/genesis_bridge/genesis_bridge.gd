@tool
extends EditorPlugin

const BridgeClient = preload("res://addons/genesis_bridge/bridge_client.gd")
const ChatDock = preload("res://addons/genesis_bridge/ui/chat_dock.gd")

const SETTING_API_KEY      = "genesis_bridge/gemini_api_key"
const SETTING_PYTHON_PATH  = "genesis_bridge/python_executable_path"
const SETTING_MODEL_FLASH  = "genesis_bridge/model_flash"
const SETTING_MODEL_LITE   = "genesis_bridge/model_lite"
const SETTING_IMG_PROVIDER = "genesis_bridge/image_provider"
const SETTING_IMAGEN_MODEL = "genesis_bridge/imagen_model"
const SETTING_DAILY_LIMIT  = "genesis_bridge/gemini_daily_limit"
const SETTING_RATE_LIMIT   = "genesis_bridge/gemini_rate_limit"

var bridge_client_instance: Node = null
var chat_dock_instance: Control = null
var _backend_pid: int = -1

# ─── Plugin lifecycle ────────────────────────────────────────────────────────

func _enter_tree() -> void:
	_register_editor_settings()

	bridge_client_instance = BridgeClient.new()
	bridge_client_instance.name = "BridgeClient"
	get_editor_interface().get_base_control().add_child(bridge_client_instance)

	var selection = get_editor_interface().get_selection()
	selection.selection_changed.connect(_on_selection_changed)

	chat_dock_instance = ChatDock.new()
	chat_dock_instance.name = "GenesisEngine"
	chat_dock_instance.set_bridge_client(bridge_client_instance)
	chat_dock_instance.setup_requested.connect(_on_setup_requested)
	chat_dock_instance.settings_saved.connect(_on_settings_saved)
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, chat_dock_instance)

	_maybe_start_backend()
	print("GenesisBridge: Plugin entered tree.")


func _exit_tree() -> void:
	_stop_backend()

	var selection = get_editor_interface().get_selection()
	if selection.selection_changed.is_connected(_on_selection_changed):
		selection.selection_changed.disconnect(_on_selection_changed)

	if chat_dock_instance:
		remove_control_from_docks(chat_dock_instance)
		chat_dock_instance.queue_free()
		chat_dock_instance = null

	if bridge_client_instance:
		bridge_client_instance.queue_free()
		bridge_client_instance = null

	print("GenesisBridge: Plugin exited tree.")

# ─── Backend process management ─────────────────────────────────────────────

func _get_backend_dir() -> String:
	return ProjectSettings.globalize_path("res://addons/genesis_bridge/backend")


func _get_venv_python() -> String:
	var venv = _get_backend_dir() + "/.venv"
	if OS.has_feature("windows"):
		return venv + "/Scripts/python.exe"
	return venv + "/bin/python"


## Write (or overwrite) the .env used by the backend config loader.
## Reads all values from EditorSettings; api_key may be passed explicitly
## during first-time setup before settings are fully saved.
func _write_env(api_key: String = "") -> void:
	var s = EditorInterface.get_editor_settings()
	if api_key.is_empty():
		api_key = s.get_setting(SETTING_API_KEY)
	var content := (
		"GEMINI_API_KEY=%s\n"        % api_key +
		"GEMINI_MODEL_FLASH=%s\n"    % s.get_setting(SETTING_MODEL_FLASH) +
		"GEMINI_MODEL_LITE=%s\n"     % s.get_setting(SETTING_MODEL_LITE) +
		"IMAGE_PROVIDER=%s\n"        % s.get_setting(SETTING_IMG_PROVIDER) +
		"IMAGEN_MODEL=%s\n"          % s.get_setting(SETTING_IMAGEN_MODEL) +
		"GEMINI_DAILY_LIMIT=%d\n"    % int(s.get_setting(SETTING_DAILY_LIMIT)) +
		"GEMINI_RATE_LIMIT=%d\n"     % int(s.get_setting(SETTING_RATE_LIMIT))
	)
	var path = _get_backend_dir() + "/.env"
	var f = FileAccess.open(path, FileAccess.WRITE)
	if f:
		f.store_string(content)
		f.close()
	else:
		push_error("GenesisBridge: Could not write .env to " + path)


func _maybe_start_backend() -> void:
	var api_key: String = EditorInterface.get_editor_settings().get_setting(SETTING_API_KEY)
	if api_key.strip_edges().is_empty():
		chat_dock_instance.show_setup("Enter your Gemini API key to get started.")
		return

	var python_exe = _get_venv_python()
	if not FileAccess.file_exists(python_exe):
		chat_dock_instance.show_setup("Python environment not installed yet. Click 'Install Backend'.")
		return

	_write_env(api_key)
	_start_backend(python_exe)


func _start_backend(python_exe: String) -> void:
	var start_script = _get_backend_dir() + "/start.py"
	# Keep-open suffix: shows a message and waits for Enter so the user can
	# read any error output before the terminal closes.
	var keep_open = '; echo ""; echo "Genesis Engine backend stopped."; read -p "Press Enter to close..."'
	var bash_cmd   = '"%s" "%s"' % [python_exe, start_script] + keep_open

	if OS.has_feature("windows"):
		# /K keeps the window open after the process exits
		_backend_pid = OS.create_process("cmd.exe", ["/K", python_exe, start_script])

	elif OS.has_feature("macos"):
		var script = 'tell application "Terminal" to do script "cd \'%s\' && \'%s\' \'%s\'"' \
			% [_get_backend_dir(), python_exe, start_script]
		_backend_pid = OS.create_process("osascript", ["-e", script])

	else:
		_backend_pid = _start_linux_terminal(bash_cmd, python_exe, start_script)

	print("GenesisBridge: Backend terminal launched (PID %d)." % _backend_pid)
	chat_dock_instance.on_backend_starting()


func _start_linux_terminal(bash_cmd: String, python_exe: String, start_script: String) -> int:
	# Try common terminal emulators in order.
	# --wait makes gnome-terminal block until the child exits (keeps PID valid).
	var terminals: Array[Array] = [
		["gnome-terminal", ["--wait", "--title=Genesis Engine Backend", "--", "bash", "-c", bash_cmd]],
		["xterm",          ["-T", "Genesis Engine Backend", "-e", "bash", "-c", bash_cmd]],
		["konsole",        ["--title", "Genesis Engine Backend", "-e", "bash", "-c", bash_cmd]],
		["xfce4-terminal", ["--title=Genesis Engine Backend", "-x", "bash", "-c", bash_cmd]],
	]
	for entry in terminals:
		if OS.execute("which", [entry[0]], []) == 0:
			return OS.create_process(entry[0], entry[1])

	push_warning("GenesisBridge: No terminal emulator found — running backend headlessly.")
	return OS.create_process(python_exe, [start_script])


func _stop_backend() -> void:
	# Prefer killing Python directly via the PID file it writes on startup.
	# This leaves the terminal window open so the user can read any final output.
	var pid_path = _get_backend_dir() + "/.pid"
	if FileAccess.file_exists(pid_path):
		var f = FileAccess.open(pid_path, FileAccess.READ)
		var python_pid = int(f.get_as_text().strip_edges())
		f.close()
		if python_pid > 0:
			OS.kill(python_pid)
			print("GenesisBridge: Backend stopped (Python PID %d)." % python_pid)
		DirAccess.remove_absolute(pid_path)
	elif _backend_pid > 0:
		OS.kill(_backend_pid)
		print("GenesisBridge: Backend terminal closed (PID %d)." % _backend_pid)
	_backend_pid = -1

# ─── Setup signal from chat dock ─────────────────────────────────────────────

## Called by the setup panel inside chat_dock when the user completes setup.
func _on_setup_requested(python_path: String, api_key: String) -> void:
	var settings = EditorInterface.get_editor_settings()
	settings.set_setting(SETTING_API_KEY, api_key)
	settings.set_setting(SETTING_PYTHON_PATH, python_path)

	_write_env(api_key)

	var backend_dir = _get_backend_dir()
	var venv_dir    = backend_dir + "/.venv"

	# Install in a thread so the editor doesn't freeze
	chat_dock_instance.show_install_progress("Creating Python environment…")
	var thread := Thread.new()
	thread.start(_install_thread.bind(python_path, venv_dir, backend_dir, thread))


func _install_thread(python_path: String, venv_dir: String, backend_dir: String, thread: Thread) -> void:
	# 1. Create venv
	var ret = OS.execute(python_path, ["-m", "venv", venv_dir])
	if ret != 0:
		call_deferred("_on_install_failed", "Failed to create Python venv (exit %d). Is Python 3 installed?" % ret, thread)
		return

	# 2. Determine pip inside venv
	var pip: String
	if OS.has_feature("windows"):
		pip = venv_dir + "/Scripts/pip.exe"
	else:
		pip = venv_dir + "/bin/pip"

	# 3. Install requirements
	ret = OS.execute(pip, ["install", "-r", backend_dir + "/requirements.txt"])
	if ret != 0:
		call_deferred("_on_install_failed", "pip install failed (exit %d). Check the Godot console for details." % ret, thread)
		return

	call_deferred("_on_install_done", thread)


func _on_settings_saved() -> void:
	_write_env()
	_stop_backend()
	var python_exe = _get_venv_python()
	if FileAccess.file_exists(python_exe):
		_start_backend(python_exe)
	else:
		chat_dock_instance.show_setup("Settings saved. Install the backend to start.")


func _on_install_done(thread: Thread) -> void:
	thread.wait_to_finish()
	chat_dock_instance.show_install_progress("")  # clear progress
	var python_exe = _get_venv_python()
	_start_backend(python_exe)


func _on_install_failed(message: String, thread: Thread) -> void:
	thread.wait_to_finish()
	push_error("GenesisBridge: Install failed — " + message)
	chat_dock_instance.show_setup(message)

# ─── Editor selection forwarding ────────────────────────────────────────────

func _register_editor_settings() -> void:
	var s = EditorInterface.get_editor_settings()
	var defaults := {
		SETTING_API_KEY:      "",
		SETTING_PYTHON_PATH:  "python3",
		SETTING_MODEL_FLASH:  "gemini-3.1-flash-lite-preview",
		SETTING_MODEL_LITE:   "gemini-3.1-flash-lite-preview",
		SETTING_IMG_PROVIDER: "local",
		SETTING_IMAGEN_MODEL: "imagen-4.0-fast-generate-001",
		SETTING_DAILY_LIMIT:  500,
		SETTING_RATE_LIMIT:   15,
	}
	for key in defaults:
		if not s.has_setting(key):
			s.set_setting(key, defaults[key])
			s.set_initial_value(key, defaults[key], false)


func _on_selection_changed() -> void:
	var selection = get_editor_interface().get_selection()
	var selected_nodes = selection.get_selected_nodes()

	if selected_nodes.size() == 0:
		bridge_client_instance.send_event("selection_changed", {})
		return

	var node = selected_nodes[0]
	var data = {
		"name": node.name,
		"type": node.get_class(),
		"scene_file_path": "",
		"script_path": ""
	}
	if node.scene_file_path != "":
		data["scene_file_path"] = node.scene_file_path
	var script = node.get_script()
	if script != null:
		data["script_path"] = script.resource_path

	bridge_client_instance.send_event("selection_changed", data)
