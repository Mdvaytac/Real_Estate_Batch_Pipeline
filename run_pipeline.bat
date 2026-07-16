@echo off
REM Bu fayl Windows Task Scheduler tərəfindən çağırılır.
REM venv-i aktivləşdirib main.py-ı işə salır.

cd /d "%~dp0"
call venv\Scripts\activate.bat
python src\main.py