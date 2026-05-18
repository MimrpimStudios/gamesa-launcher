extends Control

@onready var changelog: RichTextLabel = $RichTextLabel
@onready var version: OptionButton = $VersionOptionButton
@onready var play: Button = $PlayButton
@onready var uninstall: Button = $UninstallButton
@onready var prereleases: CheckBox = $PreReleasesCheckBox
@onready var force_install: CheckBox = $ForceInstallCheckBox

var data = null # Inicializujeme explicitně na null
var data_downloaded
var cesta_k_exe = "res://assets/bin/gamesa_launcher_cli.exe"
var vybrana_verze: String = "" # Globální proměnná pro vybranou verzi
var ma_prerelease_volbu: bool
# Ikony pro různé typy verzí
var latest = preload("uid://bdaly080dwtnr")
var release = preload("uid://ca1xspl6ngldb")
var prerelease = preload("uid://sg0lj3lbql4")

# Sledování běžícího instalačního procesu na pozadí (-1 znamená, že nic neběží)
var instalacni_pid: int = -1

# Cesta ke konfiguračnímu souboru launcheru pro uložení nastavení a poslední vybrané verze
var cesta_k_configu = "user://launcher_config.cfg"

# Proměnná pro druhé vlákno (Thread)
var bg_thread: Thread

# Pomocná proměnná pro zjištění skutečného tagu verze, která odpovídá "latest" z JSONu
var aktualni_skutecny_latest_tag: String = ""
# Pomocná proměnná pro zjištění skutečného tagu verze, která odpovídá nejnovějšímu prerelease
var aktualni_skutecny_latest_prerelease_tag: String = ""

func _ready():
	# Nastavení maximální velikosti ikon na rozměr běžného textu (16x16px)
	var popup = version.get_popup()
	popup.add_theme_constant_override("icon_max_width", 16)
	version.add_theme_constant_override("icon_max_width", 16)

	# Propojení signálů pro filtry a vynucenou instalaci

	# Načtení předchozího stavu CheckBoxů z konfigurace
	nacti_nastaveni_filtru()

	# Startujeme druhé vlákno pro asynchronní načítání z internetu a disku
	bg_thread = Thread.new()
	bg_thread.start(_run_background_init)

# Funkce, která běží na druhém vlákně a neblokuje GUI launcheru
func _run_background_init() -> void:
	# 1. Aktualizace seznamu z GitHubu
	var update_res = spusti_launcher(["update", "--json"])
	if update_res != null and update_res.has("status"):
		print("Update status: ", update_res["status"])
	else:
		print("Nepodařilo se provést update.")
		
	# 2. Získání všech verzí
	var loaded_data = spusti_launcher(["versions", "--json"])
	
	# Pošleme data bezpečně zpět do hlavního vlákna Godotu
	call_deferred("_on_background_init_finished", loaded_data)

# Spustí se na hlavním vlákně, jakmile načítání na pozadí skončí
func _on_background_init_finished(loaded_data) -> void:
	# Vyčistíme a ukončíme vlákno
	if bg_thread:
		bg_thread.wait_to_finish()
		bg_thread = null
		
	data = loaded_data
	if data != null and data.has("status") and data["status"] == "success":
		print("Seznam verzí úspěšně načten.")
		naplň_dropdown_verzi()
	else:
		print("Nepodařilo se získat validní seznam verzí.")

func _process(_delta: float) -> void:
	# Každý snímek kontrolujeme, zda na pozadí stále běží stahování/instalace
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
	# Ošetření chyby: Pokud data ještě nebyla stažena/připravena, neprovádíme plnění
	if data == null:
		return
		
	version.clear()
	
	if data.has("data") and data["data"].has("versions") and data["data"]["versions"] is Array:
		var pole_verzi = data["data"]["versions"]
		
		# Vyhledáme nejnovější stabilní verzi (typ "latest") a nejnovější prerelease
		aktualni_skutecny_latest_tag = ""
		aktualni_skutecny_latest_prerelease_tag = ""
		
		for polozka in pole_verzi:
			var typ = polozka.get("type", "")
			var jmeno = polozka.get("name", "")
			if typ == "latest":
				aktualni_skutecny_latest_tag = jmeno
			elif typ == "prerelease" and aktualni_skutecny_latest_prerelease_tag == "":
				# První nalezený pre-release je ten nejnovější
				aktualni_skutecny_latest_prerelease_tag = jmeno
		
		# Pokud se žádná "latest" nenašla, použijeme jako zálohu první v poli
		if aktualni_skutecny_latest_tag == "" and pole_verzi.size() > 0:
			aktualni_skutecny_latest_tag = pole_verzi[0].get("name", "")

		# Načteme si uloženou verzi z minulého spuštění
		var posledni_vybrana_verze = nacti_ulozenou_verzi()
		var index_k_vyberu = 0 # Výchozí index je první (tedy možnost "Latest")
		var zobrazeny_idx = 0
		
		# PRVNÍ KROK: Do dropdownu přidáme virtuální/zástupnou volbu "Latest"
		version.add_item("Latest")
		if latest:
			version.set_item_icon(0, latest)
		
		# Pokud si konfigurace pamatuje z minula "Latest" nebo soubor neexistuje
		if posledni_vybrana_verze == "Latest" or posledni_vybrana_verze == "":
			index_k_vyberu = 0
			
		zobrazeny_idx += 1
		
		# DRUHÝ KROK: Přidáme virtuální volbu "Latest Prerelease", pokud jsou pre-releasy povolené
		ma_prerelease_volbu = false
		if prereleases and prereleases.button_pressed and aktualni_skutecny_latest_prerelease_tag != "":
			ma_prerelease_volbu = true
			version.add_item("Latest Prerelease")
			if prerelease:
				version.set_item_icon(zobrazeny_idx, prerelease)
			
			if posledni_vybrana_verze == "Latest Prerelease":
				index_k_vyberu = zobrazeny_idx
				
			zobrazeny_idx += 1
		
		# TŘETÍ KROK: Přidáme všechny konkrétní verze
		for idx in range(pole_verzi.size()):
			var polozka = pole_verzi[idx]
			var jmeno_verze = polozka.get("name", "Neznámá")
			var typ_verze = polozka.get("type", "release")
			
			# Filtrování pre-releasů na základě stavu CheckBoxu
			if typ_verze == "prerelease" and prereleases and not prereleases.button_pressed:
				continue # Přeskočíme tuto verzi
			
			# Přidáme text verze do OptionButtonu
			version.add_item(jmeno_verze)
			
			# Vybereme správnou ikonku podle typu z preloadu
			match typ_verze:
				"latest":
					if latest: version.set_item_icon(zobrazeny_idx, latest)
				"prerelease":
					if prerelease: version.set_item_icon(zobrazeny_idx, prerelease)
				"release":
					if release: version.set_item_icon(zobrazeny_idx, release)
			
			# Pokud tato verze odpovídá té, kterou hráč vybral minule, uložíme si její index
			if jmeno_verze == posledni_vybrana_verze:
				index_k_vyberu = zobrazeny_idx
				
			zobrazeny_idx += 1
			
		if version.item_count > 0:
			# Ochrana proti přetečení indexu po změně filtrů
			if index_k_vyberu >= version.item_count:
				index_k_vyberu = 0
				
			# Vybereme index a vyvoláme změnu GUI prvků
			version.selected = index_k_vyberu
			_on_version_option_button_item_selected(index_k_vyberu)
			
		print("OptionButton byl úspěšně naplněn ", version.item_count, " verzemi s ikonami.")
	else:
		print("Chyba: Data neobsahují platný strukturovaný seznam verzí pod klíčem data.versions.")

func _on_version_option_button_item_selected(index: int) -> void:
	if index < 0 or index >= version.item_count: return
	vybrana_verze = version.get_item_text(index)
	
	# Uložíme aktuální výběr na disk pro příští spuštění hry
	uloz_vybranou_verzi(vybrana_verze)
	
	# Vyhodnocení zástupných textů na reálné tagy verzí pro kontrolu instalace
	var testovana_verze = vybrana_verze
	if vybrana_verze == "Latest":
		testovana_verze = aktualni_skutecny_latest_tag
	elif vybrana_verze == "Latest Prerelease":
		testovana_verze = aktualni_skutecny_latest_prerelease_tag
	
	# Zkontrolujeme, zda je verze již nainstalovaná
	var data_installed = spusti_launcher(["installed", "--json"])
	if data_installed != null and data_installed.get("status") == "success":
		var stazene = data_installed["data"].get("installed", [])
		if testovana_verze in stazene:
			# Pokud je vynucená instalace aktivní, chceme povolit opětovné stažení/reinstalaci
			if force_install and force_install.button_pressed:
				play.text = "Reinstalovat"
			else:
				play.text = "Spustit hru"
		else:
			play.text = "Stáhnout a instalovat"

func _on_play_button_pressed() -> void:
	if vybrana_verze == "": return
	
	# Pokud zrovna probíhá instalace, zamezíme dalšímu klikání
	if instalacni_pid != -1: return
	
	var globalni_cesta = ProjectSettings.globalize_path(cesta_k_exe)

	# Přeložíme zástupný text na skutečný tag verze, který pošleme do CLI příkazu
	var verze_pro_prikaz = vybrana_verze
	if vybrana_verze == "Latest":
		verze_pro_prikaz = aktualni_skutecny_latest_tag
	elif vybrana_verze == "Latest Prerelease":
		verze_pro_prikaz = aktualni_skutecny_latest_prerelease_tag

	if play.text == "Stáhnout a instalovat" or play.text == "Reinstalovat":
		play.disabled = true
		
		# Pokud děláme Force Install (nebo je popisek tlačítka Reinstalovat), nejprve hru odinstalujeme
		if play.text == "Reinstalovat" or (force_install and force_install.button_pressed):
			play.text = "Odinstalování staré verze..."
			print("Force Install: Odinstalovávám verzi ", verze_pro_prikaz, " před zahájením stahování.")
			var uninstall_res = spusti_launcher(["uninstall", verze_pro_prikaz, "--json"])
			if uninstall_res != null and uninstall_res.get("status") == "success":
				print("Stará verze úspěšně odinstalována.")
			else:
				print("Předběžná odinstalace se nezdařila nebo nebyla nutná, pokračuji ve stahování.")

		play.text = "Stahování..."
		
		# Spustí se samostatný proces na pozadí, který neblokuje hlavní vlákno Godotu
		instalacni_pid = OS.create_process(globalni_cesta, ["install", verze_pro_prikaz], false)
		
		if instalacni_pid != -1:
			print("Instalace verze ", verze_pro_prikaz, " byla úspěšně spuštěna na pozadí pod PID: ", instalacni_pid)
		else:
			print("Kritická chyba: Nepodařilo se vytvořit instalační proces.")
			play.disabled = false
			_on_version_option_button_item_selected(version.selected)

	elif play.text == "Spustit hru":
		print("Spouštím hru...")
		var vystup = []
		var exit_code = OS.execute(globalni_cesta, ["start", verze_pro_prikaz], vystup, true, false)
		
		if exit_code == 0:
			print("Hra úspěšně nahozena.")
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

	# Přeložíme zástupný text na skutečný tag verze
	var verze_pro_prikaz = vybrana_verze
	if vybrana_verze == "Latest":
		verze_pro_prikaz = aktualni_skutecny_latest_tag
	elif vybrana_verze == "Latest Prerelease":
		verze_pro_prikaz = aktualni_skutecny_latest_prerelease_tag

	print("Zahajuji odinstalaci verze: ", verze_pro_prikaz)
	
	# Zavoláme launcher s příkazem pro smazání verze
	var uninstall_res = spusti_launcher(["uninstall", verze_pro_prikaz, "--json"])
	
	if uninstall_res != null and uninstall_res.has("status"):
		if uninstall_res["status"] == "success":
			print("Odinstalace úspěšná: ", uninstall_res.get("message", ""))
			
			# Obnovíme stav hlavního tlačítka (přepne se zpět na "Stáhnout a instalovat")
			_on_version_option_button_item_selected(version.selected)
		else:
			print("Odinstalace selhala: ", uninstall_res.get("message", "Neznámá chyba."))
	else:
		print("Kritická chyba: Launcher neodpověděl validním JSONem.")

# Signál pro změnu zobrazení Pre-releasů v menu
func _on_prereleases_toggled(_button_pressed: bool) -> void:
	uloz_nastaveni_filtru()
	naplň_dropdown_verzi()

# Signál pro změnu vynucené reinstalace
func _on_force_install_toggled(_button_pressed: bool) -> void:
	uloz_nastaveni_filtru()
	if version.item_count > 0:
		_on_version_option_button_item_selected(version.selected)

# Pomocná funkce: Uložení vybrané verze do lokální konfigurace launcheru
func uloz_vybranou_verzi(nazev_verze: String) -> void:
	var config = ConfigFile.new()
	config.load(cesta_k_configu) # Načteme stávající nastavení
	config.set_value("Nastaveni", "posledni_verze", nazev_verze)
	config.save(cesta_k_configu)

# Pomocná funkce: Načtení naposledy vybrané verze z konfigurace
func nacti_ulozenou_verzi() -> String:
	var config = ConfigFile.new()
	var chyba = config.load(cesta_k_configu)
	if chyba == OK:
		return config.get_value("Nastaveni", "posledni_verze", "")
	return ""

# Pomocná funkce: Uložení stavu filtrů a nastavení do konfigurace
func uloz_nastaveni_filtru() -> void:
	var config = ConfigFile.new()
	config.load(cesta_k_configu)
	if prereleases:
		config.set_value("Filtry", "prereleases", prereleases.button_pressed)
	if force_install:
		config.set_value("Filtry", "force_install", force_install.button_pressed)
	config.save(cesta_k_configu)

# Pomocná funkce: Načtení nastavení a uplatnění na CheckBoxech
func nacti_nastaveni_filtru() -> void:
	var config = ConfigFile.new()
	var chyba = config.load(cesta_k_configu)
	if chyba == OK:
		if prereleases:
			prereleases.button_pressed = config.get_value("Filtry", "prereleases", true)
		if force_install:
			force_install.button_pressed = config.get_value("Filtry", "force_install", false)


func _on_close_texture_button_pressed() -> void:
	get_tree().quit(0)
