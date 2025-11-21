from flask import Flask, request, jsonify, send_file
import gspread
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
SHEET_ID = os.getenv("SHEET_ID")

app = Flask(__name__)

creds_json = os.getenv("CREDENTIALS_JSON")
if not creds_json:
    raise ValueError("CREDENTIALS_JSON не встановлено!")
creds_dict = json.loads(creds_json)
client = gspread.service_account_from_dict(creds_dict)

sh = client.open_by_key(SHEET_ID)
cats_sheet = sh.worksheet("Categories")
trans_sheet = sh.worksheet("Transactions")
pers_sheet = sh.worksheet("Persons")
cont_sheet = sh.worksheet("Contributions")

def safe_int(s, default=0):
    try:
        return int(s) if s.strip() else default
    except (ValueError, TypeError):
        return default

def load_data():
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

@app.route('/', methods=['GET'])
def index():
    return send_file('index.html')

@app.route('/getCategories', methods=['POST'])
def get_categories():
    if not check_user():
        return jsonify({'error': 'Доступ заборонено'}), 403
    CATS, PERSONAL, USERS, CONTRIBUTIONS = load_data()  # Оновлюємо дані
    return jsonify({'categories': list(CATS.keys())})

@app.route('/addExpense', methods=['POST'])
def add_expense():
    user_id = check_user()
    if not user_id:
        return jsonify({'error': 'Доступ заборонено'}), 403
    CATS, PERSONAL, USERS, CONTRIBUTIONS = load_data()  # Оновлюємо дані
    data = request.json
    cat = data.get('cat')
    amount = int(data.get('amount', 0))
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
    if not check_user():
        return jsonify({'error': 'Доступ заборонено'}), 403
    CATS, PERSONAL, USERS, CONTRIBUTIONS = load_data()  # Оновлюємо дані
    mk = datetime.now().strftime("%Y%m")
    rows = [r for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk]
    spent = {c: sum(safe_int(r[3]) for r in rows if r[2] == c) for c in CATS}
    text = "\n".join(
        f"{c}: {spent.get(c,0)} / {limit} ({int(spent.get(c,0)/limit*100)}%) {'80%' if 80<=spent.get(c,0)/limit*100<100 else '100%' if spent.get(c,0)/limit*100>=100 else ''}"
        for c, limit in CATS.items() if limit > 0
    )
    total_spent = sum(spent.values())
    
    g_id = 350174070
    d_id = 387290608
    g_name = USERS.get(g_id, "Hlib")
    d_name = USERS.get(d_id, "Daria")
    g_spent = sum(safe_int(r[3]) for r in rows if r[1] == g_name)
    d_spent = sum(safe_int(r[3]) for r in rows if r[1] == d_name)
    g_limit = PERSONAL.get(g_name, 0)
    d_limit = PERSONAL.get(d_name, 0)
    g_balance = g_limit - g_spent
    d_balance = d_limit - d_spent
    
    summary_text = f"{text}\n\nРазом витрачено: {total_spent} грн\n{g_name}: {g_balance}/{g_limit}\n{d_name}: {d_balance}/{d_limit}"
    return jsonify({'summary': summary_text})

@app.route('/contributions', methods=['POST'])
def contributions():
    if not check_user():
        return jsonify({'error': 'Доступ заборонено'}), 403
    CATS, PERSONAL, USERS, CONTRIBUTIONS = load_data()  # Оновлюємо дані
    
    mk = datetime.now().strftime("%Y%m")
    rows = [r for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk]
    g_spent = sum(safe_int(r[3]) for r in rows if r[1] == "Hlib")
    d_spent = sum(safe_int(r[3]) for r in rows if r[1] == "Daria")
    
    g_contrib = CONTRIBUTIONS.get("Hlib", {})
    d_contrib = CONTRIBUTIONS.get("Daria", {})
    g_balance = PERSONAL.get("Hlib", 0) - g_spent
    d_balance = PERSONAL.get("Daria", 0) - d_spent
    
    text = f"Внесок у бюджет:\nГліб: {g_contrib.get('total', 0)} грн (баланс {g_balance} грн)\n"
    for cat, amount in g_contrib.items():
        if cat != 'total' and amount > 0:
            text += f" - {cat}: {amount} грн\n"
    
    text += f"Дарʼя: {d_contrib.get('total', 0)} грн (баланс {d_balance} грн)\n"
    for cat, amount in d_contrib.items():
        if cat != 'total' and amount > 0:
            text += f" - {cat}: {amount} грн\n"
    
    return jsonify({'contributions': text.strip()})

@app.route('/balance', methods=['POST'])
def balance():
    if not check_user():
        return jsonify({'error': 'Доступ заборонено'}), 403
    mk = datetime.now().strftime("%Y%m")
    rows = [r for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk]
    
    g_id = 350174070
    d_id = 387290608
    g_name = USERS.get(g_id, "Hlib")
    d_name = USERS.get(d_id, "Daria")
    g_spent = sum(safe_int(r[3]) for r in rows if r[1] == g_name)
    d_spent = sum(safe_int(r[3]) for r in rows if r[1] == d_name)
    
    g_limit = PERSONAL.get(g_name, 0)
    d_limit = PERSONAL.get(d_name, 0)
    g_balance = g_limit - g_spent
    d_balance = d_limit - d_spent
    return jsonify({'balance': f"{g_name}: {g_balance}/{g_limit} (залишок)\n{d_name}: {d_balance}/{d_limit} (залишок)"})

@app.route('/undo', methods=['POST'])
def undo():
    user_id = check_user()
    if not user_id:
        return jsonify({'error': 'Доступ заборонено'}), 403
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
    if not check_user():
        return jsonify({'error': 'Доступ заборонено'}), 403
    rows = trans_sheet.get_all_values()[1:][-5:][::-1]
    text = "\n".join(
        f"{r[0].split()[0]} – {r[2]} – {r[3]} – {r[1]} – \"{r[4]}\"" 
        for r in rows if len(r) > 4
    ) or "Пусто"
    return jsonify({'last': text})

@app.route('/getSettings', methods=['POST'])
def get_settings():
    if not check_user():
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    cats = [{"name": c, "limit": l} for c, l in CATS.items()]
    
    g_name = USERS.get(350174070, "Hlib")
    d_name = USERS.get(387290608, "Daria")
    limits = {
        "Гліб": PERSONAL.get(g_name, 0),
        "Дарʼя": PERSONAL.get(d_name, 0)
    }
    
    return jsonify({
        'categories': cats,
        'limits': limits
    })

@app.route('/updateLimit', methods=['POST'])
def update_limit():
    user_id = check_user()
    if not user_id:
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    data = request.json
    type_ = data.get('type')  # 'category' or 'person'
    name = data.get('name')
    value = safe_int(data.get('value', 0))
    
    if type_ == 'category':
        if name not in CATS:
            return jsonify({'error': 'Категорія не існує'})
        row = cats_sheet.find(name).row
        cats_sheet.update_cell(row, 2, value)
        CATS[name] = value
    elif type_ == 'person':
        person_name = USERS.get(user_id)
        if name not in ["Гліб", "Дарʼя"]:
            return jsonify({'error': 'Невірне імʼя'})
        row = pers_sheet.find(name).row
        pers_sheet.update_cell(row, 3, value)
        PERSONAL[name] = value
    else:
        return jsonify({'error': 'Невірний тип'})
    
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
