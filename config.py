"""Environment-backed configuration for Reddit Pilot."""
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_admin_id: int
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str
    reddit_refresh_token: str
    allowed_subreddits: frozenset[str]
    database_path: str


def load_settings() -> Settings:
    allowlist = frozenset(
        item.strip().lower().removeprefix("r/")
        for item in os.getenv("ALLOWED_SUBREDDITS", "").split(",")
        if item.strip()
    )
    try:
        admin_id = int(_required("TELEGRAM_ADMIN_ID"))
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_ADMIN_ID must be an integer") from exc

    return Settings(
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        telegram_admin_id=admin_id,
        reddit_client_id=_required("REDDIT_CLIENT_ID"),
        reddit_client_secret=_required("REDDIT_CLIENT_SECRET"),
        reddit_user_agent=os.getenv(
            "REDDIT_USER_AGENT", "RedditPilot/1.0"
        ).strip(),
        reddit_refresh_token=_required("REDDIT_REFRESH_TOKEN"),
        allowed_subreddits=allowlist,
        database_path=os.getenv("DATABASE_PATH", "reddit_pilot.db"),
    )
