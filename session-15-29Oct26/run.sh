python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
source lab.env

pytest -q
python -m app.cli --list
python -m app.cli ORD-1001