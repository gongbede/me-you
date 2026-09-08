from fastapi import APIRouter

from ..config import APP_NAME, VERSION


router = APIRouter()


@router.get("/")
def root():
    return {
        "application": APP_NAME,
        "version": VERSION,
        "message": "Welcome to Me&You.",
    }


@router.get("/about")
def about():
    return {
        "application": APP_NAME,
        "version": VERSION,
        "description": "Me&You is a social, communication, education, media, music, and AI platform.",
    }
