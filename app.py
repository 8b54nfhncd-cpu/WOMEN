import os
import json
import logging
import requests
from flask import Flask, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))

if not BOT_TOKEN or not GROUP_ID:
    raise RuntimeError("BOT_TOKEN и GROUP_ID обязательны")

app = Flask(__name__)

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Словарь: message_id в группе -> user_id
group_msg_to_user = {}

def send_telegram(chat_id, text, reply_to=None):
    """Отправка сообщения в Telegram"""
    url = f"{API_URL}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    return requests.post(url, json=data).json()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        if not update:
            return "OK", 200
        
        logger.info(f"Получен update: {update}")
        
        # Сообщение от пользователя (не из группы)
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            
            # Если это сообщение из группы — обрабатываем ответы
            if chat_id == GROUP_ID:
                # Ответ админа на сообщение в группе
                if msg.get("reply_to_message"):
                    original_msg_id = msg["reply_to_message"]["message_id"]
                    if original_msg_id in group_msg_to_user:
                        user_id = group_msg_to_user[original_msg_id]
                        # Отправляем ответ пользователю
                        send_telegram(user_id, f"📩 Ответ:\n\n{msg['text']}")
                        send_telegram(GROUP_ID, f"✅ Ответ отправлен пользователю", reply_to=msg["message_id"])
                        logger.info(f"Ответ отправлен пользователю {user_id}")
                else:
                    send_telegram(GROUP_ID, "⚠️ Чтобы ответить — нажми «Ответить» на сообщение пользователя", reply_to=msg["message_id"])
            
            # Сообщение от пользователя (не админа)
            elif chat_id != GROUP_ID:
                user_id = chat_id
                user_name = msg["from"].get("first_name", "Аноним")
                text = msg.get("text", "📎 Сообщение без текста")
                
                # Пересылаем в группу
                sent_data = send_telegram(GROUP_ID, f"💬 От {user_name} (ID: `{user_id}`):\n\n{text}")
                if sent_data.get("ok"):
                    group_msg_id = sent_data["result"]["message_id"]
                    group_msg_to_user[group_msg_id] = user_id
                
                # Подтверждаем пользователю
                send_telegram(user_id, "✅ Сообщение отправлено админу")
        
        return "OK", 200
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return "OK", 200

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

def set_webhook():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        requests.post(f"{API_URL}/deleteWebhook")
        result = requests.post(f"{API_URL}/setWebhook", json={"url": webhook_url})
        logger.info(f"Webhook установлен: {webhook_url} - {result.json()}")

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
