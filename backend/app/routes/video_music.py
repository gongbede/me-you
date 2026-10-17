import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import (
    Follow, MediaAsset, MusicCategoryFollow, Notification, Playlist, PlaylistItem,
    Track, User, UserBlock, Video, VideoComment, VideoLike, VideoView,
)
from ..notification_preferences import add_notifications
from ..privacy import can_view_profile
from ..rate_limit import RateLimitStore, get_rate_limit_store
from ..security import get_current_postgres_user, get_optional_postgres_user

router = APIRouter(tags=["video and music"])
VIDEO_CATEGORIES = {"Education", "Programming", "Technology", "Music", "Entertainment", "Sports", "Lifestyle", "Faith", "Other"}
MUSIC_CATEGORIES = {"Afrobeats", "R&B", "Hip-hop", "Gospel", "Highlife", "Amapiano", "Pop", "Reggae and Dancehall", "Jazz", "Rock", "Classical", "Instrumental", "Other"}
NOTIFICATION_FANOUT_LIMIT = 500


class VideoCreate(BaseModel):
    media_asset_id: uuid.UUID
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    category: str = Field(min_length=1, max_length=32)
    visibility: Literal["PUBLIC", "FOLLOWERS", "PRIVATE"] = "PUBLIC"

    @field_validator("title", "category")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value cannot be blank")
        return value.strip()


class TrackCreate(BaseModel):
    media_asset_id: uuid.UUID
    title: str = Field(min_length=1, max_length=120)
    artist_name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=32)
    visibility: Literal["PUBLIC", "FOLLOWERS", "PRIVATE"] = "PUBLIC"
    rights_confirmed: bool


class VideoUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    category: str = Field(min_length=1, max_length=32)
    visibility: Literal["PUBLIC", "FOLLOWERS", "PRIVATE"] = "PUBLIC"


class VideoCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Comment cannot be blank")
        return value.strip()


class PlaylistCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    visibility: Literal["PUBLIC", "FOLLOWERS", "PRIVATE"] = "PUBLIC"

    @field_validator("title")
    @classmethod
    def playlist_title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Playlist title cannot be blank")
        return value.strip()


class PlaylistReorder(BaseModel):
    track_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)

    @field_validator("track_ids")
    @classmethod
    def track_ids_are_unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Track ids must not repeat")
        return value


async def visible_media(item: Video | Track, viewer: User | None, database: AsyncSession) -> bool:
    if item.is_hidden and not (viewer and viewer.is_platform_admin):
        return False
    owner = await database.get(User, item.owner_id)
    return bool(owner and await can_view_profile(owner, item.visibility, viewer, database))


def visible_media_clause(model: type[Video] | type[Track], viewer: User | None):
    owner_active = exists(select(User.id).where(User.id == model.owner_id, User.is_active.is_(True)))
    if viewer is None:
        return and_(owner_active, model.visibility == "PUBLIC")
    follows_owner = exists(select(Follow.follower_id).where(
        Follow.follower_id == viewer.id, Follow.following_id == model.owner_id
    ))
    blocked_pair = exists(select(UserBlock.id).where(or_(
        and_(UserBlock.blocker_id == viewer.id, UserBlock.blocked_id == model.owner_id),
        and_(UserBlock.blocker_id == model.owner_id, UserBlock.blocked_id == viewer.id),
    )))
    allowed_visibility = or_(
        model.owner_id == viewer.id,
        model.visibility == "PUBLIC",
        and_(model.visibility == "FOLLOWERS", follows_owner),
    )
    return and_(
        owner_active,
        allowed_visibility,
        or_(model.owner_id == viewer.id, not_(blocked_pair)),
    )


async def require_asset(asset_id: uuid.UUID, owner_id: uuid.UUID, purpose: str, database: AsyncSession) -> MediaAsset:
    asset = await database.scalar(select(MediaAsset).where(
        MediaAsset.id == asset_id, MediaAsset.owner_id == owner_id,
        MediaAsset.purpose == purpose, MediaAsset.status == "READY",
    ))
    if asset is None:
        raise HTTPException(status_code=422, detail=f"A ready {purpose.lower()} asset is required")
    return asset


def video_data(video: Video) -> dict:
    return {
        "id": str(video.id), "owner_id": str(video.owner_id),
        "media_asset_id": str(video.media_asset_id), "title": video.title,
        "description": video.description, "category": video.category,
        "visibility": video.visibility, "duration_seconds": video.duration_seconds,
        "view_count": video.view_count, "created_at": video.created_at,
    }


def track_data(track: Track) -> dict:
    return {
        "id": str(track.id), "owner_id": str(track.owner_id),
        "media_asset_id": str(track.media_asset_id), "title": track.title,
        "artist_name": track.artist_name, "category": track.category,
        "visibility": track.visibility, "duration_seconds": track.duration_seconds,
        "play_count": track.play_count, "created_at": track.created_at,
    }


@router.post("/videos", status_code=201)
async def create_video(
    data: VideoCreate, current: User = Depends(get_current_postgres_user),
    db: AsyncSession = Depends(get_postgres_session),
):
    if data.category not in VIDEO_CATEGORIES:
        raise HTTPException(422, "Unsupported video category")
    asset = await require_asset(data.media_asset_id, current.id, "VIDEO", db)
    item = Video(owner_id=current.id, media_asset_id=asset.id, title=data.title.strip(),
                 description=data.description, category=data.category, visibility=data.visibility)
    db.add(item)
    await db.flush()
    if data.visibility in {"PUBLIC", "FOLLOWERS"}:
        recent = await db.scalar(select(Notification.id).where(
            Notification.actor_id == current.id, Notification.type == "NEW_VIDEO",
            Notification.created_at >= datetime.now(timezone.utc) - timedelta(hours=1),
            Notification.target_type == "VIDEO",
        ).limit(1))
        if recent is None:
            # Fan-out is capped at 500 recipients per upload.
            followers = (await db.scalars(select(Follow.follower_id).where(Follow.following_id == current.id).limit(NOTIFICATION_FANOUT_LIMIT))).all()
            await add_notifications(db, [
                Notification(recipient_id=user_id, actor_id=current.id, type="NEW_VIDEO",
                             title=f"{current.username} shared a video", target_type="VIDEO",
                             target_id=item.id, payload={"video_id": str(item.id)})
                for user_id in followers if user_id != current.id
            ])
    await db.commit()
    await db.refresh(item)
    return video_data(item)


@router.get("/videos")
async def list_videos(
    category: str | None = None, q: str = Query(default="", max_length=100),
    mine: bool = False,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=50),
    current: User | None = Depends(get_optional_postgres_user),
    db: AsyncSession = Depends(get_postgres_session),
):
    statement = select(Video)
    if not (current and current.is_platform_admin):
        statement = statement.where(Video.is_hidden.is_(False))
    if mine:
        if current is None:
            raise HTTPException(401, "Authentication required")
        statement = statement.where(Video.owner_id == current.id)
    if category:
        statement = statement.where(Video.category == category)
    if q:
        statement = statement.where(Video.title.ilike(f"%{q}%"))
    statement = statement.where(visible_media_clause(Video, current))
    candidates = list((await db.scalars(statement.order_by(Video.created_at.desc(), Video.id.desc()).offset(offset).limit(limit))).all())
    return [video_data(item) for item in candidates]


@router.put("/videos/{video_id}")
async def update_video(video_id: uuid.UUID, data: VideoUpdate, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    if data.category not in VIDEO_CATEGORIES or not data.title.strip():
        raise HTTPException(422, "Invalid video title or category")
    item = await db.scalar(select(Video).where(Video.id == video_id, Video.owner_id == current.id))
    if item is None:
        raise HTTPException(404, "Video not found")
    item.title = data.title.strip()
    item.description = data.description.strip()
    item.category = data.category
    item.visibility = data.visibility
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return video_data(item)


@router.get("/videos/{video_id}/comments")
async def list_video_comments(video_id: uuid.UUID, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100), current: User | None = Depends(get_optional_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    item = await db.get(Video, video_id)
    if item is None or not await visible_media(item, current, db):
        raise HTTPException(404, "Video not found")
    comments = (await db.scalars(select(VideoComment).where(VideoComment.video_id == video_id).order_by(VideoComment.created_at, VideoComment.id).offset(offset).limit(limit))).all()
    return [{"id": str(comment.id), "video_id": str(comment.video_id), "author_id": str(comment.author_id), "content": comment.content, "created_at": comment.created_at} for comment in comments]


@router.delete("/videos/comments/{comment_id}", status_code=204)
async def delete_video_comment(comment_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    comment = await db.get(VideoComment, comment_id)
    if comment is None or (comment.author_id != current.id and not current.is_platform_admin):
        raise HTTPException(404, "Comment not found")
    await db.delete(comment)
    await db.commit()


@router.get("/videos/{video_id}")
async def get_video(video_id: uuid.UUID, current: User | None = Depends(get_optional_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    item = await db.get(Video, video_id)
    if item is None or not await visible_media(item, current, db):
        raise HTTPException(404, "Video not found")
    like_count = await db.scalar(select(func.count(VideoLike.user_id)).where(VideoLike.video_id == item.id))
    liked = bool(current and await db.get(VideoLike, (item.id, current.id)))
    return {**video_data(item), "like_count": int(like_count or 0), "liked_by_me": liked}


@router.delete("/videos/{video_id}", status_code=204)
async def delete_video(video_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    item = await db.scalar(select(Video).where(Video.id == video_id, Video.owner_id == current.id))
    if item is None:
        raise HTTPException(404, "Video not found")
    await db.delete(item)
    await db.commit()


@router.post("/videos/{video_id}/like", status_code=204)
async def like_video(video_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    item = await db.get(Video, video_id)
    if item is None or not await visible_media(item, current, db):
        raise HTTPException(404, "Video not found")
    existing = await db.get(VideoLike, (video_id, current.id))
    if existing is None:
        db.add(VideoLike(video_id=video_id, user_id=current.id))
        if item.owner_id != current.id:
            await add_notifications(db, [Notification(recipient_id=item.owner_id, actor_id=current.id, type="VIDEO_LIKE", title=f"{current.username} liked your video", target_type="VIDEO", target_id=item.id)])
        await db.commit()


@router.delete("/videos/{video_id}/like", status_code=204)
async def unlike_video(video_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    item = await db.get(Video, video_id)
    if item is None or not await visible_media(item, current, db):
        raise HTTPException(404, "Video not found")
    like = await db.get(VideoLike, (video_id, current.id))
    if like is not None:
        await db.delete(like)
        await db.commit()


@router.post("/videos/{video_id}/view", status_code=204)
async def count_video_view(video_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session), limiter: RateLimitStore | None = Depends(get_rate_limit_store)):
    if limiter is None:
        raise HTTPException(503, "Rate limiting is unavailable")
    count, retry = await limiter.increment("video_view", str(current.id), 60)
    if count > 60:
        raise HTTPException(429, "View rate limit reached", headers={"Retry-After": str(retry)})
    item = await db.get(Video, video_id)
    if item is None or not await visible_media(item, current, db):
        raise HTTPException(404, "Video not found")
    try:
        db.add(VideoView(video_id=video_id, user_id=current.id, view_date=datetime.now(timezone.utc).date()))
        item.view_count += 1
        await db.commit()
    except IntegrityError:
        await db.rollback()


@router.post("/videos/{video_id}/comments", status_code=201)
async def comment_video(video_id: uuid.UUID, data: VideoCommentCreate, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    item = await db.get(Video, video_id)
    if item is None or not await visible_media(item, current, db):
        raise HTTPException(404, "Video not found")
    comment = VideoComment(video_id=video_id, author_id=current.id, content=data.content)
    db.add(comment)
    await db.flush()
    if item.owner_id != current.id:
        await add_notifications(db, [Notification(recipient_id=item.owner_id, actor_id=current.id, type="VIDEO_COMMENT", title=f"{current.username} commented on your video", target_type="VIDEO", target_id=item.id)])
    await db.commit()
    await db.refresh(comment)
    return {"id": str(comment.id), "video_id": str(video_id), "author_id": str(current.id), "content": comment.content, "created_at": comment.created_at}


@router.post("/tracks", status_code=201)
async def create_track(data: TrackCreate, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    if not data.rights_confirmed:
        raise HTTPException(422, "Confirm that you own this audio or have permission to share it")
    if data.category not in MUSIC_CATEGORIES:
        raise HTTPException(422, "Unsupported music category")
    asset = await require_asset(data.media_asset_id, current.id, "AUDIO", db)
    item = Track(owner_id=current.id, media_asset_id=asset.id, title=data.title.strip(), artist_name=data.artist_name.strip(), category=data.category, visibility=data.visibility, rights_confirmed_at=datetime.now(timezone.utc))
    db.add(item)
    await db.flush()
    if data.visibility in {"PUBLIC", "FOLLOWERS"}:
        recent = await db.scalar(select(Notification.id).where(
            Notification.actor_id == current.id, Notification.type == "NEW_TRACK",
            Notification.created_at >= datetime.now(timezone.utc) - timedelta(hours=1),
            Notification.target_type == "TRACK",
        ).limit(1))
    else:
        recent = True
    if recent is None:
        followers = set((await db.scalars(select(Follow.follower_id).where(Follow.following_id == current.id).limit(NOTIFICATION_FANOUT_LIMIT))).all())
        category_followers = set((await db.scalars(select(MusicCategoryFollow.user_id).where(MusicCategoryFollow.category == data.category).limit(NOTIFICATION_FANOUT_LIMIT))).all())
        await add_notifications(db, [Notification(recipient_id=uid, actor_id=current.id, type="NEW_TRACK", title=f"{current.username} shared a track", target_type="TRACK", target_id=item.id) for uid in list(followers | category_followers)[:NOTIFICATION_FANOUT_LIMIT] if uid != current.id])
    await db.commit()
    await db.refresh(item)
    return track_data(item)


@router.put("/tracks/{track_id}")
async def update_track(track_id: uuid.UUID, data: TrackCreate, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    if not data.rights_confirmed:
        raise HTTPException(422, "Confirm that you own this audio or have permission to share it")
    if data.category not in MUSIC_CATEGORIES:
        raise HTTPException(422, "Unsupported music category")
    item = await db.scalar(select(Track).where(Track.id == track_id, Track.owner_id == current.id))
    if item is None:
        raise HTTPException(404, "Track not found")
    item.title = data.title.strip()
    item.artist_name = data.artist_name.strip()
    item.category = data.category
    item.visibility = data.visibility
    item.rights_confirmed_at = datetime.now(timezone.utc)
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return track_data(item)


@router.delete("/tracks/{track_id}", status_code=204)
async def delete_track(track_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    item = await db.scalar(select(Track).where(Track.id == track_id, Track.owner_id == current.id))
    if item is None:
        raise HTTPException(404, "Track not found")
    await db.delete(item)
    await db.commit()


@router.get("/tracks")
async def list_tracks(category: str | None = None, q: str = Query(default="", max_length=100), mine: bool = False, offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=50), current: User | None = Depends(get_optional_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    statement = select(Track)
    if mine:
        if current is None:
            raise HTTPException(401, "Authentication required")
        statement = statement.where(Track.owner_id == current.id)
    if not mine and not (current and current.is_platform_admin):
        statement = statement.where(Track.is_hidden.is_(False))
    if category:
        statement = statement.where(Track.category == category)
    if q:
        statement = statement.where(Track.title.ilike(f"%{q}%"))
    statement = statement.where(visible_media_clause(Track, current))
    if not mine:
        statement = statement.where(visible_media_clause(Track, current))
    tracks = list((await db.scalars(statement.order_by(Track.created_at.desc(), Track.id.desc()).offset(offset).limit(limit))).all())
    return [track_data(item) for item in tracks]


@router.get("/tracks/{track_id}")
async def get_track(track_id: uuid.UUID, current: User | None = Depends(get_optional_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    item = await db.get(Track, track_id)
    if item is None or not await visible_media(item, current, db):
        raise HTTPException(404, "Track not found")
    return track_data(item)


@router.post("/tracks/{track_id}/play", status_code=204)
async def count_track_play(track_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session), limiter: RateLimitStore | None = Depends(get_rate_limit_store)):
    if limiter is None:
        raise HTTPException(503, "Rate limiting is unavailable")
    item = await db.get(Track, track_id)
    if item is None or not await visible_media(item, current, db):
        raise HTTPException(404, "Track not found")
    count, _retry = await limiter.increment(f"track_play:{track_id}", str(current.id), 3600)
    if count > 1:
        return
    item.play_count += 1
    await db.commit()


@router.post("/playlists", status_code=201)
async def create_playlist(data: PlaylistCreate, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    playlist = Playlist(owner_id=current.id, title=data.title, visibility=data.visibility)
    db.add(playlist)
    await db.commit()
    await db.refresh(playlist)
    return {"id": str(playlist.id), "title": playlist.title, "owner_id": str(current.id)}


@router.get("/playlists")
async def list_playlists(current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    playlists = (await db.scalars(select(Playlist).where(Playlist.owner_id == current.id).order_by(Playlist.created_at.desc()).limit(100))).all()
    return [{"id": str(item.id), "title": item.title, "owner_id": str(item.owner_id), "visibility": item.visibility} for item in playlists]


@router.get("/playlists/{playlist_id}")
async def get_playlist(playlist_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    playlist = await db.get(Playlist, playlist_id)
    owner = await db.get(User, playlist.owner_id) if playlist is not None else None
    if playlist is None or owner is None or (
        playlist.owner_id != current.id
        and not await can_view_profile(owner, playlist.visibility, current, db)
    ):
        raise HTTPException(404, "Playlist not found")
    rows = (await db.execute(
        select(Track).join(PlaylistItem, PlaylistItem.track_id == Track.id)
        .where(PlaylistItem.playlist_id == playlist_id)
        .where(
            Track.visibility != "PRIVATE"
            if playlist.owner_id != current.id
            else True
        )
        .order_by(PlaylistItem.position)
    )).scalars().all()
    return {
        "id": str(playlist.id), "title": playlist.title,
        "owner_id": str(playlist.owner_id), "visibility": playlist.visibility,
        "tracks": [track_data(track) for track in rows],
    }


@router.put("/playlists/{playlist_id}")
async def rename_playlist(playlist_id: uuid.UUID, data: PlaylistCreate, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    playlist = await db.scalar(select(Playlist).where(Playlist.id == playlist_id, Playlist.owner_id == current.id))
    if playlist is None:
        raise HTTPException(404, "Playlist not found")
    playlist.title = data.title
    playlist.visibility = data.visibility
    playlist.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(playlist.id), "title": playlist.title}


@router.delete("/playlists/{playlist_id}", status_code=204)
async def delete_playlist(playlist_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    playlist = await db.scalar(select(Playlist).where(Playlist.id == playlist_id, Playlist.owner_id == current.id))
    if playlist is None:
        raise HTTPException(404, "Playlist not found")
    await db.delete(playlist)
    await db.commit()


@router.post("/playlists/{playlist_id}/tracks/{track_id}", status_code=204)
async def add_playlist_track(playlist_id: uuid.UUID, track_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    playlist = await db.scalar(select(Playlist).where(Playlist.id == playlist_id, Playlist.owner_id == current.id))
    track = await db.get(Track, track_id)
    if playlist is None or track is None:
        raise HTTPException(404, "Playlist or track not found")
    if not await visible_media(track, current, db):
        raise HTTPException(404, "Track not found")
    if playlist.visibility == "PUBLIC" and track.visibility == "PRIVATE" and track.owner_id != playlist.owner_id:
        raise HTTPException(409, "Private tracks cannot be added to a public playlist")
    if await db.get(PlaylistItem, (playlist_id, track_id)) is not None:
        return
    position = int(await db.scalar(select(func.coalesce(func.max(PlaylistItem.position), -1)).where(PlaylistItem.playlist_id == playlist_id))) + 1
    db.add(PlaylistItem(playlist_id=playlist_id, track_id=track_id, position=position))
    await db.commit()


@router.delete("/playlists/{playlist_id}/tracks/{track_id}", status_code=204)
async def remove_playlist_track(playlist_id: uuid.UUID, track_id: uuid.UUID, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    playlist = await db.scalar(select(Playlist).where(Playlist.id == playlist_id, Playlist.owner_id == current.id))
    if playlist is None:
        raise HTTPException(404, "Playlist not found")
    item = await db.get(PlaylistItem, (playlist_id, track_id))
    if item is not None:
        await db.delete(item)
        await db.commit()


@router.put("/playlists/{playlist_id}/order", status_code=204)
async def reorder_playlist(playlist_id: uuid.UUID, data: PlaylistReorder, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    playlist = await db.scalar(select(Playlist).where(Playlist.id == playlist_id, Playlist.owner_id == current.id))
    if playlist is None:
        raise HTTPException(404, "Playlist not found")
    entries = list((await db.scalars(select(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id))).all())
    by_track = {entry.track_id: entry for entry in entries}
    if set(by_track) != set(data.track_ids):
        raise HTTPException(422, "Order must include every playlist track exactly once")
    offset = len(entries) + 1
    for entry in entries:
        entry.position += offset
    await db.flush()
    for position, track_id in enumerate(data.track_ids):
        by_track[track_id].position = position
    await db.commit()


@router.put("/music/categories/{category}/follow", status_code=204)
async def follow_music_category(category: str, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    if category not in MUSIC_CATEGORIES:
        raise HTTPException(422, "Unsupported music category")
    if await db.get(MusicCategoryFollow, (current.id, category)) is None:
        db.add(MusicCategoryFollow(user_id=current.id, category=category))
        await db.commit()


@router.get("/music/categories/follows")
async def list_music_category_follows(current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    return list((await db.scalars(
        select(MusicCategoryFollow.category)
        .where(MusicCategoryFollow.user_id == current.id)
        .order_by(MusicCategoryFollow.category)
    )).all())


@router.delete("/music/categories/{category}/follow", status_code=204)
async def unfollow_music_category(category: str, current: User = Depends(get_current_postgres_user), db: AsyncSession = Depends(get_postgres_session)):
    entry = await db.get(MusicCategoryFollow, (current.id, category))
    if entry is not None:
        await db.delete(entry)
        await db.commit()
