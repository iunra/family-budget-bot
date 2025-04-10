import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Получаем токен из переменной окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Настройка Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Семейный бюджет")
transactions_ws = sheet.worksheet("Транзакции")
limits_ws = sheet.worksheet("Лимиты")

user_state = {}

def get_russian_month():
    month_name = datetime.today().strftime("%B")
    months_ru = {
        "January": "Январь", "February": "Февраль", "March": "Март",
        "April": "Апрель", "May": "Май", "June": "Июнь",
        "July": "Июль", "August": "Август", "September": "Сентябрь",
        "October": "Октябрь", "November": "Ноябрь", "December": "Декабрь"
    }
    return months_ru.get(month_name, month_name)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton("➕ Расход"),
        KeyboardButton("💰 Доход"),
        KeyboardButton("📂 Категории"),
        KeyboardButton("📊 Остатки по лимитам")
    )
    markup.add(KeyboardButton("🚪 Выход"))
    await message.answer("Привет! Что хочешь добавить?", reply_markup=markup)

@dp.message_handler(lambda message: message.text == "🔄 Старт")
async def handle_restart_button(message: types.Message):
    await start(message)

@dp.message_handler(lambda message: message.text == "🚪 Выход")
async def handle_exit(message: types.Message):
    user_state.pop(message.from_user.id, None)
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔄 Старт"))
    await message.answer(
        "Вы вышли из режима ввода. Нажмите «🔄 Старт», чтобы начать заново.",
        reply_markup=markup
    )

@dp.message_handler(lambda message: message.text == "↩ Назад")
async def handle_back(message: types.Message):
    user_state.pop(message.from_user.id, None)
    await start(message)

@dp.message_handler(lambda message: message.text == "📊 Остатки по лимитам")
async def handle_limits_summary(message: types.Message):
    month = datetime.today().strftime("%Y-%m")
    limits = limits_ws.get_all_records()
    transactions = transactions_ws.get_all_records()

    response_lines = ["📊 Остатки по лимитам:"]

    for limit in limits:
        if limit.get("Месяц") != month:
            continue
        category = limit.get("Категория")
        max_amount = float(limit.get("Лимит (₸)", 0))
        spent = sum(
            float(r.get("Сумма", 0))
            for r in transactions
            if r.get("Тип") == "Расход" and r.get("Категория") == category and r.get("Дата", "").startswith(month)
        )
        remaining = max_amount - spent
        response_lines.append(f"{category}: потрачено {spent:.0f} ₸, осталось {remaining:.0f} ₸ из {max_amount:.0f} ₸")

    await message.answer("\n".join(response_lines))

@dp.message_handler(lambda message: message.text == "📂 Категории")
async def handle_categories_button(message: types.Message):
    await show_categories(message)

@dp.message_handler(commands=['категории'])
async def show_categories(message: types.Message):
    user_state[message.from_user.id] = {"stage": "категории"}
    month = datetime.today().strftime("%Y-%m")
    limits = limits_ws.get_all_records()

    lines = ["📋 Категории и лимиты на этот месяц:"]
    for item in limits:
        if item['Месяц'] == month:
            lines.append(f"- {item['Категория']}: {item['Лимит (₸)']} ₸")

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("➕ Добавить категорию/лимит"))
    markup.add(KeyboardButton("✏ Изменить категорию/лимит"))
    markup.add(KeyboardButton("↩ Назад"), KeyboardButton("🚪 Выход"))

    await message.answer("\n".join(lines), reply_markup=markup)

@dp.message_handler(lambda message: message.text == "➕ Добавить категорию/лимит")
async def handle_add_category(message: types.Message):
    await message.answer("Добавление категории пока не реализовано.")

@dp.message_handler(lambda message: message.text == "✏ Изменить категорию/лимит")
async def handle_edit_category(message: types.Message):
    await message.answer("Изменение категории пока не реализовано.")

@dp.message_handler(lambda message: message.text in ["➕ Расход", "💰 Доход"])
async def handle_type(message: types.Message):
    user_state[message.from_user.id] = {
        "type": "Расход" if "Расход" in message.text else "Доход"
    }

    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    if message.text == "➕ Расход":
        limits = limits_ws.get_all_records()
        categories = sorted(list(set(l["Категория"] for l in limits)))
        for cat in categories:
            markup.add(KeyboardButton(cat))
    else:  # Доход
        income_categories = ["Зарплата", "Долг", "Подарок", "Родительские"]
        for cat in income_categories:
            markup.add(KeyboardButton(cat))

    markup.add(KeyboardButton("🚪 Выход"))
    await message.answer("Выберите категорию:", reply_markup=markup)

@dp.message_handler(lambda message: message.from_user.id in user_state and "category" not in user_state[message.from_user.id])
async def handle_category(message: types.Message):
    user_state[message.from_user.id]["category"] = message.text
    await message.answer("Введите сумму:")

@dp.message_handler(lambda message: message.from_user.id in user_state and "amount" not in user_state[message.from_user.id])
async def handle_amount(message: types.Message):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Пожалуйста, введите сумму числом.")
        return

    state = user_state.pop(message.from_user.id)
    operation_type = state["type"]
    category = state["category"]
    user = message.from_user.first_name
    today = datetime.today().strftime("%Y-%m-%d")
    month = datetime.today().strftime("%Y-%m")

    transactions_ws.append_row([today, operation_type, category, amount, user])

    limits = limits_ws.get_all_records()
    current_limit = next(
        (l for l in limits if l["Категория"] == category and l["Месяц"] == month),
        None
    )

    if operation_type == "Расход" and current_limit:
        rows = transactions_ws.get_all_records()
        spent = sum(
            float(r["Сумма"])
            for r in rows
            if r["Тип"] == "Расход" and r["Категория"] == category and r["Дата"].startswith(month)
        )
        remaining = current_limit["Лимит (₸)"] - spent

        month_name_ru = get_russian_month()
        await message.answer(
            f"📅 {month_name_ru}:\n"
            f"Вы потратили на категорию \"{category}\" — {spent:.0f} ₸\n"
            f"Осталось — {remaining:.0f} ₸ из {current_limit['Лимит (₸)']} ₸"
        )
    else:
        await message.answer("✅ Записано!")

    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    if operation_type == "Доход":
        categories = ["Зарплата", "Долг", "Подарок", "Родительские"]
    else:
        limits = limits_ws.get_all_records()
        categories = sorted(list(set(l["Категория"] for l in limits)))

    for cat in categories:
        markup.add(KeyboardButton(cat))
    markup.add(KeyboardButton("🚪 Выход"))
    user_state[message.from_user.id] = {"type": operation_type}

    await message.answer("Выберите следующую категорию или нажмите 🚪 Выход:", reply_markup=markup)

if __name__ == '__main__':
    executor.start_polling(dp)