from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import APP_NAME, VERSION
from .database import init_db, init_mongodb
from .routes.general import router as general_router
from .routes.login import router as login_router
from .routes.registration import router as registration_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_mongodb()
    yield


app = FastAPI(title=APP_NAME, version=VERSION, lifespan=lifespan)
app.include_router(general_router)
app.include_router(registration_router)
app.include_router(login_router)
init_db()


def main():
    print("Me&You backend has started.")
    print(f"Application: {APP_NAME}")
    print(f"Version: {VERSION}")


if __name__ == "__main__":
    main()