"""Favorites and tags endpoints for user metadata."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteRequest(BaseModel):
    """Request to add/remove favorite."""

    media_id: str | None = None
    person_id: str | None = None


class TagRequest(BaseModel):
    """Request to add tag."""

    media_id: str
    tag: str


class TagDeleteRequest(BaseModel):
    """Request to delete tag."""

    media_id: str
    tag: str


class FavoritesResponse(BaseModel):
    """Response with list of favorites."""

    media_ids: list[str]
    person_ids: list[str]


class TagsResponse(BaseModel):
    """Response with tags for media."""

    tags: dict[str, list[str]]  # media_id -> list of tags


@router.get("/media", response_model=list[str])
async def get_media_favorites(_token: str = Depends(verify_token)) -> list[str]:
    """Get all media favorites."""
    async for db in get_db():
        cursor = await db.execute("SELECT media_id FROM media_favorites ORDER BY created_at_ms DESC")
        rows = await cursor.fetchall()
        return [row["media_id"] for row in rows]
    return []


@router.post("/media")
async def add_media_favorite(
    request: FavoriteRequest,
    _token: str = Depends(verify_token),
) -> dict[str, str]:
    """Add a media item to favorites."""
    if not request.media_id:
        raise HTTPException(status_code=400, detail="media_id is required")

    async for db in get_db():
        # Verify media exists
        cursor = await db.execute("SELECT media_id FROM media WHERE media_id = ?", (request.media_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Media not found")

        # Add favorite
        now_ms = int(datetime.now().timestamp() * 1000)
        await db.execute(
            """
            INSERT OR IGNORE INTO media_favorites (media_id, created_at_ms)
            VALUES (?, ?)
            """,
            (request.media_id, now_ms),
        )
        await db.commit()

    logger.info(f"Added media favorite: {request.media_id}")
    return {"status": "ok", "media_id": request.media_id}


@router.delete("/media/{media_id}")
async def remove_media_favorite(
    media_id: str,
    _token: str = Depends(verify_token),
) -> dict[str, str]:
    """Remove a media item from favorites."""
    async for db in get_db():
        cursor = await db.execute("DELETE FROM media_favorites WHERE media_id = ?", (media_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Favorite not found")

    logger.info(f"Removed media favorite: {media_id}")
    return {"status": "ok", "media_id": media_id}


@router.get("/persons", response_model=list[str])
async def get_person_favorites(_token: str = Depends(verify_token)) -> list[str]:
    """Get all person favorites."""
    async for db in get_db():
        cursor = await db.execute("SELECT person_id FROM person_favorites ORDER BY created_at_ms DESC")
        rows = await cursor.fetchall()
        return [row["person_id"] for row in rows]
    return []


@router.post("/persons")
async def add_person_favorite(
    request: FavoriteRequest,
    _token: str = Depends(verify_token),
) -> dict[str, str]:
    """Add a person to favorites."""
    if not request.person_id:
        raise HTTPException(status_code=400, detail="person_id is required")

    async for db in get_db():
        # Verify person exists
        cursor = await db.execute("SELECT person_id FROM persons WHERE person_id = ?", (request.person_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Person not found")

        # Add favorite
        now_ms = int(datetime.now().timestamp() * 1000)
        await db.execute(
            """
            INSERT OR IGNORE INTO person_favorites (person_id, created_at_ms)
            VALUES (?, ?)
            """,
            (request.person_id, now_ms),
        )
        await db.commit()

    logger.info(f"Added person favorite: {request.person_id}")
    return {"status": "ok", "person_id": request.person_id}


@router.delete("/persons/{person_id}")
async def remove_person_favorite(
    person_id: str,
    _token: str = Depends(verify_token),
) -> dict[str, str]:
    """Remove a person from favorites."""
    async for db in get_db():
        cursor = await db.execute("DELETE FROM person_favorites WHERE person_id = ?", (person_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Favorite not found")

    logger.info(f"Removed person favorite: {person_id}")
    return {"status": "ok", "person_id": person_id}


@router.get("/tags", response_model=TagsResponse)
async def get_all_tags(_token: str = Depends(verify_token)) -> TagsResponse:
    """Get all tags for all media."""
    async for db in get_db():
        cursor = await db.execute("SELECT media_id, tag FROM media_tags ORDER BY created_at_ms DESC")
        rows = await cursor.fetchall()
        tags: dict[str, list[str]] = {}
        for row in rows:
            media_id = row["media_id"]
            tag = row["tag"]
            if media_id not in tags:
                tags[media_id] = []
            tags[media_id].append(tag)
        return TagsResponse(tags=tags)
    return TagsResponse(tags={})


@router.get("/tags/{media_id}", response_model=list[str])
async def get_media_tags(
    media_id: str,
    _token: str = Depends(verify_token),
) -> list[str]:
    """Get tags for a specific media item."""
    async for db in get_db():
        cursor = await db.execute(
            "SELECT tag FROM media_tags WHERE media_id = ? ORDER BY created_at_ms DESC",
            (media_id,),
        )
        rows = await cursor.fetchall()
        return [row["tag"] for row in rows]
    return []


@router.post("/tags")
async def add_tag(
    request: TagRequest,
    _token: str = Depends(verify_token),
) -> dict[str, str]:
    """Add a tag to a media item."""
    if not request.tag or not request.tag.strip():
        raise HTTPException(status_code=400, detail="tag is required and cannot be empty")

    tag = request.tag.strip()

    async for db in get_db():
        # Verify media exists
        cursor = await db.execute("SELECT media_id FROM media WHERE media_id = ?", (request.media_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Media not found")

        # Add tag
        now_ms = int(datetime.now().timestamp() * 1000)
        await db.execute(
            """
            INSERT OR IGNORE INTO media_tags (media_id, tag, created_at_ms)
            VALUES (?, ?, ?)
            """,
            (request.media_id, tag, now_ms),
        )
        await db.commit()

    logger.info(f"Added tag '{tag}' to media: {request.media_id}")
    return {"status": "ok", "media_id": request.media_id, "tag": tag}


@router.delete("/tags")
async def remove_tag(
    request: TagDeleteRequest,
    _token: str = Depends(verify_token),
) -> dict[str, str]:
    """Remove a tag from a media item."""
    async for db in get_db():
        cursor = await db.execute(
            "DELETE FROM media_tags WHERE media_id = ? AND tag = ?",
            (request.media_id, request.tag),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Tag not found")

    logger.info(f"Removed tag '{request.tag}' from media: {request.media_id}")
    return {"status": "ok", "media_id": request.media_id, "tag": request.tag}
