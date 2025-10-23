from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime


from states.booking import BookingStates
from services.email_sender import send_booking_email
from database.db import save_booking, mark_slot_as_taken, save_slot, get_available_time_slots
from services.google import get_available_dates_for_branch, get_active_branches

booking_router = Router()


# --- Начало записи ---
@booking_router.message(F.text == "Начать запись")
async def start_cmd(message: Message, state: FSMContext):
    await state.set_state(BookingStates.choosing_branch)

    branches = get_active_branches()
    if not branches:
        await message.answer("❌ Не удалось получить список филиалов из Google Sheets.")
        return

    builder = InlineKeyboardBuilder()
    for branch in branches:
        builder.button(text=branch, callback_data=f"select_branch:{branch}")
    builder.adjust(2)

    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Для записи к стилисту, пожалуйста, выберите <b>Магазин</b>:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# --- Выбор даты ---
@booking_router.callback_query(F.data.startswith("select_branch:"))
async def branch_selected(callback: CallbackQuery, state: FSMContext):
    branch = callback.data.split("select_branch:")[1].strip()
    await state.update_data(branch=branch)
    await state.set_state(BookingStates.choosing_date)

    dates = get_available_dates_for_branch(branch)

    builder = InlineKeyboardBuilder()
    if dates:
        for date in dates:
            try:
                display_date = datetime.strptime(date, "%m/%d/%Y").strftime("%d-%m-%Y")
            except ValueError:
                display_date = date
            builder.button(text=display_date, callback_data=f"select_date:{date}")
    else:
        builder.button(text="Нет доступных дат", callback_data="none")

    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_branch"))

    await callback.message.edit_text(
        f"📍 <b>{branch}</b>\n\n"
        "Выберите дату для записи:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

# --- Выбор времени ---
@booking_router.callback_query(F.data.startswith("select_date:"))
async def date_selected(callback: CallbackQuery, state: FSMContext):
    date = callback.data.split("select_date:")[1].strip()
    await state.update_data(date=date)
    data = await state.get_data()
    branch = data["branch"]

    try:
        display_date = datetime.strptime(data['date'], "%m/%d/%Y").strftime("%d-%m-%Y")
    except ValueError:
        display_date = data['date']

    tg_user_id = callback.from_user.id

    available_times = get_available_time_slots(branch, date, tg_user_id)

    builder = InlineKeyboardBuilder()
    if available_times:
        for t in available_times:
            builder.button(text=t, callback_data=f"select_time:{t}")
    else:
        builder.button(text="Нет свободных слотов", callback_data="none")

    builder.button(text="⬅️ Назад", callback_data="back_to_date")
    builder.adjust(3, 3, 1)

    await callback.message.edit_text(
        f"📅 Дата: <b>{display_date}</b>\nВыберите время:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# --- Имя ---
@booking_router.callback_query(F.data.startswith("select_time:"))
async def time_selected(callback: CallbackQuery, state: FSMContext):
    time = callback.data.split("select_time:")[1]
    await state.update_data(time=time)
    await state.set_state(BookingStates.choosing_name)

    await callback.message.edit_text("Введите ваше <b>имя</b>:", parse_mode="HTML")
    await callback.answer()


# --- Телефон ---
@booking_router.message(BookingStates.choosing_name)
async def name_received(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(BookingStates.choosing_phone)
    await message.answer("Теперь отправьте <b>номер телефона</b> (в формате +7...):", parse_mode="HTML")


# --- Подтверждение ---
@booking_router.message(BookingStates.choosing_phone)
async def phone_received(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    data = await state.get_data()

    try:
        display_date = datetime.strptime(data['date'], "%m/%d/%Y").strftime("%d-%m-%Y")
    except ValueError:
        display_date = data['date']

    summary = (
        f"Вы выбрали:\n"
        f"📍 Магазин: <b>{data['branch']}</b>\n"
        f"📅 Дата: <b>{display_date}</b>\n"
        f"🕒 Время: <b>{data['time']}</b>\n"
        f"👤 Имя: <b>{data['name']}</b>\n"
        f"📞 Телефон: <b>{data['phone']}</b>\n\n"
        f"Подтвердить запись?"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm_booking")
    builder.button(text="⬅️ Назад", callback_data="back_to_time")
    builder.adjust(1, 1)

    await state.set_state(BookingStates.confirming)
    await message.answer(summary, reply_markup=builder.as_markup(), parse_mode="HTML")


# --- Финальное подтверждение ---
@booking_router.callback_query(F.data == "confirm_booking")
async def confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    data["user_id"] = callback.from_user.id

    try:
        if callback.message.text != "⏳ Отправляем данные...":
            await callback.message.edit_text("⏳ Отправляем данные...")
    except TelegramBadRequest:
        pass

    try:
        success, msg = await save_slot(
            branch=data["branch"],
            date=data["date"],
            time=data["time"],
            tg_user_id=data["user_id"],
            username=callback.from_user.username or data["name"],
            phone=data["phone"]
        )

        if not success:
            await callback.message.edit_text(msg)
            await state.clear()
            await callback.answer()
            return

        send_booking_email(data)
        mark_slot_as_taken(data["date"], data["time"], data["branch"], data["user_id"])
        save_booking(data)

        try:
            display_date = datetime.strptime(data['date'], "%m/%d/%Y").strftime("%d-%m-%Y")
        except ValueError:
            display_date = data['date']

        done = (
            f"<b>{data['name']}, Вы успешно записаны! ✅</b>\n\n"
            f"📍 Магазин: <b>{data['branch']}</b>\n"
            f"📅 Дата: <b>{display_date}</b>\n"
            f"🕒 Время: <b>{data['time']}</b>\n\n"
            f"Спасибо, что выбрали нас!"
        )

        await callback.message.edit_text(done, parse_mode="HTML")

    except Exception as e:
        print(f"[BOOKING ERROR]: {e}")
        try:
            await callback.message.edit_text("❌ Не удалось записать вас. Попробуйте позже.")
        except TelegramBadRequest:
            pass

    await state.clear()
    await callback.answer()
