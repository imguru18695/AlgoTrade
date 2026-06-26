from dotenv import load_dotenv
import os

load_dotenv()

KITE_API_KEY = os.environ["KITE_API_KEY"]
KITE_API_SECRET = os.environ["KITE_API_SECRET"]
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

REDIRECT_URL = f"{APP_BASE_URL}/auth/callback"
TOKEN_FILE = "access_token.txt"
DB_FILE = "algoplatform.db"
