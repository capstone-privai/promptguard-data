import os

from app.env import load_env

load_env()

DEBUG = os.environ.get("DEBUG", "0") == "1"
SESSION_SECRET = os.environ["SESSION_SECRET"]

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.example.invalid")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = "noreply@shop.example.invalid"
SMTP_PASSWORD = "{{secret:smtp_password}}"

STRIPE_SECRET_KEY = "{{secret:stripe_key}}"
STRIPE_WEBHOOK_TOLERANCE_SECONDS = 300
