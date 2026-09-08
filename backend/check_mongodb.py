import asyncio
import os

from app.database import ping_mongodb


async def main() -> int:
    if not os.getenv("ME_YOU_MONGODB_URI"):
        print("MongoDB check failed: ME_YOU_MONGODB_URI is not configured.")
        return 1

    try:
        await ping_mongodb()
    except Exception as error:
        print(f"MongoDB check failed: MongoDB is unreachable ({type(error).__name__}).")
        return 1

    print("MongoDB check passed: MongoDB is reachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
