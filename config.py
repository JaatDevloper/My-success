# Try to get from environment variables first, then fallback to hardcoded value
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7631768276:AAEUjV-iVGb1_6ZFWxF_VJH4hwsv6yBF4BI")

# Also support BOT_TOKEN variable which is used in simple_bot.py
BOT_TOKEN = os.environ.get("BOT_TOKEN", TELEGRAM_BOT_TOKEN)

# Ensure both tokens are available as environment variables
os.environ["TELEGRAM_BOT_TOKEN"] = TELEGRAM_BOT_TOKEN
os.environ["BOT_TOKEN"] = BOT_TOKEN
