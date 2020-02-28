import json
import boto3
import os
import sys
import logging

from collections import defaultdict
from functools import partial
from typing import List, Tuple
from functools import wraps

USER_TABLE_NAME = 'LinkGiverTable'
CONFIG_TABLE_NAME = 'LinkGiverConfig'
QUESTION_TABLE_NAME = 'LinkGiverQuestions'
UNAME_KEY = 'Username'
ANSWERS_KEY = 'answers'
KEY_LOC = '../keys/keys.json'
logger = logging.getLogger(__name__)


class DynamoDBCachePopulationErr(Exception):
    pass


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class CultureCaches(object, metaclass=Singleton):
    def __init__(self):
        self.answers_sequence = defaultdict(list)
        with open(KEY_LOC, 'r') as f:
            keys = json.load(f)

        db = boto3.resource('dynamodb', region_name='eu-north-1', **keys)
        user_data_table = db.Table(USER_TABLE_NAME)
        records = user_data_table.scan().get('Items')
        if not records:
            raise DynamoDBCachePopulationErr(f'Failed to fetch data from {USER_TABLE_NAME}')

        self.judge_cache = set()
        self.user_cache = defaultdict(partial(defaultdict, int))
        for entry in records:
            username_key = entry[UNAME_KEY]
            user_answers = entry[ANSWERS_KEY]
            self.judge_cache.add(username_key)
            yes_count, no_count = CultureCaches.get_answer_counts(user_answers)
            self.user_cache[username_key]['yes_count'] = yes_count
            self.user_cache[username_key]['no_count'] = no_count
            self.user_cache[username_key]['current_question'] = len(user_answers)

        questions_table = db.Table(QUESTION_TABLE_NAME)
        questions = questions_table.scan().get('Items')
        if not questions:
            raise DynamoDBCachePopulationErr(f'Failed to fetch data from {QUESTION_TABLE_NAME}')
        self.questions_cache = {int(item['id']): item for item in questions}
        self.questions_count = len(self.questions_cache)

    def clear_caches(self, key: str) -> None:
        if key in self.user_cache:
            del self.user_cache[key]
        if key in self.answers_sequence:
            del self.answers_sequence[key]

    @staticmethod
    def get_answer_counts(user_answers: List[bool]) -> Tuple[int, int]:
        yes_count = 0
        no_count = 0
        for answer in user_answers:
            if answer:
                yes_count += 1
            else:
                no_count += 1
        return yes_count, no_count


def set_db_value(username, answers, **kwargs):
    with open(KEY_LOC) as f:
        keys = json.load(f)
    db = boto3.resource('dynamodb', region_name='eu-north-1', **keys)
    table = db.Table(USER_TABLE_NAME)
    with table.batch_writer() as batch:
        batch.put_item(Item={UNAME_KEY: username, ANSWERS_KEY: answers, **kwargs})


class BotConfig(object, metaclass=Singleton):
    def __init__(self):
        with open(KEY_LOC, 'r') as f:
            keys = json.load(f)
        db = boto3.resource('dynamodb', region_name='eu-north-1', **keys)
        user_data_table = db.Table(CONFIG_TABLE_NAME)
        cfg = user_data_table.scan().get('Items')[0]
        self.admins = cfg['Admins']
        self.updater = None
        self.phrases = cfg['bot_strings']
        self.restrict_reruns = cfg['restrict_reruns']


def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in BotConfig().admins:
            logging.critical("Unauthorized access denied for {}.".format(user_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped


def stop_and_restart():
    """Gracefully stop the Updater and replace the current process with a new one"""
    BotConfig().updater.stop()
    logger.info('Bot stopped')
    os.execl(sys.executable, sys.executable, *sys.argv)


@restricted
def restart(update, context):
    pass

# dynamo db examples to avoid looking up docs
# def dynamoDBTest():
#     with open('../keys/keys.json', 'r') as f:
#         keys = json.load(f)
#     db = boto3.resource('dynamodb', region_name='eu-north-1', **keys)
#     table = db.Table('LinkGiverTable')
#     record = table.get_item(Key={"Username": "TestUser1"}).get("Item").get('answers')
#     # with table.batch_writer() as batch:
#     #     batch.put_item(Item={"Author": "John Grisham", "Title": "The Rainmaker",
#     #                      "Category": "Suspense", "Formats": {"Hardcover": "J4SUKVGU", "Paperback": "D7YF4FCX"}})
#     # data = table.scan()
#     # table.update_item(Key={'Username': 'TestUser2'},
#     #                   ExpressionAttributeNames={'#answers': 'answers'},
#     #                   ExpressionAttributeValues={':new_answers': [True, True, False]},
#     #                   UpdateExpression="SET #answers = :new_answers")
#     print(1)
