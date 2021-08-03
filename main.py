import datetime
import json
import logging
import os

import dotenv
import requests
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from bs4 import BeautifulSoup
from googletrans import Translator
from sqlalchemy.orm import sessionmaker
from sqlalchemy.util import asyncio
from tabulate import tabulate

from models import database_dsn, Note, Translation

logging.basicConfig(level=logging.INFO)

dotenv.load_dotenv()

bot = Bot(token=os.getenv('TOKEN'))
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

session = sessionmaker(bind=database_dsn)()


class TranslateForm(StatesGroup):
    lang_src = State()
    lang_dst = State()
    execute = State()


class Form(StatesGroup):
    repeat = State()
    note = State()
    shop = State()


@dp.message_handler(commands=['start'])
async def send_greeting(message: types.Message):
    await bot.send_message(message.chat.id, f'Привет, я Пиксель, самый маленький член семьи, '
                                            f'но служу так, что позавидуют многие 😊\n\n'
                                            f'С чего начем <b>{message.chat.first_name}</b>? '
                                            f'Подсказка - /menu', parse_mode='html')


@dp.message_handler(commands=['menu'])
async def create_menu(message: types.Message):
    markup = types.ReplyKeyboardMarkup(row_width=3, resize_keyboard=True, one_time_keyboard=True, keyboard=[
        [
            types.KeyboardButton('/повторяй_за_мной'),
            types.KeyboardButton('/заметки'),
        ],
        [
            types.KeyboardButton('/дополнительно'),
            types.KeyboardButton('/поиск_в_магазинах')
        ],
    ])

    await bot.send_message(message.chat.id, 'Меню:', reply_markup=markup)


@dp.message_handler(commands=['повторяй_за_мной'], state='*')
async def command_repeat(message: types.Message):
    logging.info(f'The bot started repeating after the user {message.from_user.id}')
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[[types.KeyboardButton('/отключить_повторение')]],
                                       one_time_keyboard=True)
    await Form.repeat.set()
    await message.reply('Напиши что-то:', reply_markup=markup)


@dp.message_handler(state='*', commands='отключить_повторение')
async def handler_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info('Cancelling state %r', current_state)
    await state.finish()
    await message.reply('Успешно')


@dp.message_handler(state=Form.repeat)
async def handler_repeat(message: types.Message):
    await message.reply(message.text)


@dp.message_handler(state='*', commands='заметки')
async def notes(message: types.Message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [
            types.KeyboardButton('/создать_заметку'),
        ],
        [
            types.KeyboardButton('/последняя_заметка'),
        ],
        [
            types.KeyboardButton('/поиск_заметок'),
        ],
    ])
    await message.reply('Выберите:', reply_markup=markup)


@dp.message_handler(state='*', commands='дополнительно')
async def additional_features(message: types.Message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [
            types.KeyboardButton('/случайная_шутка'),
            types.KeyboardButton('/переведи_текст')
        ],
    ])
    await message.reply('Выберите:', reply_markup=markup)


@dp.message_handler(state='*', commands='создать_заметку')
async def command_note(message: types.Message):
    logging.info(f'The note was created by the user {message.from_user.id}')
    await Form.note.set()
    await bot.send_message(
        message.chat.id,
        'Напишите заметку и я её запишу\n(P.S: клянусь что никому не покажу 😁)',
        parse_mode='html'
    )


@dp.message_handler(state=Form.note)
async def save_note(message: types.Message, state: FSMContext):
    logging.info(f'The note was saved for the user {message.from_user.id}')
    query = Note(user_id=message.from_user.id, note=message.text, created_at=datetime.datetime.now())
    session.add(query)
    session.commit()
    await state.finish()
    await bot.send_message(message.chat.id, 'Записал, спасибо за доверие  😉')


@dp.message_handler(commands='последняя_заметка', state='*')
async def command_my_note(message: types.Message, state: FSMContext):
    logging.info(f'The last note was viewed by the user {message.from_user.id}')
    try:
        my_note = session.query(Note).filter(Note.user_id == message.from_user.id).order_by(Note.id.desc()).first()
        await bot.send_message(message.chat.id, my_note.note)
        await state.finish()
    except AttributeError as e:
        await bot.send_message(message.chat.id, f'У вас пока нет заметок\n')
        logging.info(f' Error: {e} with user. Error occurred with user: {message.from_user.id}')


@dp.message_handler(commands='случайная_шутка')
async def handler_joke(message: types.Message):
    logging.info(f'The joke was created by the user {message.from_user.id}')
    url = r"https://official-joke-api.appspot.com/random_joke"
    request = requests.get(url)
    data = json.loads(request.text)
    await bot.send_message(message.chat.id, 'Вот и твоя шутка')
    await asyncio.sleep(1)
    await bot.send_message(message.chat.id, data["setup"])
    await asyncio.sleep(3)
    await bot.send_message(message.chat.id, data['punchline'])


@dp.message_handler(state='*', commands='переведи_текст')
async def handler_translate(message: types.Message):
    await bot.send_message(message.chat.id, 'Правила:\n1.Язык должен быть написан на английском<b>!</b>\n'
                                            '<b>Пример</b>: Russian или ru\n'
                                            '2.Доступны почти все языки мира<b>!</b>\n'
                                            '3.Если вы напишите неправилный язык то перевод будет <b>Неверный!</b>\n'
                                            '4.Текст не должен превышать 1000 символов<b>!</b>',
                           parse_mode='html')
    await message.reply('На каком языке написан ваш текст?')
    await TranslateForm.lang_src.set()


@dp.message_handler(state=TranslateForm.lang_src)
async def handler_translate_lang_src(message: types.Message, state: FSMContext):
    lang_src = message.text
    await state.update_data({'lang_src': lang_src})

    await message.reply('В какой язык вы хотите его перевести?')
    await TranslateForm.lang_dst.set()


@dp.message_handler(state=TranslateForm.lang_dst)
async def handler_translate_lang_dst(message: types.Message, state: FSMContext):
    lang_dst = message.text
    await state.update_data({'lang_dst': lang_dst})

    await bot.send_message(message.chat.id, 'Пишите текст:\n'
                                            '<b>Warning - (Текст не должен превышать 1000 символов)</b>',
                           parse_mode='html')
    await TranslateForm.execute.set()


@dp.message_handler(state=TranslateForm.execute)
async def handler_translate_execute(message: types.Message, state: FSMContext):
    translator = Translator()
    data = await state.get_data()
    lang_src = data.get('lang_src')
    lang_dst = data.get('lang_dst')
    try:
        result = translator.translate(message.text[:1000], src=lang_src, dest=lang_dst)
        query = Translation(user_id=message.from_user.id,
                            original_text=message.text,
                            translation_text=result.text,
                            original_language=result.src,
                            translation_language=result.dest,
                            created_at=datetime.datetime.now(),
                            )
        session.add(query)
        session.commit()
        await bot.send_message(message.chat.id, result.text)
        await state.finish()
    except ValueError as e:
        await bot.send_message(message.chat.id, f'Вы ввели неверный язык - {e}')
        await handler_translate(message)
        logging.info(f'User {message.from_user.id} translated the text')


@dp.inline_handler(lambda query: len(query.query) > 0, state='*')
async def view_data(query: types.InlineQuery):
    if query.query.lower().split(':')[0] == 'notes':
        note_title, save_note_data = await handler_notes(query)
        await bot.answer_inline_query(note_title, save_note_data, cache_time=False)
    elif query.query.lower().split(':')[0] == 'shop':
        product_title, save_product_data = await handler_goods(query)
        await bot.answer_inline_query(product_title, save_product_data, cache_time=False)
        await Form.shop.set()


@dp.message_handler(commands=['поиск_заметок'])
async def command_notes(message: types.Message):
    logging.info(f'A user has started searching for notes {message.from_user.id}')
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton('Поиск', switch_inline_query_current_chat='notes:'))
    await bot.send_message(message.chat.id, "Поиск заметок:", reply_markup=keyboard)


@dp.inline_handler()
async def handler_notes(note_title):
    name = note_title.query.lower().split(':')[-1]
    note_data = session.query(Note).filter((Note.note.contains(name)) &
                                           (Note.user_id == note_title.from_user.id)).limit(20)
    save_note_data = []
    for i in note_data:
        content = types.InputTextMessageContent(
            message_text=f'Твоя запись: {i.note}',
        )

        data = types.InlineQueryResultArticle(
            id=i.id,
            title=i.note,
            description=f'Запись была создана: {i.created_at}',
            input_message_content=content
        )
        save_note_data.append(data)
    return note_title.id, save_note_data


@dp.message_handler(commands='поиск_в_магазинах')
async def command_goods(message: types.Message):
    logging.info(f'User {message.from_user.id} started searching for products')
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton('Поиск', switch_inline_query_current_chat='shop:'))
    await bot.send_message(message.chat.id, "Поиск товаров:", reply_markup=keyboard)


@dp.inline_handler()
async def handler_goods(product_title):
    product_name = product_title.query.lower().split(':')[-1]
    save_product_data = []
    i = 0
    page = 1
    elements = 0
    while True:
        r = requests.get(f'https://e-catalog.md/ro/search?q={product_name}&page={page}')
        html = BeautifulSoup(r.text, 'html.parser')
        items = html.select('.products-list__body > .products-list__item')
        if len(items):
            for el in items:
                if elements == 20:
                    break
                else:
                    image = el.select('.product-card > .product-card__image > a > img')
                    title = el.select('.product-card > .product-card__info > .product-card__name > a')
                    price = el.select('.product-card > .product-card__actions > .product-card__prices > span')

                    if not price:
                        price = 'Not found'
                    else:
                        price = price[0].text

                    content = types.InputTextMessageContent(
                        message_text=title[0].get('href')
                    )
                    i += 1
                    elements += 1
                    data = types.InlineQueryResultArticle(
                        id=str(i),
                        title=f'Название: {title[0].text}',
                        description=f'Цена: {price}',
                        input_message_content=content,
                        thumb_url=image[0].get('src'),
                        thumb_width=48,
                        thumb_height=48

                    )
                    save_product_data.append(data)
                    continue
            page += 1
        return product_title.id, save_product_data


@dp.message_handler(state=Form.shop)
async def description_detail_goods(message: types.Message, state: FSMContext):
    column = []
    row = []
    table = []

    detail_description_goods = message.text
    await state.update_data({'detail_goods': detail_description_goods})
    data = await state.get_data()

    data = data.get('detail_goods')
    try:
        request = requests.get(data)
    except Exception as e:
        logging.info(f'User with id {message.from_user.id} violated parsing processing. Error: {e}')
        await bot.send_message(message.chat.id, 'Пожалуйста, ничего не пишите в чат и попробуйте снова!')
        await state.finish()
    else:
        html_content = BeautifulSoup(request.text, 'html.parser')
        await bot.send_message(message.chat.id, 'Одну секунду, собираю информацию...')
        await bot.send_message(message.chat.id, 'Советую перевернуть телефон в горизонтальное положение!')
        await asyncio.sleep(2)
        for detail_data in html_content.select('.spec > .spec__section > .spec__row'):
            title = detail_data.select('.spec__name')
            detail = detail_data.select('.spec__value')
            row.append(title[0].text)
            column.append(detail[0].text)
            continue

        headers = ["Category", "Description"]

        for i in range(len(column)):
            table.append([row[i], column[i]])
        data = tabulate(tabular_data=table, headers=headers, tablefmt="fancy_grid")
        await bot.send_message(message.chat.id, 'Характеристики товара:')
        await asyncio.sleep(1)
        await bot.send_message(message.chat.id, f'```{data}```', parse_mode="Markdown")
        await comment_detail_goods(message, state)


@dp.message_handler(state=Form.shop)
async def comment_detail_goods(message: types.Message, state: FSMContext):
    comments_author = []
    comments_content = []
    comments_date = []
    formatted_text = []
    tb = []

    data_state = await state.get_data()
    data = data_state.get('detail_goods')

    try:
        request = requests.get(data)
    except Exception as e:
        logging.info(f'User with id {message.from_user.id} violated parsing processing. Error: {e}')
        await bot.send_message(message.chat.id, 'Пожалуйста, ничего не пишите в чат и попробуйте снова!')
        await state.finish()
    else:
        html_content = BeautifulSoup(request.text, 'html.parser')

        def group_by_length(words, length=100):
            current_index = 0
            current_length = 0
            for k, word in enumerate(words):
                current_length += len(word) + 1
                if current_length > length:
                    yield words[current_index:k]
                    current_index = k
                    current_length = len(word)
            else:
                yield words[current_index:]

        for detail_comments in html_content.select('.reviews-list__content > .reviews-list__item'):
            author = detail_comments.select('.review > .review__content > .review__author')
            text = detail_comments.select('.review > .review__content > .review__text')
            date = detail_comments.select('.review > .review__content > .review__date')
            comments_author.append(author[0].text)
            comments_content.append(text[0].text)
            comments_date.append(date[0].text)
            formatted_text.append('\n'.join(' '.join(row) for row in group_by_length(text[0].text.split(' '), 50)))
            continue
        await bot.send_message(message.chat.id, 'Отзывы:')
        if not comments_author:
            await bot.send_message(message.chat.id, 'К сожеленю, отзывов у данного товара нету')
            await shop_detail_goods(message, state)
        else:
            header = ["User", "Date", "Content"]
            for i in range(len(comments_content)):
                tb.append([comments_author[i], comments_date[i], formatted_text[i]])

            data = tabulate(tabular_data=tb, tablefmt="fancy_grid", headers=header, stralign='left')
            await asyncio.sleep(1)
            await bot.send_message(message.chat.id, f'```{data}```', parse_mode="Markdown")
            await shop_detail_goods(message, state)


@dp.message_handler(state=Form.shop)
async def shop_detail_goods(message: types.Message, state: FSMContext):
    shop_name = []
    shop_price = []
    shop_link = []
    tb = []
    count = 0

    data_state = await state.get_data()
    data = data_state.get('detail_goods')

    request = requests.get(data)
    await state.finish()
    html_content = BeautifulSoup(request.text, 'html.parser')
    for detail_shop in html_content.select('.listing_container > .available'):
        image = detail_shop.select('.item_info > .item_merchant > .merchant_logo > img')
        price = detail_shop.select('.item_price > .item_basic_price')
        link = detail_shop.select('.item_actions > a')

        shop_name.append(image[0].get('alt'))
        shop_price.append(price[0].text)
        shop_link.append(link[0].get('href'))
        continue
    await bot.send_message(message.chat.id, 'Магазины:')

    header = ["Name", "Price", "Link"]

    for i in range(len(shop_name)):
        tb.append([shop_name[i], shop_price[i], shop_link[i]])
        count += 1
        if count == 7:
            break
    data = tabulate(tabular_data=tb, tablefmt="fancy_grid", headers=header, stralign='left')
    await bot.send_message(message.chat.id, f'```{data}```', parse_mode="MarkdownV2")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=False)
