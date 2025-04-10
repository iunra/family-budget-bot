import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Получаем токен из Replit Secrets
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

# Месяц по-русски
def get_russian_month():
    month_name = datetime.today().strftime("%B")
    months_ru = {
        "January": "Январь", "February": "Февраль", "March": "Март",
        "April": "Апрель", "May": "Май", "June": "Июнь",
        "July": "Июль", "August": "Август", "September": "Сентябрь",
        "October": "Октябрь", "November": "Ноябрь", "December": "Декабрь"
    }
    return months_ru.get(month_name, month_name)

# /start
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("➕ Расход"), KeyboardButton("💰 Доход"))
    await message.answer("Привет! Что хочешь добавить?", reply_markup=markup)

# Обработка выбора типа
@dp.message_handler(lambda message: message.text in ["➕ Расход", "💰 Доход"])
async def handle_type(message: types.Message):
    user_state[message.from_user.id] = {
        "type": "Расход" if "Расход" in message.text else "Доход"
    }

    # Получаем категории из лимитов
    limits = limits_ws.get_all_records()
    categories = sorted(list(set(l["Категория"] for l in limits)))

    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for cat in categories:
        markup.add(KeyboardButton(cat))
    markup.add(KeyboardButton("➕ Другая категория"))
    await message.answer("Выберите категорию или нажмите '➕ Другая категория':", reply_markup=markup)

# Обработка категории
@dp.message_handler(lambda message: message.from_user.id in user_state and "category" not in user_state[message.from_user.id])
async def handle_category(message: types.Message):
    if message.text == "➕ Другая категория":
        await message.answer("Введите новую категорию:")
    else:
        user_state[message.from_user.id]["category"] = message.text
        await message.answer("Введите сумму:")

# Обработка суммы
@dp.message_handler(lambda message: message.from_user.id in user_state and "amount" not in user_state[message.from_user.id])
async def handle_amount(message: types.Message):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Пожалуйста, введите сумму числом.")
        return

    data = user_state.pop(message.from_user.id)
    user = message.from_user.first_name
    today = datetime.today().strftime("%Y-%m-%d")
    month = datetime.today().strftime("%Y-%m")

    # Запись в таблицу
    transactions_ws.append_row([today, data["type"], data["category"], amount, user])

    # Ищем лимит
    limits = limits_ws.get_all_records()
    current_limit = next(
        (l for l in limits if l["Категория"] == data["category"] and l["Месяц"] == month),
        None
    )

    if data["type"] == "Расход" and current_limit:
        rows = transactions_ws.get_all_records()
        spent = sum(
            float(r["Сумма"])
            for r in rows
            if r["Тип"] == "Расход" and r["Категория"] == data["category"] and r["Дата"].startswith(month)
        )
        remaining = current_limit["Лимит (₸)"] - spent

        month_name_ru = get_russian_month()
        await message.answer(
            f"📅 {month_name_ru}:\n"
            f"Вы потратили на категорию \"{data['category']}\" — {spent:.0f} ₸\n"
            f"Осталось — {remaining:.0f} ₸ из {current_limit['Лимит (₸)']} ₸"
        )
    else:
        await message.answer("✅ Записано!")

# Запуск
if __name__ == '__main__':
    executor.start_polling(dp)
