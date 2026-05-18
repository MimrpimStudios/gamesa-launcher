import requests
import json as json_lib
import os
import sys

def file(url: str, output_file: str, format_json: bool = False):
    temporary_file = output_file + ".tmp"
    
    try:
        response = requests.get(url, stream=True)

        if response.status_code == 200:
            total_size = response.headers.get('content-length')
            
            directory = os.path.dirname(output_file)
            if directory:
                os.makedirs(directory, exist_ok=True)

            with open(temporary_file, 'wb') as f:
                if total_size is None:
                    if format_json:
                        print(json_lib.dumps({"status": "progress", "percent": -1}))
                        sys.stdout.flush()
                    else:
                        print("Downloading (file size unknown)...")
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                else:
                    total_size = int(total_size)
                    downloaded = 0
                    last_percentage = -1
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        percentage = int((downloaded / total_size) * 100)
                        
                        # Only prints progress if the percentage changed
                        if percentage != last_percentage:
                            last_percentage = percentage
                            if format_json:
                                print(json_lib.dumps({"status": "progress", "percent": percentage}))
                                sys.stdout.flush()
                            else:
                                bar_length = 100
                                filled = int(bar_length * downloaded / total_size)
                                bar = '█' * filled + '░' * (bar_length - filled)
                                sys.stdout.write(f"\rDownloading: [{bar}] {percentage}% ({downloaded // 1024} KB / {total_size // 1024} KB)")
                                sys.stdout.flush()
            
            if not format_json:
                print()

            if os.path.exists(temporary_file):
                os.replace(temporary_file, output_file)
                if not format_json:
                    print(f"File was successfully downloaded and replaced: '{output_file}'")
        else:
            if format_json:
                print(json_lib.dumps({"status": "error", "message": f"HTTP status: {response.status_code}"}))
                sys.stdout.flush()
            else:
                print(f"Download error. HTTP status: {response.status_code}")
            if os.path.exists(temporary_file):
                os.remove(temporary_file)
                
    except Exception as e:
        if format_json:
            print(json_lib.dumps({"status": "error", "message": str(e)}))
            sys.stdout.flush()
        else:
            print(f"\nNetwork or write error: {e}")
        if os.path.exists(temporary_file):
            os.remove(temporary_file)

def json(url: str, output_file: str):
    try:
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            
            directory = os.path.dirname(output_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
                
            with open(output_file, "w", encoding="utf-8") as f:
                json_lib.dump(data, f, ensure_ascii=False, indent=4)
        else:
            print(f"Error loading JSON. HTTP status: {response.status_code}")
    except Exception as e:
        print(f"Network error while loading JSON: {e}")