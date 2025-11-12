import os
import asyncio
import gspread
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import re

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# НОВИЙ СПОСІБ — gspread 6+ + google-auth
client = gspread.service_account(filename="credentials.json")
sh = client.open_by_key(SHEET_ID)
cats_sheet = sh.worksheet("Categories")
trans_sheet = sh.worksheet("Transactions")
pers_sheet = sh.worksheet("Persons")

# ЗАХИСТ ВІД ПОМИЛОК У ДАНИХ
def safe_int(s, default=0):
    try:
        return int(s)
    except (ValueError, TypeError):
        return default

# ЗАВАНТАЖЕННЯ ДАНИХ
CATS = {}
for row in cats_sheet.get_all_values()[1:]:
    if len(row) >= 2 and row[0].strip():
        CATS[row[0].strip()] = safe_int(row[1], 0)

PERSONAL = {}
USERS = {}
for row in pers_sheet.get_all_values()[1:]:
    if len(row) >= 3:
        tid = row[0].strip()
        name = row[1].strip()
        limit = safe_int(row[2], 0)
        if tid.isdigit():
            USERS[int(tid)] = name
            PERSONAL[name] = limit

class AddExpense(StatesGroup):
    category = State()
    amount = State()
    note = State()

def month_key():
    return datetime.now().strftime("%Y%m")

def main_menu():
    kb = [
        [types.KeyboardButton(text="Додати витрату"), types.KeyboardButton(text="Підсумок за місяць")],
        [types.KeyboardButton(text="Баланс Гліб / Дарʼя"), types.KeyboardButton(text="Скасувати останню")],
        [types.KeyboardButton(text="Останні транзакції"), types.KeyboardButton(text="Налаштування")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def cat_keyboard():
    kb = [[InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}")] for cat in CATS]
    kb.append([InlineKeyboardButton(text="Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("start"))
async def start(msg: types.Message):
    await msg.answer("Бюджет-бот готовий!", reply_markup=main_menu())

@dp.message(F.text == "Додати витрату")
async def add_expense(msg: types.Message, state: FSMContext):
    if not CATS:
        await msg.answer("Категорії не знайдено. Додай у таблицю.")
        return
    await msg.answer("Оберіть категорію:", reply_markup=cat_keyboard())
    await state.set_state(AddExpense.category)

@dp.callback_query(F.data.startswith("cat_"))
async def cat_selected(cb: CallbackQuery, state: FSMContext):
    cat = cb.data.split("_", 1)[1]
    if cat not in CATS:
        await cb.answer("Категорія недоступна", show_alert=True)
        return
    await state.update_data(category=cat)
    await cb.message.edit_text(f"Введіть суму для {cat}:")
    await state.set_state(AddExpense.amount)
    await cb.answer()

@dp.message(AddExpense.amount)
async def get_amount(msg: types.Message, state: FSMContext):
    if not re.fullmatch(r"\d+", msg.text):
        await msg.answer("Тільки число!")
        return
    amount = int(msg.text)
    if amount <= 0:
        await msg.answer("Сума має бути > 0")
        return
    await state.update_data(amount=amount)
    await msg.answer("Нотатка (або .):")
    await state.set_state(AddExpense.note)

@dp.message(AddExpense.note)
async def save_expense(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    cat, amount = data["category"], data["amount"]
    note = msg.text.strip() if msg.text.strip() != "." else ""
    person = USERS.get(msg.from_user.id, "Невідомий")
    
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        person, cat, amount, note, str(msg.chat.id), month_key()
    ]
    trans_sheet.append_row(row)
    
    # ПЕРЕРАХУНОК
    mk = month_key()
    spent = sum(safe_int(r[3]) for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk and r[2] == cat)
    limit = CATS[cat]
    perc = spent / limit * 100 if limit else 0
    warn = "80%" if 80 <= perc < 100 else "100%" if perc >= 100 else ""
    
    p_spent = sum(safe_int(r[3]) for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk and r[1] == person)
    p_limit = PERSONAL.get(person, 0)
    p_warn = "наближаєтесь" if p_limit and 80 <= p_spent/p_limit*100 < 100 else "перевищення!" if p_limit and p_spent/p_limit*100 >= 100 else ""
    
    await msg.answer(
        f"{amount} грн — {cat}\n"
        f"Залишок: {limit - spent} ({int(perc)}%) {warn}\n"
        f"{person}: {p_spent}/{p_limit} {p_warn}",
        reply_markup=main_menu()
    )
    await state.clear()

@dp.message(F.text == "Підсумок за місяць")
async def summary(msg: types.Message):
    mk = month_key()
    rows = [r for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk]
    spent = {c: sum(safe_int(r[3]) for r in rows if r[2] == c) for c in CATS}
    text = "\n".join(
        f"{c}: {spent.get(c,0)} / {lim} ({int(spent.get(c,0)/lim*100)}%) {'80%' if 80<=spent.get(c,0)/lim*100<100 else '100%' if spent.get(c,0)/lim*100>=100 else ''}"
        for c, lim in CATS.items() if lim > 0
    )
    total = sum(spent.values())
    g = sum(safe_int(r[3]) for r in rows if r[1] == "Гліб")
    d = sum(safe_int(r[3]) for r in rows if r[1] == "Дарʼя")
    await msg.answer(f"{text}\n\nРазом: {total} грн\nГліб: {g}/45000\nДарʼя: {d}/33000")

@dp.message(F.text == "Баланс Гліб / Дарʼя")
async def balance(msg: types.Message):
    mk = month_key()
    rows = [r for r in trans_sheet.get_all_values()[1:] if len(r)>6 and r[6] == mk]
    g = sum(safe_int(r[3]) for r in rows if r[1] == "Гліб")
    d = sum(safe_int(r[3]) for r in rows if r[1] == "Дарʼя")
    await msg.answer(f"Гліб: {g}/45000 → {45000-g}\nДарʼя: {d}/33000 → {33000-d}")

@dp.message(F.text == "Скасувати останню")
async def undo(msg: types.Message):
    person = USERS.get(msg.from_user.id)
    if not person:
        await msg.answer("Ти не в базі")
        return
    rows = trans_sheet.get_all_values()
    mk = month_key()
    for i in range(len(rows)-1, 0, -1):
        r = rows[i]
        if len(r) > 6 and r[1] == person and r[6] == mk:
            trans_sheet.delete_rows(i+1)
            await msg.answer("Видалено")
            return
    await msg.answer("Немає транзакцій")

@dp.message(F.text == "Останні транзакції")
async def last5(msg: types.Message):
    rows = trans_sheet.get_all_values()[1:][-5:][::-1]
    text = "\n".join(
        f"{r[0].split()[0]} – {r[2]} – {r[3]} – {r[1]} – \"{r[4]}\"" 
        for r in rows if len(r) > 4
    ) or "Пусто"
    await msg.answer(text)

@dp.message(Command("setcat"))
async def setcat(msg: types.Message):
    try:
        _, cat, lim = msg.text.split()
        row = cats_sheet.find(cat).row
        cats_sheet.update_cell(row, 2, int(lim))
        CATS[cat] = int(lim)
        await msg.answer(f"{cat} → {lim}")
    except Exception as e:
        await msg.answer("Формат: /setcat Еда 25000")

@dp.message(Command("setpers"))
async def setpers(msg: types.Message):
    try:
        _, name, lim = msg.text.split()
        row = pers_sheet.find(name).row
        pers_sheet.update_cell(row, 3, int(lim))
        PERSONAL[name] = int(lim)
        await msg.answer(f"{name} → {lim}")
    except Exception as e:
        await msg.answer("Формат: /setpers Гліб 50000")

async def main():
    print("Бот запущений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
