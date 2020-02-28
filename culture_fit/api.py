import logging
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ConversationHandler

from core.core import CultureCaches, set_db_value, restart, BotConfig

AWAITING_START, QUESTIONS = range(2)
logger = logging.getLogger(__name__)
err_msg = 'Произошла внутренняя ошибка'


def reply_with_starting_keyboard(update, msg):
    keyboard = [['Начать']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    update.message.reply_text(msg, reply_markup=reply_markup)


def ask_question_with_keyboard(update, question):
    keyboard = [[]]
    items_per_row = 2
    counter = 0
    for idx, variant in sorted(question['variants'].items()):
        if counter == items_per_row:
            keyboard.append([])
            counter = 0
        keyboard[-1].append(variant)
        counter += 1
    reply_markup = ReplyKeyboardMarkup(keyboard)
    update.message.reply_text(question['text'], reply_markup=reply_markup)


def welcome_msg(update, context):
    msg = BotConfig().phrases.get('start', err_msg)
    reply_with_starting_keyboard(update, msg)
    return AWAITING_START


def get_question(user_key: str, increment_iter: bool = True, get_next=False):
    ucache = CultureCaches().user_cache[user_key]
    qid = ucache['current_question']
    if get_next:
        qid += 1
    question = CultureCaches().questions_cache.get(qid)
    if increment_iter:
        ucache['current_question'] += 1
    return question  # can return None if its a last question


def cleanup_cache(user_name_key):
    if user_name_key in CultureCaches().user_cache:
        del CultureCaches().user_cache[user_name_key]
    return CultureCaches().user_cache[user_name_key]


def ask_question(update, context):
    user_name_key = str(update.effective_user.id)
    user_meta_info = {
        'Nickname': update.effective_user.name,
        'Link': update.effective_user.link,
        'FullName': update.effective_user.full_name,
    }

    if user_name_key in CultureCaches().judge_cache and BotConfig().restrict_reruns:
        update.message.reply_text(BotConfig().phrases.get('already_passed'))
        return ConversationHandler.END

    if update.message.text == '/restart_bot':
        restart(update, context)
        return ConversationHandler.END

    if update.message.text == 'Начать':
        CultureCaches().clear_caches(user_name_key)
        question = get_question(user_name_key,
                                increment_iter=False)
        ask_question_with_keyboard(update, question)
        return QUESTIONS

    question = get_question(user_name_key)
    if not question:
        logging.critical(f'Could not get a question for key {user_name_key}')
        update.message.reply_text(err_msg)
        return ConversationHandler.END

    variants = question['variants']
    correct_answers_ids = list(map(int, question['correct_answers']))
    correct_answers = {txt: idx for idx, txt in variants.items() if int(idx) in correct_answers_ids}
    if not correct_answers:
        logging.critical(f'Could not find correct answers! question: {question}, user_key: {user_name_key}')
        update.message.reply_text(err_msg)
        return ConversationHandler.END

    all_answers = {txt: idx for idx, txt in variants.items()}

    if update.message.text == '/rerun':
        CultureCaches().clear_caches(user_name_key)
        reply_with_starting_keyboard(update, BotConfig().phrases.get('rerun', err_msg))
        return AWAITING_START

    elif update.message.text in correct_answers.keys():
        CultureCaches().user_cache[user_name_key]['yes_count'] += 1
        answer_id = correct_answers[update.message.text]
        CultureCaches().answers_sequence[user_name_key].append(answer_id)
    elif update.message.text in all_answers.keys():
        CultureCaches().user_cache[user_name_key]['no_count'] += 1
        answer_id = all_answers[update.message.text]
        CultureCaches().answers_sequence[user_name_key].append(answer_id)
    else:
        reply_markup = ReplyKeyboardRemove()
        update.message.reply_text(BotConfig().phrases.get('not_recognized', err_msg),
                                  reply_markup=reply_markup)
        CultureCaches().clear_caches(user_name_key)
        return ConversationHandler.END

    # review stop iteration condition
    if CultureCaches().user_cache[user_name_key]['current_question'] >= CultureCaches().questions_count:
        reply_markup = ReplyKeyboardRemove()
        failed = CultureCaches().user_cache[user_name_key]['no_count']
        verdict = BotConfig().phrases.get('failed', err_msg) if failed > 0 \
            else BotConfig().phrases.get('passed', err_msg)
        update.message.reply_text(f'Конец разговора. {verdict}', reply_markup=reply_markup)
        CultureCaches().judge_cache.add(user_name_key)
        set_db_value(username=user_name_key,
                     answers=CultureCaches().answers_sequence[user_name_key],
                     **user_meta_info)
        return ConversationHandler.END

    next_question = get_question(user_name_key, increment_iter=False)
    ask_question_with_keyboard(update, next_question)

    return QUESTIONS


