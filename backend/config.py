import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    SIGNAL_PHONE_NUMBER = os.getenv("SIGNAL_PHONE_NUMBER")
    USER_PHONE_NUMBER = os.getenv("USER_PHONE_NUMBER")

settings = Settings()

