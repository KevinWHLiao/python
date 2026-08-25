@echo off
setlocal
cd /d "%~dp0.."
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

python -m PyInstaller --noconfirm --clean ^
  --name NKRO_GhostKey_Test ^
  --windowed ^
  --add-data "config;config" ^
  --distpath dist ^
  --workpath build ^
  main.py
if errorlevel 1 exit /b 1

rem Editable config/logs beside the exe for the production line
xcopy /E /I /Y config "dist\NKRO_GhostKey_Test\config\" >nul
if not exist "dist\NKRO_GhostKey_Test\logs" mkdir "dist\NKRO_GhostKey_Test\logs"

echo.
echo Build output: %cd%\dist\NKRO_GhostKey_Test\
endlocal
