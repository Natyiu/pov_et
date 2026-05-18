from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import CreditType, POINTS, ReputationLog, User, level_for_points


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    display_name: str,
    credit_type: CreditType,
    credit_value: str | None = None,
    bio: str | None = None,
) -> User:
    user = User(
        telegram_id=telegram_id,
        display_name=display_name,
        credit_type=credit_type,
        credit_value=credit_value,
        bio=bio,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(session: AsyncSession, user: User, **kwargs) -> User:
    for key, value in kwargs.items():
        setattr(user, key, value)
    await session.commit()
    await session.refresh(user)
    return user


async def add_reputation(
    session: AsyncSession,
    user: User,
    reason: str,
) -> tuple[int, bool]:
    points = POINTS.get(reason, 0)
    if points == 0:
        return user.reputation_points, False

    old_level = user.level
    user.reputation_points += points
    new_level = level_for_points(user.reputation_points)
    leveled_up = new_level != old_level
    user.level = new_level

    log = ReputationLog(
        user_id=user.id,
        points_added=points,
        reason=reason,
        timestamp=datetime.utcnow(),
    )
    session.add(log)
    await session.commit()
    return user.reputation_points, leveled_up


async def ban_user(session: AsyncSession, user: User):
    user.is_banned = True
    await session.commit()
