from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from datetime import datetime

from states.booking import BookingStates
from database.db import get_available_time_slots
from services.google import get_active_branches

back_router = Router()


@back_router.callback_query(F.data == "back_to_branch")
async def back_to_branch(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_branch)

    branches = get_active_branches()

    builder = InlineKeyboardBuilder()
    for branch in branches:
        builder.button(text=branch, callback_data=f"select_branch:{branch}")
    builder.adjust(2)

    await callback.message.edit_text(
        "👋 <b>Добро пожаловать!</b>\n\nВыберите <b>Магазин</b>:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@back_router.callback_query(F.data == "back_to_date")
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    branch = data.get("branch")

    if not branch:
        await callback.message.edit_text("⚠️ Ошибка: не удалось определить магазин. Попробуйте начать заново.")
        return

    await state.set_state(BookingStates.choosing_date)

    from services.google import get_available_dates_for_branch
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
        f"📍 <b>{branch}</b>\n\nВыберите дату:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()



@back_router.callback_query(F.data == "back_to_time")
async def back_to_time(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_time)
    data = await state.get_data()
    branch = data.get("branch", "не выбран")
    date = data.get("date", "не выбрана")

    try:
        display_date = datetime.strptime(date, "%m/%d/%Y").strftime("%d-%m-%Y")
    except ValueError:
        display_date = date

    tg_user_id = callback.from_user.id


    times = get_available_time_slots(branch, date, tg_user_id)

    builder = InlineKeyboardBuilder()
    for time in times:
        builder.button(text=time, callback_data=f"select_time:{time}")
    builder.button(text="⬅️ Назад", callback_data="back_to_date")
    builder.adjust(3, 3, 1)

    await callback.message.edit_text(
        f"📍 Магазин: <b>{branch}</b>\n"
        f"📅 Дата: <b>{display_date}</b>\n\n"
        "Выберите время:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()