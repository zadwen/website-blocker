@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt -r requirements-build.txt || goto :err
python -m unittest discover -s tests -p "test_logic.py" -v || goto :err
python -m unittest discover -s tests -p "test_upgrade.py" -v || goto :err
python -m unittest discover -s tests -p "test_reliability.py" -v || goto :err
python tools\make_icon.py || goto :err
python -m PyInstaller --clean --noconfirm --onefile --noconsole --uac-admin --name WebsiteBlocker --icon assets\icon.ico main.py || goto :err
echo.
echo Done: dist\WebsiteBlocker.exe
exit /b 0
:err
echo Build failed. Read the error above.
exit /b 1
