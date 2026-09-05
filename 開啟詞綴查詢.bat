@echo off
cd /d "%~dp0"
py -3 -c "import customtkinter" 2>nul
if errorlevel 1 (
  echo Installing customtkinter...
  py -3 -m pip install -r requirements.txt
)
py -3 poe_affix_gui.py
if errorlevel 1 pause
