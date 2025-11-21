from flask import Flask, request, jsonify, send_from_directory
import gspread
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
SHEET_ID = os.getenv("SHEET_ID")

app = Flask(__name__, static_folder='.')

creds_json = os.getenv("CREDENTIALS_JSON")
if not creds_json:
    raise ValueError("CREDENTIALS_JSON не встановлено!")
creds_dict = json.loads(creds_json)
client = gspread.service_account_from_dict(creds_dict)

sh = client.open_by_key(SHEET_ID)

def safe_int(s, default=0):
    try:
        return int(s) if s.strip() else default
    except (ValueError, TypeError):
        return default

def load_data():
    cats_sheet = sh.worksheet("Categories")
    trans_sheet = sh.worksheet("Transactions")
    pers_sheet = sh.worksheet("Persons")
    cont_sheet = sh.worksheet("Contributions")

    CATS = {row[0]: int(row[1]) for row in cats_sheet.get_all_values()[1:] if len(row) >= 2 and row[0]}
    PERSONAL = {row[1]: int(row[2]) for row in pers_sheet.get_all_values()[1:] if len(row) > 2 and row[1]}
    USERS = {int(row[0]): row[1] for row in pers_sheet.get_all_values()[1:] if row[0].isdigit()}
    
    CONTRIBUTIONS = {}
    for row in cont_sheet.get_all_values()[1:]:
        if len(row) >= 11 and row[0]:
            name = row[0]
            CONTRIBUTIONS[name] = {
                'total': safe_int(row[1]),
                'Квартира': safe_int(row[2]),
                'Еда': safe_int(row[3]),
                'Коты': safe_int(row[4]),
                'Химия': safe_int(row[5]),
                'Красота и здоровье': safe_int(row[6]),
                'Развлечения': safe_int(row[7]),
                'Такси': safe_int(row[8]),
                'Другое': safe_int(row[9]),
                'Сбережения': safe_int(row[10])
            }
    return CATS, PERSONAL, USERS, CONTRIBUTIONS

# ... (решта коду — addExpense, summary, contributions, etc.) ...

# У кожному маршруті — оновлюємо дані
@app.route('/summary', methods=['POST'])
def summary():
    CATS, PERSONAL, USERS, CONTRIBUTIONS = load_data()  # ← ДИНАМІЧНО ОНОВЛЮЄМО
    if not check_user():
        return jsonify({'error': 'Доступ заборонено'}), 403
    # ... (решта функції) ...

# Аналогічно для інших маршрутів: addExpense, contributions, etc. — додай CATS, PERSONAL, USERS, CONTRIBUTIONS = load_data() на початку

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
