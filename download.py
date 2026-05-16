import requests
import json as json_lib
import os
import sys

def file(url: str, vystupni_soubor: str):
    docasny_soubor = vystupni_soubor + ".tmp"
    
    try:
        # Odeslání požadavku
        response = requests.get(url, stream=True)

        if response.status_code == 200:
            # Zjištění celkové velikosti souboru v bajtech z hlavičky serveru
            total_size = response.headers.get('content-length')
            
            slozka = os.path.dirname(vystupni_soubor)
            if slozka:
                os.makedirs(slozka, exist_ok=True)

            with open(docasny_soubor, 'wb') as f:
                if total_size is None:
                    # Pokud server neposlal velikost, stahujeme bez procent
                    print("Stahování (velikost souboru neznámá)...")
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                else:
                    total_size = int(total_size)
                    downloaded = 0
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Výpočet procent a vykreslení progress baru
                        procenta = int((downloaded / total_size) * 100)
                        delka_baru = 20
                        zaplneno = int(delka_baru * downloaded / total_size)
                        bar = '█' * zaplneno + '░' * (delka_baru - zaplneno)
                        
                        # \r vrátí kurzor na začátek řádku, end='' zabrání odřádkování
                        sys.stdout.write(f"\rStahování: [{bar}] {procenta}% ({downloaded // 1024} KB / {total_size // 1024} KB)")
                        sys.stdout.flush()
            
            # Odřádkování po dokončení cyklu
            print()

            if os.path.exists(docasny_soubor):
                os.replace(docasny_soubor, vystupni_soubor)
                print(f"Soubor byl úspěšně stažen a nahrazen: '{vystupni_soubor}'")
        else:
            print(f"Chyba při stahování. HTTP status: {response.status_code}")
            if os.path.exists(docasny_soubor):
                os.remove(docasny_soubor)
                
    except Exception as e:
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
            print(f"JSON data úspěšně uložena do: '{vystupni_soubor}'")
        else:
            print(f"Chyba při načítání JSON. HTTP status: {response.status_code}")
    except Exception as e:
        print(f"Chyba sítě při načítání JSON: {e}")