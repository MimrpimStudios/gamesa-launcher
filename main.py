import os
import json
import download
import platformdirs
import sys
import zipfile
import shutil
import subprocess


cli_version = "0.0.1"
APPDATA = platformdirs.user_data_dir("Gamesa_launcher")
os.makedirs(APPDATA, exist_ok=True)

CESTA_VERSIONS_JSON = os.path.join(APPDATA, "versions.json")
CESTA_RELEASES_JSON = os.path.join(APPDATA, "releases.json")
SLOZKA_VERSIONS = os.path.join(APPDATA, "Versions")

FORMAT_JSON = "--json" in sys.argv

def posli_vystup(status: str, zprava: str, data: dict = None):
    """Pomocná funkce pro unifikovaný výstup do Godotu (JSON) nebo konzole."""
    if FORMAT_JSON:
        vystup = {
            "status": status,
            "message": zprava,
            "data": data if data is not None else {}
        }
        print(json.dumps(vystup, ensure_ascii=False))
    else:
        if status == "error":
            print(f"Chyba: {zprava}")
        else:
            print(zprava)
            
    # Pokud dojde k chybě v CLI, ukončíme proces s chybovým kódem
    if status == "error":
        sys.exit(1)

def resolve_version(version: str) -> str:
    """Pokud je zadáno 'latest', vyhledá a vrátí skutečný nejnovější stabilní tag."""
    if version.lower() != "latest":
        return version

    if not os.path.exists(CESTA_VERSIONS_JSON) or not os.path.exists(CESTA_RELEASES_JSON):
        posli_vystup("error", "Seznam verzí je prázdný. Spusťte nejdříve aktualizaci (update).")
        return version

    try:
        with open(CESTA_VERSIONS_JSON, "r", encoding="utf-8") as f:
            versions_data = json.load(f)
        with open(CESTA_RELEASES_JSON, "r", encoding="utf-8") as f:
            vsechny_releases = json.load(f)
    except Exception:
        posli_vystup("error", "Nepodařilo se načíst lokální soubory pro zjištění verze 'latest'.")
        return version

    # Najdeme první stabilní verzi, která není prerelease a máme pro ni asset
    skutecny_latest_tag = None
    for release in vsechny_releases:
        tag = release.get("tag_name")
        if tag in versions_data and not release.get("prerelease", False):
            skutecny_latest_tag = tag
            break
            
    # Nouzový plán: pokud jsou všechny pre-release, vezmeme úplně první dostupnou verzi
    if skutecny_latest_tag is None and vsechny_releases:
        for release in vsechny_releases:
            tag = release.get("tag_name")
            if tag in versions_data:
                skutecny_latest_tag = tag
                break

    if skutecny_latest_tag:
        return skutecny_latest_tag
    
    return version

def load_versions():
    """Tento příkaz jako JEDINÝ stahuje z internetu. Stáhne VŠECHNY releasy z GitHubu."""
    stary_stdout = sys.stdout
    if FORMAT_JSON:
        sys.stdout = open(os.devnull, 'w')

    try:
        # Stahujeme kompletní seznam všech releasů
        download.json("https://api.github.com/repos/mimrpimstudios/gamesa/releases", CESTA_RELEASES_JSON)
    except Exception as e:
        sys.stdout = stary_stdout
        posli_vystup("error", f"Síťová chyba při komunikaci s GitHub API: {e}")
        return
    finally:
        if FORMAT_JSON:
            sys.stdout = stary_stdout

    if not os.path.exists(CESTA_RELEASES_JSON):
        posli_vystup("error", "Nepodařilo se ověřit verze z internetu.")
        return
    
    try:
        with open(CESTA_RELEASES_JSON, "r", encoding="utf-8") as f:
            vsechny_releases = json.load(f)
    except json.JSONDecodeError:
        posli_vystup("error", "Soubor s verzemi z GitHubu je poškozený.")
        return

    vysledny_slovnik = {}

    # Projdeme úplně všechny nalezené releasy od nejnovějšího po nejstarší
    for release in vsechny_releases:
        verze = release.get("tag_name")
        for asset in release.get("assets", []):
            if asset.get("name") == "Gamesa.zip":
                link = asset.get("browser_download_url")
                vysledny_slovnik[verze] = link
                break  # Jakmile najdeme Gamesa.zip, skočíme na další release

    # Uložíme kompletní seznam všech verzí do lokálního souboru
    with open(CESTA_VERSIONS_JSON, "w", encoding="utf-8") as f:
        json.dump(vysledny_slovnik, f, indent=4, ensure_ascii=False)
        
    pocet_verzi = len(vysledny_slovnik)
    posli_vystup("success", f"Seznam verzí úspěšně aktualizován. Nalezeno {pocet_verzi} verzí.", {"total_versions": pocet_verzi})

def list_versions():
    """BEZ INTERNETU: Pouze otevře lokální soubory a vrátí VŠECHNY uložené verze se strukturou pro Godot."""
    if not os.path.exists(CESTA_VERSIONS_JSON) or not os.path.exists(CESTA_RELEASES_JSON):
        posli_vystup("error", "Seznam verzí je prázdný. Spusťte nejdříve aktualizaci (update).")
        return

    try:
        with open(CESTA_VERSIONS_JSON, "r", encoding="utf-8") as f:
            versions_data = json.load(f)
        with open(CESTA_RELEASES_JSON, "r", encoding="utf-8") as f:
            vsechny_releases = json.load(f)
    except json.JSONDecodeError:
        posli_vystup("error", "Lokální datové soubory jsou poškozené.")
        return

    # Vytvoříme si mapování tagů na to, zda jsou na GitHubu označené jako prerelease
    prerelease_map = {r.get("tag_name"): r.get("prerelease", False) for r in vsechny_releases}

    # Najdeme PRVNÍ release, který NENÍ označen jako prerelease. To je náš "Latest" (stabilní release)
    skutecny_latest_tag = None
    for release in vsechny_releases:
        tag = release.get("tag_name")
        # Musí to být verze, pro kterou máme stažený asset link ve versions_data
        if tag in versions_data and not release.get("prerelease", False):
            skutecny_latest_tag = tag
            break
            
    # Pokud by náhodou byly všechny releasy označené jako prerelease, vezmeme jako nouzovku ten úplně první
    if skutecny_latest_tag is None and vsechny_releases:
        for release in vsechny_releases:
            tag = release.get("tag_name")
            if tag in versions_data:
                skutecny_latest_tag = tag
                break

    strukturovany_seznam = []
    # Projdeme verze a přiřadíme jim správný typ
    for verze in versions_data.keys():
        if verze == skutecny_latest_tag:
            typ = "latest"
        elif prerelease_map.get(verze, False):
            typ = "prerelease"
        else:
            typ = "release"
            
        strukturovany_seznam.append({
            "name": verze,
            "type": typ
        })

    if FORMAT_JSON:
        posli_vystup("success", "Seznam všech verzí načten z disku.", {"versions": strukturovany_seznam})
    else:
        print("\n--- Všechny známé verze hry Gamesa ---")
        for polozka in strukturovany_seznam:
            print(f" • {polozka['name']} [{polozka['type']}]")
        print("--------------------------------------\n")

def list_installed_versions():
    """BEZ INTERNETU: Prohledá složku a zjistí, co je fyzicky staženo."""
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
    """Stáhne konkrétní hru na základě odkazu z lokálního datového souboru."""
    if not os.path.exists(CESTA_VERSIONS_JSON):
        posli_vystup("error", "Soubor versions.json neexistuje. Spusťte nejdříve update.")
        return

    try:
        with open(CESTA_VERSIONS_JSON, "r", encoding="utf-8") as f:
            versions_data = json.load(f)
    except Exception:
        posli_vystup("error", "Nepodařilo se načíst lokální soubor versions.json.")
        return
        
    if version not in versions_data:
        posli_vystup("error", f"Verze {version} není v seznamu známých verzí.")
        return

    os.makedirs(SLOZKA_VERSIONS, exist_ok=True)
    vystupni_zip = os.path.join(SLOZKA_VERSIONS, f"Gamesa_{version}.zip")
    cilova_slozka_hry = os.path.join(SLOZKA_VERSIONS, f"Gamesa_{version}")

    if os.path.exists(os.path.join(cilova_slozka_hry, "Gamesa.exe")):
        posli_vystup("success", f"Verze {version} už je nainstalovaná.", {"version": version})
        return

    # Při instalaci záměrně neblokujeme stdout, pokud nejedeme v čistém JSON režimu,
    # aby download.py mohl pohodlně vykreslovat progress bar do konzole.
    stary_stdout = sys.stdout
    if FORMAT_JSON:
        sys.stdout = open(os.devnull, 'w')

    # Pokusíme se o stažení souboru
    try:
        download.file(versions_data[version], vystupni_zip)
    except Exception as e:
        if FORMAT_JSON:
            sys.stdout = stary_stdout
        posli_vystup("error", f"Chyba při stahování souboru: {e}")
        return
    finally:
        if FORMAT_JSON and sys.stdout != stary_stdout:
            sys.stdout = stary_stdout

    # Kontrola staženého archivu
    if not os.path.exists(vystupni_zip) or os.path.getsize(vystupni_zip) == 0:
        posli_vystup("error", "Stažení selhalo (soubor nebyl vytvořen nebo je prázdný).")
        return
    
    # Rozbalení staženého ZIP souboru
    try:
        with zipfile.ZipFile(vystupni_zip, 'r') as zip_ref:
            zip_ref.extractall(cilova_slozka_hry)
        
        # Smazání ZIP souboru po úspěšné instalaci
        if os.path.exists(vystupni_zip):
            os.remove(vystupni_zip)
            
        posli_vystup("success", f"Verze {version} byla úspěšně nainstalována.", {"version": version})
        
    except zipfile.BadZipFile:
        if os.path.exists(vystupni_zip):
            os.remove(vystupni_zip)
        posli_vystup("error", "Stažený soubor ZIP je poškozený.")
    except Exception as e:
        posli_vystup("error", f"Chyba při rozbalování souboru: {e}")

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

def start_version(version: str, parametry: str = f"-launcher --type=CLI --version={cli_version}"):
    """Spustí hru bezpečně, nezávisle a ve správném pracovním adresáři."""
    cilova_slozka_hry = os.path.join(SLOZKA_VERSIONS, f"Gamesa_{version}")
    spustitelny_soubor = os.path.join(cilova_slozka_hry, "Gamesa.exe")
    
    if os.path.exists(spustitelny_soubor):
        try:
            # POUŽIJEME SUBPROCESS:
            # - start_new_session=True zajistí, že hra poběží dál i po zavření launcheru
            # - cwd nastaví pracovní složku přímo do složky hry, takže správně načte assety
            subprocess.Popen(
                [spustitelny_soubor], 
                cwd=cilova_slozka_hry, 
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
            posli_vystup("success", f"Hra verze {version} byla spuštěna.", {"version": version})
        except Exception as e:
            posli_vystup("error", f"Nepodařilo se spustit proces: {e}")
    else:
        posli_vystup("error", f"Spustitelný soubor pro verzi {version} nebyl nalezen.")

if __name__ == "__main__":
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
        else:
            # Pokud voláme akce nad verzí, provedeme překlad zástupného slova 'latest'
            cilova_verze = resolve_version(argumenty[2])
            
            if prikaz == "install":
                install_version(cilova_verze)
            elif prikaz == "uninstall":
                uninstall_version(cilova_verze)
            elif prikaz == "start":
                start_version(cilova_verze)
            else:
                posli_vystup("error", "Neznámý příkaz.")
    else:
        if FORMAT_JSON:
            posli_vystup("error", "Nebyl zadán žádný příkaz.")
        else:
            print("Použití:\n  python main.py <prikaz> [verze] [--json]")