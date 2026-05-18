import os
import json
import download_launcher
import platformdirs
import sys
import zipfile
import shutil
import subprocess


cli_version = "1.0.0.0"
APPDATA = platformdirs.user_data_dir("Gamesa_launcher")
os.makedirs(APPDATA, exist_ok=True)

VERSIONS_JSON_PATH = os.path.join(APPDATA, "versions.json")
RELEASES_JSON_PATH = os.path.join(APPDATA, "releases.json")
VERSIONS_DIR = os.path.join(APPDATA, "Versions")

FORMAT_JSON = "--json" in sys.argv

def send_output(status: str, message: str, data: dict = None):
    """Helper function for unified output to Godot (JSON) or the console."""
    if FORMAT_JSON:
        output = {
            "status": status,
            "message": message,
            "data": data if data is not None else {}
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.stdout.flush()
    else:
        if status == "error":
            print(f"Error: {message}")
        else:
            print(message)
            
    # If an error occurs in the CLI, we terminate the process with an error code
    if status == "error":
        sys.exit(1)

def resolve_version(version: str) -> str:
    """If 'latest' is specified, looks up and returns the actual latest stable tag."""
    if version.lower() != "latest":
        return version

    if not os.path.exists(VERSIONS_JSON_PATH) or not os.path.exists(RELEASES_JSON_PATH):
        send_output("error", "The version list is empty. Please run update first.")
        return version

    try:
        with open(VERSIONS_JSON_PATH, "r", encoding="utf-8") as f:
            versions_data = json.load(f)
        with open(RELEASES_JSON_PATH, "r", encoding="utf-8") as f:
            all_releases = json.load(f)
    except Exception:
        send_output("error", "Failed to load local files to determine the 'latest' version.")
        return version

    # Find the first stable version that is not a prerelease and has a matching asset
    actual_latest_tag = None
    for release in all_releases:
        tag = release.get("tag_name")
        if tag in versions_data and not release.get("prerelease", False):
            actual_latest_tag = tag
            break
            
    # Fallback plan: if all are pre-releases, take the very first available version
    if actual_latest_tag is None and all_releases:
        for release in all_releases:
            tag = release.get("tag_name")
            if tag in versions_data:
                actual_latest_tag = tag
                break

    if actual_latest_tag:
        return actual_latest_tag
    
    return version

def load_versions():
    """This command is the ONLY one downloading from the internet. It fetches ALL GitHub releases."""
    old_stdout = sys.stdout
    if FORMAT_JSON:
        sys.stdout = open(os.devnull, 'w')

    try:
        # Fetching the complete list of all releases from the mimrpimstudios repository
        download_launcher.json("https://api.github.com/repos/mimrpimstudios/gamesa/releases", RELEASES_JSON_PATH)
    except Exception as e:
        sys.stdout = old_stdout
        send_output("error", f"Network error during GitHub API communication: {e}")
        return
    finally:
        if FORMAT_JSON:
            sys.stdout = old_stdout

    if not os.path.exists(RELEASES_JSON_PATH):
        send_output("error", "Failed to verify versions from the internet.")
        return
    
    try:
        with open(RELEASES_JSON_PATH, "r", encoding="utf-8") as f:
            all_releases = json.load(f)
    except json.JSONDecodeError:
        send_output("error", "The GitHub version file is corrupted.")
        return

    result_dict = {}

    # Go through all found releases from newest to oldest
    for release in all_releases:
        version = release.get("tag_name")
        for asset in release.get("assets", []):
            if asset.get("name") == "Gamesa.zip":
                link = asset.get("browser_download_url")
                result_dict[version] = link
                break  # Once we find Gamesa.zip, we jump to the next release

    # Save the complete list of all versions to a local file
    with open(VERSIONS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=4, ensure_ascii=False)
        
    version_count = len(result_dict)
    send_output("success", f"Version list successfully updated. Found {version_count} versions.", {"total_versions": version_count})

def list_versions():
    """OFFLINE ONLY: Simply opens local files and returns ALL saved versions structured for Godot."""
    if not os.path.exists(VERSIONS_JSON_PATH) or not os.path.exists(RELEASES_JSON_PATH):
        send_output("error", "The version list is empty. Please run update first.")
        return

    try:
        with open(VERSIONS_JSON_PATH, "r", encoding="utf-8") as f:
            versions_data = json.load(f)
        with open(RELEASES_JSON_PATH, "r", encoding="utf-8") as f:
            all_releases = json.load(f)
    except json.JSONDecodeError:
        send_output("error", "Local data files are corrupted.")
        return

    # Create a mapping of tags to see whether they are marked as prerelease on GitHub
    prerelease_map = {r.get("tag_name"): r.get("prerelease", False) for r in all_releases}

    # Find the FIRST release that is NOT marked as a prerelease. This is our "Latest" (stable release)
    actual_latest_tag = None
    for release in all_releases:
        tag = release.get("tag_name")
        # It must be a version we have a downloaded asset link for in versions_data
        if tag in versions_data and not release.get("prerelease", False):
            actual_latest_tag = tag
            break
            
    # If by any chance all releases are marked as prerelease, we take the absolute first one as fallback
    if actual_latest_tag is None and all_releases:
        for release in all_releases:
            tag = release.get("tag_name")
            if tag in versions_data:
                actual_latest_tag = tag
                break

    structured_list = []
    # Loop through versions and assign their respective types
    for version in versions_data.keys():
        if version == actual_latest_tag:
            ver_type = "latest"
        elif prerelease_map.get(version, False):
            ver_type = "prerelease"
        else:
            ver_type = "release"
            
        structured_list.append({
            "name": version,
            "type": ver_type
        })

    if FORMAT_JSON:
        send_output("success", "Loaded all versions from disk.", {"versions": structured_list})
    else:
        print("\n--- All known Gamesa versions ---")
        for item in structured_list:
            print(f" • {item['name']} [{item['type']}]")
        print("---------------------------------\n")

def list_installed_versions():
    """OFFLINE ONLY: Scans the directory and detects what has been physically downloaded."""
    installed = []
    if os.path.exists(VERSIONS_DIR):
        installed = [
            name.replace("Gamesa_", "") 
            for name in os.listdir(VERSIONS_DIR) 
            if os.path.isdir(os.path.join(VERSIONS_DIR, name)) and name.startswith("Gamesa_")
        ]

    if FORMAT_JSON:
        send_output("success", "Installed versions list loaded.", {"installed": installed})
    else:
        if not installed:
            print("No versions are currently installed.")
            return
        print("\n--- Installed versions on PC ---")
        for version in installed:
            print(f" • {version}")
        print("--------------------------------\n")

def install_version(version: str):
    """Downloads a specific game version using the link from the local data file."""
    if not os.path.exists(VERSIONS_JSON_PATH):
        send_output("error", "The file versions.json does not exist. Please run update first.")
        return

    try:
        with open(VERSIONS_JSON_PATH, "r", encoding="utf-8") as f:
            versions_data = json.load(f)
    except Exception:
        send_output("error", "Failed to load local file versions.json.")
        return
        
    if version not in versions_data:
        send_output("error", f"Version {version} is not in the list of known versions.")
        return

    os.makedirs(VERSIONS_DIR, exist_ok=True)
    output_zip = os.path.join(VERSIONS_DIR, f"Gamesa_{version}.zip")
    target_game_dir = os.path.join(VERSIONS_DIR, f"Gamesa_{version}")

    if os.path.exists(os.path.join(target_game_dir, "Gamesa.exe")):
        send_output("success", f"Version {version} is already installed.", {"version": version})
        return

    # Start the download and pass whether it should run in JSON format
    try:
        download_launcher.file(versions_data[version], output_zip, format_json=FORMAT_JSON)
    except Exception as e:
        send_output("error", f"Error occurred during file download: {e}")
        return

    # Check the downloaded archive
    if not os.path.exists(output_zip) or os.path.getsize(output_zip) == 0:
        send_output("error", "Download failed (file was not created or is empty).")
        return
    
    # Extract the downloaded ZIP file
    try:
        with zipfile.ZipFile(output_zip, 'r') as zip_ref:
            zip_ref.extractall(target_game_dir)
        
        # Delete the ZIP file after a successful installation
        if os.path.exists(output_zip):
            os.remove(output_zip)
            
        send_output("success", f"Version {version} has been successfully installed.", {"version": version})
        
    except zipfile.BadZipFile:
        if os.path.exists(output_zip):
            os.remove(output_zip)
        send_output("error", "The downloaded ZIP file is corrupted.")
    except Exception as e:
        send_output("error", f"Error occurred during file extraction: {e}")

def uninstall_version(version: str):
    """Deletes the game directory from the disk."""
    target_game_dir = os.path.join(VERSIONS_DIR, f"Gamesa_{version}")
    
    if os.path.exists(target_game_dir) and os.path.isdir(target_game_dir):
        try:
            shutil.rmtree(target_game_dir)
            send_output("success", f"Version {version} was successfully removed.", {"version": version})
        except Exception as e:
            send_output("error", f"Error occurred during directory deletion: {e}")
    else:
        send_output("error", f"Version {version} is not installed.")

def start_version(version: str, parameters: str = ""):
    """Safely starts the game independently and within the correct working directory."""
    parameters = parameters.strip() + f" -launcherCLI -versionCLI={cli_version}"
    target_game_dir = os.path.join(VERSIONS_DIR, f"Gamesa_{version}")
    executable_file = os.path.join(target_game_dir, "Gamesa.exe")
    
    if os.path.exists(executable_file):
        try:
            # cwd sets the working directory directly to the game folder so it loads assets correctly
            subprocess.Popen(
                [executable_file] + parameters.split(),
                cwd=target_game_dir,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
            send_output("success", f"Game version {version} has been launched.", {"version": version})
        except Exception as e:
            send_output("error", f"Failed to start the process: {e}")
    else:
        send_output("error", f"Executable for version {version} was not found.")

if __name__ == "__main__":
    arguments = [arg for arg in sys.argv if arg != "--json"]

    if len(arguments) > 1:
        command = arguments[1].lower()
        
        if command == "update":
            load_versions()
        elif command == "versions":
            list_versions()
        elif command == "installed":
            list_installed_versions()
        elif command in ("install", "uninstall", "start") and len(arguments) < 3:
            send_output("error", f"Missing version specification for command '{command}'.")
        else:
            # If we call actions on a version, resolve the 'latest' placeholder alias first
            target_version = resolve_version(arguments[2])
            
            if command == "install":
                install_version(target_version)
            elif command == "uninstall":
                uninstall_version(target_version)
            elif command == "start":
                # Safe handling if parameters for start weren't passed
                parameters = resolve_version(arguments[3]) if len(arguments) > 3 else ""
                start_version(target_version, parameters)
            else:
                send_output("error", "Unknown command.")
    else:
        if FORMAT_JSON:
            send_output("error", "No command was specified.")
        else:
            print("Usage:\n  python main.py <command> [version] [--json]")