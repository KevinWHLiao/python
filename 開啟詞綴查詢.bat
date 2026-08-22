@echo off
cd /d "%~dp0"
py -3 poe_affix_gui.py
if errorlevel 1 pause
