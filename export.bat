@echo off
pyinstaller -n gamesa_launcher_cli -i "NONE" .\main.py --noconfirm
del .\godot\assets\bin\* /q /f
copy .\dist\gamesa_launcher_cli\* .\godot\assets\bin\ /y