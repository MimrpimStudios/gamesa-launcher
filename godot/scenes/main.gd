extends Control

@onready var changelog: RichTextLabel = $RichTextLabel
@onready var version: OptionButton = $VersionOptionButton
@onready var play: Button = $PlayButton
@onready var uninstall: Button = $UninstallButton

var data
var data_downloaded
var cesta_k_exe = "res://assets/bin/gamesa_launcher_cli.exe"
var vybrana_verze: String = "" # Globální proměnná na začátku skriptu

# NOVÉ: Sem si uložíme ID běžícího instalačního procesu na pozadí (-1 znamená, že nic neběží)
var instalacni_pid: int = -1

func _ready():
	# 1. Aktualizace seznamu z GitHubu
	var update_res = spusti_launcher(["update", "--json"])
	if update_res != null and update_res.has("status"):
		print("Update status: ", update_res["status"])
	else:
		print("Nepodařilo se provést update.")
		
	# 2. Získání všech verzí
	data = spusti_launcher(["versions", "--json"])
	if data != null and data.has("status") and data["status"] == "success":
		print("Seznam verzí úspěšně načten.")
		naplň_dropdown_verzi()
	else:
		print("Nepodařilo se získat validní seznam verzí.")

func _process(_delta: float) -> void:
	# NOVÉ: Každý snímek kontrolujeme, zda na pozadí stále běží stahování/instalace
	if instalacni_pid != -1:
		# Pokud proces s tímto PID už na pozadí neběží, znamená to, že skončil
		if not OS.is_process_running(instalacni_pid):
			print("Instalační proces (PID: ", instalacni_pid, ") na pozadí skončil!")
			
			# Vynulujeme PID sledování
			instalacni_pid = -1
			play.disabled = false
			
			# Zavoláme výběr verze znovu, čímž se spustí příkaz "installed" a tlačítko se přepne na "Spustit hru"
			_on_version_option_button_item_selected(version.selected)

func spusti_launcher(prikazy: Array) -> Dictionary:
	var globalni_cesta = ProjectSettings.globalize_path(cesta_k_exe)
	
	if not FileAccess.file_exists(globalni_cesta):
		print("Chyba: Soubor neexistuje na cestě: ", globalni_cesta)
		return {}
		
	var vystup = []
	var exit_code = OS.execute(globalni_cesta, prikazy, vystup, true, false)
	
	if exit_code == 0 and vystup.size() > 0:
		var surový_text = vystup[0]
		var json = JSON.new()
		var chyba = json.parse(surový_text)
		
		if chyba == OK:
			return json.data
		else:
			print("Chyba parsování JSONu: ", json.get_error_message())
			return {}
	else:
		print("Spuštění selhalo. Exit kód: ", exit_code)
		return {}

func naplň_dropdown_verzi() -> void:
	version.clear()
	
	if data.has("data") and data["data"].has("versions") and data["data"]["versions"] is Array:
		var pole_verzi = data["data"]["versions"]
		
		for verze in pole_verzi:
			version.add_item(verze)
			
		if version.item_count > 0:
			version.selected = 0
			_on_version_option_button_item_selected(0)
			
		print("OptionButton byl úspěšně naplněn ", pole_verzi.size(), " verzemi.")
	else:
		print("Chyba: Data neobsahují platný seznam verzí pod klíčem data.versions.")


func _on_version_option_button_item_selected(index: int) -> void:
	vybrana_verze = version.get_item_text(index)
	var data_installed = spusti_launcher(["installed", "--json"])
	if data_installed != null and data_installed.get("status") == "success":
		var stazene = data_installed["data"].get("installed", [])
		if vybrana_verze in stazene:
			play.text = "Spustit hru"
		else:
			play.text = "Stáhnout a instalovat"

func _on_play_button_pressed() -> void:
	if vybrana_verze == "": return
	
	# Pokud zrovna probíhá instalace, zamezíme dalšímu klikání
	if instalacni_pid != -1: return
	
	var globalni_cesta = ProjectSettings.globalize_path(cesta_k_exe)

	if play.text == "Stáhnout a instalovat":
		play.disabled = true
		play.text = "Stahování..."
		
		# ÚPRAVA: Místo OS.execute() použijeme OS.create_process()
		# Spustí se samostatný proces na pozadí, který neblokuje hlavní vlákno Godotu.
		instalacni_pid = OS.create_process(globalni_cesta, ["install", vybrana_verze], false)
		
		if instalacni_pid != -1:
			print("Instalace verze ", vybrana_verze, " byla úspěšně spuštěna na pozadí pod PID: ", instalacni_pid)
		else:
			print("Kritická chyba: Nepodařilo se vytvořit instalační proces.")
			play.disabled = false
			play.text = "Stáhnout a instalovat"

	elif play.text == "Spustit hru":
		print("Spouštím hru...")
		# U spuštění hry můžeme nechat OS.execute, protože Python hru nahodí přes subprocess
		# bleskově (v řádu milisekund) a hned se sám ukončí, takže Godot nezatuhne.
		var vystup = []
		var exit_code = OS.execute(globalni_cesta, ["start", vybrana_verze], vystup, true, false)
		
		if exit_code == 0:
			print("Hra úspěšně nahozena.")
			# get_tree().quit() # Volitelně můžeš odkomentovat pro zavření launcheru po startu hry
		else:
			print("Hru se nepodařilo spustit.")


func _on_uninstall_button_pressed() -> void:
	if vybrana_verze == "":
		print("Chyba: Není vybrána žádná verze pro odinstalaci.")
		return
		
	# Pokud zrovna probíhá stahování jiné verze, raději odinstalaci zablokujeme
	if instalacni_pid != -1:
		print("Nelze odinstalovat hru, dokud běží stahování.")
		return

	print("Zahajuji odinstalaci verze: ", vybrana_verze)
	
	# Zavoláme launcher s příkazem pro smazání verze
	var uninstall_res = spusti_launcher(["uninstall", vybrana_verze, "--json"])
	
	if uninstall_res != null and uninstall_res.has("status"):
		if uninstall_res["status"] == "success":
			print("Odinstalace úspěšná: ", uninstall_res.get("message", ""))
			
			# Obnovíme stav hlavního tlačítka (přepne se zpět na "Stáhnout a instalovat")
			_on_version_option_button_item_selected(version.selected)
		else:
			print("Odinstalace selhala: ", uninstall_res.get("message", "Neznámá chyba."))
	else:
		print("Kritická chyba: Launcher neodpověděl validním JSONem.")
