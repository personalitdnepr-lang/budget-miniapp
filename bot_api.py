from flask import Flask, request, jsonify, send_from_directory
import gspread
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
SHEET_ID = os.getenv("SHEET_ID")

app = Flask(__name__, static_folder='.')

print("Starting bot_api.py...")  # ← ЛОГУВАННЯ
print(f"SHEET_ID: {SHEET_ID}")  # ← Перевірка

# === Google Sheets ===
creds_json = os.getenv("CREDENTIALS_JSON")
if not creds_json:
    print("ERROR: CREDENTIALS_JSON not set!")
    raise ValueError("CREDENTIALS_JSON не встановлено!")

try:
    creds_dict = json.loads(creds_json)
    print("Credentials loaded successfully")
    client = gspread.service_account_from_dict(creds_dict)
except Exception as e:
    print(f"ERROR loading credentials: {e}")
    raise

try:
    sh = client.open_by_key(SHEET_ID)
    print("Google Sheet opened")
except Exception as e:
    print(f"ERROR opening sheet: {e}")
    raise

cats_sheet = sh.worksheet("Categories")
trans_sheet = sh.worksheet("Transactions")
pers_sheet = sh.worksheet("Persons")

# === Дані ===
def load_data():
    CATS = {row[0]: int(row[1]) for row in cats_sheet.get_all_values()[1:] if len(row) >= 2 and row[0]}
    PERSONAL = {row[1]: int(row[2]) for row in pers_sheet.get_all_values()[1:] if len(row) > 2 and row[1]}
    USERS = {int(row[0]): row[1] for row in pers_sheet.get_all_values()[1:] if row[0].isdigit()}
    return CATS, PERSONAL, USERS

CATS, PERSONAL, USERS = load_data()
print(f"Loaded {len(CATS)} categories, {len(USERS)} users")

ALLOWED_IDS = [350174070, 387290608]

# === HTML ===
@app.route('/', methods=['GET'])
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>', methods=['GET'])
def static_files(path):
    return send_from_directory('.', path)

# === API ===
@app.route('/getCategories', methods=['POST'])
def get_categories():
    user_id = request.json.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    return jsonify({'categories': list(CATS.keys())})

# (додай інші маршрути)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Server running on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
