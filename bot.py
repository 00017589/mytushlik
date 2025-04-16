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

# States for conversation handler
PHONE, NAME = range(2)

# File paths
DATA_FILE = "data.json"
ADMIN_FILE = "admins.json"

# Initialize data structure
def initialize_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"users": {}, "daily_attendance": {}, "attendance_history": {}}

# Initialize admin list
def initialize_admins():
    if os.path.exists(ADMIN_FILE):
        with open(ADMIN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"admins": []}

# Save data to file
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Save admins to file
def save_admins(admins):
    with open(ADMIN_FILE, "w", encoding="utf-8") as f:
        json.dump(admins, f)

# Check if user is admin
def is_admin(user_id, admins):
    return str(user_id) in admins["admins"]

# ---------------------- User Registration Handlers ---------------------- #

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    data = initialize_data()

    if user_id in data["users"]:
        user_name = data["users"][user_id]["name"].split()[0]  # Get first name
        await update.message.reply_text(
            f"👋 Salom, {user_name}!\n\nMy Tushlik botga qaytganingizdan xursandmiz! Quyidagi tugmalardan foydalanishingiz mumkin:",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["🧾 Qarzimni tekshirish", "📊 Qatnashishlarim"],
                    ["📝 Bugungi tushlik", "❓ Yordam"],
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

# Phone number handler
async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone_number = update.message.contact.phone_number
    else:
        await update.message.reply_text("Iltimos, \"Telefon raqamni yuborish\" tugmasini bosing.")
        return PHONE

    context.user_data["phone"] = phone_number
    await update.message.reply_text("Rahmat! Endi to'liq ismingizni kiriting (Masalan: Abdurahmonov Sardor).")
    return NAME

# Name handler
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    full_name = update.message.text
    user_id = str(update.effective_user.id)
    context.user_data["name"] = full_name

    data = initialize_data()
    # Register user
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
                ["📝 Bugungi tushlik", "❓ Yordam"],
            ],
            resize_keyboard=True,
        ),
    )
    return ConversationHandler.END

# ---------------------- Attendance Handlers ---------------------- #

# Daily attendance request sender (scheduled)
async def send_attendance_request(context: ContextTypes.DEFAULT_TYPE):
    data = initialize_data()
    today = datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")

    # Initialize today's attendance data
    if today not in data["daily_attendance"]:
        data["daily_attendance"][today] = {"confirmed": [], "declined": [], "pending": []}

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
            # Skip if user already responded
            if (user_id in data["daily_attendance"][today]["confirmed"] or
                user_id in data["daily_attendance"][today]["declined"]):
                continue

            # Add to pending if not already there
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

# Daily attendance confirmation sender (scheduled)
async def send_attendance_confirmation(context: ContextTypes.DEFAULT_TYPE):
    data = initialize_data()
    today = datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")

    if today not in data["daily_attendance"]:
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Ha ✅", callback_data=f"confirmation_yes_{today}"),
                InlineKeyboardButton("Yo'q ❌", callback_data=f"confirmation_no_{today}"),
                InlineKeyboardButton("Bekor qilish ↩️", callback_data=f"confirmation_cancel_{today}"),
            ]
        ]
    )

    # Send confirmation only to users who initially confirmed
    for user_id in data["daily_attendance"][today]["confirmed"]:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="Tushlikka qatnashishingizni tasdiqlaysizmi?",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Failed to send attendance confirmation to user {user_id}: {e}")

# Daily attendance summary sender (scheduled)
async def send_attendance_summary(context: ContextTypes.DEFAULT_TYPE):
    data = initialize_data()
    admins = initialize_admins()
    today = datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")

    if today not in data["daily_attendance"]:
        return

    confirmed_count = len(data["daily_attendance"][today]["confirmed"])
    confirmed_names = [
        data["users"][uid]["name"] for uid in data["daily_attendance"][today]["confirmed"] if uid in data["users"]
    ]

    summary = f"🍽️ {today} - Tushlik qatnashuvchilar soni: {confirmed_count}\n\n"
    if confirmed_names:
        summary += "✅ Qatnashuvchilar:\n"
        for i, name in enumerate(confirmed_names, 1):
            summary += f"{i}. {name}\n"
    else:
        summary += "❌ Bugun qatnashuvchilar yo'q."

    # Update debts for confirmed users
    for user_id in data["daily_attendance"][today]["confirmed"]:
        if user_id in data["users"]:
            data["users"][user_id]["debt"] += 25000

    # Save attendance to history
    if today not in data["attendance_history"]:
        data["attendance_history"][today] = {
            "confirmed": data["daily_attendance"][today]["confirmed"].copy(),
            "declined": data["daily_attendance"][today]["declined"].copy(),
        }

    save_data(data)

    # Send summary to all admins
    for admin_id in admins["admins"]:
        try:
            await context.bot.send_message(chat_id=admin_id, text=summary)
        except Exception as e:
            logger.error(f"Failed to send attendance summary to admin {admin_id}: {e}")

# Callback query handler for attendance and confirmations
async def attendance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = initialize_data()
    user_id = str(query.from_user.id)
    callback_data = query.data

    # Process attendance response
    if callback_data.startswith("attendance_"):
        action, date = callback_data.replace("attendance_", "").split("_")
        if date not in data["daily_attendance"]:
            data["daily_attendance"][date] = {"confirmed": [], "declined": [], "pending": []}

        # Remove user from pending and any existing list to avoid duplication
        if user_id in data["daily_attendance"][date]["pending"]:
            data["daily_attendance"][date]["pending"].remove(user_id)
        if user_id in data["daily_attendance"][date]["confirmed"]:
            data["daily_attendance"][date]["confirmed"].remove(user_id)
        if user_id in data["daily_attendance"][date]["declined"]:
            data["daily_attendance"][date]["declined"].remove(user_id)

        if action == "yes":
            data["daily_attendance"][date]["confirmed"].append(user_id)
            await query.edit_message_text("Rahmat! Tushlikda ko'rishguncha.")
        elif action == "no":
            data["daily_attendance"][date]["declined"].append(user_id)
            await query.edit_message_text("Tushlik uchun javobingiz qayd etildi.")

    # Process confirmation response
    elif callback_data.startswith("confirmation_"):
        action, date = callback_data.replace("confirmation_", "").split("_")
        if date not in data["daily_attendance"]:
            await query.edit_message_text("Xatolik yuz berdi. Qayta urinib ko'ring.")
            return

        if action == "yes":
            await query.edit_message_text("Tushlikdagi ishtirokingiz tasdiqlandi!")
        elif action == "no":
            if user_id in data["daily_attendance"][date]["confirmed"]:
                data["daily_attendance"][date]["confirmed"].remove(user_id)
                data["daily_attendance"][date]["declined"].append(user_id)
                await query.edit_message_text("Tushlikni bekor qildingiz.")
        elif action == "cancel":
            if user_id in data["daily_attendance"][date]["confirmed"]:
                data["daily_attendance"][date]["confirmed"].remove(user_id)
            if user_id in data["daily_attendance"][date]["declined"]:
                data["daily_attendance"][date]["declined"].remove(user_id)
            if user_id not in data["daily_attendance"][date]["pending"]:
                data["daily_attendance"][date]["pending"].append(user_id)
            # Ask again
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Ha ✅", callback_data=f"attendance_yes_{date}"),
                        InlineKeyboardButton("Yo'q ❌", callback_data=f"attendance_no_{date}"),
                    ]
                ]
            )
            await query.edit_message_text(
                text="Bugun tushlikka qatnashasizmi? (25,000 so'm)", reply_markup=keyboard
            )

    save_data(data)

def schedule_morning_attendance_check(app):
    now = datetime.datetime.now(TASHKENT_TZ)
    # Set time for morning attendance request: 7:00 AM Tashkent time
    target_time = now.replace(hour=7, minute=0, second=0, microsecond=0)
    if now > target_time:
        target_time += datetime.timedelta(days=1)
    seconds_until_target = (target_time - now).total_seconds()
    app.job_queue.run_once(send_attendance_request, seconds_until_target)
    app.job_queue.run_daily(send_attendance_request, time=datetime.time(hour=7, minute=0, second=0, tzinfo=TASHKENT_TZ))


def schedule_confirmation_check(app):
    now = datetime.datetime.now(TASHKENT_TZ)
    # Set time for confirmation prompt: 9:00 AM Tashkent time
    target_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now > target_time:
        target_time += datetime.timedelta(days=1)
    seconds_until_target = (target_time - now).total_seconds()
    app.job_queue.run_once(send_attendance_confirmation, seconds_until_target)
    app.job_queue.run_daily(send_attendance_confirmation, time=datetime.time(hour=9, minute=0, second=0, tzinfo=TASHKENT_TZ))


def schedule_summary_report(app):
    now = datetime.datetime.now(TASHKENT_TZ)
    # Update target time to 10:00 AM for the final list
    target_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if now > target_time:
        target_time += datetime.timedelta(days=1)
    seconds_until_target = (target_time - now).total_seconds()
    app.job_queue.run_once(send_attendance_summary, seconds_until_target)
    app.job_queue.run_daily(send_attendance_summary, time=datetime.time(hour=10, minute=0, second=0, tzinfo=TASHKENT_TZ))


# ---------------------- Debt and Attendance Check ---------------------- #

# Check debt command handler
async def check_debt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = initialize_data()
    if user_id not in data["users"]:
        await update.message.reply_text("Siz ro'yxatdan o'tmagansiz. Ro'yxatdan o'tish uchun /start buyrug'ini yuboring.")
        return
    debt = data["users"][user_id]["debt"]
    await update.message.reply_text(f"Sizning qarzingiz: {debt:,} so'm")

# Check attendance command handler
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

# ---------------------- Admin Commands ---------------------- #

# Make admin command handler
async def make_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()

    # First user to run this command becomes admin
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

# Remove admin command handler
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

# Reset debt command handler (for individual or all users)
async def reset_debt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    # Reset individual user's debt if argument is given
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

# Modify debt command handler
async def modify_debt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Noto'g'ri format. Quyidagi formatda yuboring:\n/qarz_ozgartirish [foydalanuvchi_id] [summa]")
        return
    target_id = context.args[0]
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Summa raqam bo'lishi kerak.")
        return
    data = initialize_data()
    if target_id not in data["users"]:
        await update.message.reply_text("Bu foydalanuvchi topilmadi.")
        return
    old_debt = data["users"][target_id]["debt"]
    data["users"][target_id]["debt"] = amount
    save_data(data)
    user_name = data["users"][target_id]["name"]
    await update.message.reply_text(f"{user_name} ning qarzi {old_debt:,} so'mdan {amount:,} so'mga o'zgartirildi.")
    try:
        await context.bot.send_message(chat_id=target_id, text=f"Sizning qarzingiz administrator tomonidan {old_debt:,} so'mdan {amount:,} so'mga o'zgartirildi.")
    except Exception as e:
        logger.error(f"Failed to notify user about debt modification: {e}")

# View all debts command handler
async def view_all_debts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    sorted_users = sorted(data["users"].items(), key=lambda x: x[1]["debt"], reverse=True)
    if not sorted_users:
        await update.message.reply_text("Foydalanuvchilar ro'yxati bo'sh.")
        return
    total_debt = sum(user_info["debt"] for _, user_info in sorted_users)
    message = "📊 QARZLAR RO'YXATI:\n\n"
    for i, (uid, user_info) in enumerate(sorted_users, 1):
        message += f"{i}. {user_info['name']}: {user_info['debt']:,} so'm\n"
    message += f"\n💰 Jami qarz: {total_debt:,} so'm"
    await update.message.reply_text(message)

# View today's attendance command handler
async def view_today_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    if user_id not in admins["admins"]:
        await update.message.reply_text("Siz admin emassiz.")
        return
    data = initialize_data()
    today = datetime.datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")
    if today not in data["daily_attendance"]:
        await update.message.reply_text("Bugun uchun ma'lumot topilmadi.")
        return
    confirmed_users = [data["users"][uid]["name"] for uid in data["daily_attendance"][today]["confirmed"] if uid in data["users"]]
    pending_users = [data["users"][uid]["name"] for uid in data["daily_attendance"][today]["pending"] if uid in data["users"]]
    message = f"🍽️ {today} - BUGUNGI TUSHLIK:\n\n"
    message += f"✅ Qatnashuvchilar ({len(confirmed_users)}):\n" + ("\n".join(f"{i}. {name}" for i, name in enumerate(confirmed_users, 1)) if confirmed_users else "Hech kim yo'q") + "\n\n"
    message += f"⏳ Javob bermaganlar ({len(pending_users)}):\n" + ("\n".join(f"{i}. {name}" for i, name in enumerate(pending_users, 1)) if pending_users else "Hech kim yo'q")
    await update.message.reply_text(message)

# Callback handler for debt reset confirmation
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

# Export data command handler
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

# Remind debtors command handler
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

# Help command handler
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = initialize_admins()
    message = "🍽️ MY TUSHLIK BOT BUYRUQLARI:\n\n"
    message += "👤 FOYDALANUVCHI UCHUN:\n"
    message += "/start - Botni ishga tushirish va ro'yxatdan o'tish\n"
    message += "/qarz - Qarzingizni tekshirish\n"
    message += "/qatnashish - Qatnashishlaringizni ko'rish\n"
    message += "/yordam - Yordam ko'rsatish\n\n"
    if is_admin(user_id, admins):
        message += "👑 ADMINISTRATOR UCHUN:\n"
        message += "/admin_qoshish [id] - Yangi admin qo'shish\n"
        message += "/admin_ochirish [id] - Adminni o'chirish\n"
        message += "/qarz_nol - Barcha qarzlarni nolga tushirish\n"
        message += "/qarz_nol [id] - Foydalanuvchi qarzini nolga tushirish\n"
        message += "/qarz_ozgartirish [id] [summa] - Qarzni o'zgartirish\n"
        message += "/qarzlar - Barcha qarzlarni ko'rish\n"
        message += "/bugun - Bugungi qatnashuvchilarni ko'rish\n"
        message += "/eksport - Ma'lumotlarni eksport qilish\n"
        message += "/eslatma - Qarzdorlarga eslatma yuborish\n"
    await update.message.reply_text(message)

# ---------------------- Keyboard Functions ---------------------- #

async def show_admin_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Admin paneli:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["👥 Foydalanuvchilar", "💰 Barcha qarzlar"],
                ["📊 Bugungi qatnashish", "🔄 Qarzlarni nollash"],
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
                ["📝 Bugungi tushlik", admin_button],
            ],
            resize_keyboard=True,
        ),
    )

# Dedicated async function to handle admin panel request
async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(str(update.effective_user.id), initialize_admins()):
        await show_admin_keyboard(update, context)
    else:
        await update.message.reply_text("Siz admin emassiz.")

# ---------------------- Main Function ---------------------- #

def main():
    token = "7827859748:AAEDW4Dlmv49bGwps2-OyPcLS_ysEn4TmPU"  # Replace with your token if needed
    application = Application.builder().token(token).build()

    # Conversation handler for registration
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
    

    # Add message handlers for user options
    application.add_handler(MessageHandler(filters.Regex("^🧾 Qarzimni tekshirish$"), check_debt))
    application.add_handler(MessageHandler(filters.Regex("^📊 Qatnashishlarim$"), check_attendance))
    application.add_handler(MessageHandler(filters.Regex("^📝 Bugungi tushlik$"), 
                                           lambda update, context: context.bot.send_message(
                                               chat_id=update.effective_chat.id,
                                               text="Bugungi tushlik haqida so'rov yuborildi!"
                                           )))
    application.add_handler(MessageHandler(filters.Regex("^❓ Yordam$"), help_command))
    application.add_handler(MessageHandler(filters.Regex("^👑 Admin panel$"), admin_panel_handler))
    application.add_handler(MessageHandler(filters.Regex("^👥 Foydalanuvchilar$"), view_all_debts))
    application.add_handler(MessageHandler(filters.Regex("^💰 Barcha qarzlar$"), view_all_debts))
    application.add_handler(MessageHandler(filters.Regex("^📊 Bugungi qatnashish$"), view_today_attendance))
    application.add_handler(MessageHandler(filters.Regex("^🔄 Qarzlarni nollash$"), reset_debt))
    application.add_handler(MessageHandler(filters.Regex("^⬅️ Asosiy menyu$"), show_regular_keyboard))

    # Add command handlers
    application.add_handler(CommandHandler("admin", show_admin_keyboard))
    application.add_handler(CommandHandler("qarz", check_debt))
    application.add_handler(CommandHandler("qatnashish", check_attendance))
    application.add_handler(CommandHandler("admin_qoshish", make_admin))
    application.add_handler(CommandHandler("admin_ochirish", remove_admin))
    application.add_handler(CommandHandler("qarz_nol", reset_debt))
    application.add_handler(CommandHandler("qarz_ozgartirish", modify_debt))
    application.add_handler(CommandHandler("qarzlar", view_all_debts))
    application.add_handler(CommandHandler("bugun", view_today_attendance))
    application.add_handler(CommandHandler("eksport", export_data))
    application.add_handler(CommandHandler("eslatma", remind_debtors))
    application.add_handler(CommandHandler("yordam", help_command))

    # Callback query handlers
    application.add_handler(CallbackQueryHandler(attendance_callback, pattern="^(attendance_|confirmation_)"))
    application.add_handler(CallbackQueryHandler(debt_reset_callback, pattern="^reset_all_debts_"))

    # Schedule jobs
    schedule_morning_attendance_check(application)
    schedule_confirmation_check(application)
    schedule_summary_report(application)

    # Start the Bot
    application.run_polling()


if __name__ == "__main__":
    main()

