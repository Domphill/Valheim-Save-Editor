# Builds dist\ValheimSaveEditor.exe. Run from the project folder.
Set-Location $PSScriptRoot
python -m pip install --upgrade pyinstaller
if (-not (Test-Path assets\icon.ico)) { python -m vse.icon assets\icon.ico }
python -m PyInstaller --onefile --windowed --name ValheimSaveEditor --icon assets\icon.ico --clean app.py
