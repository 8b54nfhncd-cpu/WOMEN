import os
import logging
from flask import Flask, request
import telebot
from telebot import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))  # ID группы, куда будут приходить сообщения

if not BOT_TOKEN or not GROUP_ID:
    raise RuntimeError("BOT_TOKEN и GROUP_ID обязательны")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# Связь: ID сообщения в группе → (user_id, user_message_id)
group_msg_to_user = {}


@bot.message_handler(commands=['start'])
def handle_start(message):
    """Пользователь написал боту впервые"""
    user_id = message.chat.id
    user_name = message.from_user.first_name or "Пользователь"
    
    bot.send_message(
        user_id,
        f"👋 Привет, {user_name}!\n\n"
        "Твои сообщения анонимно уходят в группу админу.\n"
        "Ответы ты получишь прямо сюда."
    )
    
    # Отправляем в группу уведомление о новом пользователе
    bot.send_message(
        GROUP_ID,
        f"🆕 **Новый пользователь в чате!**\n"
        f"👤 Имя: {user_name}\n"
        f"🆔 ID: `{user_id}`\n\n"
        f"_Чтобы ответить — нажми «Ответить» на его сообщение_",
        parse_mode="Markdown"
    )
    logger.info(f"Новый пользователь: {user_name} (ID: {user_id})")


@bot.message_handler(func=lambda message: message.chat.id != GROUP_ID)
def forward_to_group(message):
    """Сообщение от НЕ-группы (то есть от пользователя) → пересылаем в группу"""
    user_id = message.chat.id
    user_name = message.from_user.first_name or "Аноним"
    
    # Формируем красивое сообщение для группы
    if message.text:
        text = f"💬 От {user_name} (ID: `{user_id}`):\n\n{message.text}"
    elif message.photo:
        text = f"🖼 От {user_name} (ID: `{user_id}`): [Отправил фото]"
    else:
        text = f"📎 От {user_name} (ID: `{user_id}`): [Другой тип сообщения]"
    
    # Отправляем в группу
    sent = bot.send_message(GROUP_ID, text, parse_mode="Markdown")
    
    # Если есть фото — перешлём отдельно
    if message.photo:
        bot.send_photo(GROUP_ID, message.photo[-1].file_id, caption=f"📸 Фото от {user_name}")
    
    # Запоминаем связь: ID сообщения в группе → данные пользователя
    group_msg_to_user[sent.message_id] = (user_id, message.message_id)
    
    # Подтверждаем пользователю
    bot.reply_to(message, "✅ Отправлено админу. Как ответит — придёт сюда.")


@bot.message_handler(func=lambda message: message.chat.id == GROUP_ID and message.reply_to_message)
def reply_from_group(message):
    """Админ ответил на сообщение в группе — отправляем пользователю"""
    original_msg_id = message.reply_to_message.message_id
    
    if original_msg_id in group_msg_to_user:
        user_id, _ = group_msg_to_user[original_msg_id]
        
        # Отправляем ответ пользователю
        reply_text = f"📩 Ответ:\n\n{message.text}"
        bot.send_message(user_id, reply_text)
        
        # Отмечаем в группе, что ответ отправлен
        bot.reply_to(message, f"✅ Ответ отправлен пользователю (ID: `{user_id}`)", parse_mode="Markdown")
        logger.info(f"Ответ отправлен {user_id}")
    else:
        bot.reply_to(message, "❌ Не найден пользователь для этого сообщения.")


@bot.message_handler(func=lambda message: message.chat.id == GROUP_ID and not message.reply_to_message)
def warn_no_reply(message):
    """Если в группе пишут без ответа — напоминаем"""
    bot.reply_to(
        message,
        "⚠️ Чтобы ответить пользователю — нажми «Ответить» на его сообщение.\n"
        "Обычный текст в чат не отправится никому."
    )


@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Bad Request', 403


@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200


def set_webhook():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        logger.warning("RENDER_EXTERNAL_URL не найден")
        return
    webhook_url = f"{render_url}/webhook"
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook: {webhook_url}")


if name == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
