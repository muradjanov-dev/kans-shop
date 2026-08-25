from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import PaymentProvider, PaymentTxState
from app.db.models.payment_transaction import PaymentTransaction


async def create(
    session: AsyncSession,
    *,
    order_id: int,
    provider: PaymentProvider,
    amount: Decimal,
    provider_transaction_id: str | None = None,
    state: PaymentTxState = PaymentTxState.CREATED,
    raw_payload: dict | None = None,
) -> PaymentTransaction:
    tx = PaymentTransaction(
        order_id=order_id,
        provider=provider,
        provider_transaction_id=provider_transaction_id,
        amount=amount,
        state=state,
        raw_payload=raw_payload or {},
    )
    session.add(tx)
    await session.flush()
    return tx


async def get_by_provider_tx_id(
    session: AsyncSession,
    provider: PaymentProvider,
    provider_transaction_id: str,
    *,
    for_update: bool = False,
) -> PaymentTransaction | None:
    stmt = select(PaymentTransaction).where(
        PaymentTransaction.provider == provider,
        PaymentTransaction.provider_transaction_id == provider_transaction_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def get_by_order_and_provider(
    session: AsyncSession,
    order_id: int,
    provider: PaymentProvider,
    *,
    for_update: bool = False,
) -> PaymentTransaction | None:
    stmt = select(PaymentTransaction).where(
        PaymentTransaction.order_id == order_id, PaymentTransaction.provider == provider
    )
    if for_update:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt.order_by(PaymentTransaction.id.desc()))


async def update_state(
    session: AsyncSession,
    tx: PaymentTransaction,
    *,
    state: PaymentTxState,
    provider_transaction_id: str | None = None,
    raw_payload: dict | None = None,
) -> PaymentTransaction:
    tx.state = state
    if provider_transaction_id is not None:
        tx.provider_transaction_id = provider_transaction_id
    if raw_payload is not None:
        tx.raw_payload = raw_payload
    await session.flush()
    return tx
