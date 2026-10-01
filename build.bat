@echo off
REM Builds dist\WebsiteBlocker.exe  (run from this folder on Windows)
python -m pip install --upgrade pyinstaller pillow || goto :err
python tools\make_icon.py || goto :err
pyinstaller --noconfirm --onefile --noconsole --uac-admin --name WebsiteBlocker --icon assets\icon.ico main.py || goto :err
echo.
echo Done: dist\WebsiteBlocker.exe
goto :eof
:err
echo Build failed.
exit /b 1
