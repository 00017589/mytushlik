import logging
import json
import os
import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ---------------------- Configuration and Global Variables ---------------------- #

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Set Tashkent timezone
TASHKENT_TZ = pytz.timezone("Asia/Tashkent")

# Conversation states for registration and name change
PHONE, NAME = range(2)
NAME_CHANGE = 200

# Conversation states for admin balance modification (modify user's balance)
ADMIN_BALANCE_SELECT_USER, ADMIN_BALANCE_ENTER_AMOUNT = range(100, 102)
# Conversation states for admin daily price adjustment (set user's daily price)
ADMIN_DAILY_PRICE_SELECT_USER, ADMIN_DAILY_PRICE_ENTER_AMOUNT = range(102, 104)

# File paths
DATA_FILE = "data.json"
ADMIN_FILE = "admins.json"

# Global lunch menu options mapping (menu option number -> dish name)
MENU_OPTIONS = {
    "1": "Qovurma Lag'mon",
    "2": "Teftel Jarkob",
    "3": "Mastava",
    "4": "Sho'rva",
    "5": "Sokoro",
    "6": "Do'lma",
    "7": "Teftel sho'rva",
    "8": "Suyuq lag'mon",
    "9": "Osh",
    "10": "Qovurma Makron",
    "11": "Xonim"
}

# ---------------------- Data and Admin Initialization ---------------------- #

def initialize_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {
            "users": {},
            "daily_attendance": {},
            "attendance_history": {}
        }
    if "kassa" not in data:
        data["kassa"] = 0
    return data

def initialize_admins():
    if os.path.exists(ADMIN_FILE):
        with open(ADMIN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"admins": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def save_admins(admins):
    with open(ADMIN_FILE, "w", encoding="utf-8") as f:
        json.dump(admins, f)

def is_admin(user_id, admins):
    return str(user_id) in admins["admins"]

# ---------------------- Registration and Name Change ---------------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    data = initialize_data()
    if user_id in data["users"]:
        user_name = data["users"][user_id]["name"].split()[0]
        await update.message.reply_text(
            f"👋 Salom, {user_name}!\n\nMy Tushlik botga qaytganingizdan xursandmiz! Quyidagi tugmalardan foydalanishingiz mumkin:",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["💸 Balansim", "📊 Qatnashishlarim"],
                    ["❌ Tushlikni bekor qilish"],
                    ["❓ Yordam"],
                ],
                resize_keyboard=True,
            ),
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "Salom! My Tushlik botiga xush kelibsiz. Ro'yxatdan o'tish uchun telefon raqamingizni yuboring.",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(text="Telefon raqamni yuborish", request_contact=True)]],
            one_time_keyboard=True,
            resize_keyboard=True,
        ),
    )
    return PHONE

async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone_number = update.message.contact.phone_number
    else:
        await update.message.reply_text("Iltimos, \"Telefon raqamni yuborish\" tugmasini bosing.")
        return PHONE
    context.user_data["phone"] = phone_number
    await update.message.reply_text("Rahmat! Endi to'liq ismingizni kiriting (Masalan: Abdurahmonov Sardor).")
    return NAME

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    full_name = update.message.text
    user_id = str(update.effective_user.id)
    data = initialize_data()
    data["users"][user_id] = {
        "name": full_name,
        "phone": context.user_data["phone"],
        "balance": 0,
        "registration_date": datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }
    save_data(data)
    admins = initialize_admins()
    if not admins["admins"]:
        admins["admins"].append(user_id)
        save_admins(admins)
    await update.message.reply_text(
        f"Ro'yxatdan o'tdingiz, {full_name}!\n\nQuyidagi imkoniyatlardan foydalanishingiz mumkin:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["💸 Balansim", "📊 Qatnashishlarim"],
                ["❌ Tushlikni bekor qilish"],
                ["❓ Yordam"],
            ],
            resize_keyboard=True,
        ),
    )
    return ConversationHandler.END

# Allow users to change their name via /ism_ozgartirish
async def start_name_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Yangi ismingizni kiriting:")
    return NAME_CHANGE

async def process_name_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_name = update.message.text
    uid = str(update.effective_user.id)
    data = initialize_data()
    if uid not in data["users"]:
        await update.message.reply_text("Iltimos, /start orqali ro'yxatdan o'ting.")
        return ConversationHandler.END
    old_name = data["users"][uid]["name"]
    data["users"][uid]["name"] = new_name
    save_data(data)
    await update.message.reply_text(f"Sizning ismingiz {old_name} dan {new_name} ga o'zgartirildi.")
    return ConversationHandler.END

# ---------------------- Attendance Survey and Summary ---------------------- #

async def send_attendance_request(context: ContextTypes.DEFAULT_TYPE, test: bool = False):
    now = datetime.datetime.now(TASHKENT_TZ)
    if not test and now.weekday() >= 5:
        return
    data = initialize_data()
    today = now.strftime("%Y-%m-%d")
    if today not in data["daily_attendance"]:
        data["daily_attendance"][today] = {"confirmed": [], "declined": [], "pending": [], "menu": {}}
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Ha ✅", callback_data=f"attendance_yes_{today}"),
                InlineKeyboardButton("Yo'q ❌", callback_data=f"attendance_no_{today}")
            ]
        ]
    )
    for uid in data["users"]:
        try:
            if uid in data["daily_attendance"][today]["confirmed"] or uid in data["daily_attendance"][today]["declined"]:
                continue
            if uid not in data["daily_attendance"][today]["pending"]:
                data["daily_attendance"][today]["pending"].append(uid)
            await context.bot.send_message(
                chat_id=uid,
                text="Bugun tushlikka qatnashasizmi? (Sizning kunlik narxingiz qo'llaniladi)",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Failed to send survey to user {uid}: {e}")
    save_data(data)

async def send_attendance_summary(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now(TASHKENT_TZ)
    if now.weekday() >= 5:
        return
    data = initialize_data()
    admins = initialize_admins()
    today = now.strftime("%Y-%m-%d")
    if today not in data["daily_attendance"]:
        return
    confirmed = data["daily_attendance"][today]["confirmed"]
    summary = f"🍽️ {today} - Tushlik qatnashuvchilari: {len(confirmed)}\n\n"
    if confirmed:
        i = 1
        for uid in confirmed:
            name = data["users"].get(uid, {}).get("name", "Noma'lum")
            dish = data["daily_attendance"][today].get("menu", {}).get(uid, "N/A")
            dish_name = MENU_OPTIONS.get(dish, "N/A") if dish != "N/A" else "N/A"
            summary += f"{i}. {name} - {dish_name}\n"
            i += 1
    else:
        summary += "❌ Bugun tushlik qatnashuvchilar yo'q."
    for uid in confirmed:
        if uid in data["users"]:
            price = data["users"][uid].get("daily_price", 25000)
            data["users"][uid]["balance"] -= price
            data["kassa"] += price
    if today not in data["attendance_history"]:
        data["attendance_history"][today] = {
            "confirmed": confirmed.copy(),
            "declined": data["daily_attendance"][today]["declined"].copy(),
            "menu": data["daily_attendance"][today].get("menu", {}).copy()
        }
    save_data(data)
    for admin_id in admins["admins"]:
        try:
            await context.bot.send_message(chat_id=admin_id, text=summary)
        except Exception as e:
            logger.error(f"Failed to send summary to admin {admin_id}: {e}")

async def attendance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = initialize_data()
    uid = str(query.from_user.id)
    callback = query.data
    if callback.startswith("attendance_"):
        action, date = callback.replace("attendance_", "").split("_")
        if date not in data["daily_attendance"]:
            data["daily_attendance"][date] = {"confirmed": [], "declined": [], "pending": [], "menu": {}}
        for lst in [data["daily_attendance"][date]["pending"],
                    data["daily_attendance"][date]["confirmed"],
                    data["daily_attendance"][date]["declined"]]:
            if uid in lst:
                lst.remove(uid)
        if action == "yes":
            menu_kb = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("1. Qovurma Lag'mon", callback_data=f"menu_1_{date}"),
                     InlineKeyboardButton("2. Teftel Jarkob", callback_data=f"menu_2_{date}")],
                    [InlineKeyboardButton("3. Mastava", callback_data=f"menu_3_{date}"),
                     InlineKeyboardButton("4. Sho'rva", callback_data=f"menu_4_{date}")],
                    [InlineKeyboardButton("5. Sokoro", callback_data=f"menu_5_{date}"),
                     InlineKeyboardButton("6. Do'lma", callback_data=f"menu_6_{date}")],
                    [InlineKeyboardButton("7. Teftel sho'rva", callback_data=f"menu_7_{date}"),
                     InlineKeyboardButton("8. Suyuq lag'mon", callback_data=f"menu_8_{date}")],
                    [InlineKeyboardButton("9. Osh", callback_data=f"menu_9_{date}"),
                     InlineKeyboardButton("10. Qovurma Makron", callback_data=f"menu_10_{date}")],
                    [InlineKeyboardButton("11. Xonim", callback_data=f"menu_11_{date}")]
                ]
            )
            await query.edit_message_text("Iltimos, menyudan tanlang:", reply_markup=menu_kb)
        elif action == "no":
            data["daily_attendance"][date]["declined"].append(uid)
            await query.edit_message_text("Tushlik uchun javobingiz qayd etildi.")
    elif callback.startswith("menu_"):
        parts = callback.split("_")
        if len(parts) >= 3:
            dish = parts[1]
            date = parts[2]
            data["daily_attendance"].setdefault(date, {"confirmed": [], "declined": [], "pending": [], "menu": {}})
            if uid not in data["daily_attendance"][date]["confirmed"]:
                data["daily_attendance"][date]["confirmed"].append(uid)
            data["daily_attendance"][date].setdefault("menu", {})[uid] = dish
            dish_name = MENU_OPTIONS.get(dish, "N/A")
            await query.edit_message_text(f"Siz tanladingiz: {dish_name}")
        else:
            await query.edit_message_text("Noto'g'ri tanlov.")
    save_data(data)

async def cancel_lunch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now(TASHKENT_TZ)
    if now.hour > 9 or (now.hour == 9 and now.minute >= 59):
        await update.message.reply_text("Tushlikni bekor qilish muddati o'tib ketdi.")
        return
    today = now.strftime("%Y-%m-%d")
    data = initialize_data()
    if today not in data["daily_attendance"]:
        await update.message.reply_text("Bugun uchun tushlik ma'lumotlari topilmadi.")
        return
    uid = str(update.effective_user.id)
    if uid in data["daily_attendance"][today]["confirmed"]:
        data["daily_attendance"][today]["confirmed"].remove(uid)
    if uid in data["daily_attendance"][today].get("menu", {}):
        del data["daily_attendance"][today]["menu"][uid]
    if uid not in data["daily_attendance"][today]["declined"]:
        data["daily_attendance"][today]["declined"].append(uid)
    save_data(data)
    await update.message.reply_text("Siz tushlikni bekor qildingiz.")

# ---------------------- Admin Functions ---------------------- #
# Admin Balance Modification
async def start_balance_modification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action_text = update.message.text
    if action_text == "💵 Balans qo'shish":
        context.user_data["balance_action"] = "add"
    elif action_text == "💸 Balans kamaytirish":
        context.user_data["balance_action"] = "subtract"
    else:
        await update.message.reply_text("Noto'g'ri amal.")
        return ConversationHandler.END
    data = initialize_data()
    if not data["users"]:
        await update.message.reply_text("Foydalanuvchilar ro'yxati bo'sh.")
        return ConversationHandler.END
    kb = []
    for uid, info in data["users"].items():
        button = InlineKeyboardButton(f"{info['name']} ({uid})", callback_data=f"balance_mod_{uid}")
        kb.append([button])
    await update.message.reply_text("Iltimos, foydalanuvchini tanlang:", reply_markup=InlineKeyboardMarkup(kb))
    return ADMIN_BALANCE_SELECT_USER

async def balance_mod_select_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Noto'g'ri tanlov.")
        return ConversationHandler.END
    target_id = parts[2]
    context.user_data["target_id"] = target_id
    if context.user_data.get("balance_action") == "add":
        await query.edit_message_text("Iltimos, qo'shmoqchi bo'lgan summani kiriting (musbat raqam):")
    else:
        await query.edit_message_text("Iltimos, kamaytirmoqchi bo'lgan summani kiriting (musbat raqam):")
    return ADMIN_BALANCE_ENTER_AMOUNT

async def balance_mod_enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount < 0:
            await update.message.reply_text("Iltimos, musbat raqam kiriting.")
            return ADMIN_BALANCE_ENTER_AMOUNT
    except ValueError:
        await update.message.reply_text("Iltimos, to'g'ri raqam kiriting.")
        return ADMIN_BALANCE_ENTER_AMOUNT
    data = initialize_data()
    target_id = context.user_data.get("target_id")
    if not target_id or target_id not in data["users"]:
        await update.message.reply_text("Foydalanuvchi topilmadi.")
        return ConversationHandler.END
    old_balance = data["users"][target_id]["balance"]
    if context.user_data.get("balance_action") == "add":
        new_balance = old_balance + amount
    else:
        new_balance = old_balance - amount
    data["users"][target_id]["balance"] = new_balance
    save_data(data)
    await update.message.reply_text(f"{data['users'][target_id]['name']} ning balansi {old_balance:,} so'mdan {new_balance:,} so'mga o'zgartirildi.")
    return ConversationHandler.END

async def cancel_balance_modification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Balans o'zgarishi bekor qilindi.")
    return ConversationHandler.END

# Admin Daily Price Adjustment
async def start_daily_price_modification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = initialize_data()
    if not data["users"]:
        await update.message.reply_text("Foydalanuvchilar ro'yxati bo'sh.")
        return ConversationHandler.END
    kb = []
    for uid, info in data["users"].items():
        button = InlineKeyboardButton(f"{info['name']} ({uid})", callback_data=f"price_mod_{uid}")
        kb.append([button])
    await update.message.reply_text("Iltimos, kunlik narxni o'zgartirmoqchi bo'lgan foydalanuvchini tanlang:", reply_markup=InlineKeyboardMarkup(kb))
    return ADMIN_DAILY_PRICE_SELECT_USER

async def daily_price_mod_select_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Noto'g'ri tanlov.")
        return ConversationHandler.END
    target_id = parts[2]
    context.user_data["price_target_id"] = target_id
    await query.edit_message_text("Iltimos, yangi kunlik narxni kiriting (soumlarda, masalan: 20000):")
    return ADMIN_DAILY_PRICE_ENTER_AMOUNT

async def daily_price_mod_enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        if price < 0:
            await update.message.reply_text("Iltimos, musbat narx kiriting.")
            return ADMIN_DAILY_PRICE_ENTER_AMOUNT
    except ValueError:
        await update.message.reply_text("Iltimos, to'g'ri narx kiriting.")
        return ADMIN_DAILY_PRICE_ENTER_AMOUNT
    data = initialize_data()
    target_id = context.user_data.get("price_target_id")
    if not target_id or target_id not in data["users"]:
        await update.message.reply_text("Foydalanuvchi topilmadi.")
        return ConversationHandler.END
    data["users"][target_id]["daily_price"] = price
    save_data(data)
    await update.message.reply_text(f"{data['users'][target_id]['name']} ning kunlik narxi {price:,} so'mga o'zgartirildi.")
    return ConversationHandler.END

async def cancel_daily_price_modification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Kunlik narx o'zgarishi bekor qilindi.")
    return ConversationHandler.END

# ---------------------- Admin and General User Commands ---------------------- #

# General user: Check balance
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = initialize_data()
    if uid not in data["users"]:
        await update.message.reply_text("Siz ro'yxatdan o'tmagansiz. /start buyrug'ini yuboring.")
        return
    bal = data["users"][uid]["balance"]
    sign = "+" if bal >= 0 else ""
    await update.message.reply_text(f"Sizning balansingiz: {sign}{bal:,} so'm")

# General user: Attendance history
async def check_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = initialize_data()
    if uid not in data["users"]:
        await update.message.reply_text("Siz ro'yxatdan o'tmagansiz. /start buyrug'ini yuboring.")
        return
    count = 0
    history = ""
    for date, rec in data["attendance_history"].items():
        if uid in rec.get("confirmed", []):
            count += 1
            history += f"✅ {date}\n"
    await update.message.reply_text(f"Siz jami {count} marta tushlikda qatnashgansiz.\n\nTarix:\n{history or 'Ma\'lumot topilmadi.'}")

# Admin: View all registered users
async def view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    data = initialize_data()
    if uid not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    if not data.get("users"):
        await update.message.reply_text("Foydalanuvchilar ro'yxati bo'sh.")
        return
    msg = "👥 Foydalanuvchilar ro'yxati:\n\n"
    i = 1
    for user_id, info in data["users"].items():
        msg += f"{i}. ID: {user_id}, Ism: {info['name']}, Telefon: {info['phone']}\n"
        i += 1
    await update.message.reply_text(msg)

# Admin: View today's attendance
async def view_attendance_today_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    data = initialize_data()
    if uid not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    today = datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")
    if today not in data["daily_attendance"]:
        await update.message.reply_text("Bugun tushlik ma'lumotlari topilmadi.")
        return
    confirmed = data["daily_attendance"][today]["confirmed"]
    if not confirmed:
        await update.message.reply_text("Bugun tushlik qatnashuvchilar yo'q.")
        return
    msg = f"🍽️ {today} - Bugungi tushlik qatnashuvchilari:\n\n"
    i = 1
    for user_id in confirmed:
        if user_id in data["users"]:
            name = data["users"][user_id]["name"]
            dish = data["daily_attendance"][today].get("menu", {}).get(user_id, "N/A")
            dish_name = MENU_OPTIONS.get(dish, "N/A") if dish != "N/A" else "N/A"
            msg += f"{i}. {name} - {dish_name}\n"
            i += 1
    await update.message.reply_text(msg)

# Admin: View all balances
async def view_all_balances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    data = initialize_data()
    if uid not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    sorted_users = sorted(data["users"].items(), key=lambda x: x[1]["balance"])
    total_balance = sum(info["balance"] for _, info in sorted_users)
    msg = "📊 BALANSLAR RO'YXATI:\n\n"
    i = 1
    for user_id, info in sorted_users:
        msg += f"{i}. {info['name']}: {info['balance']:,} so'm\n"
        i += 1
    msg += f"\n💰 Jami balans: {total_balance:,} so'm"
    await update.message.reply_text(msg)

# Admin: View Kassa (with emoji)
async def view_kassa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    data = initialize_data()
    if uid not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    bal = data.get("kassa", 0)
    sign = "+" if bal >= 0 else ""
    await update.message.reply_text(f"💰 Kassa: {sign}{bal:,} so'm")

# Admin: Reset balances
async def reset_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    data = initialize_data()
    if uid not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    if context.args:
        target_id = context.args[0]
        if target_id not in data["users"]:
            await update.message.reply_text("Bu foydalanuvchi topilmadi.")
            return
        old_bal = data["users"][target_id]["balance"]
        data["users"][target_id]["balance"] = 0
        save_data(data)
        await update.message.reply_text(f"{data['users'][target_id]['name']} ning balansi {old_bal:,} so'mdan 0 so'mga tushirildi.")
    else:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Ha ✅", callback_data="reset_all_balances_confirm"),
              InlineKeyboardButton("Yo'q ❌", callback_data="reset_all_balances_cancel")]]
        )
        await update.message.reply_text("Hamma foydalanuvchilarning balanslarini nolga tushurishni xohlaysizmi?", reply_markup=kb)

async def balance_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    admins = initialize_admins()
    data = initialize_data()
    if uid not in admins["admins"]:
        await query.edit_message_text("Siz admin emassiz.")
        return
    if query.data == "reset_all_balances_confirm":
        count = sum(1 for info in data["users"].values() if info["balance"] != 0)
        total = sum(info["balance"] for info in data["users"].values())
        for user_id in data["users"]:
            data["users"][user_id]["balance"] = 0
        save_data(data)
        await query.edit_message_text(f"✅ {count} foydalanuvchining jami {total:,} so'mli balansi nolga tushirildi.")
    else:
        await query.edit_message_text("Balanslarni nolga tushirish bekor qilindi.")

# Admin: Make admin
async def make_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    if not admins["admins"]:
        admins["admins"].append(uid)
        save_admins(admins)
        await update.message.reply_text("Siz admin sifatida tayinlandingiz!")
        return
    if uid in admins["admins"]:
        if not context.args:
            await update.message.reply_text("Yangi admin uchun foydalanuvchi ID kiriting. Masalan: /admin_qoshish 123456789")
            return
        new_admin = context.args[0]
        if new_admin in admins["admins"]:
            await update.message.reply_text("Bu foydalanuvchi allaqachon admin.")
            return
        data = initialize_data()
        if new_admin not in data["users"]:
            await update.message.reply_text("Bu foydalanuvchi topilmadi.")
            return
        admins["admins"].append(new_admin)
        save_admins(admins)
        try:
            await context.bot.send_message(chat_id=new_admin, text="Tabriklaymiz! Siz admin sifatida tayinlandingiz.")
        except Exception as e:
            logger.error(f"Failed to notify new admin: {e}")
        await show_admin_keyboard(update, context)
        await update.message.reply_text(f"Foydalanuvchi {new_admin} admin sifatida tayinlandi.")
    else:
        await update.message.reply_text("Siz admin emassiz.")

# Admin: Remove admin
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    if uid not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    if not context.args:
        await update.message.reply_text("Adminni o'chirish uchun foydalanuvchi ID kiriting. Masalan: /admin_ochirish 123456789")
        return
    target = context.args[0]
    if target not in admins["admins"]:
        await update.message.reply_text("Bu foydalanuvchi admin emas.")
        return
    if target == uid and len(admins["admins"]) == 1:
        await update.message.reply_text("Siz yagona admin, o'zingizni o'chira olmaysiz.")
        return
    admins["admins"].remove(target)
    save_admins(admins)
    try:
        await context.bot.send_message(chat_id=target, text="Sizning admin huquqlaringiz bekor qilindi.")
    except Exception as e:
        logger.error(f"Failed to notify removed admin: {e}")
    await update.message.reply_text(f"Foydalanuvchi {target} admin ro'yxatidan o'chirildi.")

# Admin: Export data
async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    if uid not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    exp = {
        "users": {},
        "total_balance": 0,
        "export_date": datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }
    for user_id, info in data["users"].items():
        exp["users"][user_id] = {"name": info["name"], "phone": info["phone"], "balance": info["balance"]}
        exp["total_balance"] += info["balance"]
    export_file = "export.json"
    with open(export_file, "w", encoding="utf-8") as f:
        json.dump(exp, f, ensure_ascii=False, indent=4)
    try:
        await update.message.reply_document(
            document=open(export_file, "rb"),
            caption=f"Ma'lumotlar eksporti. Jami balans: {exp['total_balance']:,} so'm"
        )
    except Exception as e:
        logger.error(f"Failed to send export file: {e}")
        await update.message.reply_text("Ma'lumotlarni eksport qilishda xatolik yuz berdi.")

# ---------------------- Low Balance Notification ---------------------- #

async def send_low_balance_notifications(context: ContextTypes.DEFAULT_TYPE):
    data = initialize_data()
    today = datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")
    for user_id, info in data["users"].items():
        if info["balance"] < 100000:
            last_notif = info.get("last_balance_notification", "")
            if last_notif == today:
                continue
            try:
                msg = (f"Hurmatli foydalanuvchi, sizning balansingiz {info['balance']:,} so'mga yetdi.\n"
                       "Iltimos, balansingizni to'ldiring. Rahmat!")
                await context.bot.send_message(chat_id=user_id, text=msg)
                data["users"][user_id]["last_balance_notification"] = today
            except Exception as e:
                logger.error(f"Failed to send low balance notification to user {user_id}: {e}")
    save_data(data)

# Legacy reminder function (optional)
async def remind_debtors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    if uid not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    debtors = [(uid, info) for uid, info in data["users"].items() if info["balance"] < 100000]
    if not debtors:
        await update.message.reply_text("Hech kimda balans muammosi yo'q.")
        return
    sent, failed = 0, 0
    for user_id, info in debtors:
        try:
            await context.bot.send_message(chat_id=user_id, text=f"Sizning balansingiz: {info['balance']:,} so'm.")
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send reminder to user {user_id}: {e}")
            failed += 1
    await update.message.reply_text(f"✅ {sent} ta foydalanuvchiga eslatma yuborildi.\n❌ {failed} ta yuborilmadi.")

# ---------------------- Help Command ---------------------- #

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    admins = initialize_admins()
    msg = "🍽️ MY TUSHLIK BOT BUYRUQLARI:\n\n"
    msg += "👤 FOYDALANUVCHI UCHUN:\n"
    msg += "/start - Botni ishga tushirish va ro'yxatdan o'tish\n"
    msg += "/balans - Balansingizni ko'rish\n"
    msg += "/qatnashish - Qatnashishlaringiz tarixi\n"
    msg += "/❌ Tushlikni bekor qilish - (agar 9:59gacha)\n"
    msg += "/ism_ozgartirish - Ismingizni o'zgartirish\n"
    msg += "/yordam - Yordam\n\n"
    if is_admin(uid, admins):
        msg += "👑 ADMINISTRATOR UCHUN:\n"
        msg += "/admin_qoshish [id] - Yangi admin qo'shish\n"
        msg += "/admin_ochirish [id] - Adminni o'chirish\n"
        msg += "Interaktiv tugmalar:\n"
        msg += " • 💵 Balans qo'shish / 💸 Balans kamaytirish\n"
        msg += " • 📝 Kunlik narx - Foydalanuvchining kunlik tushlik narxini sozlash\n"
        msg += "/balans_nol - Barcha balanslarni nolga tushirish\n"
        msg += "/balanslar - Barcha foydalanuvchilarning balanslari\n"
        msg += "/bugun - Bugungi tushlik qatnashuvchilari\n"
        msg += "/eksport - Ma'lumotlarni eksport qilish\n"
        msg += "/eslatma - Kam balansli foydalanuvchilarga eslatma yuborish\n"
        msg += "/kassa - 💰 Kassa balansini ko'rish\n"
        msg += "/test_survey - (Test) Tushlik so'rovini yuborish\n"
    await update.message.reply_text(msg)

# ---------------------- Keyboard Functions ---------------------- #

async def show_admin_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Admin paneli:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["👥 Foydalanuvchilar", "💰 Barcha balanslar"],
                ["💵 Balans qo'shish", "💸 Balans kamaytirish"],
                ["📝 Kunlik narx", "📊 Bugungi qatnashuv"],
                ["🔄 Balanslarni nollash", "💰 Kassa"],
                ["⬅️ Asosiy menyu", "❓ Yordam"],
            ],
            resize_keyboard=True,
        ),
    )

async def show_regular_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_button = "👑 Admin panel" if is_admin(str(update.effective_user.id), initialize_admins()) else "❓ Yordam"
    await update.message.reply_text(
        "Asosiy menyu:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["💸 Balansim", "📊 Qatnashishlarim"],
                ["❌ Tushlikni bekor qilish", admin_button],
            ],
            resize_keyboard=True,
        ),
    )

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(str(update.effective_user.id), initialize_admins()):
        await show_admin_keyboard(update, context)
    else:
        await update.message.reply_text("Siz admin emassiz.")

# ---------------------- Testing Command ---------------------- #

async def test_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_attendance_request(context, test=True)
    await update.message.reply_text("Test survey yuborildi!")

# ---------------------- Scheduled Low Balance Notification ---------------------- #

async def scheduled_low_balance_notification(context: ContextTypes.DEFAULT_TYPE):
    await send_low_balance_notifications(context)

# ---------------------- Main Function ---------------------- #

def main():
    token = "7827859748:AAEDW4Dlmv49bGwps2-OyPcLS_ysEn4TmPU"
    application = Application.builder().token(token).build()

    # Registration conversation
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE: [MessageHandler(filters.CONTACT, phone),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)]
        },
        fallbacks=[CommandHandler("cancel", lambda update, context: ConversationHandler.END)]
    )
    application.add_handler(reg_conv)

    # Name change conversation
    name_conv = ConversationHandler(
        entry_points=[CommandHandler("ism_ozgartirish", start_name_change)],
        states={
            NAME_CHANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_name_change)]
        },
        fallbacks=[CommandHandler("cancel", lambda update, context: ConversationHandler.END)]
    )
    application.add_handler(name_conv)

    # Admin Balance Modification conversation
    balance_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(💵 Balans qo'shish|💸 Balans kamaytirish)$"), start_balance_modification)],
        states={
            ADMIN_BALANCE_SELECT_USER: [CallbackQueryHandler(balance_mod_select_user_callback, pattern="^balance_mod_")],
            ADMIN_BALANCE_ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, balance_mod_enter_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel_balance_modification)]
    )
    application.add_handler(balance_conv)

    # Admin Daily Price Adjustment conversation
    daily_price_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(📝 Kunlik narx)$"), start_daily_price_modification)],
        states={
            ADMIN_DAILY_PRICE_SELECT_USER: [CallbackQueryHandler(daily_price_mod_select_user_callback, pattern="^price_mod_")],
            ADMIN_DAILY_PRICE_ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, daily_price_mod_enter_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel_daily_price_modification)]
    )
    application.add_handler(daily_price_conv)

    # Handlers for general user options
    application.add_handler(MessageHandler(filters.Regex("^💸 Balansim$"), check_balance))
    application.add_handler(MessageHandler(filters.Regex("^📊 Qatnashishlarim$"), check_attendance))
    application.add_handler(MessageHandler(filters.Regex("^❌ Tushlikni bekor qilish$"), cancel_lunch))
    application.add_handler(MessageHandler(filters.Regex("^❓ Yordam$"), help_command))
    application.add_handler(MessageHandler(filters.Regex("^👑 Admin panel$"), admin_panel_handler))
    application.add_handler(MessageHandler(filters.Regex("^👥 Foydalanuvchilar$"), view_users))
    application.add_handler(MessageHandler(filters.Regex("^💰 Barcha balanslar$"), view_all_balances))
    application.add_handler(MessageHandler(filters.Regex("^📊 Bugungi qatnashuv$"), view_attendance_today_admin))
    application.add_handler(MessageHandler(filters.Regex("^🔄 Balanslarni nollash$"), reset_balance))
    application.add_handler(MessageHandler(filters.Regex("^💰 Kassa$"), view_kassa))
    application.add_handler(MessageHandler(filters.Regex("^⬅️ Asosiy menyu$"), show_regular_keyboard))

    # Command handlers
    application.add_handler(CommandHandler("admin", show_admin_keyboard))
    application.add_handler(CommandHandler("balans", check_balance))
    application.add_handler(CommandHandler("qatnashish", check_attendance))
    application.add_handler(CommandHandler("admin_qoshish", make_admin))
    application.add_handler(CommandHandler("admin_ochirish", remove_admin))
    application.add_handler(CommandHandler("balans_nol", reset_balance))
    application.add_handler(CommandHandler("balanslar", view_all_balances))
    application.add_handler(CommandHandler("bugun", view_attendance_today_admin))
    application.add_handler(CommandHandler("eksport", export_data))
    application.add_handler(CommandHandler("eslatma", remind_debtors))
    application.add_handler(CommandHandler("kassa", view_kassa))
    application.add_handler(CommandHandler("test_survey", test_survey))

    # Callback query handlers for attendance survey and balance reset
    application.add_handler(CallbackQueryHandler(attendance_callback, pattern="^(attendance_|menu_)"))
    application.add_handler(CallbackQueryHandler(balance_reset_callback, pattern="^reset_all_balances_"))

    # Schedule daily jobs:
    now = datetime.datetime.now(TASHKENT_TZ)
    target_morning = now.replace(hour=7, minute=0, second=0, microsecond=0)
    if now >= target_morning:
        target_morning += datetime.timedelta(days=1)
    application.job_queue.run_once(send_attendance_request, (target_morning - now).total_seconds())
    application.job_queue.run_daily(send_attendance_request, time=datetime.time(hour=7, minute=0, second=0, tzinfo=TASHKENT_TZ))
    target_summary = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if now >= target_summary:
        target_summary += datetime.timedelta(days=1)
    application.job_queue.run_once(send_attendance_summary, (target_summary - now).total_seconds())
    application.job_queue.run_daily(send_attendance_summary, time=datetime.time(hour=10, minute=0, second=0, tzinfo=TASHKENT_TZ))
    target_notification = now.replace(hour=12, minute=0, second=0, microsecond=0)
    if now >= target_notification:
        target_notification += datetime.timedelta(days=1)
    application.job_queue.run_once(scheduled_low_balance_notification, (target_notification - now).total_seconds())
    application.job_queue.run_daily(scheduled_low_balance_notification, time=datetime.time(hour=12, minute=0, second=0, tzinfo=TASHKENT_TZ))
    
    application.run_polling()

if __name__ == "__main__":
    main()
