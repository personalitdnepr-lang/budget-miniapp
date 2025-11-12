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
cats_sheet = sh.worksheet("Categories")
trans_sheet = sh.worksheet("Transactions")
pers_sheet = sh.worksheet("Persons")

def load_data():
    CATS = {row[0]: int(row[1]) for row in cats_sheet.get_all_values()[1:] if len(row) >= 2 and row[0]}
    PERSONAL = {row[1]: int(row[2]) for row in pers_sheet.get_all_values()[1:] if len(row) > 2 and row[1]}
    USERS = {int(row[0]): row[1] for row in pers_sheet.get_all_values()[1:] if row[0].isdigit()}
    return CATS, PERSONAL, USERS

CATS, PERSONAL, USERS = load_data()

ALLOWED_IDS = ['350174070', '387290608']

@app.route('/<action>', methods=['POST'])
def api_handler(action):
    user_id = request.json.get('userId', '0')
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'}), 403
    # ... решта логіки

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

    mk = datetime.now().strftime("%Y%m")
    row = [datetime.now().strftime("%Y-%m-%d %H:%M"), person, cat, amount, note, 0, mk]
    trans_sheet.append_row(row)
    
    spent = sum(safe_int(r[3]) for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk and r[2] == cat)
    limit = CATS[cat]
    balance = limit - spent
    perc = spent / limit * 100 if limit else 0
    warn = "80%" if 80 <= perc < 100 else "100%" if perc >= 100 else ""
    
    p_spent = sum(safe_int(r[3]) for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk and r[1] == person)
    p_limit = PERSONAL.get(person, 0)
    p_balance = p_limit - p_spent
    p_warn = "наближаєтесь" if p_limit and 80 <= p_spent/p_limit*100 < 100 else "перевищення!" if p_limit and p_spent/p_limit*100 >= 100 else ""
    
    message = f"{amount} грн — {cat}\nБаланс: {balance} ({int(perc)}%) {warn}\n{person}: {p_balance}/{p_limit} {p_warn}"
    return jsonify({'message': message})

@app.route('/summary', methods=['POST'])
def summary():
    user_id = request.json.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    mk = datetime.now().strftime("%Y%m")
    rows = [r for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk]
    spent = {c: sum(safe_int(r[3]) for r in rows if r[2] == c) for c in CATS}
    text = "\n".join(
        f"{c}: {limit - spent.get(c,0)} / {limit} ({int(spent.get(c,0)/limit*100)}%) {'80%' if 80<=spent.get(c,0)/limit*100<100 else '100%' if spent.get(c,0)/limit*100>=100 else ''}"
        for c, limit in CATS.items() if limit > 0
    )
    total_spent = sum(spent.values())
    g_spent = sum(safe_int(r[3]) for r in rows if r[1] == "Гліб")
    d_spent = sum(safe_int(r[3]) for r in rows if r[1] == "Дарʼя")
    g_balance = 45000 - g_spent
    d_balance = 33000 - d_spent
    summary_text = f"{text}\n\nРазом витрачено: {total_spent} грн\nГліб: {g_balance}/45000\nДарʼя: {d_balance}/33000"
    return jsonify({'summary': summary_text})

@app.route('/balance', methods=['POST'])
def balance():
    user_id = request.json.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    mk = datetime.now().strftime("%Y%m")
    rows = [r for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk]
    g_spent = sum(safe_int(r[3]) for r in rows if r[1] == "Гліб")
    d_spent = sum(safe_int(r[3]) for r in rows if r[1] == "Дарʼя")
    g_balance = 45000 - g_spent
    d_balance = 33000 - d_spent
    return jsonify({'balance': f"Гліб: {g_balance}/45000 (залишок)\nДарʼя: {d_balance}/33000 (залишок)"})

@app.route('/undo', methods=['POST'])
def undo():
    user_id = request.json.get('userId', 0)
    if user_id not in ALLOWED_IDS:
        return jsonify({'error': 'Доступ заборонено'})
    person = USERS.get(user_id, '')
    if not person:
        return jsonify({'message': 'Ти не в базі'})
    rows = trans_sheet.get_all_values()
    mk = datetime.now().strftime("%Y%m")
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
