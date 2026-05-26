from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.models import Media, Submission, SubmissionStatus


async def create_submission(
    session: AsyncSession,
    user_id: int,
    caption: str | None,
    location: str | None,
    file_ids: list[str],
    hashtags: list[str] | None = None,
) -> Submission:
    submission = Submission(
        user_id=user_id,
        caption=caption,
        location=location,
        hashtags=",".join(hashtags) if hashtags else None,
        status=SubmissionStatus.pending,
    )
    session.add(submission)
    await session.flush()

    for idx, file_id in enumerate(file_ids):
        media = Media(
            submission_id=submission.id,
            telegram_file_id=file_id,
            order_index=idx,
        )
        session.add(media)

    await session.commit()
    await session.refresh(submission)
    return submission


async def get_submission(session: AsyncSession, submission_id: int) -> Submission | None:
    result = await session.execute(
        select(Submission)
        .options(selectinload(Submission.media))
        .where(Submission.id == submission_id)
    )
    return result.scalar_one_or_none()


async def get_pending_submissions(session: AsyncSession) -> list[Submission]:
    result = await session.execute(
        select(Submission)
        .options(selectinload(Submission.media))
        .where(Submission.status == SubmissionStatus.pending)
        .order_by(Submission.created_at)
    )
    return result.scalars().all()


async def update_submission_status(
    session: AsyncSession,
    submission: Submission,
    status: SubmissionStatus,
    admin_note: str | None = None,
    channel_message_id: int | None = None,
) -> Submission:
    submission.status = status
    submission.reviewed_at = datetime.utcnow()
    if admin_note:
        submission.admin_note = admin_note
    if channel_message_id is not None:
        submission.channel_message_id = channel_message_id
    await session.commit()
    return submission


async def update_submission_caption(
    session: AsyncSession,
    submission: Submission,
    new_caption: str,
) -> Submission:
    submission.caption = new_caption
    await session.commit()
    return submission
