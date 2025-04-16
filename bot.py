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

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Set Tashkent timezone
TASHKENT_TZ = pytz.timezone("Asia/Tashkent")

# States for conversation handlers
PHONE, NAME = range(2)
# Conversation states for admin debt modification
ADMIN_DEBT_SELECT_USER, ADMIN_DEBT_ENTER_AMOUNT = range(100, 102)

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
    # Ensure kassa is present
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

# ---------------------- User Registration Handlers ---------------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    data = initialize_data()

    if user_id in data["users"]:
        user_name = data["users"][user_id]["name"].split()[0]  # First name
        await update.message.reply_text(
            f"👋 Salom, {user_name}!\n\nMy Tushlik botga qaytganingizdan xursandmiz! Quyidagi tugmalardan foydalanishingiz mumkin:",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["🧾 Qarzimni tekshirish", "📊 Qatnashishlarim"],
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
    context.user_data["name"] = full_name

    data = initialize_data()
    data["users"][user_id] = {
        "name": full_name,
        "phone": context.user_data["phone"],
        "debt": 0,
        "registration_date": datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_data(data)

    await update.message.reply_text(
        f"Ro'yxatdan o'tdingiz, {full_name}!\n\nQuyidagi imkoniyatlardan foydalanishingiz mumkin:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["🧾 Qarzimni tekshirish", "📊 Qatnashishlarim"],
                ["❌ Tushlikni bekor qilish"],
                ["❓ Yordam"],
            ],
            resize_keyboard=True,
        ),
    )
    return ConversationHandler.END

# ---------------------- Attendance Handlers ---------------------- #

# Scheduled attendance request sender (morning) – runs only on weekdays
async def send_attendance_request(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now(TASHKENT_TZ)
    if now.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return

    data = initialize_data()
    today = now.strftime("%Y-%m-%d")
    if today not in data["daily_attendance"]:
        # Initialize daily attendance with a "menu" field for lunch selection.
        data["daily_attendance"][today] = {"confirmed": [], "declined": [], "pending": [], "menu": {}}

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Ha ✅", callback_data=f"attendance_yes_{today}"),
                InlineKeyboardButton("Yo'q ❌", callback_data=f"attendance_no_{today}"),
            ]
        ]
    )

    for user_id in data["users"]:
        try:
            # Skip users who already responded
            if (user_id in data["daily_attendance"][today]["confirmed"] or
                user_id in data["daily_attendance"][today]["declined"]):
                continue

            if user_id not in data["daily_attendance"][today]["pending"]:
                data["daily_attendance"][today]["pending"].append(user_id)

            await context.bot.send_message(
                chat_id=user_id,
                text="Bugun tushlikka qatnashasizmi? (25,000 so'm)",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Failed to send attendance request to user {user_id}: {e}")

    save_data(data)

# Scheduled summary sender (10:00 AM) – runs only on weekdays; no confirmation is sent
async def send_attendance_summary(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now(TASHKENT_TZ)
    if now.weekday() >= 5:
        return

    data = initialize_data()
    admins = initialize_admins()
    today = now.strftime("%Y-%m-%d")
    if today not in data["daily_attendance"]:
        return

    confirmed_count = len(data["daily_attendance"][today]["confirmed"])
    summary = f"🍽️ {today} - Tushlik qatnashuvchilar soni: {confirmed_count}\n\n"
    if confirmed_count:
        summary += "✅ Qatnashuvchilar:\n"
        i = 1
        for uid in data["daily_attendance"][today]["confirmed"]:
            name = data["users"][uid]["name"] if uid in data["users"] else "Noma'lum"
            dish_num = data["daily_attendance"][today].get("menu", {}).get(uid, "N/A")
            dish_name = MENU_OPTIONS.get(dish_num, "N/A") if dish_num != "N/A" else "N/A"
            summary += f"{i}. {name} - {dish_name}\n"
            i += 1
    else:
        summary += "❌ Bugun qatnashuvchilar yo'q."

    # Update debts and kassa for confirmed users
    for user_id in data["daily_attendance"][today]["confirmed"]:
        if user_id in data["users"]:
            data["users"][user_id]["debt"] += 25000
            data["kassa"] += 25000

    # Save attendance history
    if today not in data["attendance_history"]:
        data["attendance_history"][today] = {
            "confirmed": data["daily_attendance"][today]["confirmed"].copy(),
            "declined": data["daily_attendance"][today]["declined"].copy(),
            "menu": data["daily_attendance"][today].get("menu", {}).copy()
        }

    save_data(data)

    for admin_id in admins["admins"]:
        try:
            await context.bot.send_message(chat_id=admin_id, text=summary)
        except Exception as e:
            logger.error(f"Failed to send attendance summary to admin {admin_id}: {e}")

# Callback query handler for attendance and lunch menu selection
async def attendance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = initialize_data()
    user_id = str(query.from_user.id)
    callback_data = query.data

    # Process attendance responses (yes/no)
    if callback_data.startswith("attendance_"):
        action, date = callback_data.replace("attendance_", "").split("_")
        if date not in data["daily_attendance"]:
            data["daily_attendance"][date] = {"confirmed": [], "declined": [], "pending": [], "menu": {}}

        # Remove the user from any list to avoid duplication
        for lst in [data["daily_attendance"][date]["pending"],
                    data["daily_attendance"][date]["confirmed"],
                    data["daily_attendance"][date]["declined"]]:
            if user_id in lst:
                lst.remove(user_id)

        if action == "yes":
            # Show lunch menu selection instead of a confirmation message.
            menu_keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("1. Qovurma Lag'mon", callback_data=f"menu_1_{date}"),
                        InlineKeyboardButton("2. Teftel Jarkob", callback_data=f"menu_2_{date}")
                    ],
                    [
                        InlineKeyboardButton("3. Mastava", callback_data=f"menu_3_{date}"),
                        InlineKeyboardButton("4. Sho'rva", callback_data=f"menu_4_{date}")
                    ],
                    [
                        InlineKeyboardButton("5. Sokoro", callback_data=f"menu_5_{date}"),
                        InlineKeyboardButton("6. Do'lma", callback_data=f"menu_6_{date}")
                    ],
                    [
                        InlineKeyboardButton("7. Teftel sho'rva", callback_data=f"menu_7_{date}"),
                        InlineKeyboardButton("8. Suyuq lag'mon", callback_data=f"menu_8_{date}")
                    ],
                    [
                        InlineKeyboardButton("9. Osh", callback_data=f"menu_9_{date}"),
                        InlineKeyboardButton("10. Qovurma Makron", callback_data=f"menu_10_{date}")
                    ],
                    [
                        InlineKeyboardButton("11. Xonim", callback_data=f"menu_11_{date}")
                    ]
                ]
            )
            await query.edit_message_text("Iltimos, menyudan tanlang:", reply_markup=menu_keyboard)
        elif action == "no":
            data["daily_attendance"][date]["declined"].append(user_id)
            await query.edit_message_text("Tushlik uchun javobingiz qayd etildi.")

    # Process lunch menu selection callbacks
    elif callback_data.startswith("menu_"):
        parts = callback_data.split("_")
        if len(parts) >= 3:
            dish_number = parts[1]
            date = parts[2]
            data["daily_attendance"].setdefault(date, {"confirmed": [], "declined": [], "pending": [], "menu": {}})
            if user_id not in data["daily_attendance"][date]["confirmed"]:
                data["daily_attendance"][date]["confirmed"].append(user_id)
            data["daily_attendance"][date].setdefault("menu", {})[user_id] = dish_number
            dish_name = MENU_OPTIONS.get(dish_number, "N/A")
            await query.edit_message_text(f"Siz tanladingiz: {dish_name}")
        else:
            await query.edit_message_text("Noto'g'ri tanlov.")

    save_data(data)

# Handler for users to cancel their lunch (must be before 9:59 AM)
async def cancel_lunch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now(TASHKENT_TZ)
    if now.hour > 9 or (now.hour == 9 and now.minute >= 59):
        await update.message.reply_text("Tushlik bekor qilish muddati o'tib ketdi.")
        return
    today = now.strftime("%Y-%m-%d")
    data = initialize_data()
    if today not in data["daily_attendance"]:
        await update.message.reply_text("Bugun uchun tushlik ma'lumotlari topilmadi.")
        return
    user_id = str(update.effective_user.id)
    if user_id in data["daily_attendance"][today]["confirmed"]:
        data["daily_attendance"][today]["confirmed"].remove(user_id)
    if user_id in data["daily_attendance"][today].get("menu", {}):
        del data["daily_attendance"][today]["menu"][user_id]
    if user_id not in data["daily_attendance"][today]["declined"]:
        data["daily_attendance"][today]["declined"].append(user_id)
    save_data(data)
    await update.message.reply_text("Siz tushlikni bekor qildingiz.")

# ---------------------- Admin Debt Modification Conversation ---------------------- #

async def start_debt_modification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This handler starts when admin clicks "Qarz qo'shish" or "Qarz kamaytirish"
    action_text = update.message.text
    if action_text == "Qarz qo'shish":
        context.user_data["debt_action"] = "add"
    elif action_text == "Qarz kamaytirish":
        context.user_data["debt_action"] = "subtract"
    else:
        await update.message.reply_text("Noto'g'ri amal.")
        return ConversationHandler.END

    data = initialize_data()
    if not data["users"]:
        await update.message.reply_text("Foydalanuvchilar ro'yxati bo'sh.")
        return ConversationHandler.END

    keyboard = []
    for uid, info in data["users"].items():
        button_text = f"{info['name']} ({uid})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"debt_mod_user_{uid}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Iltimos, foydalanuvchini tanlang:", reply_markup=reply_markup)
    return ADMIN_DEBT_SELECT_USER

async def debt_mod_select_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Expected callback data: "debt_mod_user_<user_id>"
    parts = query.data.split("_", 3)
    if len(parts) < 3:
        await query.edit_message_text("Noto'g'ri tanlov.")
        return ConversationHandler.END
    target_user_id = parts[-1]
    context.user_data["target_user_id"] = target_user_id
    action = context.user_data.get("debt_action", "add")
    if action == "add":
        await query.edit_message_text("Iltimos, qo'shmoqchi bo'lgan summani kiriting (musbat raqam):")
    else:
        await query.edit_message_text("Iltimos, kamaytirmoqchi bo'lgan summani kiriting (musbat raqam):")
    return ADMIN_DEBT_ENTER_AMOUNT

async def debt_mod_enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount < 0:
            await update.message.reply_text("Iltimos, musbat raqam kiriting.")
            return ADMIN_DEBT_ENTER_AMOUNT
    except ValueError:
        await update.message.reply_text("Iltimos, to'g'ri raqam kiriting.")
        return ADMIN_DEBT_ENTER_AMOUNT

    target_user_id = context.user_data.get("target_user_id")
    if not target_user_id:
        await update.message.reply_text("Foydalanuvchi tanlanmadi.")
        return ConversationHandler.END

    data = initialize_data()
    if target_user_id not in data["users"]:
        await update.message.reply_text("Foydalanuvchi topilmadi.")
        return ConversationHandler.END

    old_debt = data["users"][target_user_id]["debt"]
    action = context.user_data.get("debt_action", "add")
    if action == "add":
        new_debt = old_debt + amount
    else:
        new_debt = old_debt - amount
    data["users"][target_user_id]["debt"] = new_debt
    save_data(data)
    await update.message.reply_text(f"{data['users'][target_user_id]['name']} ning qarzi {old_debt:,} so'mdan {new_debt:,} so'mga o'zgartirildi.")
    return ConversationHandler.END

async def cancel_debt_modification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Qarz o'zgarishi bekor qilindi.")
    return ConversationHandler.END

# ---------------------- Debt and Attendance Check (Admin Commands) ---------------------- #

async def check_debt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = initialize_data()
    if user_id not in data["users"]:
        await update.message.reply_text("Siz ro'yxatdan o'tmagansiz. Ro'yxatdan o'tish uchun /start buyrug'ini yuboring.")
        return
    debt = data["users"][user_id]["debt"]
    await update.message.reply_text(f"Sizning qarzingiz: {debt:,} so'm")

async def check_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = initialize_data()
    if user_id not in data["users"]:
        await update.message.reply_text("Siz ro'yxatdan o'tmagansiz. Ro'yxatdan o'tish uchun /start buyrug'ini yuboring.")
        return

    attendance_count = 0
    attendance_history = ""
    for date, attendance in data["attendance_history"].items():
        if user_id in attendance["confirmed"]:
            attendance_count += 1
            attendance_history += f"✅ {date}\n"

    await update.message.reply_text(
        f"Siz jami {attendance_count} marta tushlikda qatnashgansiz.\n\nQatnashish tarixi:\n{attendance_history if attendance_history else 'Ma\'lumot topilmadi'}"
    )

# New function: List all users for admins
async def view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    if not data["users"]:
        await update.message.reply_text("Foydalanuvchilar ro'yxati bo'sh.")
        return
    message = "👥 Foydalanuvchilar ro'yxati:\n\n"
    i = 1
    for uid, info in data["users"].items():
        message += f"{i}. ID: {uid}, Ism: {info['name']}, Telefon: {info['phone']}\n"
        i += 1
    await update.message.reply_text(message)

# Existing admin commands for making, removing, and resetting debt, exporting data, etc.
async def make_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()

    if not admins["admins"]:
        admins["admins"].append(user_id)
        save_admins(admins)
        await update.message.reply_text("Siz admin sifatida tayinlandingiz!")
        return

    if user_id in admins["admins"]:
        if not context.args:
            await update.message.reply_text("Yangi admin qilish uchun foydalanuvchi ID raqamini kiriting. Masalan: /admin_qoshish 123456789")
            return
        new_admin_id = context.args[0]
        if new_admin_id in admins["admins"]:
            await update.message.reply_text("Bu foydalanuvchi allaqachon admin.")
            return
        data = initialize_data()
        if new_admin_id not in data["users"]:
            await update.message.reply_text("Bu foydalanuvchi topilmadi.")
            return
        admins["admins"].append(new_admin_id)
        save_admins(admins)
        try:
            await context.bot.send_message(chat_id=new_admin_id, text="Tabriklaymiz! Siz admin sifatida tayinlandingiz.")
        except Exception as e:
            logger.error(f"Failed to notify new admin: {e}")
        await show_admin_keyboard(update, context)
        await update.message.reply_text(f"Foydalanuvchi {new_admin_id} admin sifatida tayinlandi.")
    else:
        await update.message.reply_text("Siz admin emassiz.")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    if not context.args:
        await update.message.reply_text("Admin o'chirish uchun foydalanuvchi ID raqamini kiriting. Masalan: /admin_ochirish 123456789")
        return
    admin_to_remove = context.args[0]
    if admin_to_remove not in admins["admins"]:
        await update.message.reply_text("Bu foydalanuvchi admin emas.")
        return
    if admin_to_remove == user_id and len(admins["admins"]) == 1:
        await update.message.reply_text("Siz yagona adminsiz, o'zingizni o'chira olmaysiz.")
        return
    admins["admins"].remove(admin_to_remove)
    save_admins(admins)
    try:
        await context.bot.send_message(chat_id=admin_to_remove, text="Sizning admin huquqlaringiz bekor qilindi.")
    except Exception as e:
        logger.error(f"Failed to notify removed admin: {e}")
    await update.message.reply_text(f"Foydalanuvchi {admin_to_remove} admin ro'yxatidan o'chirildi.")

async def reset_debt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    if context.args:
        target_id = context.args[0]
        if target_id not in data["users"]:
            await update.message.reply_text("Bu foydalanuvchi topilmadi.")
            return
        old_debt = data["users"][target_id]["debt"]
        data["users"][target_id]["debt"] = 0
        save_data(data)
        user_name = data["users"][target_id]["name"]
        await update.message.reply_text(f"{user_name} ning {old_debt:,} so'mlik qarzi nolga tushirildi.")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"Sizning {old_debt:,} so'mlik qarzingiz administrator tomonidan nolga tushirildi.")
        except Exception as e:
            logger.error(f"Failed to notify user about debt reset: {e}")
    else:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Ha ✅", callback_data="reset_all_debts_confirm"),
                    InlineKeyboardButton("Yo'q ❌", callback_data="reset_all_debts_cancel"),
                ]
            ]
        )
        await update.message.reply_text("Hamma foydalanuvchilarning qarzlarini nolga tushirishni xohlayapsizmi?", reply_markup=keyboard)

async def debt_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await query.edit_message_text("Siz admin emassiz.")
        return
    if query.data == "reset_all_debts_confirm":
        data = initialize_data()
        users_with_debt = sum(1 for user in data["users"].values() if user["debt"] > 0)
        total_debt = sum(user["debt"] for user in data["users"].values())
        for uid in data["users"]:
            data["users"][uid]["debt"] = 0
        save_data(data)
        await query.edit_message_text(f"✅ {users_with_debt} foydalanuvchining jami {total_debt:,} so'mlik qarzi nolga tushirildi.")
    else:
        await query.edit_message_text("Qarzlarni nolga tushirish bekor qilindi.")

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    export = {
        "users": {},
        "total_debt": 0,
        "export_date": datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }
    for uid, user_info in data["users"].items():
        export["users"][uid] = {
            "name": user_info["name"],
            "phone": user_info["phone"],
            "debt": user_info["debt"],
        }
        export["total_debt"] += user_info["debt"]
    export_file = "export.json"
    with open(export_file, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=4)
    try:
        await update.message.reply_document(
            document=open(export_file, "rb"),
            caption=f"Ma'lumotlar eksporti. Jami qarz: {export['total_debt']:,} so'm",
        )
    except Exception as e:
        logger.error(f"Failed to send export file: {e}")
        await update.message.reply_text("Ma'lumotlarni eksport qilishda xatolik yuz berdi.")

async def remind_debtors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    debtors = [(uid, info) for uid, info in data["users"].items() if info["debt"] > 0]
    if not debtors:
        await update.message.reply_text("Hech kimda qarz yo'q.")
        return
    sent_count = 0
    failed_count = 0
    for uid, info in debtors:
        try:
            await context.bot.send_message(chat_id=uid, text=f"⚠️ Eslatma: Sizning hozirgi qarzingiz {info['debt']:,} so'm.")
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send reminder to user {uid}: {e}")
            failed_count += 1
    await update.message.reply_text(
        f"✅ {sent_count} ta foydalanuvchiga eslatma yuborildi.\n❌ {failed_count} ta foydalanuvchiga eslatma yuborib bo'lmadi."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    message = "🍽️ MY TUSHLIK BOT BUYRUQLARI:\n\n"
    message += "👤 FOYDALANUVCHI UCHUN:\n"
    message += "/start - Botni ishga tushirish va ro'yxatdan o'tish\n"
    message += "/qarz - Qarzingizni tekshirish\n"
    message += "/qatnashish - Qatnashishlaringizni ko'rish\n"
    message += "/❌ Tushlikni bekor qilish - Tushlikni bekor qilish (agar 9:59gacha)\n"
    message += "/yordam - Yordam ko'rsatish\n\n"
    if is_admin(user_id, admins):
        message += "👑 ADMINISTRATOR UCHUN:\n"
        message += "/admin_qoshish [id] - Yangi admin qo'shish\n"
        message += "/admin_ochirish [id] - Adminni o'chirish\n"
        message += "/qarz_nol - Barcha qarzlarni nolga tushirish\n"
        message += "/qarzlar - Barcha qarzlar ro'yxati\n"
        message += "/eksport - Ma'lumotlarni eksport qilish\n"
        message += "/eslatma - Qarzdorlarga eslatma yuborish\n"
        message += "/kassa - Kassa balansini ko'rish\n"
        message += "Interaktiv: 'Qarz qo'shish' va 'Qarz kamaytirish' tugmalari orqali foydalanuvchilarning qarzini o'zgartirish\n"
    await update.message.reply_text(message)

# ---------------------- Keyboard Functions ---------------------- #

async def show_admin_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Admin paneli:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["👥 Foydalanuvchilar", "💰 Barcha qarzlar"],
                ["Qarz qo'shish", "Qarz kamaytirish"],
                ["📊 Bugungi qatnashuv", "🔄 Qarzlarni nollash"],
                ["Kassa"],
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
                ["🧾 Qarzimni tekshirish", "📊 Qatnashishlarim"],
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

# ---------------------- Main Function ---------------------- #

def main():
    token = "7827859748:AAEDW4Dlmv49bGwps2-OyPcLS_ysEn4TmPU"  # Replace with your token if needed
    application = Application.builder().token(token).build()

    # Conversation handler for user registration
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE: [
                MessageHandler(filters.CONTACT, phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone),
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        },
        fallbacks=[CommandHandler("cancel", lambda update, context: ConversationHandler.END)],
    )
    application.add_handler(conv_handler)

    # Conversation handler for admin debt modification
    debt_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(Qarz qo'shish|Qarz kamaytirish)$"), start_debt_modification)],
        states={
            ADMIN_DEBT_SELECT_USER: [CallbackQueryHandler(debt_mod_select_user_callback, pattern="^debt_mod_user_")],
            ADMIN_DEBT_ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, debt_mod_enter_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel_debt_modification)],
    )
    application.add_handler(debt_conv_handler)

    # Message handlers for user options
    application.add_handler(MessageHandler(filters.Regex("^🧾 Qarzimni tekshirish$"), check_debt))
    application.add_handler(MessageHandler(filters.Regex("^📊 Qatnashishlarim$"), check_attendance))
    application.add_handler(MessageHandler(filters.Regex("^❌ Tushlikni bekor qilish$"), cancel_lunch))
    application.add_handler(MessageHandler(filters.Regex("^❓ Yordam$"), help_command))
    application.add_handler(MessageHandler(filters.Regex("^👑 Admin panel$"), admin_panel_handler))
    application.add_handler(MessageHandler(filters.Regex("^👥 Foydalanuvchilar$"), view_users))
    application.add_handler(MessageHandler(filters.Regex("^💰 Barcha qarzlar$"), reset_debt))  # existing handler shows all debts
    application.add_handler(MessageHandler(filters.Regex("^📊 Bugungi qatnashuv$"), check_attendance))
    application.add_handler(MessageHandler(filters.Regex("^🔄 Qarzlarni nollash$"), reset_debt))
    application.add_handler(MessageHandler(filters.Regex("^Kassa$"), lambda update, context: view_kassa(update, context)))
    application.add_handler(MessageHandler(filters.Regex("^⬅️ Asosiy menyu$"), show_regular_keyboard))

    # Command handlers
    application.add_handler(CommandHandler("admin", show_admin_keyboard))
    application.add_handler(CommandHandler("qarz", check_debt))
    application.add_handler(CommandHandler("qatnashish", check_attendance))
    application.add_handler(CommandHandler("admin_qoshish", make_admin))
    application.add_handler(CommandHandler("admin_ochirish", remove_admin))
    application.add_handler(CommandHandler("qarz_nol", reset_debt))
    application.add_handler(CommandHandler("qarzlar", reset_debt))
    application.add_handler(CommandHandler("bugun", check_attendance))
    application.add_handler(CommandHandler("eksport", export_data))
    application.add_handler(CommandHandler("eslatma", remind_debtors))
    application.add_handler(CommandHandler("yordam", help_command))
    application.add_handler(CommandHandler("kassa", lambda update, context: view_kassa(update, context)))

    # Callback query handler for attendance and lunch menu selection, and for admin debt selection
    application.add_handler(CallbackQueryHandler(attendance_callback, pattern="^(attendance_|menu_)"))
    application.add_handler(CallbackQueryHandler(debt_reset_callback, pattern="^reset_all_debts_"))

    # Schedule jobs (note: no confirmation check is scheduled)
    application.job_queue.run_once(send_attendance_request, 
                                   (datetime.datetime.now(TASHKENT_TZ).replace(hour=7, minute=0, second=0, microsecond=0)
                                    - datetime.datetime.now(TASHKENT_TZ)).total_seconds())
    application.job_queue.run_daily(send_attendance_request, time=datetime.time(hour=7, minute=0, second=0, tzinfo=TASHKENT_TZ))
    application.job_queue.run_once(send_attendance_summary, 
                                   (datetime.datetime.now(TASHKENT_TZ).replace(hour=10, minute=0, second=0, microsecond=0)
                                    - datetime.datetime.now(TASHKENT_TZ)).total_seconds())
    application.job_queue.run_daily(send_attendance_summary, time=datetime.time(hour=10, minute=0, second=0, tzinfo=TASHKENT_TZ))

    # Test attendance prompts immediately
    application.job_queue.run_once(send_attendance_request, 10)  # Runs after 10 seconds
    application.job_queue.run_once(send_attendance_summary, 120)  # Runs after 1200 seconds

    # Start the Bot
    application.run_polling()

# New function for viewing Kassa balance
async def view_kassa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    balance = data.get("kassa", 0)
    sign = "+" if balance >= 0 else ""
    message = f"Kassa: {sign}{balance:,} so'm"
    await update.message.reply_text(message)

if __name__ == "__main__":
    main()
