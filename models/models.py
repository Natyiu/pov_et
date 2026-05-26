from datetime import datetime
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(AsyncAttrs, DeclarativeBase):
    pass


class CreditType(str, enum.Enum):
    username = "username"
    channel = "channel"
    anonymous = "anonymous"


class SubmissionStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    featured = "featured"
    featured_weekly = "featured_weekly"
    featured_monthly = "featured_monthly"


class ReputationLevel(str, enum.Enum):
    observer = "Observer"
    street_explorer = "Street Explorer"
    city_wanderer = "City Wanderer"
    frame_collector = "Frame Collector"
    visual_storyteller = "Visual Storyteller"
    archive_contributor = "Archive Contributor"
    city_curator = "City Curator"
    visual_legend = "Visual Legend"


LEVEL_THRESHOLDS = {
    ReputationLevel.observer: 0,
    ReputationLevel.street_explorer: 2,
    ReputationLevel.city_wanderer: 8,
    ReputationLevel.frame_collector: 20,
    ReputationLevel.visual_storyteller: 40,
    ReputationLevel.archive_contributor: 70,
    ReputationLevel.city_curator: 110,
    ReputationLevel.visual_legend: 160,
}

POINTS = {
    "approved": 1,
    "weekly_featured": 5,
    "monthly_featured": 15,
    "photographer_spotlight": 25,
    "community_favorite": 3,
}

BADGES = {
    "rain_chaser": ("🌧", "Rain Chaser", "submitted rain/weather moments"),
    "coffee_moment": ("☕", "Coffee Moment Capturer", "submitted coffee/cafe scenes"),
    "night_walker": ("🌃", "Night Walker", "submitted night photography"),
    "street_observer": ("🚶", "Street Observer", "submitted street photography"),
    "urban_eye": ("🏙", "Urban Eye", "submitted architecture/city frames"),
    "film_mood": ("🎞", "Film Mood Creator", "submitted atmospheric/moody shots"),
    "mobile_photographer": ("📱", "Mobile Photographer", "submitted via mobile"),
    "travel_seeker": ("🧭", "Travel Frame Seeker", "submitted from multiple regions"),
}

AVAILABLE_HASHTAGS = [
    "sunset",
    "flowers",
    "citylights",
    "countryside",
    "streetvibes",
    "rainyday",
    "nightwalk",
    "mountains",
    "clouds",
    "cafevibes",
    "nature",
    "roads",
    "sky",
    "urbanvibes",
    "goldenhour",
    "dailylife",
    "vintagevibes",
    "windowview",
    "moodygrams",
    "architecture",
    "morningvibes",
    "streetshots",
    "landscape",
    "villagevibes",
    "travelgram",
]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    display_name = Column(String(64), nullable=False)
    credit_type = Column(Enum(CreditType), nullable=False)
    credit_value = Column(String(64), nullable=True)
    bio = Column(String(256), nullable=True)
    reputation_points = Column(Integer, default=0)
    level = Column(Enum(ReputationLevel), default=ReputationLevel.observer)
    badges = Column(Text, default="")
    is_banned = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    submissions = relationship("Submission", back_populates="user")
    reputation_logs = relationship("ReputationLog", back_populates="user")

    def has_badge(self, badge_key: str) -> bool:
        return badge_key in (self.badges or "").split(",")

    def add_badge(self, badge_key: str):
        current = set(filter(None, (self.badges or "").split(",")))
        current.add(badge_key)
        self.badges = ",".join(current)

    def get_credit_display(self) -> str:
        if self.credit_type == CreditType.anonymous:
            return "Anonymous"
        if self.credit_value:
            return f"@{self.credit_value.lstrip('@')}"
        return self.display_name


def level_for_points(points: int) -> ReputationLevel:
    level = ReputationLevel.observer
    for lvl, threshold in LEVEL_THRESHOLDS.items():
        if points >= threshold:
            level = lvl
    return level


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    caption = Column(Text, nullable=True)
    location = Column(String(128), nullable=True)
    hashtags = Column(Text, nullable=True)
    status = Column(Enum(SubmissionStatus), default=SubmissionStatus.pending)
    admin_note = Column(Text, nullable=True)
    channel_message_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="submissions")
    media = relationship("Media", back_populates="submission", cascade="all, delete-orphan")


class Media(Base):
    __tablename__ = "media"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    telegram_file_id = Column(String(256), nullable=False)
    media_type = Column(String(16), default="photo")
    order_index = Column(Integer, default=0)

    submission = relationship("Submission", back_populates="media")


class ReputationLog(Base):
    __tablename__ = "reputation_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    points_added = Column(Integer, nullable=False)
    reason = Column(String(128), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="reputation_logs")
