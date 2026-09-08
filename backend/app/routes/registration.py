from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from ..database import get_mongo_database
from ..schemas import UserCreate, UserResponse
from ..security import password_hash


router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, database=Depends(get_mongo_database)):
    users = database["users"]
    if await users.find_one({"username": user_data.username}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    if await users.find_one({"email": user_data.email}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    user = {
        "_id": uuid4().hex,
        "username": user_data.username,
        "email": user_data.email,
        "password_hash": password_hash.hash(user_data.password),
        "created_at": datetime.now(timezone.utc),
    }

    try:
        await users.insert_one(user)
    except DuplicateKeyError as error:
        key_pattern = (error.details or {}).get("keyPattern", {})
        if "username" in key_pattern:
            detail = "Username already exists"
        elif "email" in key_pattern:
            detail = "Email already exists"
        else:
            detail = "Username or email already exists"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from None

    return {
        "id": user["_id"],
        "username": user["username"],
        "email": user["email"],
        "created_at": user["created_at"],
    }
