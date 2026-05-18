import requests
import json as json_lib
import os
import sys

def file(url: str, vystupni_soubor: str, format_json: bool = False):
    docasny_soubor = vystupni_soubor + ".tmp"
    
    try:
        response = requests.get(url, stream=True)

        if response.status_code == 200:
            total_size = response.headers.get('content-length')
            
            slozka = os.path.dirname(vystupni_soubor)
            if slozka:
                os.makedirs(slozka, exist_ok=True)

            with open(docasny_soubor, 'wb') as f:
                if total_size is None:
                    if format_json:
                        print(json_lib.dumps({"status": "progress", "percent": -1}))
                        sys.stdout.flush()
                    else:
                        print("Stahování (velikost souboru neznámá)...")
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                else:
                    total_size = int(total_size)
                    downloaded = 0
                    posledni_procenta = -1
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        procenta = int((downloaded / total_size) * 100)
                        
                        # Vypíše progres pouze pokud se procento změnilo
                        if procenta != posledni_procenta:
                            posledni_procenta = procenta
                            if format_json:
                                print(json_lib.dumps({"status": "progress", "percent": procenta}))
                                sys.stdout.flush()
                            else:
                                delka_baru = 20
                                zaplneno = int(delka_baru * downloaded / total_size)
                                bar = '█' * zaplneno + '░' * (delka_baru - zaplneno)
                                sys.stdout.write(f"\rStahování: [{bar}] {procenta}% ({downloaded // 1024} KB / {total_size // 1024} KB)")
                                sys.stdout.flush()
            
            if not format_json:
                print()

            if os.path.exists(docasny_soubor):
                os.replace(docasny_soubor, vystupni_soubor)
                if not format_json:
                    print(f"Soubor byl úspěšně stažen a nahrazen: '{vystupni_soubor}'")
        else:
            if format_json:
                print(json_lib.dumps({"status": "error", "message": f"HTTP status: {response.status_code}"}))
                sys.stdout.flush()
            else:
                print(f"Chyba při stahování. HTTP status: {response.status_code}")
            if os.path.exists(docasny_soubor):
                os.remove(docasny_soubor)
                
    except Exception as e:
        if format_json:
            print(json_lib.dumps({"status": "error", "message": str(e)}))
            sys.stdout.flush()
        else:
            print(f"\nChyba sítě nebo zápisu: {e}")
        if os.path.exists(docasny_soubor):
            os.remove(docasny_soubor)

def json(url: str, vystupni_soubor: str):
    try:
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            
            slozka = os.path.dirname(vystupni_soubor)
            if slozka:
                os.makedirs(slozka, exist_ok=True)
                
            with open(vystupni_soubor, "w", encoding="utf-8") as f:
                json_lib.dump(data, f, ensure_ascii=False, indent=4)
        else:
            print(f"Chyba při načítání JSON. HTTP status: {response.status_code}")
    except Exception as e:
        print(f"Chyba sítě při načítání JSON: {e}")