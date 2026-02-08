#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

pip install -q -r requirements.txt

open "http://localhost:5050" 2>/dev/null || xdg-open "http://localhost:5050" 2>/dev/null &
python app.py
