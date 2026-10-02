from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import APP_NAME, VERSION
from .database import init_mongodb
from .routes.general import router as general_router
from .routes.account import router as account_router
from .routes.comments import router as comments_router
from .routes.conversations import router as conversations_router
from .routes.education import router as education_router
from .routes.education_learning import router as education_learning_router
from .routes.follows import router as follows_router
from .routes.institutions import router as institutions_router
from .routes.login import router as login_router
from .routes.likes import router as likes_router
from .routes.me import router as me_router
from .routes.messages import router as messages_router
from .routes.notifications import router as notifications_router
from .routes.posts import router as posts_router
from .routes.profile import router as profile_router
from .routes.registration import router as registration_router
from .routes.search import router as search_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_mongodb()
    yield


app = FastAPI(title=APP_NAME, version=VERSION, lifespan=lifespan)
app.include_router(general_router)
app.include_router(registration_router)
app.include_router(login_router)
app.include_router(me_router)
app.include_router(profile_router)
app.include_router(account_router)
app.include_router(posts_router)
app.include_router(comments_router)
app.include_router(likes_router)
app.include_router(follows_router)
app.include_router(notifications_router)
app.include_router(conversations_router)
app.include_router(messages_router)
app.include_router(education_router)
app.include_router(education_learning_router)
app.include_router(institutions_router)
app.include_router(search_router)


def main():
    print("Me&You backend has started.")
    print(f"Application: {APP_NAME}")
    print(f"Version: {VERSION}")


if __name__ == "__main__":
    main()