from aiogram import Bot, Router

from models.models import BADGES, LEVEL_THRESHOLDS, ReputationLevel

router = Router()


def get_next_level(current_level: ReputationLevel, points: int) -> ReputationLevel | None:
    levels = list(LEVEL_THRESHOLDS.keys())
    try:
        idx = levels.index(current_level)
        if idx + 1 < len(levels):
            return levels[idx + 1]
    except ValueError:
        pass
    return None


def points_to_next_level(level: ReputationLevel, points: int) -> int | None:
    next_lvl = get_next_level(level, points)
    if not next_lvl:
        return None
    return LEVEL_THRESHOLDS[next_lvl] - points


async def send_level_up_message(bot: Bot, telegram_id: int, new_level: ReputationLevel):
    level_messages = {
        ReputationLevel.street_explorer: "You've become a Street Explorer. The city is your canvas.",
        ReputationLevel.city_wanderer: "City Wanderer - you move through places with intention.",
        ReputationLevel.frame_collector: "Frame Collector - your eye is developing something rare.",
        ReputationLevel.visual_storyteller: "Visual Storyteller. Your moments carry weight.",
        ReputationLevel.archive_contributor: "Archive Contributor - your work is shaping the collection.",
        ReputationLevel.city_curator: "City Curator - you understand this place deeply.",
        ReputationLevel.visual_legend: "Visual Legend. ✦ Few reach here.",
    }
    msg = level_messages.get(new_level, f"You've reached {new_level.value}.")
    try:
        await bot.send_message(chat_id=telegram_id, text=f"✦ {msg}")
    except Exception:
        pass


async def award_badge_if_earned(bot: Bot, user, session, submission) -> list[str]:
    new_badges = []
    caption = (submission.caption or "").lower()
    location = (submission.location or "").lower()
    combined = f"{caption} {location}"

    checks = {
        "rain_chaser": any(w in caption for w in ["rain", "wet", "storm", "drizzle"]),
        "coffee_moment": any(w in combined for w in ["coffee", "cafe", "buna", "macchiato"]),
        "night_walker": any(w in caption for w in ["night", "dark", "evening", "dusk"]),
        "urban_eye": any(w in combined for w in ["building", "architecture", "street", "road"]),
        "film_mood": any(w in caption for w in ["light", "shadow", "mood", "atmosphere", "grain"]),
    }

    for badge_key, condition in checks.items():
        if condition and not user.has_badge(badge_key):
            user.add_badge(badge_key)
            new_badges.append(badge_key)

    if new_badges:
        await session.commit()
        for badge_key in new_badges:
            emoji, name, _ = BADGES[badge_key]
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"{emoji} New badge: {name}",
                )
            except Exception:
                pass

    return new_badges
