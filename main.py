import os
import logging
import asyncio
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

TOKEN = "7611707530:AAHM7JAiHLIs6iWXKEufpRmOiL8X-XzSoBU"
OWNER_CHAT_ID = 7813241568
LEADERS = [7813241568, 2098914966, 5656244338, 6372106185]

BANNED_USERS = set()
PENDING_REQUESTS = {}
LEADER_MESSAGES = {}
PASSWORD_ATTEMPTS = {}
PRIVATE_USERS = set()

REJECTION_REASONS = {
    "inappropriate": "❌ صورة غير مناسبة / Inappropriate image",
    "rules": "❌ مخالفة القوانين / Violates rules",
    "other": "❌ سبب آخر / Other reason"
}

COLORS = {}
steps = [0x00, 0x5f, 0x87, 0xaf, 0xd7, 0xff]
for r in steps:
    for g in steps:
        for b in steps:
            hex_code = f"c{r:02x}{g:02x}{b:02x}"
            COLORS[(r, g, b)] = hex_code
for g in range(8, 248, 10):
    hex_code = f"c{g:02x}{g:02x}{g:02x}"
    COLORS[(g, g, g)] = hex_code

def get_color_code(rgb):
    r, g, b = rgb
    closest = min(COLORS.keys(), key=lambda c: (r - c[0])**2 + (g - c[1])**2 + (b - c[2])**2)
    return COLORS[closest]

def convert_image_to_colored_text(image_path):
    img = Image.open(image_path).convert("RGBA")
    img = img.resize((40, 45))
    pixels = img.load()
    lines = []
    for y in range(img.height):
        line = ""
        current_color = None
        buffer = ""
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                buffer += "  "
                continue
            hex_color = get_color_code((r, g, b))
            if hex_color != current_color:
                if buffer:
                    line += f"<{current_color}>{buffer}"
                buffer = "███"
                current_color = hex_color
            else:
                buffer += "███"
        if buffer:
            line += f"<{current_color}>{buffer}"
        lines.append(line)
    return "\n".join(lines) + "\n</c>"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً! أرسل صورة للتحويل أو استخدم /private للدخول للوضع الخاص.\n\n"
        "Hello! Send an image to convert or use /private to enter private mode."
    )

async def private_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت.\n\n🚫 You are banned from using the bot.")
        return
    PASSWORD_ATTEMPTS[user_id] = 0
    await update.message.reply_text("رجاءً أدخل كلمة المرور:\n\nPlease enter the password:")

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت.\n\n🚫 You are banned from using the bot.")
        return
    if user_id not in PASSWORD_ATTEMPTS:
        return

    password = update.message.text.strip()
    if password == "QAMAR":
        PASSWORD_ATTEMPTS.pop(user_id, None)
        PRIVATE_USERS.add(user_id)
        await update.message.reply_text("✅ تم الدخول إلى الوضع الخاص. أرسل صورتك.\n\n✅ You have entered private mode. Send your image.")
    else:
        PASSWORD_ATTEMPTS[user_id] += 1
        attempts_left = 5 - PASSWORD_ATTEMPTS[user_id]
        if attempts_left <= 0:
            BANNED_USERS.add(user_id)
            PASSWORD_ATTEMPTS.pop(user_id, None)
            await update.message.reply_text("🚫 تم حظرك بعد 5 محاولات خاطئة.\n\n🚫 You have been banned after 5 failed attempts.")
            await context.bot.send_message(OWNER_CHAT_ID,
                f"⚠️ المستخدم {user_id} تم حظره بعد 5 محاولات خاطئة لكلمة المرور.\n⚠️ User {user_id} was banned after 5 wrong password attempts.")
        else:
            await update.message.reply_text(f"❌ كلمة المرور خاطئة. لديك {attempts_left} محاولات متبقية.\n\n❌ Incorrect password. You have {attempts_left} attempts left.")

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in BANNED_USERS:
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت.\n\n🚫 You are banned from using the bot.")
        return

    file_id = update.message.photo[-1].file_id

    if user.id in PRIVATE_USERS:
        file_path = f"{user.id}_private.png"
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(file_path)

        result = convert_image_to_colored_text(file_path)
        output = f"{user.id}_private.txt"
        with open(output, "w", encoding="utf-8") as f:
            f.write(result)

        await context.bot.send_document(chat_id=user.id, document=open(output, "rb"), filename=output)
        os.remove(file_path)
        os.remove(output)
        await update.message.reply_text("✅ تم تحويل الصورة وإرسالها لك في الخاص.\n\n✅ Image converted and sent to you privately.")
    else:
        PENDING_REQUESTS[user.id] = (file_id, user.username or str(user.id))
        LEADER_MESSAGES[user.id] = []

        keyboard = [[
            InlineKeyboardButton("✅ قبول", callback_data=f"accept:{user.id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_prompt:{user.id}")
        ]]

        for leader in LEADERS:
            msg = await context.bot.send_photo(
                chat_id=leader,
                photo=file_id,
                caption=f"طلب من @{user.username or user.id}\nRequest from @{user.username or user.id}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            LEADER_MESSAGES[user.id].append((leader, msg.message_id))

        await update.message.reply_text("📨 تم إرسال صورتك لقادة المجموعة للقبول أو الرفض.\n\n📨 Your image has been sent to the group leaders for approval or rejection.")

async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("accept:"):
        user_id = int(data.split(":")[1])
        if user_id not in PENDING_REQUESTS:
            await query.edit_message_caption("❌ تم اتخاذ إجراء مسبقاً.\n\n❌ Action already taken.")
            return

        file_id, username = PENDING_REQUESTS[user_id]
        file_path = f"{user_id}_public.png"
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(file_path)

        result = convert_image_to_colored_text(file_path)
        output = f"{user_id}_public.txt"
        with open(output, "w", encoding="utf-8") as f:
            f.write(result)

        await context.bot.send_document(chat_id=user_id, document=open(output, "rb"), filename=output)
        await context.bot.send_message(chat_id=user_id, text="✅ تم قبول صورتك ومعالجتها بنجاح.\n\n✅ Your image has been accepted and processed.")

        os.remove(file_path)
        os.remove(output)

        for l_id, msg_id in LEADER_MESSAGES.get(user_id, []):
            try:
                await context.bot.edit_message_reply_markup(chat_id=l_id, message_id=msg_id, reply_markup=None)
                await context.bot.edit_message_caption(chat_id=l_id, message_id=msg_id,
                                                       caption=f"✅ تم قبول الصورة بواسطة @{query.from_user.username or query.from_user.id}\n✅ Image accepted by @{query.from_user.username or query.from_user.id}")
            except:
                pass

        PENDING_REQUESTS.pop(user_id, None)
        LEADER_MESSAGES.pop(user_id, None)
        return

    if data.startswith("reject_prompt:"):
        user_id = int(data.split(":")[1])
        buttons = [
            [InlineKeyboardButton(text, callback_data=f"reject:{user_id}:{key}")]
            for key, text in REJECTION_REASONS.items()
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
        await query.answer("اختر سبب الرفض\nChoose rejection reason")
        return

    if data.startswith("reject:"):
        parts = data.split(":")
        user_id = int(parts[1])
        reason_key = parts[2]
        reason_text = REJECTION_REASONS.get(reason_key, "❌ رفض / Rejected")

        if user_id not in PENDING_REQUESTS:
            await query.edit_message_caption("❌ تم اتخاذ إجراء مسبقاً.\n\n❌ Action already taken.")
            return

        BANNED_USERS.add(user_id)

        for l_id, msg_id in LEADER_MESSAGES.get(user_id, []):
            try:
                await context.bot.edit_message_reply_markup(chat_id=l_id, message_id=msg_id, reply_markup=None)
                await context.bot.edit_message_caption(chat_id=l_id, message_id=msg_id,
                                                       caption=f"{reason_text} بواسطة @{query.from_user.username or query.from_user.id}")
            except:
                pass

        await context.bot.send_message(chat_id=user_id, text=f"🚫 تم رفض صورتك و حظرك من البوت. السبب: {reason_text}\n\n🚫 Your image was rejected and you have been banned from the bot. Reason: {reason_text}")

        PENDING_REQUESTS.pop(user_id, None)
        LEADER_MESSAGES.pop(user_id, None)
        return

async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    if not context.args:
        await update.message.reply_text("❌ استخدم: /block <user_id>\n\n❌ Usage: /block <user_id>")
        return
    try:
        uid = int(context.args[0])
        BANNED_USERS.add(uid)
        await update.message.reply_text(f"🚫 تم حظر المستخدم {uid}.\n\n🚫 User {uid} has been banned.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}\n\n❌ Error: {e}")

async def banned_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    if not BANNED_USERS:
        await update.message.reply_text("✅ لا يوجد محظورين حالياً.\n\n✅ No banned users currently.")
        return

    buttons = [[InlineKeyboardButton(f"فك الحظر عن {uid}", callback_data=f"unban:{uid}")] for uid in BANNED_USERS]
    await update.message.reply_text("المستخدمين المحظورين:\n\nBanned users:", reply_markup=InlineKeyboardMarkup(buttons))

async def unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split(":")[1])
    if uid in BANNED_USERS:
        BANNED_USERS.remove(uid)
        await query.edit_message_text(f"✅ تم فك الحظر عن {uid}.\n\n✅ Unbanned user {uid}.")
    else:
        await query.edit_message_text("❌ المستخدم غير محظور.\n\n❌ User is not banned.")

async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت.\n\n🚫 You are banned from using the bot.")
        return

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    logging.basicConfig(level=logging.INFO)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("private", private_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(CallbackQueryHandler(handle_decision, pattern="^(accept|reject_prompt|reject):"))
    app.add_handler(CallbackQueryHandler(unban_callback, pattern="^unban:"))
    app.add_handler(CommandHandler("block", block_command))
    app.add_handler(CommandHandler("banned", banned_list_command))
    app.add_handler(MessageHandler(filters.ALL, handle_any_message))

    asyncio.run(app.run_polling())
