from aiogram.fsm.state import State, StatesGroup


class CheckoutStates(StatesGroup):
    choosing_type = State()
    entering_name = State()
    entering_phone = State()
    entering_address = State()
    entering_address_comment = State()
    entering_comment = State()
    choosing_payment = State()
    uploading_receipt = State()
    confirming = State()
