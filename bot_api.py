
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

        if len(row) >= 11 and row[0]:  # +1 колонка Savings

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

                'Сбережения': safe_int(row[10])  # Нова колонка

            }

    return CATS, PERSONAL, USERS, CONTRIBUTIONS

CATS, PERSONAL, USERS, CONTRIBUTIONS = load_data()

ALLOWED_IDS = [350174070, 387290608]

@app.route('/', methods=['GET'])

def index():

    return send_from_directory('.', 'index.html')

@app.route('/<path:path>', methods=['GET'])

def static_files(path):

    return send_from_directory('.', path)

def check_user():

    user_id = request.json.get('userId', 0)

    try:

        user_id = int(user_id)

    except:

        return None

    if user_id not in ALLOWED_IDS:

        return None

    return user_id

@app.route('/getCategories', methods=['POST'])

def get_categories():

    if not check_user():

        return jsonify({'error': 'Доступ заборонено'}), 403

    return jsonify({'categories': list(CATS.keys())})

@app.route('/addExpense', methods=['POST'])

def add_expense():

    user_id = check_user()

    if not user_id:

        return jsonify({'error': 'Доступ заборонено'}), 403

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

    

    contrib_data = {}

    for row in cont_sheet.get_all_values()[1:]:

        if len(row) >= 11 and row[0]:

            name = row[0]

            contrib_data[name] = {

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

    

    g_contrib = contrib_data.get(g_name, {})

    d_contrib = contrib_data.get(d_name, {})

    

    text = f"Внесок у бюджет:\n{g_name}: {g_contrib.get('total', 0)} грн (баланс {g_balance} грн)\n"

    for cat, amount in g_contrib.items():

        if cat != 'total' and amount > 0:

            text += f" - {cat}: {amount} грн\n"

    

    text += f"{d_name}: {d_contrib.get('total', 0)} грн (баланс {d_balance} грн)\n"

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

if __name__ == '__main__':

    port = int(os.environ.get("PORT", 5000))

    app.run(host='0.0.0.0', port=port, debug=False)

@app.route('/getSettings', methods=['POST']) def get_settings():     if not check_user():         return jsonify({'error': 'Доступ заборонено'}), 403

    # Категорії     cats = [{"name": c, "limit": l} for c, l in CATS.items()]

    # Ліміти     g_name = USERS.get(350174070, "Hlib")     d_name = USERS.get(387290608, "Daria")     limits = {         "Гліб": PERSONAL.get(g_name, 0),         "Дарʼя": PERSONAL.get(d_name, 0)     }

    return jsonify({         'categories': cats,         'limits': limits     })

@app.route('/updateLimit', methods=['POST']) def update_limit():     user_id = check_user()     if not user_id:         return jsonify({'error': 'Доступ заборонено'}), 403

    data = request.json     type_ = data.get('type')  # 'category' or 'person'     name = data.get('name')     value = int(data.get('value', 0))

    if type_ == 'category':         if name not in CATS:             return jsonify({'error': 'Категорія не існує'})         # Оновлюємо в Google Sheets         row = cats_sheet.find(name).row         cats_sheet.update_cell(row, 2, value)         CATS[name] = value     elif type_ == 'person':         person_name = USERS.get(user_id)         if name not in ["Гліб", "Дарʼя"]:             return jsonify({'error': 'Невірне імʼя'})         # Оновлюємо в Google Sheets         row = pers_sheet.find(name).row         pers_sheet.update_cell(row, 3, value)         PERSONAL[name] = value     else:         return jsonify({'error': 'Невірний тип'})

    return jsonify({'success': True})

if __name__ == '__main__':     port = int(os.environ.get("PORT", 5000))     app.run(host='0.0.0.0', port=port, debug=False) EOF
cat > index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Бюджет</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      --bg: var(--tg-theme-bg-color, #fff);
      --text: var(--tg-theme-text-color, #000);
      --hint: var(--tg-theme-hint-color, #999);
      --btn: var(--tg-theme-button-color, #2481cc);
      --btn-text: var(--tg-theme-button-text-color, #fff);
      --secondary: var(--tg-theme-secondary-bg-color, #f0f0f0);
      --border: var(--tg-theme-hint-color, #e0e0e0);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: var(--bg); color: var(--text); padding: 20px; min-height: 100vh;
      line-height: 1.5;
    }
    .header { 
      font-size: 24px; font-weight: 700; text-align: center; margin-bottom: 24px; 
      background: linear-gradient(135deg, var(--btn), #1a73e8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 16px; margin-bottom: 24px; }
    button {
      background: linear-gradient(135deg, var(--btn), #1a5fd7); color: var(--btn-text); border: none; padding: 16px;
      border-radius: 16px; font-size: 16px; font-weight: 600; cursor: pointer;
      transition: all 0.3s ease; text-align: center; box-shadow: 0 4px 12px rgba(36, 129, 204, 0.2);
    }
    button:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(36, 129, 204, 0.3); }
    button:active { opacity: 0.9; transform: translateY(0); }
    .output {
      background: var(--secondary); padding: 20px; border-radius: 16px;
      font-size: 15px; white-space: pre-line; min-height: 80px; color: var(--text);
      box-shadow: 0 2px 8px rgba(0,0,0,0.1); border: 1px solid var(--border);
    }
    .popup { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; backdrop-filter: blur(4px); }
    .popup-content { background: var(--bg); padding: 24px; border-radius: 20px; width: 90%; max-width: 400px; box-shadow: 0 20px 40px rgba(0,0,0,0.2); transform: scale(0.95); animation: popupIn 0.3s ease; }
    @keyframes popupIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
    .input { width: 100%; padding: 14px; margin: 12px 0; border: 1px solid var(--border); border-radius: 12px; font-size: 16px; transition: border-color 0.3s; }
    .input:focus { border-color: var(--btn); outline: none; }
    .btn-group { display: flex; gap: 12px; margin-top: 20px; }
    .btn { flex: 1; padding: 14px; border-radius: 12px; font-weight: 600; cursor: pointer; transition: all 0.3s; }
    .btn-primary { background: linear-gradient(135deg, var(--btn), #1a5fd7); color: var(--btn-text); }
    .btn-secondary { background: var(--secondary); color: var(--text); border: 1px solid var(--border); }
    .btn:hover { transform: translateY(-1px); }
    .hidden { display: none; }
    .user-info { text-align: center; margin-bottom: 16px; font-size: 14px; color: var(--hint); }
    .settings-item { margin: 12px 0; display: flex; justify-content: space-between; align-items: center; }
    .settings-item input { width: 80px; padding: 8px; border-radius: 8px; border: 1px solid var(--border); }
    .settings-item button { padding: 8px 12px; font-size: 12px; }
  </style>
</head>
<body>
  <div class="user-info">
    Привіт, <span id="userName">Гліб</span>!
  </div>
  <div class="header">Бюджет</div>
  <div class="grid">
    <button onclick="showAdd()">Додати витрату</button>
    <button onclick="showSummary()">Підсумок</button>
    <button onclick="showBalance()">Баланс</button>
    <button onclick="undoLast()">Скасувати</button>
    <button onclick="showLast()">Останні</button>
    <button onclick="showContributions()">Внесок</button>
    <button onclick="showSettings()">Налаштування</button>
  </div>
  <div id="output" class="output">Завантаження...</div>

  <!-- Popup для додавання витрати -->
  <div id="addPopup" class="popup hidden">
    <div class="popup-content">
      <h3>Додати витрату</h3>
      <select id="categorySelect" class="input">
        <option value="">— Завантаження... —</option>
      </select>
      <input type="number" id="amountInput" placeholder="Сума (грн)" class="input" min="1">
      <input type="text" id="noteInput" placeholder="Нотатка (необов'язково)" class="input">
      <div class="btn-group">
        <button class="btn btn-secondary" onclick="hidePopup('addPopup')">Скасувати</button>
        <button class="btn btn-primary" onclick="saveExpense()">Додати</button>
      </div>
    </div>
  </div>

  <!-- Новий popup для налаштувань -->
  <div id="settingsPopup" class="popup hidden">
    <div class="popup-content">
      <h3>Налаштування</h3>
      <div id="settingsContent">Завантаження...</div>
      <div class="btn-group">
        <button class="btn btn-secondary" onclick="hidePopup('settingsPopup')">Закрити</button>
        <button class="btn btn-primary" onclick="saveSettings()">Оновити</button>
      </div>
    </div>
  </div>

  <script>
    const tg = window.Telegram.WebApp;
    tg.ready(); tg.expand();

    const API_URL = '';
    const userId = tg.initDataUnsafe?.user?.id?.toString() || '0';
    const ID_TO_NAME = { '350174070': 'Гліб', '387290608': 'Дарʼя' };
    const userName = ID_TO_NAME[userId] || 'Користувач';

    document.getElementById('userName').textContent = userName;

    async function api(action, data = {}) {
      data.action = action; data.userId = userId;
      try {
        const res = await fetch(API_URL + '/' + action, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });
        return await res.json();
      } catch (err) {
        return { error: 'Сервер недоступний' };
      }
    }

    async function loadCategories() {
      const res = await api('getCategories');
      const select = document.getElementById('categorySelect');
      select.innerHTML = '<option value="">— Оберіть —</option>';
      if (res.categories && res.categories.length > 0) {
        res.categories.forEach(cat => {
          const opt = document.createElement('option');
          opt.value = cat; opt.textContent = cat;
          select.appendChild(opt);
        });
      } else {
        select.innerHTML += '<option value="">Немає категорій</option>';
      }
    }

    function showPopup(id) {
      document.getElementById(id).classList.remove('hidden');
      if (id === 'addPopup') loadCategories();
    }

    function hidePopup(id) {
      document.getElementById(id).classList.add('hidden');
    }

    window.showAdd = () => showPopup('addPopup');
    window.showSummary = async () => {
      document.getElementById('output').innerText = 'Завантаження...';
      const res = await api('summary');
      document.getElementById('output').innerText = res.summary || res.error || 'Пусто';
    };
    window.showBalance = async () => {
      document.getElementById('output').innerText = 'Завантаження...';
      const res = await api('balance');
      document.getElementById('output').innerText = res.balance || 'Помилка';
    };
    window.undoLast = async () => {
      const res = await api('undo');
      tg.showAlert(res.message || 'Готово');
      showSummary();
    };
    window.showLast = async () => {
      document.getElementById('output').innerText = 'Завантаження...';
      const res = await api('last5');
      document.getElementById('output').innerText = res.last || 'Пусто';
    };
    window.showContributions = async () => {
      document.getElementById('output').innerText = 'Завантаження...';
      const res = await api('contributions');
      document.getElementById('output').innerText = res.contributions || res.error || 'Пусто';
    };

    // Налаштування
    let settingsData = {};
    window.showSettings = async () => {
      document.getElementById('settingsPopup').classList.remove('hidden');
      const res = await api('getSettings');
      if (res.error) {
        document.getElementById('settingsContent').innerText = res.error;
        return;
      }
      settingsData = res;
     
      let html = "<h4>Категорії:</h4>";
      res.categories.forEach(cat => {
        html += `<div class="settings-item">
          <span>${cat.name}:</span>
          <input type="number" data-type="category" data-name="${cat.name}" value="${cat.limit}">
          <button onclick="updateSingle('category', '${cat.name}', this.previousElementSibling.value)">ОК</button>
        </div>`;
      });
     
      html += "<h4>Ліміти:</h4>";
      html += `<div class="settings-item">
        <span>Гліб:</span>
        <input type="number" data-type="person" data-name="Гліб" value="${res.limits['Гліб']}">
        <button onclick="updateSingle('person', 'Гліб', this.previousElementSibling.value)">ОК</button>
      </div>`;
      html += `<div class="settings-item">
        <span>Дарʼя:</span>
        <input type="number" data-type="person" data-name="Дарʼя" value="${res.limits['Дарʼя']}">
        <button onclick="updateSingle('person', 'Дарʼя', this.previousElementSibling.value)">ОК</button>
      </div>`;
     
      document.getElementById('settingsContent').innerHTML = html;
    };
    async function updateSingle(type, name, input) {
      const value = parseInt(input.value);
      if (isNaN(value) || value < 0) return tg.showAlert('Невірне значення');
     
      const res = await api('updateLimit', { type, name, value });
      if (res.success) {
        tg.showAlert('Оновлено!');
        showSummary();
      } else {
        tg.showAlert(res.error || 'Помилка');
      }
    }
    async function saveSettings() {
      tg.showAlert('Використовуйте "ОК" біля кожного поля');
    }

    async function saveExpense() {
      const cat = document.getElementById('categorySelect').value;
      const amount = document.getElementById('amountInput').value;
      const note = document.getElementById('noteInput').value || '.';
      
      if (!cat || !amount || amount <= 0) {
        tg.showAlert('Заповніть суму та категорію');
        return;
      }

      const res = await api('addExpense', { cat, amount, note });
      tg.showAlert(res.message || res.error || 'Додано');
      hidePopup('addPopup');
      showSummary();
    }

    showSummary();
  </script>
</body>
</html>
