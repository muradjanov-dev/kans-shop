from aiogram.fsm.state import State, StatesGroup


class AdminOrderStates(StatesGroup):
    entering_cancel_reason = State()
    writing_to_customer = State()
