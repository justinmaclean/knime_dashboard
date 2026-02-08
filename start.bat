@echo off
cd /d "%~dp0"

if not exist venv\Scripts\activate.bat (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

pip install -q -r requirements.txt

start http://localhost:5050
python app.py
