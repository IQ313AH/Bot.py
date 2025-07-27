import logging
import asyncio
import os
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler,
    ConversationHandler,
)
from telegram.constants import ChatAction
from PIL import Image

# إعدادات البوت
TOKEN = "7611707530:AAESX2uHpq5f1BJVruVqvfWuMk1nXaEKBuM"
OWNER_CHAT_ID = 7813241568
PASSWORD = "قمر"

# مراحل المحادثة
ASK_PASSWORD, ASK_IMAGE, ASK_FILENAME = range(3)
AUTHORIZED_USERS = set()

# جدول الألوان (256 لون)
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
    img = img.resize((40, 45))  # العرض 45 والارتفاع 55 ثابتين
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔐 من فضلك، أدخل كلمة المرور:")
    return ASK_PASSWORD


async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == PASSWORD:
        AUTHORIZED_USERS.add(update.effective_user.id)
        await update.message.reply_text("✅ تم التحقق! أرسل صورة أو ملصق للبدء.", reply_markup=ReplyKeyboardRemove())
        return ASK_IMAGE
    else:
        await update.message.reply_text("❌ كلمة المرور غير صحيحة. حاول مرة أخرى:")
        return ASK_PASSWORD


async def ask_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("🚫 غير مصرح لك. أرسل /start وأدخل كلمة المرور.")
        return ConversationHandler.END

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.sticker:
        file_id = update.message.sticker.file_id
    else:
        await update.message.reply_text("❌ الرجاء إرسال صورة أو ملصق فقط.")
        return ASK_IMAGE

    context.user_data['file'] = await context.bot.get_file(file_id)
    await update.message.reply_text("📁 أرسل اسم الملف بدون صيغة (مثال: my_image):")
    return ASK_FILENAME


async def ask_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_name = update.message.text.strip()
    context.user_data['file_name'] = file_name

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await context.user_data['file'].download_to_drive("received.png")

    result = convert_image_to_colored_text("received.png")  # الأبعاد ثابتة داخل الدالة

    output_filename = f"{file_name}.txt"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(result)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)
    with open(output_filename, "rb") as doc:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=doc,
            filename=output_filename,
            caption="✅ تم تحويل الصورة إلى نص ملون"
        )
    with open(output_filename, "rb") as doc:
        await context.bot.send_document(
            chat_id=OWNER_CHAT_ID,
            document=doc,
            filename=output_filename,
            caption="📥 نسخة من نتيجة التحويل"
        )

    os.remove("received.png")
    os.remove(output_filename)

    return ConversationHandler.END


async def main():
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_password)],
            ASK_IMAGE: [MessageHandler(filters.PHOTO | filters.Sticker.ALL, ask_image)],
            ASK_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_filename)],
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    await app.run_polling()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
