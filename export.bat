@echo off
pyinstaller -n gamesa_launcher_cli -i "NONE" .\main.py --noconfirm
del .\godot\assets\bin\* /q /f
del .\dist\gamesa_launcher_gui\assets\bin\* /q /f
copy .\dist\gamesa_launcher_cli\* .\godot\assets\bin\ /y
copy .\dist\gamesa_launcher_cli\* .\dist\gamesa_launcher_gui\assets\bin\ /y