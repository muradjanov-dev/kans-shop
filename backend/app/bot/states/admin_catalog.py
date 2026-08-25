from aiogram.fsm.state import State, StatesGroup


class ProductFormStates(StatesGroup):
    choosing_category = State()
    entering_name_uz = State()
    entering_description_uz = State()
    entering_sku = State()
    entering_price = State()
    entering_stock = State()
    choosing_unit = State()
    uploading_images = State()
    reviewing = State()


class ProductEditStates(StatesGroup):
    editing_field = State()
    uploading_images = State()


class StockAdjustStates(StatesGroup):
    entering_custom_amount = State()


class CategoryFormStates(StatesGroup):
    entering_name_uz = State()


class BroadcastFormStates(StatesGroup):
    entering_content = State()
    choosing_button = State()
    entering_button_text = State()
    entering_button_url = State()
    choosing_target = State()
    confirming = State()
    sending = State()


class SettingEditStates(StatesGroup):
    entering_value = State()


class SourceFormStates(StatesGroup):
    entering_name = State()
    entering_code = State()


class AdminManageFormStates(StatesGroup):
    entering_telegram_id = State()
    entering_name = State()
    choosing_role = State()
