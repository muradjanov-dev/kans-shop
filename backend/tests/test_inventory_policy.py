from app.db.repositories import setting_repository
from app.services.inventory_policy import get_inventory_policy


async def test_inventory_policy_defaults_to_tracking_when_unset(db_session):
    policy = await get_inventory_policy(db_session)

    assert policy.stock_tracking_enabled is True


async def test_inventory_policy_reads_persisted_false(db_session):
    await setting_repository.set_value(db_session, "stock_tracking_enabled", False)

    policy = await get_inventory_policy(db_session)

    assert policy.stock_tracking_enabled is False


async def test_inventory_policy_malformed_value_fails_safe_to_tracking(db_session):
    await setting_repository.set_value(db_session, "stock_tracking_enabled", "false")

    policy = await get_inventory_policy(db_session)

    assert policy.stock_tracking_enabled is True
