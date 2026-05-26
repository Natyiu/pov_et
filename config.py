from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_CHAT_ID: int
    ADMIN_USER_ID: int | None = None
    CHANNEL_ID: str
    CHANNEL_URL: Optional[str] = None
    CHANNEL_TITLE: str = "Ethiopia Visual Archive"
    DATABASE_URL: str = "sqlite+aiosqlite:///./pov_et.db"

    ARCHIVE_CHANNEL_ID: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()
