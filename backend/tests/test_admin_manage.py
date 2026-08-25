"""The lockout guard around admin management.

Every rule here protects the same thing: there must always be at least one active superadmin,
because the only way to grant admin access is through a superadmin. Losing the last one means
no route back in short of editing the database by hand.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.manage import _may_demote
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.db.repositories import admin_repository


async def _add(
    session: AsyncSession,
    telegram_id: int,
    role: AdminRole = AdminRole.SUPERADMIN,
    *,
    is_active: bool = True,
) -> Admin:
    created = await admin_repository.create(
        session, telegram_id=telegram_id, full_name=f"Admin {telegram_id}", role=role
    )
    if not is_active:
        await admin_repository.set_active(session, created, False)
    return created


async def test_last_active_superadmin_cannot_be_demoted(
    db_session: AsyncSession, admin: Admin
) -> None:
    """`admin` (the conftest fixture) is the only superadmin here."""
    assert await admin_repository.count_active_superadmins(db_session) == 1

    allowed = await _may_demote(db_session, admin, new_role=AdminRole.MANAGER, is_active=True)
    assert allowed is False


async def test_last_active_superadmin_cannot_be_deactivated(
    db_session: AsyncSession, admin: Admin
) -> None:
    allowed = await _may_demote(
        db_session, admin, new_role=AdminRole.SUPERADMIN, is_active=False
    )
    assert allowed is False


async def test_superadmin_can_be_demoted_when_another_one_remains(
    db_session: AsyncSession, admin: Admin
) -> None:
    await _add(db_session, 222222, AdminRole.SUPERADMIN)
    assert await admin_repository.count_active_superadmins(db_session) == 2

    allowed = await _may_demote(db_session, admin, new_role=AdminRole.MANAGER, is_active=True)
    assert allowed is True


async def test_an_inactive_second_superadmin_does_not_count_as_a_backup(
    db_session: AsyncSession, admin: Admin
) -> None:
    """A deactivated superadmin cannot log in, so it must not license demoting the active one."""
    await _add(db_session, 333333, AdminRole.SUPERADMIN, is_active=False)
    assert await admin_repository.count_active_superadmins(db_session) == 1

    allowed = await _may_demote(db_session, admin, new_role=AdminRole.OPERATOR, is_active=True)
    assert allowed is False


@pytest.mark.parametrize("role", [AdminRole.MANAGER, AdminRole.OPERATOR])
async def test_non_superadmins_are_always_removable(
    db_session: AsyncSession, admin: Admin, role: AdminRole
) -> None:
    target = await _add(db_session, 444444, role)
    allowed = await _may_demote(db_session, target, new_role=role, is_active=False)
    assert allowed is True


async def test_promoting_someone_to_superadmin_is_always_allowed(
    db_session: AsyncSession, admin: Admin
) -> None:
    target = await _add(db_session, 555555, AdminRole.OPERATOR)
    allowed = await _may_demote(
        db_session, target, new_role=AdminRole.SUPERADMIN, is_active=True
    )
    assert allowed is True


async def test_created_admin_is_active_and_findable_by_telegram_id(
    db_session: AsyncSession,
) -> None:
    """What actually grants access: UserRegistrationMiddleware looks the new admin up by
    telegram_id on their next message, so the row must be active and indexed under that id."""
    created = await _add(db_session, 666666, AdminRole.MANAGER)

    found = await admin_repository.get_by_telegram_id(db_session, 666666)
    assert found is not None
    assert found.id == created.id
    assert found.is_active is True
    assert found.role == AdminRole.MANAGER


async def test_removed_admin_is_no_longer_found(db_session: AsyncSession) -> None:
    created = await _add(db_session, 777777, AdminRole.OPERATOR)
    await admin_repository.delete(db_session, created)

    assert await admin_repository.get_by_telegram_id(db_session, 777777) is None
