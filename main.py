import os
import json
import download
import platformdirs
import sys
import zipfile
import shutil

APPDATA = platformdirs.user_data_dir("Gamesa_launcher")
os.makedirs(APPDATA, exist_ok=True)

CESTA_VERSIONS_JSON = os.path.join(APPDATA, "versions.json")
CESTA_LATEST_JSON = os.path.join(APPDATA, "latest_release.json")
SLOZKA_VERSIONS = os.path.join(APPDATA, "Versions")

# Globální vlajka, zda chceme výstup v JSONu pro GUI
FORMAT_JSON = "--json" in sys.argv

def posli_vystup(status: str, zprava: str, data: dict = None):
    """
    Unifikovaná funkce pro výstup. Pokud je zapnutý FORMAT_JSON,
    vytiskne strojově čitelný JSON, jinak vypíše běžný text.
    """
    if FORMAT_JSON:
        vystup = {
            "status": status,  # "success" nebo "error"
            "message": zprava,
            "data": data if data is not None else {}
        }
        print(json.dumps(vystup, ensure_ascii=False))
    else:
        if status == "error":
            print(f"Chyba: {zprava}")
        else:
            print(zprava)

def load_versions():
    """Stáhne POUZE nejnovější release z GitHubu a zařadí ho do lokální databáze."""
    # Dočasně potlačíme vnitřní printy z download.py, pokud jedeme v JSON režimu
    stary_stdout = sys.stdout
    if FORMAT_JSON:
        sys.stdout = open(os.devnull, 'w')

    try:
        download.json("https://api.github.com/repos/mimrpimstudios/gamesa/releases/latest", CESTA_LATEST_JSON)
    except Exception as e:
        sys.stdout = stary_stdout
        posli_vystup("error", f"Síťová chyba při komunikaci s GitHub API: {e}")
        return
    finally:
        if FORMAT_JSON:
            sys.stdout = stary_stdout

    if not os.path.exists(CESTA_LATEST_JSON):
        posli_vystup("error", "Nepodařilo se ověřit nejnovější verzi (soubor nebyl stažen).")
        return
    
    try:
        with open(CESTA_LATEST_JSON, "r", encoding="utf-8") as f:
            latest_release = json.load(f)
    except json.JSONDecodeError:
        posli_vystup("error", "Soubor s nejnovější verzí z GitHubu je poškozený.")
        return

    vysledny_slovnik = {}
    if os.path.exists(CESTA_VERSIONS_JSON):
        try:
            with open(CESTA_VERSIONS_JSON, "r", encoding="utf-8") as f:
                vysledny_slovnik = json.load(f)
        except json.JSONDecodeError:
            pass

    verze = latest_release.get("tag_name")
    nasel_se_zip = False
    
    for asset in latest_release.get("assets", []):
        if asset.get("name") == "Gamesa.zip":
            link = asset.get("browser_download_url")
            vysledny_slovnik[verze] = link
            nasel_se_zip = True
            break

    if nasel_se_zip:
        with open(CESTA_VERSIONS_JSON, "w", encoding="utf-8") as f:
            json.dump(vysledny_slovnik, f, indent=4, ensure_ascii=False)
        posli_vystup("success", f"Seznam verzí aktualizován. Nejnovější nalezená verze: {verze}", {"latest_version": verze})
    else:
        posli_vystup("error", f"V nejnovějším releasu ({verze}) nebyl nalezen soubor Gamesa.zip.")

def list_versions():
    """Vrátí/vypíše seznam všech známých verzí."""
    if not os.path.exists(CESTA_VERSIONS_JSON):
        posli_vystup("error", "Seznam verzí je prázdný. Spusťte nejdříve aktualizaci (update).")
        return

    with open(CESTA_VERSIONS_JSON, "r", encoding="utf-8") as f:
        versions_data = json.load(f)

    if FORMAT_JSON:
        posli_vystup("success", "Seznam známých verzí načten.", {"versions": list(versions_data.keys())})
    else:
        print("\n--- Všechny známé verze hry Gamesa ---")
        for verze in versions_data.keys():
            print(f" • {verze}")
        print("--------------------------------------\n")

def list_installed_versions():
    """Vrátí/vypíše seznam aktuálně rozbalených verzí na disku."""
    nainstalovane = []
    if os.path.exists(SLOZKA_VERSIONS):
        nainstalovane = [
            jmeno.replace("Gamesa_", "") 
            for jmeno in os.listdir(SLOZKA_VERSIONS) 
            if os.path.isdir(os.path.join(SLOZKA_VERSIONS, jmeno)) and jmeno.startswith("Gamesa_")
        ]

    if FORMAT_JSON:
        posli_vystup("success", "Seznam nainstalovaných verzí načten.", {"installed": nainstalovane})
    else:
        if not nainstalovane:
            print("Nemáte nainstalovanou žádnou verzi.")
            return
        print("\n--- Nainstalované verze v PC ---")
        for verze in nainstalovane:
            print(f" • {verze}")
        print("--------------------------------\n")

def install_version(version: str):
    """Stáhne a rozbalí vybranou verzi."""
    if not os.path.exists(CESTA_VERSIONS_JSON):
        posli_vystup("error", "Soubor versions.json neexistuje. Spusťte update.")
        return

    with open(CESTA_VERSIONS_JSON, "r", encoding="utf-8") as f:
        versions_data = json.load(f)
        
    if version not in versions_data:
        posli_vystup("error", f"Verze {version} není v seznamu známých verzí.")
        return

    os.makedirs(SLOZKA_VERSIONS, exist_ok=True)
    vystupni_zip = os.path.join(SLOZKA_VERSIONS, f"Gamesa_{version}.zip")
    cilova_slozka_hry = os.path.join(SLOZKA_VERSIONS, f"Gamesa_{version}")

    if os.path.exists(os.path.join(cilova_slozka_hry, "Gamesa.exe")):
        posli_vystup("success", f"Verze {version} už je nainstalovaná.", {"version": version})
        return

    # Pokud stahujeme pro GUI, progress bar v download.py bude vypisovat řádky s \r. 
    # GUI může tyto řádky číst a parsovat si procenta.
    if not FORMAT_JSON:
        print(f"Zahajuji stahování verze {version}...")
        
    download.file(versions_data[version], vystupni_zip)
    
    if os.path.exists(vystupni_zip):
        if not FORMAT_JSON:
            print(f"Rozbaluji verzi {version}...")
        try:
            with zipfile.ZipFile(vystupni_zip, 'r') as zip_ref:
                zip_ref.extractall(cilova_slozka_hry)
            
            if os.path.exists(vystupni_zip):
                os.remove(vystupni_zip)
            posli_vystup("success", f"Verze {version} byla úspěšně nainstalována.", {"version": version})
        except zipfile.BadZipFile:
            if os.path.exists(vystupni_zip):
                os.remove(vystupni_zip)
            posli_vystup("error", "Stažený soubor ZIP byl poškozený.")

def uninstall_version(version: str):
    """Odebere složku s hrou z disku."""
    cilova_slozka_hry = os.path.join(SLOZKA_VERSIONS, f"Gamesa_{version}")
    
    if os.path.exists(cilova_slozka_hry) and os.path.isdir(cilova_slozka_hry):
        try:
            shutil.rmtree(cilova_slozka_hry)
            posli_vystup("success", f"Verze {version} byla úspěšně odebrána.", {"version": version})
        except Exception as e:
            posli_vystup("error", f"Chyba při mazání složky: {e}")
    else:
        posli_vystup("error", f"Verze {version} není nainstalována.")

def start_version(version: str):
    """Spustí hru."""
    spustitelny_soubor = os.path.join(SLOZKA_VERSIONS, f"Gamesa_{version}", "Gamesa.exe")
    
    if os.path.exists(spustitelny_soubor):
        try:
            os.startfile(spustitelny_soubor)
            posli_vystup("success", f"Hra verze {version} byla spuštěna.", {"version": version})
        except Exception as e:
            posli_vystup("error", f"Nepodařilo se spustit soubor: {e}")
    else:
        posli_vystup("error", f"Spustitelný soubor pro verzi {version} nebyl nalezen.")

if __name__ == "__main__":
    # Odstraníme přepínač --json z argumentů, aby nám nekazil poziční indexy
    argumenty = [arg for arg in sys.argv if arg != "--json"]

    if len(argumenty) > 1:
        prikaz = argumenty[1].lower()
        
        if prikaz == "update":
            load_versions()
        elif prikaz == "versions":
            list_versions()
        elif prikaz == "installed":
            list_installed_versions()
        elif prikaz in ("install", "uninstall", "start") and len(argumenty) < 3:
            posli_vystup("error", f"Chybí specifikace verze u příkazu '{prikaz}'.")
        elif prikaz == "install":
            install_version(argumenty[2])
        elif prikaz == "uninstall":
            uninstall_version(argumenty[2])
        elif prikaz == "start":
            start_version(argumenty[2])
        else:
            posli_vystup("error", "Neznámý příkaz.")
    else:
        if FORMAT_JSON:
            posli_vystup("error", "Nebyl zadán žádný příkaz.")
        else:
            print("Použití:\n  python main.py <prikaz> [verze] [--json]")
            print("Příkazy: update, versions, installed, install, uninstall, start")