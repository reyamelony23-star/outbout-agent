"""Configuration for the outbound sales automation web app."""

import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json"
)

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me-in-prod")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

CLAUDE_MODEL = "claude-opus-4-7"

DECK_OUTPUT_DIR = os.getenv("DECK_OUTPUT_DIR", "decks")

APIFY_ACTOR_ID = "compass/crawler-google-places"
DEFAULT_MAX_RESULTS = 20
CHAT_OUTREACH_CAP = 5
