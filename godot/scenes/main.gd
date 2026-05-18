extends Control

@onready var changelog: RichTextLabel = $RichTextLabel
@onready var version: OptionButton = $VersionOptionButton
@onready var play: Button = $PlayButton
@onready var uninstall: Button = $UninstallButton
@onready var prereleases: CheckBox = $PreReleasesCheckBox
@onready var force_install: CheckBox = $ForceInstallCheckBox
@onready var progress_bar: ProgressBar = $ProgressBar
@onready var progress_bar_label: Label = $ProgressBar/ProgressBarLabel

var global_version = ProjectSettings.get_setting("application/config/version")
var changelog_text = """Welcome to the new Gamesa launcher (version """ + str(global_version) + """). Now better by look and function.

What is new?
I do not know!
But I'm actually the person who should know it...
But I am not a person! I am RichTextLabel!
And also I do not know what it means. Maybe it means I am rich label with text. But it is true I have a lot of text!

Do you know what is prereleases and latest?
Prereleases is updates that is  not stable and buggy (a lot). Latest is a newest version"""

var data = null # Explicitly initialize as null
var data_downloaded
var cli_exe_path: String = ""
var selected_version: String = "" # Global variable for the selected version
var has_prerelease_option: bool

# Icons for different version types
var latest = preload("uid://bdaly080dwtnr")
var release = preload("uid://ca1xspl6ngldb")
var prerelease = preload("uid://sg0lj3lbql4")

# Tracking the running background installation process via communication pipe
var install_pipe: Dictionary = {}
var install_thread: Thread = null # Separate thread to safely read the pipe

# Path to the launcher configuration file to save settings and the last selected version
var config_path = "user://launcher_config.cfg"

# Variable for the background initialization thread
var bg_thread: Thread

# Helper variable to discover the actual version tag corresponding to "latest" from the JSON
var current_actual_latest_tag: String = ""
# Helper variable to discover the actual version tag corresponding to the newest prerelease
var current_actual_latest_prerelease_tag: String = ""
var current_exe_dir: String = ""

func _ready() -> void:
	if OS.has_feature("editor"):
		# In editor we want to work with project root
		current_exe_dir = ProjectSettings.globalize_path("res://")
		cli_exe_path = current_exe_dir + "assets/bin/gamesa_launcher_cli.exe"
	else:
		# When exported, it takes the real folder containing your exported .exe
		current_exe_dir = OS.get_executable_path().get_base_dir() + "/"
		cli_exe_path = current_exe_dir + "assets/bin/gamesa_launcher_cli.exe"
		
	print("Directory used: ", current_exe_dir)
	
	# Restrict the maximum size of icons to match regular text (16x16px)
	set_changelog()
	var popup = version.get_popup()
	popup.add_theme_constant_override("icon_max_width", 16)
	version.add_theme_constant_override("icon_max_width", 16)

	# Load the previous state of checkboxes from config
	load_filter_settings()

	if progress_bar_label:
		progress_bar_label.text = ""

	# Start the background thread for asynchronous loading from internet and disk
	bg_thread = Thread.new()
	bg_thread.start(_run_background_init)

# CLEANUP BEFORE CLOSING THE LAUNCHER/GAME
func _notification(what: int) -> void:
	# Catches close requests from the OS window manager or launcher garbage collection
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_PREDELETE:
		print("Launcher is closing, performing safe cleanup...")
		terminate_install_monitoring()

# Function running on a secondary thread that does not block the launcher's GUI
func _run_background_init() -> void:
	# 1. Update version list from GitHub
	var update_res = run_launcher(["update", "--json"])
	if update_res != null and update_res.has("status"):
		print("Update status: ", update_res["status"])
	else:
		print("Failed to perform update.")
		
	# 2. Get all available versions
	var loaded_data = run_launcher(["versions", "--json"])
	
	# Send data safely back to the main Godot thread
	call_deferred("_on_background_init_finished", loaded_data)

# Triggers on the main thread once background loading finishes
func _on_background_init_finished(loaded_data) -> void:
	# Clean up and join thread
	if bg_thread:
		bg_thread.wait_to_finish()
		bg_thread = null
		
	data = loaded_data
	if data != null and data.has("status") and data["status"] == "success":
		print("Version list successfully loaded.")
		populate_version_dropdown()
	else:
		print("Failed to retrieve a valid list of versions.")

func _process(_delta: float) -> void:
	# We no longer read the pipe in _process (a dedicated thread handles it).
	# We only monitor if the background process died unexpectedly.
	if install_pipe.has("pid"):
		var pid = install_pipe.get("pid", -1)
		if pid != -1 and not OS.is_process_running(pid):
			terminate_install_monitoring()

# Running on an independent thread, constantly listening to the Python output
func _threaded_pipe_reader(pipe: FileAccess) -> void:
	while pipe.is_open() and pipe.get_error() == OK:
		var line = pipe.get_line()
		
		# If we hit the end of the stream, break out of the loop
		if line == "" and pipe.get_error() != OK:
			break
			
		# Safely pass the line to the main thread for processing
		call_deferred("_process_python_line", line.strip_edges())
	
	# Safe shutdown of monitoring from the main thread when done
	call_deferred("terminate_install_monitoring")

# Processing lines sent from the background on the main thread (UI thread-safe)
func _process_python_line(line: String) -> void:
	if line == "": return
	
	var json = JSON.new()
	if json.parse(line) == OK:
		var res = json.data
		if res is Dictionary:
			# Capture download progress for the progress bar and text label
			if res.get("status") == "progress":
				var percentage = res.get("percent", 0)
				if percentage >= 0:
					progress_bar.value = percentage
					if progress_bar_label:
						progress_bar_label.text = "Downloading: " + str(percentage) + " %"
				else:
					if progress_bar_label:
						progress_bar_label.text = "Downloading (size unknown)..."
					
			# Capture final success or download error states
			elif res.get("status") == "success":
				print("Installation completed: ", res.get("message"))
				if progress_bar_label:
					progress_bar_label.text = "Installation completed successfully!"
			elif res.get("status") == "error":
				print("Installation error: ", res.get("message"))
				if progress_bar_label:
					progress_bar_label.text = "Error: " + str(res.get("message"))

# Helper function to clear state after installation and when quitting
func terminate_install_monitoring() -> void:
	if install_pipe.is_empty() and install_thread == null:
		return

	# PROCESS SAFEGUARD: If the process is still running, kill it directly (e.g. if the launcher closes)
	if install_pipe.has("pid"):
		var pid = install_pipe["pid"]
		if pid != -1 and OS.is_process_running(pid):
			print("Terminating background download process (PID: ", pid, ")...")
			OS.kill(pid)

	if install_pipe.has("stdio"):
		install_pipe["stdio"].close()
	
	install_pipe = {}
	
	# If the thread is still active, safely wait for it to join and clear it
	if install_thread:
		if install_thread.is_started():
			install_thread.wait_to_finish()
		install_thread = null
		
	play.disabled = false
	progress_bar.value = 0
	if progress_bar_label:
		# If installation was aborted by user/crash, clear the label after a moment
		if progress_bar_label.text.begins_with("Downloading"):
			progress_bar_label.text = ""
			
	_on_version_option_button_item_selected(version.selected)

func run_launcher(commands: Array) -> Dictionary:
	var global_path = ProjectSettings.globalize_path(cli_exe_path)
	
	if not FileAccess.file_exists(global_path):
		print("Error: File does not exist at path: ", global_path)
		return {}
		
	var output = []
	var exit_code = OS.execute(global_path, commands, output, true, false)
	
	if exit_code == 0 and output.size() > 0:
		var raw_text = output[0]
		var json = JSON.new()
		var error = json.parse(raw_text)
		
		if error == OK:
			return json.data
		else:
			print("JSON Parsing Error: ", json.get_error_message())
			return {}
	else:
		print("Execution failed. Exit code: ", exit_code)
		return {}

func populate_version_dropdown() -> void:
	if data == null:
		return
		
	version.clear()
	
	if data.has("data") and data["data"].has("versions") and data["data"]["versions"] is Array:
		var versions_array = data["data"]["versions"]
		
		# Find the latest stable version (type "latest") and latest prerelease
		current_actual_latest_tag = ""
		current_actual_latest_prerelease_tag = ""
		
		for item in versions_array:
			var ver_type = item.get("type", "")
			var name = item.get("name", "")
			if ver_type == "latest":
				current_actual_latest_tag = name
			elif ver_type == "prerelease" and current_actual_latest_prerelease_tag == "":
				current_actual_latest_prerelease_tag = name
		
		if current_actual_latest_tag == "" and versions_array.size() > 0:
			current_actual_latest_tag = versions_array[0].get("name", "")

		var last_selected_version = load_saved_version()
		var index_to_select = 0
		var display_idx = 0
		
		version.add_item("Latest")
		if latest:
			version.set_item_icon(0, latest)
		
		if last_selected_version == "Latest" or last_selected_version == "":
			index_to_select = 0
			
		display_idx += 1
		
		has_prerelease_option = false
		if prereleases and prereleases.button_pressed and current_actual_latest_prerelease_tag != "":
			has_prerelease_option = true
			version.add_item("Latest Prerelease")
			if prerelease:
				version.set_item_icon(display_idx, prerelease)
			
			if last_selected_version == "Latest Prerelease":
				index_to_select = display_idx
				
			display_idx += 1
		
		for idx in range(versions_array.size()):
			var item = versions_array[idx]
			var version_name = item.get("name", "Unknown")
			var version_type = item.get("type", "release")
			
			if version_type == "prerelease" and prereleases and not prereleases.button_pressed:
				continue
			
			version.add_item(version_name)
			
			match version_type:
				"latest":
					if latest: version.set_item_icon(display_idx, latest)
				"prerelease":
					if prerelease: version.set_item_icon(display_idx, prerelease)
				"release":
					if release: version.set_item_icon(display_idx, release)
			
			if version_name == last_selected_version:
				index_to_select = display_idx
				
			display_idx += 1
			
		if version.item_count > 0:
			if index_to_select >= version.item_count:
				index_to_select = 0
				
			version.selected = index_to_select
			_on_version_option_button_item_selected(index_to_select)
			
		print("OptionButton populated successfully with ", version.item_count, " versions.")
	else:
		print("Error: Data does not contain a valid structured version list.")

func _on_version_option_button_item_selected(index: int) -> void:
	if index < 0 or index >= version.item_count: return
	selected_version = version.get_item_text(index)
	save_selected_version(selected_version)
	
	var tested_version = selected_version
	if selected_version == "Latest":
		tested_version = current_actual_latest_tag
	elif selected_version == "Latest Prerelease":
		tested_version = current_actual_latest_prerelease_tag
	
	var data_installed = run_launcher(["installed", "--json"])
	if data_installed != null and data_installed.get("status") == "success":
		var downloaded = data_installed["data"].get("installed", [])
		if tested_version in downloaded:
			if force_install and force_install.button_pressed:
				play.text = "Reinstall"
			else:
				play.text = "Launch Game"
		else:
			play.text = "Download and Install"

func _on_play_button_pressed() -> void:
	if selected_version == "": return
	if install_pipe.has("stdio"): return
	
	var global_path = ProjectSettings.globalize_path(cli_exe_path)
	var command_version = selected_version
	if selected_version == "Latest":
		command_version = current_actual_latest_tag
	elif selected_version == "Latest Prerelease":
		command_version = current_actual_latest_prerelease_tag

	if play.text == "Download and Install" or play.text == "Reinstall":
		play.disabled = true
		progress_bar.value = 0
		
		if play.text == "Reinstall" or (force_install and force_install.button_pressed):
			play.text = "Uninstalling..."
			if progress_bar_label:
				progress_bar_label.text = "Uninstalling older version..."
			var uninstall_res = run_launcher(["uninstall", command_version, "--json"])
			if uninstall_res != null and uninstall_res.get("status") == "success":
				print("Old version successfully uninstalled.")

		play.text = "Downloading..."
		if progress_bar_label:
			progress_bar_label.text = "Preparing download..."
		
		# Execute background process with output pipe
		install_pipe = OS.execute_with_pipe(global_path, ["install", command_version, "--json"])
		
		if install_pipe.has("stdio") and install_pipe.get("pid", -1) != -1:
			print("Installation launched in the background under PID: ", install_pipe["pid"])
			# Start background thread to read pipe and keep GUI interactive
			install_thread = Thread.new()
			install_thread.start(_threaded_pipe_reader.bind(install_pipe["stdio"]))
		else:
			print("Critical error: Failed to initialize installation process.")
			if progress_bar_label:
				progress_bar_label.text = "Failed to launch installer!"
			terminate_install_monitoring()
			
	elif play.text == "Launch Game":
		print("Launching game...")
		var extra_args_string = "-launcherGUI -versionGUI=" + str(global_version)
		var parameters = ["start", command_version, extra_args_string]
		var output = []
		var exit_code = OS.execute(global_path, parameters, output, true, false)
		if exit_code == 0:
			print("Game successfully launched.")
		else:
			print("Failed to start the game. Exit code: ", exit_code)

func _on_uninstall_button_pressed() -> void:
	if selected_version == "": return
	if install_pipe.has("stdio"): return

	var command_version = selected_version
	if selected_version == "Latest":
		command_version = current_actual_latest_tag
	elif selected_version == "Latest Prerelease":
		command_version = current_actual_latest_prerelease_tag

	print("Initializing uninstallation for version: ", command_version)
	if progress_bar_label:
		progress_bar_label.text = "Uninstalling version " + command_version + "..."
	
	var uninstall_res = run_launcher(["uninstall", command_version, "--json"])
	
	if uninstall_res != null and uninstall_res.has("status"):
		if uninstall_res["status"] == "success":
			print("Uninstall successful: ", uninstall_res.get("message", ""))
			if progress_bar_label:
				progress_bar_label.text = "Uninstall completed!"
			_on_version_option_button_item_selected(version.selected)
		else:
			print("Uninstall failed: ", uninstall_res.get("message", ""))
			if progress_bar_label:
				progress_bar_label.text = "Failed to delete files."
	else:
		print("Critical error: CLI failed to reply with valid JSON.")
		if progress_bar_label:
			progress_bar_label.text = "CLI communication error."

func _on_prereleases_toggled(_button_pressed: bool) -> void:
	save_filter_settings()
	populate_version_dropdown()

func _on_force_install_toggled(_button_pressed: bool) -> void:
	save_filter_settings()
	if version.item_count > 0:
		_on_version_option_button_item_selected(version.selected)

func save_selected_version(version_name: String) -> void:
	var config = ConfigFile.new()
	config.load(config_path)
	config.set_value("Settings", "last_version", version_name)
	config.save(config_path)

func load_saved_version() -> String:
	var config = ConfigFile.new()
	var error = config.load(config_path)
	if error == OK:
		return config.get_value("Settings", "last_version", "")
	return ""

func save_filter_settings() -> void:
	var config = ConfigFile.new()
	config.load(config_path)
	if prereleases:
		config.set_value("Filters", "prereleases", prereleases.button_pressed)
	if force_install:
		config.set_value("Filters", "force_install", force_install.button_pressed)
	config.save(config_path)

func load_filter_settings() -> void:
	var config = ConfigFile.new()
	var error = config.load(config_path)
	if error == OK:
		if prereleases:
			prereleases.button_pressed = config.get_value("Filters", "prereleases", true)
		if force_install:
			force_install.button_pressed = config.get_value("Filters", "force_install", false)

func _on_close_texture_button_pressed() -> void:
	get_tree().quit(0)

func set_changelog():
	changelog.set_text(changelog_text)
