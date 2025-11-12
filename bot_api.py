from flask import Flask, request, jsonify, send_from_directory
import gspread
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
SHEET_ID = os.getenv("SHEET_ID")

app = Flask(__name__, static_folder='.')

# === Google Sheets: з змінної CREDENTIALS_JSON ===
creds_json = os.getenv("CREDENTIALS_JSON")
if not creds_json:
    raise ValueError("CREDENTIALS_JSON не встановлено! Додай у змінні середовища Railway.")

creds_dict = json.loads(creds_json)
client = gspread.service_account_from_dict(creds_dict)

sh = client.open_by_key(SHEET_ID)
cats_sheet = sh.worksheet("Categories")
trans_sheet = sh.worksheet("Transactions")
pers_sheet = sh.worksheet("Persons")

# === Розподіл витрат ===
HLIB_SHARE = {
    'Квартира': 11000,
    'Еда': 15000,
    'Коты': 3000,
    'Химия': 0,
    'Красота и здоровье': 0,
    'Развлечения': 10000,
    'Такси': 3000,
    'Другое': 3000,
    'Сбережения': 0
}

DARIA_SHARE = {
    'Квартира': 11000,
    'Еда': 5000,
    'Коты': 1000,
    'Химия': 1000,
    'Красота и здоровье': 7000,
    'Развлечения': 5000,
    'Такси': 1000,
    'Другое': 2000,
    'Сбережения': 0
}

# === Завантаження даних ===
def load_data():
    CATS = {}
    OWNERS = {}
    for row in cats_sheet.get_all_values()[1:]:
        if len(row) >= 3 and row[0]:
            CATS[row[0]] = int(row[1])
            OWNERS[row[0]] = row[2]  # shared / Hlib / Daria
    PERSONAL = {row[1]: int(row[2]) for row in pers_sheet.get_all_values()[1:] if len(row) > 2 and row[1]}
    USERS = {int(row[0]): row[1] for row in pers_sheet.get_all_values()[1:] if row[0].isdigit()}
    return CATS, PERSONAL, USERS, OWNERS

CATS, PERSONAL, USERS, OWNERS = load_data()

ALLOWED_IDS = [350174070, 387290608]

# === HTML ===
@app.route('/', methods=['GET'])
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>', methods=['GET'])
def static_files(path):
    return send_from_directory('.', path)

def safe_int(s, default=0):
    try:
        return int(s)
    except (ValueError, TypeError):
        return default

def month_key():
    return datetime.now().strftime("%Y%m")

@app.route('/getCategories', methods=['POST'])
def get_categories():
    user_id = request.json.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    return jsonify({'categories': list(CATS.keys())})

@app.route('/addExpense', methods=['POST'])
def add_expense():
    data = request.json
    user_id = data.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    cat = data.get('cat')
    amount = data.get('amount')
    note = data.get('note', '—')
    person = USERS.get(user_id, 'Невідомий')
    
    if cat not in CATS:
        return jsonify({'error': 'Категорія не існує'})

    cat_owner = OWNERS.get(cat, 'shared')
    
    if cat_owner == 'shared':
        hlib_share = (HLIB_SHARE.get(cat, 0) / CATS[cat]) * amount if CATS[cat] else 0
        daria_share = (DARIA_SHARE.get(cat, 0) / CATS[cat]) * amount if CATS[cat] else 0
    elif cat_owner == 'Hlib':
        hlib_share = amount
        daria_share = 0
    elif cat_owner == 'Daria':
        hlib_share = 0
        daria_share = amount
    else:
        hlib_share = 0
        daria_share = 0

    mk = month_key()
    row = [datetime.now().strftime("%Y-%m-%d %H:%M"), person, cat, amount, note, 0, mk, hlib_share, daria_share]
    trans_sheet.append_row(row)
    
    spent = sum(safe_int(r[3]) for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk and r[2] == cat)
    limit = CATS[cat]
    perc = spent / limit * 100 if limit else 0
    warn = "80%" if 80 <= perc < 100 else "100%" if perc >= 100 else ""
    
    p_spent = sum(safe_int(r[3]) for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk and r[1] == person)
    p_limit = PERSONAL.get(person, 0)
    p_warn = "наближаєтесь" if p_limit and 80 <= p_spent/p_limit*100 < 100 else "перевищення!" if p_limit and p_spent/p_limit*100 >= 100 else ""
    
    message = f"{amount} грн — {cat}\nЗалишок: {limit - spent} ({int(perc)}%) {warn}\n{person}: {p_limit - p_spent}/{p_limit} {p_warn}"
    return jsonify({'message': message})

@app.route('/summary', methods=['POST'])
def summary():
    user_id = request.json.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    mk = month_key()
    rows = [r for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk]
    spent = {c: sum(safe_int(r[3]) for r in rows if r[2] == c) for c in CATS}
    text = "\n".join(
        f"{c}: {lim - spent.get(c,0)} / {lim} ({int(spent.get(c,0)/lim*100)}%) {'80%' if 80<=spent.get(c,0)/lim*100<100 else '100%' if spent.get(c,0)/lim*100>=100 else ''}"
        for c, lim in CATS.items() if lim > 0
    )
    total = sum(spent.values())
    g_spent = sum(safe_int(r[7]) for r in rows if len(r) > 7)
    d_spent = sum(safe_int(r[8]) for r in rows if len(r) > 8)
    g_balance = 45000 - g_spent
    d_balance = 33000 - d_spent
    summary_text = f"{text}\n\nРазом: {total} грн\nГліб: {g_balance}/45000\nДарʼя: {d_balance}/33000"
    return jsonify({'summary': summary_text})

@app.route('/balance', methods=['POST'])
def balance():
    user_id = request.json.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    mk = month_key()
    rows = [r for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk]
    g_spent = sum(safe_int(r[7]) for r in rows if len(r) > 7)
    d_spent = sum(safe_int(r[8]) for r in rows if len(r) > 8)
    g_balance = 45000 - g_spent
    d_balance = 33000 - d_spent
    return jsonify({'balance': f"Гліб: {g_balance}/45000\nДарʼя: {d_balance}/33000"})

@app.route('/undo', methods=['POST'])
def undo():
    user_id = request.json.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    person = USERS.get(user_id, '')
    if not person:
        return jsonify({'message': 'Ти не в базі'})
    rows = trans_sheet.get_all_values()
    mk = month_key()
    for i in range(len(rows)-1, 0, -1):
        r = rows[i]
        if len(r) > 6 and r[1] == person and r[6] == mk:
            trans_sheet.delete_rows(i+1)
            return jsonify({'message': 'Видалено'})
    return jsonify({'message': 'Немає транзакцій'})

@app.route('/last5', methods=['POST'])
def last5():
    user_id = request.json.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    rows = trans_sheet.get_all_values()[1:][-5:][::-1]
    text = "\n".join(
        f"{r[0].split()[0]} – {r[2]} – {r[3]} – {r[1]} – \"{r[4]}\"" 
        for r in rows if len(r) > 4
    ) or "Пусто"
    return jsonify({'last': text})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
EOF
