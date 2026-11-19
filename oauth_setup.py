"""One-time helper to obtain a Reddit OAuth refresh token.

Create a Reddit web app with redirect URI http://localhost:8080.
Run locally, open the printed URL, approve access, then paste the
state and code query parameters from the redirected URL.
"""
import os
import secrets
import praw
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
user_agent = os.getenv("REDDIT_USER_AGENT", "RedditPilot/1.0").strip()
if not client_id or not client_secret:
    raise SystemExit("Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env first.")

reddit = praw.Reddit(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri="http://localhost:8080",
    user_agent=user_agent,
)
state = secrets.token_urlsafe(16)
url = reddit.auth.url(
    scopes=["identity", "read", "submit"],
    state=state,
    duration="permanent",
)
print("\nOpen this URL in your browser and approve Reddit Pilot:\n")
print(url)
print("\nAfter approval, copy 'state' and 'code' from the redirected URL.")
returned_state = input("State: ").strip()
if returned_state != state:
    raise SystemExit("OAuth state mismatch; aborting.")
code = input("Code: ").strip()
if not code:
    raise SystemExit("No authorization code supplied.")
refresh_token = reddit.auth.authorize(code)
print("\nOAuth complete. Add this line to your local .env (never commit it):\n")
print(f"REDDIT_REFRESH_TOKEN={refresh_token}")
