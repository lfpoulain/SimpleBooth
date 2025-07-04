import asyncio
import logging
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

async def _send_telegram_photo(bot_token, chat_id, photo_path, caption):
    bot = Bot(token=bot_token)
    cleaned_chat_id = chat_id.strip()
    if cleaned_chat_id and cleaned_chat_id[0].isalpha() and not cleaned_chat_id.startswith('@'):
        cleaned_chat_id = '@' + cleaned_chat_id
    logger.info(f"[TELEGRAM] Utilisation de l'ID de chat: '{cleaned_chat_id}'")
    try:
        with open(photo_path, 'rb') as photo_file:
            await bot.send_photo(chat_id=cleaned_chat_id, photo=photo_file, caption=caption)
    except Exception as e:
        if "chat not found" in str(e).lower():
            logger.info(f"[TELEGRAM] ERREUR: Chat introuvable avec l'ID '{cleaned_chat_id}'")
            logger.info("[TELEGRAM] Assurez-vous que:")
            logger.info("   - Le bot a été ajouté au groupe/canal")
            logger.info("   - Pour un groupe: l'ID commence par '-' (ex: -123456789)")
            logger.info("   - Pour un canal: utilisez '@nom_du_canal' ou ajoutez le bot comme admin")
            logger.info("   - Pour un chat privé: utilisez l'ID numérique de l'utilisateur")
        raise

def send_to_telegram(photo_path, config, photo_type="photo"):
    if not config.get('telegram_enabled', False):
        return
    bot_token = config.get('telegram_bot_token', '')
    chat_id = config.get('telegram_chat_id', '')
    if not bot_token or not chat_id:
        logger.info("[TELEGRAM] Configuration incomplète (token ou chat_id manquant)")
        return
    try:
        logger.info(f"[TELEGRAM] Envoi de {photo_path} vers le chat {chat_id}")
        caption = "📸 Nouvelle photo du photobooth!"
        if photo_type == "effet":
            caption = "🎨 Photo avec effet IA du photobooth!"
        async def send_photo_async():
            try:
                await _send_telegram_photo(bot_token, chat_id, photo_path, caption)
                logger.info("[TELEGRAM] Photo envoyée avec succès!")
            except Exception as e:
                logger.info(f"[TELEGRAM] Erreur dans la coroutine: {e}")
        asyncio.run(send_photo_async())
    except TelegramError as e:
        logger.info(f"[TELEGRAM] Erreur Telegram: {e}")
    except Exception as e:
        logger.info(f"[TELEGRAM] Erreur lors de l'envoi: {e}")

