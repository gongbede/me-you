from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_mongo_database
from ..schemas import LoginRequest, LoginResponse
from ..security import create_access_token, password_hash


router = APIRouter()
AUTHENTICATION_ERROR = "Invalid email or password"


@router.post("/login", response_model=LoginResponse)
async def login(login_data: LoginRequest, database=Depends(get_mongo_database)):
    user = await database["users"].find_one({"email": login_data.email})
    if user is None or not password_hash.verify(login_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_ERROR,
        )

    return {
        "message": "Login successful",
        "access_token": create_access_token(user["_id"]),
        "token_type": "bearer",
        "id": user["_id"],
        "username": user["username"],
        "email": user["email"],
    }
