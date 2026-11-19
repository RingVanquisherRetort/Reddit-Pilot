"""Small wrapper around the official Reddit API via PRAW."""
import praw
from config import load_settings


class RedditClient:
    def __init__(self) -> None:
        cfg = load_settings()
        self.reddit = praw.Reddit(
            client_id=cfg.reddit_client_id,
            client_secret=cfg.reddit_client_secret,
            user_agent=cfg.reddit_user_agent,
            refresh_token=cfg.reddit_refresh_token,
        )
        self.reddit.read_only = False

    def me(self) -> dict:
        user = self.reddit.user.me()
        if user is None:
            raise RuntimeError("Reddit did not return an authenticated user")
        return {
            "name": user.name,
            "link_karma": user.link_karma,
            "comment_karma": user.comment_karma,
            "created_utc": int(user.created_utc),
        }

    def subreddit_info(self, name: str) -> dict:
        sub = self.reddit.subreddit(name)
        # Accessing display_name/about fields causes PRAW to fetch subreddit metadata.
        return {
            "name": sub.display_name,
            "title": sub.title,
            "description": (sub.public_description or "")[:500],
            "subscribers": sub.subscribers,
            "over18": sub.over18,
        }

    def search(self, query: str, limit: int = 5) -> list[dict]:
        results = []
        for post in self.reddit.subreddit("all").search(
            query, sort="relevance", time_filter="week", limit=limit
        ):
            results.append({
                "title": post.title[:250],
                "subreddit": post.subreddit.display_name,
                "score": post.score,
                "url": f"https://www.reddit.com{post.permalink}",
            })
        return results

    def submit_text(self, subreddit: str, title: str, body: str) -> str:
        submission = self.reddit.subreddit(subreddit).submit(
            title=title, selftext=body
        )
        return f"https://www.reddit.com{submission.permalink}"
