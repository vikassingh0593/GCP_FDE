# 1. Activate the environment created by setup.sh
source .venv/bin/activate

# 2. Confirm which Python is running
which python
python --version

# Expected:
# .../01_google_native_production_rag/.venv/bin/python


# 3. Check whether Document AI is installed in THIS environment
python -m pip show google-cloud-documentai


# 4. Test the import directly
python -c "from google.cloud import documentai; print('Document AI import OK')"

python -m pip install --upgrade google-cloud-documentai

python -c "from google.cloud import documentai; print('Document AI import OK')"

