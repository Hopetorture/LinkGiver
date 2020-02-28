#!/usr/bin/env python3
import logging
from telegram.ext import (
    Updater,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    Filters,
)

from culture_fit.api import welcome_msg, ask_question, AWAITING_START, QUESTIONS
from core.core import CultureCaches, BotConfig, restart

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def error(update, context):
    """Log Errors caused by Updates."""
    logger.critical('Update "%s" caused error "%s"', update, context.error)


def run_bot():
    logging.info('Bot is starting')
    CultureCaches()  # init caches to see a fails quickly
    with open('token.txt', 'r') as f:
        token = f.read().strip()

    updater = Updater(token=token, use_context=True)
    dispatcher = updater.dispatcher
    BotConfig().updater = updater
    start_handler = CommandHandler('start', welcome_msg)
    questionaire = ConversationHandler(
        per_message=False,
        entry_points=[MessageHandler(Filters.text, ask_question)],
        states={
            AWAITING_START: [MessageHandler(Filters.text, ask_question), ],

            QUESTIONS: [MessageHandler(Filters.text, ask_question), ]
        },
        fallbacks=[CommandHandler('error', error)]
    )

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(questionaire)
    dispatcher.add_handler(CommandHandler('restart_bot', restart, filters=Filters.user(user_id=BotConfig().admins)))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    run_bot()
