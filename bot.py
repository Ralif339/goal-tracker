import config
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram import F
import sqlite3  
from pytz import timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram.filters import ChatMemberUpdatedFilter, KICKED
from aiogram.types import ChatMemberUpdated


bot = Bot(config.token)
dp = Dispatcher()

con = sqlite3.connect("database.db")
cur = con.cursor()
cur.execute("PRAGMA foreign_keys = ON;")

reminder_scheduler = AsyncIOScheduler(timezone=timezone("Europe/Moscow"))
reminder_scheduler_started = False

complete_task_button = InlineKeyboardButton(text='Завершить задачу', callback_data='complete_task')
task_keyboard = InlineKeyboardMarkup(inline_keyboard=[[complete_task_button]])


async def send_remind():
    sql_request = f"""
                SELECT name, status, deadline, user_id
                FROM Goals
                """
    for row in cur.execute(sql_request):
        goal_name, status, deadline, user_id = row
        deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        today = datetime.today().date()

        if (deadline_date - today).days == 1 and status == "В процессе":
            await bot.send_message(user_id, f'🔔Напоминаю, что для выполнения цели "{goal_name}" остался 1 день!')


async def send_motivation():
    sql_request = f"""
                SELECT name, status, user_id, creation_date
                FROM Goals
                """
    for row in cur.execute(sql_request):
        goal_name, status, user_id, creation_date = row
        creation_date = datetime.strptime(creation_date, "%Y-%m-%d").date()
        today = datetime.today().date()

        if (today - creation_date).days == 3 and status == "В процессе":
            await bot.send_message(user_id, f'🗿Да уж... Чем вы там занимаетесь!? У вас есть невыполненная цель: {goal_name}')


async def start_reminder_scheduler(user_id):
    global reminder_scheduler_started
    if not reminder_scheduler_started:
        reminder_scheduler.add_job(send_remind, CronTrigger(hour=10)) 
        reminder_scheduler.add_job(send_motivation, CronTrigger(hour=10)) 
        await bot.send_message(user_id, "🔔Напоминание за день до дедлайна включено!") 
        reminder_scheduler.start()
        reminder_scheduler_started = True
    

@dp.message(Command('start'))
async def process_start(message: Message):
    await message.answer("👋Приветствую, данный телеграм-бот поможет вам отслеживать ваши цели.\n" +
                         "Для дополнительной информации напишите /help")


@dp.message(Command('help'))
async def process_help(message: Message):
    await message.answer('🎯Создать цель: /add_goal [название] [дата:год-месяц-число]\n'+
                         '📝Разбить цель на подзадачи: /add_task [название] [дата:год-месяц-число] [goal_id]\n'+
                         '📈Просмотр целей и её прогресса: /list_goals\n'+
                         '📋Подробный просмотр задач выбранной цели: /view_goal [goal_id]\n'+
                         '✅Отметить задачу как выполненную: /done_task [task_id]\n'+
                         '✅Отметить цель как выполненную: /done_goal [goal_id]\n'+
                         '📊Статистика: /stats')
    
    
def find_name_arg(args: str) -> str:
    quotes_index = []
    name_arg = ""
    for index in range(len(args)):
        if args[index] == '"':
            quotes_index.append(index)

    if quotes_index:
        name_arg = args[quotes_index[0]+1:quotes_index[1]]
    else:
        return ""
        
    return name_arg
    
    
@dp.message(Command('add_goal'))
async def process_add_goal(message: Message, command: CommandObject):
    try:
        args = command.args
        name_arg = find_name_arg(args)
        date_arg = datetime.strptime(args.split('" ')[1], "%Y-%m-%d").date()
        deadline_arg = args.split('" ')[1]
        today = datetime.today().strftime("%Y-%m-%d")
        sql_request = f"""
            INSERT INTO Goals(Name, Deadline, Status, User_id, Creation_date) 
            VALUES ('{name_arg}', '{deadline_arg}', 'В процессе', {message.from_user.id}, '{today}')
            """
        cur.execute(sql_request)
        con.commit()
        await message.reply("✅Цель успешно добавлена!\nВы можете добавить подзадачи с помощью команды /add_task.")
        await start_reminder_scheduler(message.from_user.id)
    except Exception as ex:
        print(ex)
        await message.answer("⚠️Подсказка: чтобы добавить цель необходимо написать команду в следующем виде:\n" +
                             '/add_goal "[название]" [дата:год-месяц-число]\n' +
                             '📄Пример: /add_goal "Изучить JavaScript" 2025-02-28')
    
    
@dp.message(Command('list_goals'))
async def process_list_goals(message: Message):
    sql_request = f"""
        SELECT name, status, id
        FROM Goals
    """
    result = ""
    i = 1
    for row in cur.execute(sql_request):
        result += f"{i}) Цель: {row[0]}. Статус: {row[1]}. goal_id: {row[2]}.\n"
        i += 1
    if result:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Завершить цель', callback_data="complete_goal")]])
        await message.answer("🎯Список ваших целей:\n" + result, reply_markup=keyboard)
    else:
        await message.answer("❗Целей еще нет.\n" +
                             "⚠️Подсказка: чтобы добавить цель необходимо написать команду в следующем виде:\n" +
                             '/add_goal "[название]" [дата:год-месяц-число]\n' +
                             '📄Пример: /add_goal "Изучить JavaScript" 2025-02-28')

    
@dp.callback_query(F.data=="complete_goal")
async def process_complete_goal(callback):
    message_text = callback.message.text
    text_rows = message_text.split('\n')[1:]
    buttons = []
    for row in text_rows:
        goal_id = row.split()[-1].strip('.')
        goal_name = row.split(':')[1].split('.')[0].strip()
        buttons.append([InlineKeyboardButton(text=f"{goal_id}: {goal_name}", callback_data=f"complete_goal_{goal_id}")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        text="Выберите цель для завершения:",
        reply_markup=keyboard
    )
    
    
@dp.callback_query(F.data.startswith("complete_goal_"))
async def process_complete_goal_button_press(callback):
    goal_id = callback.data.split('_')[2]
    sql_request = f"""
        UPDATE Goals
        SET status = 'Выполнено'
        WHERE id = {goal_id}
    """
    cur.execute(sql_request)
    con.commit()
    await callback.message.edit_text(
        text="Цель отмечена завершенной!"
    )
    

@dp.message(Command('add_task'))
async def process_add_task(message: Message, command: CommandObject):
    try:
        args = command.args
        name_arg = find_name_arg(args)
        goal_id = args.split()[-1]
        deadline_arg = args.split('" ')[1].split()[0]
        date_arg = datetime.strptime(deadline_arg, "%Y-%m-%d").date()
        sql_request = f"""
            INSERT INTO Tasks(Name, Deadline, Goal_id, Status) 
            VALUES ('{name_arg}', '{deadline_arg}', {goal_id}, 'В процессе')
            """
        cur.execute(sql_request)
        con.commit()
        await message.reply("✅Задача успешно добавлена!")
    except Exception as ex:
        print(ex)
        await message.answer("⚠️Подсказка: чтобы добавить задачу необходимо написать команду в следующем виде:\n" +
                             '/add_task "[название]" [дата:год-месяц-число] [goal_id]\n' +
                             'Пример: /add_task "Прочитать книгу по JavaScript" 2025-01-25 1\n' +
                             "❗Узнать goal_id вы можете при помощи команды /list_goals")


@dp.message(Command('view_goal'))
async def process_view_goal(message: Message, command: CommandObject):
    goal_id = command.args
    user_id = message.from_user.id
    try:
        sql_request = f"""
                SELECT g.name, t.name, t.deadline, t.status, t.id, g.user_id
                FROM Tasks t INNER JOIN Goals g on g.id = t.goal_id
                WHERE g.id = {goal_id} and g.user_id = {user_id}
                """
        table = cur.execute(sql_request)
        result = ""
        goal_name = ""
        for row in table:
            goal_name = row[0]
            result += f"Задача: {row[1]}, срок: {row[2]}, статус: {row[3]}, task_id: {row[4]}.\n"
        if result:
            await message.answer(f"📋Ваши задачи для цели {goal_name}:\n" + result, reply_markup=task_keyboard)
        else:
            await message.answer("⚠️Цель и (или) задачи не существуют.")
    except Exception as ex:
        print(ex)
        await message.reply("⚠️Произошла ошибка! Убедитесь, что goal_id существует." +
                            " Для этого напишите команду /list_goals")


@dp.message(Command('done_goal'))
async def process_done_goal(message: Message, command: CommandObject):
    try:
        goal_id = command.args
        sql_request = f"""
                UPDATE Goals
                SET Status = 'Выполнено'
                WHERE Goals.id = {goal_id}
                """
        cur.execute(sql_request)
        con.commit()
        sql_request = f"""
                SELECT name
                FROM Goals
                WHERE Goals.id = {goal_id}
                """
        goal_name = cur.execute(sql_request).fetchone()[0]
        
        await message.reply(f'🎉Отличная работа!\nВы выполнили цель "{goal_name}".\nПродолжайте в том же духе!')
    except Exception as ex:
        print(ex)
        await message.answer("⚠️Подсказка: чтобы завершить цель необходимо написать команду в следующем виде:\n" +
                             "/done_goal [goal_id]\n" +
                             '📄Пример: /done_goal 1' +
                             "❗Узнать goal_id вы можете при помощи команды /list_goals")


@dp.message(Command('done_task'))
async def process_done_task(message: Message, command: CommandObject):
    try:
        task_id = command.args
        sql_request = f"""
                UPDATE Tasks
                SET Status = 'Выполнено'
                WHERE Tasks.id = {task_id}
                """
        cur.execute(sql_request)
        con.commit()
        sql_request = f"""
                SELECT name
                FROM Tasks
                WHERE Tasks.id = {task_id}
                """
        task_name = cur.execute(sql_request).fetchone()[0]
        
        await message.reply(f'🎉Отличная работа!\nВы выполнили задачу "{task_name}".\nПродолжайте в том же духе!')
    except Exception as ex:
        print(ex)
        await message.answer("⚠️Подсказка: чтобы завершить задачу необходимо написать команду в следующем виде:\n" +
                             "/done_task [task_id]\n" +
                             '📄Пример: /done_task 1\n' +
                             "❗Узнать task_id вы можете при помощи команды /view_goal [goal_id]")


@dp.message(Command('stats'))
async def process_user_stats(message: Message):
    sql_request = f"""
        SELECT COUNT(*)
        FROM Goals
        WHERE status = 'Выполнено'
    """
    goals_done = cur.execute(sql_request).fetchone()[0]
    sql_request = f"""
        SELECT COUNT(*)
        FROM Tasks
        WHERE status = 'Выполнено'
    """
    tasks_done = cur.execute(sql_request).fetchone()[0]
    sql_request = f"""
        SELECT COUNT(*)
        FROM Goals
    """
    goals_count = cur.execute(sql_request).fetchone()[0]
    sql_request = f"""
        SELECT COUNT(*)
        FROM Tasks
    """
    tasks_count = cur.execute(sql_request).fetchone()[0]
    if goals_count and tasks_count:
        await message.answer(f"Целей выполнено: {goals_done}({goals_done/goals_count*100}%).\nЗадач выполнено: {tasks_done}({tasks_done/tasks_count*100}%)")
    elif goals_count:
        await message.answer(f"Целей выполнено: {goals_done}({goals_done/goals_count*100}%).\nЗадач выполнено: {tasks_done}(0%)")
    else:
        await message.answer("⚠️Для начала добавьте цели и задачи!")

@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def process_user_blocked_bot(event: ChatMemberUpdated):
    try:
        sql_request = f"""
            SELECT id, user_id
            FROM Goals
            WHERE user_id = {event.from_user.id}
        """
        for row in cur.execute(sql_request):
            goal_id = row[0]
            delete_request = f"""
                DELETE FROM Tasks 
                WHERE goal_id = {goal_id}
            """
            cur.execute(delete_request)
            con.commit()
        for row in cur.execute(sql_request):
            goal_id = row[0]
            delete_request = f"""
                DELETE FROM Goals 
                WHERE id = {goal_id}
            """
            con.commit()
        print(f'Пользователь {event.from_user.id} заблокировал бота')
    except Exception as ex:
        print(ex)


@dp.callback_query(F.data=="complete_task")
async def process_button_press(callback):
    message_text = callback.message.text
    text_rows = message_text.split('\n')[1:]
    buttons = []
    for row in text_rows:
        task_id = row.split()[-1].strip('.')
        task_name = row.split(':')[1].split(',')[0].strip()
        buttons.append([InlineKeyboardButton(text=f"{task_id}: {task_name}", callback_data=f"complete_task_{task_id}")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        text="Выберите задачу для завершения:",
        reply_markup=keyboard
    )
    

@dp.callback_query(F.data.startswith("complete_task_"))
async def process_complete_task_button_press(callback):
    task_id = callback.data.split('_')[2]
    sql_request = f"""
        UPDATE Tasks
        SET status = 'Выполнено'
        WHERE id = {task_id}
    """
    cur.execute(sql_request)
    con.commit()
    await callback.message.edit_text(
        text="Задача отмечена завершенной!"
    )


@dp.message()
async def process_unknown_command(message: Message):
    await message.reply("⚠️Неизвестная команда.\n" + 
                        "Для получения помощи напишите /help")


async def main():
    global reminder_scheduler_started
    reminder_scheduler_started = False
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())