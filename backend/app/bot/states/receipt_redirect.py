from aiogram.fsm.state import State, StatesGroup


class ReceiptRedirectStates(StatesGroup):
    """Standalone from CheckoutStates: entered via a `receipt_{order_id}` deep link when a
    customer places a card_transfer order from the web storefront (which has no in-app photo
    upload) and is redirected into the bot just to attach the receipt to that existing order.
    """

    uploading = State()
