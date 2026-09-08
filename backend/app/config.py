import os

from dotenv import load_dotenv


load_dotenv()

APP_NAME = "Me&You"
VERSION = "1.0"
DATABASE_URL = "sqlite:///./me_you.db"
JWT_SECRET_KEY = os.getenv("ME_YOU_JWT_SECRET_KEY", "development-only-me-you-jwt-secret")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30