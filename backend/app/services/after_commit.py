"""Small transaction hook for effects that must follow a durable purchase commit."""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

log = get_logger(__name__)

AfterCommitAction = Callable[[], Awaitable[None]]
_ACTIONS_KEY = "app.services.after_commit.actions"


def register_after_commit(session: AsyncSession, action: AfterCommitAction) -> None:
    """Queue an ID-based effect to run only after this session commits successfully."""
    actions: list[AfterCommitAction] = session.info.setdefault(_ACTIONS_KEY, [])
    actions.append(action)


async def commit_with_after_commit(session: AsyncSession) -> None:
    """Commit first, then run queued effects without changing the commit outcome."""
    actions: list[AfterCommitAction] = session.info.pop(_ACTIONS_KEY, [])
    # Actions are removed before commit, so a failed commit can never leak them into a later
    # transaction on the same session.
    await session.commit()

    for action in actions:
        try:
            await action()
        except Exception:
            event_id = getattr(
                action,
                "after_commit_event_id",
                getattr(action, "__name__", "unknown_after_commit_action"),
            )
            log.error("after_commit_action_failed", event_id=event_id)
