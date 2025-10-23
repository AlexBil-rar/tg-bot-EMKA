from aiogram.fsm.state import StatesGroup, State

class BookingStates(StatesGroup):
    choosing_branch = State()
    choosing_date = State()
    choosing_time = State()
    choosing_name = State()
    choosing_phone = State()
    confirming = State()
