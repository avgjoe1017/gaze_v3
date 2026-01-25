"""Face management endpoints."""

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

from ..db.connection import get_db
from ..middleware.auth import verify_token
from ..ml.face_detector import (
    bytes_to_embedding,
    embedding_to_bytes,
    compute_face_similarity,
    find_matching_person,
    get_faces_dir,
)
from ..utils.logging import get_logger

logger = get_logger(__name__)

async def verify_face_recognition_enabled(_token: str = Depends(verify_token)) -> None:
    """Ensure face recognition is enabled before accessing faces endpoints."""
    async for db in get_db():
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("face_recognition_enabled",),
        )
        row = await cursor.fetchone()
        if row:
            try:
                enabled = bool(json.loads(row["value"]))
            except Exception:
                enabled = str(row["value"]).lower() == "true"
        else:
            enabled = False

    if not enabled:
        raise HTTPException(
            status_code=403,
            detail="Face recognition is disabled. Enable it in Settings to use Faces.",
        )


router = APIRouter(
    prefix="/faces",
    tags=["faces"],
    dependencies=[Depends(verify_face_recognition_enabled)],
)


# =============================================================================
# Helper Functions
# =============================================================================


async def select_best_thumbnail(person_id: str, db) -> str | None:
    """Select face with highest similarity to person's average embedding (centroid).

    This ensures the thumbnail is the most representative face for this person.
    """
    # Get all face embeddings for this person
    cursor = await db.execute(
        """
        SELECT face_id, embedding
        FROM faces
        WHERE person_id = ? AND embedding IS NOT NULL
        """,
        (person_id,),
    )
    faces = await cursor.fetchall()

    if not faces:
        return None

    if len(faces) == 1:
        return faces[0]["face_id"]

    # Convert embeddings to numpy arrays
    embeddings = []
    face_ids = []
    for face in faces:
        try:
            emb = bytes_to_embedding(face["embedding"])
            if emb is not None:
                embeddings.append(emb)
                face_ids.append(face["face_id"])
        except Exception as e:
            logger.warning(f"Failed to parse embedding for face {face['face_id']}: {e}")
            continue

    if not embeddings:
        return None

    # Compute centroid (average embedding)
    embeddings_array = np.array(embeddings)
    centroid = np.mean(embeddings_array, axis=0)

    # Find face closest to centroid
    best_face_id = None
    best_similarity = -1.0

    for face_id, emb in zip(face_ids, embeddings):
        # Compute cosine similarity
        similarity = compute_face_similarity(emb, centroid)
        if similarity > best_similarity:
            best_similarity = similarity
            best_face_id = face_id

    return best_face_id


async def reanalyze_after_retag(
    old_person_id: str | None,
    new_person_id: str,
    db,
) -> list[dict]:
    """Re-check unassigned faces after a face is reassigned.

    Returns suggestions for faces that might belong to either person.
    """
    suggestions = []

    # Get embeddings for the new person
    cursor = await db.execute(
        """
        SELECT face_id, embedding
        FROM faces
        WHERE person_id = ? AND embedding IS NOT NULL
        LIMIT 10
        """,
        (new_person_id,),
    )
    new_person_faces = await cursor.fetchall()

    if not new_person_faces:
        return suggestions

    # Parse embeddings
    new_embeddings = []
    for face in new_person_faces:
        try:
            emb = bytes_to_embedding(face["embedding"])
            if emb is not None:
                new_embeddings.append(emb)
        except Exception:
            continue

    if not new_embeddings:
        return suggestions

    # Compute average embedding for new person
    new_person_centroid = np.mean(np.array(new_embeddings), axis=0)

    # Get unassigned faces
    cursor = await db.execute(
        """
        SELECT face_id, embedding, crop_path
        FROM faces
        WHERE person_id IS NULL AND embedding IS NOT NULL
        LIMIT 100
        """
    )
    unassigned_faces = await cursor.fetchall()

    # Check similarity to new person
    for face in unassigned_faces:
        try:
            face_emb = bytes_to_embedding(face["embedding"])
            if face_emb is None:
                continue

            similarity = compute_face_similarity(face_emb, new_person_centroid)

            # Higher threshold for suggestions (0.65)
            if similarity > 0.65:
                suggestions.append({
                    "face_id": face["face_id"],
                    "suggested_person_id": new_person_id,
                    "confidence": float(similarity),
                    "crop_path": face["crop_path"],
                })
        except Exception as e:
            logger.warning(f"Failed to check face {face['face_id']}: {e}")
            continue

    # Sort by confidence descending
    suggestions.sort(key=lambda x: x["confidence"], reverse=True)

    # Return top 10 suggestions
    return suggestions[:10]


# =============================================================================
# Models
# =============================================================================


class Face(BaseModel):
    """Face detection model."""

    face_id: str
    video_id: str
    frame_id: str
    timestamp_ms: int
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confidence: float
    crop_path: str | None = None
    age: int | None = None
    gender: str | None = None
    person_id: str | None = None
    person_name: str | None = None
    cluster_id: str | None = None
    created_at_ms: int


class FacesResponse(BaseModel):
    """Faces list response."""

    faces: list[Face]
    total: int


class Person(BaseModel):
    """Named person model."""

    person_id: str
    name: str
    face_count: int = 0
    thumbnail_face_id: str | None = None
    thumbnail_crop_path: str | None = None
    recognition_mode: str = "average"
    created_at_ms: int
    updated_at_ms: int


class PersonsResponse(BaseModel):
    """Persons list response."""

    persons: list[Person]
    total: int


class CreatePersonRequest(BaseModel):
    """Create person request."""

    name: str
    face_ids: list[str] = []


class UpdatePersonRequest(BaseModel):
    """Update person request."""

    name: str | None = None
    thumbnail_face_id: str | None = None


class AssignFaceRequest(BaseModel):
    """Assign face to person request."""

    person_id: str | None


class MergeFacesRequest(BaseModel):
    """Merge faces into a person request."""

    face_ids: list[str]
    person_id: str | None = None  # If None, create new person
    name: str | None = None  # Name for new person


class ClusterFacesRequest(BaseModel):
    """Cluster faces request."""

    threshold: float = 0.6  # Similarity threshold for clustering
    video_id: str | None = None  # Optional: only cluster faces from this video


class FaceCluster(BaseModel):
    """Face cluster."""

    cluster_id: str
    face_count: int
    sample_faces: list[Face]


class ClustersResponse(BaseModel):
    """Clusters list response."""

    clusters: list[FaceCluster]
    total: int


class SimilarFacesResponse(BaseModel):
    """Similar faces response."""

    faces: list[Face]
    similarities: list[float]


class ConfusingPair(BaseModel):
    """Confusing person pair model."""
    person_a_id: str
    person_a_name: str
    person_b_id: str
    person_b_name: str
    threshold: float
    correction_count: int


class ConfusingPairsResponse(BaseModel):
    """Confusing pairs response."""
    pairs: list[ConfusingPair]
    total: int


# =============================================================================
# Faces Endpoints
# =============================================================================


@router.get("", response_model=FacesResponse)
async def list_faces(
    video_id: str | None = Query(None, description="Filter by video"),
    person_id: str | None = Query(None, description="Filter by person"),
    unassigned: bool = Query(False, description="Only show unassigned faces"),
    cluster_id: str | None = Query(None, description="Filter by cluster"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _token: str = Depends(verify_token),
) -> FacesResponse:
    """List faces with optional filters."""
    conditions = []
    params: list = []

    if video_id:
        conditions.append("f.video_id = ?")
        params.append(video_id)

    if person_id:
        conditions.append("f.person_id = ?")
        params.append(person_id)

    if unassigned:
        conditions.append("f.person_id IS NULL")

    if cluster_id:
        conditions.append("f.cluster_id = ?")
        params.append(cluster_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async for db in get_db():
        # Get total count
        cursor = await db.execute(
            f"SELECT COUNT(*) as count FROM faces f WHERE {where_clause}",
            params,
        )
        row = await cursor.fetchone()
        total = row["count"] if row else 0

        # Get faces with person name
        cursor = await db.execute(
            f"""
            SELECT f.*, p.name as person_name
            FROM faces f
            LEFT JOIN persons p ON f.person_id = p.person_id
            WHERE {where_clause}
            ORDER BY f.created_at_ms DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )
        rows = await cursor.fetchall()

        faces = [
            Face(
                face_id=row["face_id"],
                video_id=row["video_id"],
                frame_id=row["frame_id"],
                timestamp_ms=row["timestamp_ms"],
                bbox_x=row["bbox_x"],
                bbox_y=row["bbox_y"],
                bbox_w=row["bbox_w"],
                bbox_h=row["bbox_h"],
                confidence=row["confidence"],
                crop_path=row["crop_path"],
                age=row["age"],
                gender=row["gender"],
                person_id=row["person_id"],
                person_name=row["person_name"],
                cluster_id=row["cluster_id"],
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        return FacesResponse(faces=faces, total=total)

    return FacesResponse(faces=[], total=0)


# =============================================================================
# Persons Endpoints
# =============================================================================


@router.get("/persons", response_model=PersonsResponse)
async def list_persons(
    search: str | None = Query(None, description="Search by name"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _token: str = Depends(verify_token),
) -> PersonsResponse:
    """List all named persons."""
    conditions = []
    params: list = []

    if search:
        conditions.append("p.name LIKE ?")
        params.append(f"%{search}%")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async for db in get_db():
        # Get total count
        cursor = await db.execute(
            f"SELECT COUNT(*) as count FROM persons p WHERE {where_clause}",
            params,
        )
        row = await cursor.fetchone()
        total = row["count"] if row else 0

        # Get persons with thumbnail info
        cursor = await db.execute(
            f"""
            SELECT p.person_id, p.name, p.face_count, p.thumbnail_face_id,
                   p.recognition_mode, p.created_at_ms, p.updated_at_ms,
                   f.crop_path as thumbnail_crop_path
            FROM persons p
            LEFT JOIN faces f ON p.thumbnail_face_id = f.face_id
            WHERE {where_clause}
            ORDER BY p.name ASC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )
        rows = await cursor.fetchall()

        persons = [
            Person(
                person_id=row["person_id"],
                name=row["name"],
                face_count=row["face_count"],
                thumbnail_face_id=row["thumbnail_face_id"],
                thumbnail_crop_path=row["thumbnail_crop_path"],
                recognition_mode=row["recognition_mode"] or "average",
                created_at_ms=row["created_at_ms"],
                updated_at_ms=row["updated_at_ms"],
            )
            for row in rows
        ]

        return PersonsResponse(persons=persons, total=total)

    return PersonsResponse(persons=[], total=0)


@router.post("/persons", response_model=Person)
async def create_person(
    request: CreatePersonRequest,
    _token: str = Depends(verify_token),
) -> Person:
    """Create a new named person."""
    person_id = str(uuid.uuid4())
    now_ms = int(datetime.now().timestamp() * 1000)

    async for db in get_db():
        # Check if name already exists
        cursor = await db.execute(
            "SELECT person_id FROM persons WHERE name = ?",
            (request.name,),
        )
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Person with this name already exists")

        # Create person
        await db.execute(
            """
            INSERT INTO persons (person_id, name, face_count, created_at_ms, updated_at_ms)
            VALUES (?, ?, 0, ?, ?)
            """,
            (person_id, request.name, now_ms, now_ms),
        )

        # Assign faces if provided
        if request.face_ids:
            for face_id in request.face_ids:
                await db.execute(
                    "UPDATE faces SET person_id = ? WHERE face_id = ?",
                    (person_id, face_id),
                )

            # Select best thumbnail based on similarity to centroid
            best_thumbnail = await select_best_thumbnail(person_id, db)

            # Update face count and set thumbnail
            await db.execute(
                """
                UPDATE persons
                SET face_count = (SELECT COUNT(*) FROM faces WHERE person_id = ?),
                    thumbnail_face_id = ?
                WHERE person_id = ?
                """,
                (person_id, best_thumbnail, person_id),
            )

        await db.commit()

        # Get the created person
        cursor = await db.execute(
            """
            SELECT p.person_id, p.name, p.face_count, p.thumbnail_face_id,
                   p.recognition_mode, p.created_at_ms, p.updated_at_ms,
                   f.crop_path as thumbnail_crop_path
            FROM persons p
            LEFT JOIN faces f ON p.thumbnail_face_id = f.face_id
            WHERE p.person_id = ?
            """,
            (person_id,),
        )
        row = await cursor.fetchone()

        return Person(
            person_id=row["person_id"],
            name=row["name"],
            face_count=row["face_count"],
            thumbnail_face_id=row["thumbnail_face_id"],
            thumbnail_crop_path=row["thumbnail_crop_path"],
            recognition_mode=row["recognition_mode"] or "average",
            created_at_ms=row["created_at_ms"],
            updated_at_ms=row["updated_at_ms"],
        )

    raise HTTPException(status_code=500, detail="Database error")


@router.get("/persons/{person_id}", response_model=Person)
async def get_person(
    person_id: str,
    _token: str = Depends(verify_token),
) -> Person:
    """Get a single person by ID."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT p.person_id, p.name, p.face_count, p.thumbnail_face_id,
                   p.recognition_mode, p.created_at_ms, p.updated_at_ms,
                   f.crop_path as thumbnail_crop_path
            FROM persons p
            LEFT JOIN faces f ON p.thumbnail_face_id = f.face_id
            WHERE p.person_id = ?
            """,
            (person_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Person not found")

        return Person(
            person_id=row["person_id"],
            name=row["name"],
            face_count=row["face_count"],
            thumbnail_face_id=row["thumbnail_face_id"],
            thumbnail_crop_path=row["thumbnail_crop_path"],
            recognition_mode=row["recognition_mode"] or "average",
            created_at_ms=row["created_at_ms"],
            updated_at_ms=row["updated_at_ms"],
        )

    raise HTTPException(status_code=404, detail="Person not found")


@router.put("/persons/{person_id}", response_model=Person)
async def update_person(
    person_id: str,
    request: UpdatePersonRequest,
    _token: str = Depends(verify_token),
) -> Person:
    """Update a person's name or thumbnail."""
    async for db in get_db():
        # Verify person exists
        cursor = await db.execute(
            "SELECT person_id FROM persons WHERE person_id = ?",
            (person_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Person not found")

        updates = []
        params = []

        if request.name is not None:
            # Check if new name conflicts
            cursor = await db.execute(
                "SELECT person_id FROM persons WHERE name = ? AND person_id != ?",
                (request.name, person_id),
            )
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="Person with this name already exists")

            updates.append("name = ?")
            params.append(request.name)

        if request.thumbnail_face_id is not None:
            # Verify face exists and belongs to this person
            cursor = await db.execute(
                "SELECT face_id FROM faces WHERE face_id = ? AND person_id = ?",
                (request.thumbnail_face_id, person_id),
            )
            if not await cursor.fetchone():
                raise HTTPException(status_code=400, detail="Face not found or not assigned to this person")

            updates.append("thumbnail_face_id = ?")
            params.append(request.thumbnail_face_id)

        if updates:
            updates.append("updated_at_ms = ?")
            params.append(int(datetime.now().timestamp() * 1000))
            params.append(person_id)

            await db.execute(
                f"UPDATE persons SET {', '.join(updates)} WHERE person_id = ?",
                params,
            )
            await db.commit()

        # Get updated person
        cursor = await db.execute(
            """
            SELECT p.person_id, p.name, p.face_count, p.thumbnail_face_id,
                   p.recognition_mode, p.created_at_ms, p.updated_at_ms,
                   f.crop_path as thumbnail_crop_path
            FROM persons p
            LEFT JOIN faces f ON p.thumbnail_face_id = f.face_id
            WHERE p.person_id = ?
            """,
            (person_id,),
        )
        row = await cursor.fetchone()

        return Person(
            person_id=row["person_id"],
            name=row["name"],
            face_count=row["face_count"],
            thumbnail_face_id=row["thumbnail_face_id"],
            thumbnail_crop_path=row["thumbnail_crop_path"],
            recognition_mode=row["recognition_mode"] or "average",
            created_at_ms=row["created_at_ms"],
            updated_at_ms=row["updated_at_ms"],
        )

    raise HTTPException(status_code=500, detail="Database error")


@router.delete("/persons/{person_id}")
async def delete_person(
    person_id: str,
    unassign_faces: bool = Query(True, description="Unassign faces instead of deleting them"),
    _token: str = Depends(verify_token),
) -> dict:
    """Delete a person."""
    async for db in get_db():
        # Verify person exists
        cursor = await db.execute(
            "SELECT person_id FROM persons WHERE person_id = ?",
            (person_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Person not found")

        if unassign_faces:
            # Unassign all faces
            await db.execute(
                "UPDATE faces SET person_id = NULL WHERE person_id = ?",
                (person_id,),
            )
        else:
            # Delete all faces (and their crops)
            cursor = await db.execute(
                "SELECT crop_path FROM faces WHERE person_id = ?",
                (person_id,),
            )
            rows = await cursor.fetchall()
            for row in rows:
                if row["crop_path"]:
                    try:
                        Path(row["crop_path"]).unlink(missing_ok=True)
                    except Exception as e:
                        logger.warning(f"Failed to delete face crop: {e}")

            await db.execute("DELETE FROM faces WHERE person_id = ?", (person_id,))

        # Delete person
        await db.execute("DELETE FROM persons WHERE person_id = ?", (person_id,))
        await db.commit()

        return {"success": True, "person_id": person_id}

    raise HTTPException(status_code=500, detail="Database error")


# =============================================================================
# Stats (must be before /{face_id} to avoid path conflict)
# =============================================================================


@router.get("/stats")
async def get_face_stats(
    _token: str = Depends(verify_token),
) -> dict:
    """Get face-related statistics including learning system metrics."""
    async for db in get_db():
        stats = {}

        # Total faces
        cursor = await db.execute("SELECT COUNT(*) as count FROM faces")
        row = await cursor.fetchone()
        stats["total_faces"] = row["count"] if row else 0

        # Assigned faces
        cursor = await db.execute("SELECT COUNT(*) as count FROM faces WHERE person_id IS NOT NULL")
        row = await cursor.fetchone()
        stats["assigned_faces"] = row["count"] if row else 0

        # Unassigned faces
        stats["unassigned_faces"] = stats["total_faces"] - stats["assigned_faces"]

        # Total persons
        cursor = await db.execute("SELECT COUNT(*) as count FROM persons")
        row = await cursor.fetchone()
        stats["total_persons"] = row["count"] if row else 0

        # Unique clusters
        cursor = await db.execute("SELECT COUNT(DISTINCT cluster_id) as count FROM faces WHERE cluster_id IS NOT NULL")
        row = await cursor.fetchone()
        stats["unique_clusters"] = row["count"] if row else 0

        # Videos with faces
        cursor = await db.execute("SELECT COUNT(DISTINCT video_id) as count FROM faces")
        row = await cursor.fetchone()
        stats["videos_with_faces"] = row["count"] if row else 0

        # Learning system stats
        # Reference faces
        cursor = await db.execute("SELECT COUNT(*) as count FROM face_references")
        row = await cursor.fetchone()
        stats["reference_faces"] = row["count"] if row else 0

        # Negative examples
        cursor = await db.execute("SELECT COUNT(*) as count FROM face_negatives")
        row = await cursor.fetchone()
        stats["negative_examples"] = row["count"] if row else 0

        # Confusing pairs
        cursor = await db.execute("SELECT COUNT(*) as count FROM person_pair_thresholds")
        row = await cursor.fetchone()
        stats["confusing_pairs"] = row["count"] if row else 0

        # Faces by assignment source
        cursor = await db.execute(
            """
            SELECT assignment_source, COUNT(*) as count
            FROM faces
            WHERE person_id IS NOT NULL
            GROUP BY assignment_source
            """
        )
        source_rows = await cursor.fetchall()
        stats["assignments_by_source"] = {
            row["assignment_source"] or "legacy": row["count"]
            for row in source_rows
        }

        # Faces needing review (low confidence auto-assignments)
        cursor = await db.execute(
            """
            SELECT COUNT(*) as count FROM faces
            WHERE assignment_source = 'auto'
              AND assignment_confidence IS NOT NULL
              AND assignment_confidence < 0.75
            """
        )
        row = await cursor.fetchone()
        stats["faces_needing_review"] = row["count"] if row else 0

        return stats

    raise HTTPException(status_code=500, detail="Database error")


@router.get("/confusing-pairs", response_model=ConfusingPairsResponse)
async def get_all_confusing_pairs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _token: str = Depends(verify_token),
) -> ConfusingPairsResponse:
    """
    Get all pairs of people that are frequently confused.

    Returns person pairs sorted by correction count (most corrected first).
    """
    async for db in get_db():
        # Get total count
        cursor = await db.execute("SELECT COUNT(*) as count FROM person_pair_thresholds")
        row = await cursor.fetchone()
        total = row["count"] if row else 0

        # Get pairs
        cursor = await db.execute(
            """
            SELECT ppt.person_a_id, ppt.person_b_id, ppt.threshold, ppt.correction_count,
                   pa.name as person_a_name, pb.name as person_b_name
            FROM person_pair_thresholds ppt
            JOIN persons pa ON ppt.person_a_id = pa.person_id
            JOIN persons pb ON ppt.person_b_id = pb.person_id
            ORDER BY ppt.correction_count DESC, ppt.threshold DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()

        pairs = [
            ConfusingPair(
                person_a_id=row["person_a_id"],
                person_a_name=row["person_a_name"],
                person_b_id=row["person_b_id"],
                person_b_name=row["person_b_name"],
                threshold=row["threshold"],
                correction_count=row["correction_count"],
            )
            for row in rows
        ]

        return ConfusingPairsResponse(pairs=pairs, total=total)

    return ConfusingPairsResponse(pairs=[], total=0)


# =============================================================================
# Individual face operations
# =============================================================================


@router.get("/{face_id}", response_model=Face)
async def get_face(
    face_id: str,
    _token: str = Depends(verify_token),
) -> Face:
    """Get a single face by ID."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT f.*, p.name as person_name
            FROM faces f
            LEFT JOIN persons p ON f.person_id = p.person_id
            WHERE f.face_id = ?
            """,
            (face_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Face not found")

        return Face(
            face_id=row["face_id"],
            video_id=row["video_id"],
            frame_id=row["frame_id"],
            timestamp_ms=row["timestamp_ms"],
            bbox_x=row["bbox_x"],
            bbox_y=row["bbox_y"],
            bbox_w=row["bbox_w"],
            bbox_h=row["bbox_h"],
            confidence=row["confidence"],
            crop_path=row["crop_path"],
            age=row["age"],
            gender=row["gender"],
            person_id=row["person_id"],
            person_name=row["person_name"],
            cluster_id=row["cluster_id"],
            created_at_ms=row["created_at_ms"],
        )

    raise HTTPException(status_code=404, detail="Face not found")


@router.get("/{face_id}/similar", response_model=SimilarFacesResponse)
async def find_similar_faces(
    face_id: str,
    threshold: float = Query(0.5, ge=0.0, le=1.0, description="Minimum similarity"),
    limit: int = Query(20, ge=1, le=100),
    _token: str = Depends(verify_token),
) -> SimilarFacesResponse:
    """Find faces similar to the given face."""
    async for db in get_db():
        # Get the source face embedding
        cursor = await db.execute(
            "SELECT embedding FROM faces WHERE face_id = ?",
            (face_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Face not found")

        source_embedding = bytes_to_embedding(row["embedding"])

        # Get all other faces with embeddings
        cursor = await db.execute(
            """
            SELECT f.*, p.name as person_name
            FROM faces f
            LEFT JOIN persons p ON f.person_id = p.person_id
            WHERE f.face_id != ?
            """,
            (face_id,),
        )
        rows = await cursor.fetchall()

        # Calculate similarities
        results = []
        for row in rows:
            embedding = bytes_to_embedding(row["embedding"])
            similarity = compute_face_similarity(source_embedding, embedding)

            if similarity >= threshold:
                results.append((row, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        results = results[:limit]

        faces = [
            Face(
                face_id=row["face_id"],
                video_id=row["video_id"],
                frame_id=row["frame_id"],
                timestamp_ms=row["timestamp_ms"],
                bbox_x=row["bbox_x"],
                bbox_y=row["bbox_y"],
                bbox_w=row["bbox_w"],
                bbox_h=row["bbox_h"],
                confidence=row["confidence"],
                crop_path=row["crop_path"],
                age=row["age"],
                gender=row["gender"],
                person_id=row["person_id"],
                person_name=row["person_name"],
                cluster_id=row["cluster_id"],
                created_at_ms=row["created_at_ms"],
            )
            for row, _ in results
        ]
        similarities = [sim for _, sim in results]

        return SimilarFacesResponse(faces=faces, similarities=similarities)

    return SimilarFacesResponse(faces=[], similarities=[])


@router.post("/{face_id}/assign")
async def assign_face_to_person(
    face_id: str,
    request: AssignFaceRequest,
    _token: str = Depends(verify_token),
) -> dict:
    """
    Assign a face to a person.

    This endpoint also records learning signals:
    - If the face was previously assigned to a different person, that becomes a negative example
    - Pair thresholds are updated for frequently confused person pairs
    - Assignment is marked as 'manual' source for weighted learning
    """
    now_ms = int(datetime.now().timestamp() * 1000)

    async for db in get_db():
        # Get face info including current assignment
        cursor = await db.execute(
            "SELECT face_id, person_id FROM faces WHERE face_id = ?",
            (face_id,),
        )
        face_row = await cursor.fetchone()
        if not face_row:
            raise HTTPException(status_code=404, detail="Face not found")

        previous_person_id = face_row["person_id"]

        # Verify target person exists (skip if unassigning)
        if request.person_id is not None:
            cursor = await db.execute(
                "SELECT person_id FROM persons WHERE person_id = ?",
                (request.person_id,),
            )
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Person not found")

        # Record learning signals if this is a reassignment (correction)
        learning_recorded = False
        if previous_person_id and request.person_id and previous_person_id != request.person_id:
            # Add negative example: this face should NOT match the previous person
            await db.execute(
                """
                INSERT OR IGNORE INTO face_negatives (face_id, person_id, created_at_ms)
                VALUES (?, ?, ?)
                """,
                (face_id, previous_person_id, now_ms),
            )

            # Update or create pair threshold for this confusing pair
            # Sort IDs for consistent key
            pair = tuple(sorted([previous_person_id, request.person_id]))
            cursor = await db.execute(
                """
                SELECT id, threshold, correction_count
                FROM person_pair_thresholds
                WHERE person_a_id = ? AND person_b_id = ?
                """,
                pair,
            )
            pair_row = await cursor.fetchone()

            if pair_row:
                # Increment threshold (cap at 0.85)
                new_threshold = min(pair_row["threshold"] + 0.02, 0.85)
                new_count = pair_row["correction_count"] + 1
                await db.execute(
                    """
                    UPDATE person_pair_thresholds
                    SET threshold = ?, correction_count = ?, updated_at_ms = ?
                    WHERE id = ?
                    """,
                    (new_threshold, new_count, now_ms, pair_row["id"]),
                )
            else:
                # Create new pair threshold starting at 0.70
                await db.execute(
                    """
                    INSERT INTO person_pair_thresholds
                    (person_a_id, person_b_id, threshold, correction_count, created_at_ms, updated_at_ms)
                    VALUES (?, ?, 0.70, 1, ?, ?)
                    """,
                    (pair[0], pair[1], now_ms, now_ms),
                )

            learning_recorded = True
            logger.info(
                f"Recorded learning signal: face {face_id} reassigned from "
                f"{previous_person_id} to {request.person_id}"
            )

        # Update face with manual assignment
        await db.execute(
            """
            UPDATE faces
            SET person_id = ?,
                assignment_source = 'manual',
                assignment_confidence = 1.0,
                assigned_at_ms = ?
            WHERE face_id = ?
            """,
            (request.person_id, now_ms, face_id),
        )

        # Update face counts for new person (if assigning, not unassigning)
        if request.person_id is not None:
            await db.execute(
                """
                UPDATE persons
                SET face_count = (SELECT COUNT(*) FROM faces WHERE person_id = ?),
                    updated_at_ms = ?
                WHERE person_id = ?
                """,
                (request.person_id, now_ms, request.person_id),
            )

        # Update face count for previous person
        if previous_person_id and previous_person_id != request.person_id:
            await db.execute(
                """
                UPDATE persons
                SET face_count = (SELECT COUNT(*) FROM faces WHERE person_id = ?),
                    updated_at_ms = ?
                WHERE person_id = ?
                """,
                (previous_person_id, now_ms, previous_person_id),
            )
            # Update thumbnail for old person
            old_best_thumbnail = await select_best_thumbnail(previous_person_id, db)
            if old_best_thumbnail:
                await db.execute(
                    "UPDATE persons SET thumbnail_face_id = ? WHERE person_id = ?",
                    (old_best_thumbnail, previous_person_id),
                )

        # Update thumbnail for new person (if assigning)
        if request.person_id is not None:
            new_best_thumbnail = await select_best_thumbnail(request.person_id, db)
            if new_best_thumbnail:
                await db.execute(
                    "UPDATE persons SET thumbnail_face_id = ? WHERE person_id = ?",
                    (new_best_thumbnail, request.person_id),
                )

        # Trigger re-analysis to find similar unassigned faces (only when assigning to a person)
        suggestions = []
        if request.person_id is not None:
            suggestions = await reanalyze_after_retag(previous_person_id, request.person_id, db)

        await db.commit()

        return {
            "success": True,
            "face_id": face_id,
            "person_id": request.person_id,
            "learning_recorded": learning_recorded,
            "suggestions": suggestions,
        }

    raise HTTPException(status_code=500, detail="Database error")


@router.delete("/{face_id}")
async def delete_face(
    face_id: str,
    _token: str = Depends(verify_token),
) -> dict:
    """Delete a face."""
    async for db in get_db():
        # Get face info
        cursor = await db.execute(
            "SELECT person_id, crop_path FROM faces WHERE face_id = ?",
            (face_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Face not found")

        person_id = row["person_id"]
        crop_path = row["crop_path"]

        # Delete face
        await db.execute("DELETE FROM faces WHERE face_id = ?", (face_id,))

        # Update person face count if assigned
        if person_id:
            await db.execute(
                """
                UPDATE persons
                SET face_count = (SELECT COUNT(*) FROM faces WHERE person_id = ?),
                    updated_at_ms = ?
                WHERE person_id = ?
                """,
                (person_id, int(datetime.now().timestamp() * 1000), person_id),
            )

        await db.commit()

        # Delete crop file if exists
        if crop_path:
            try:
                Path(crop_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to delete face crop: {e}")

        return {"success": True, "face_id": face_id}

    raise HTTPException(status_code=500, detail="Database error")


# =============================================================================
# Merge & Cluster Endpoints
# =============================================================================


@router.post("/merge")
async def merge_faces(
    request: MergeFacesRequest,
    _token: str = Depends(verify_token),
) -> dict:
    """Merge multiple faces into a person."""
    if len(request.face_ids) == 0:
        raise HTTPException(status_code=400, detail="At least one face ID required")

    now_ms = int(datetime.now().timestamp() * 1000)

    async for db in get_db():
        person_id = request.person_id

        if person_id:
            # Verify person exists
            cursor = await db.execute(
                "SELECT person_id FROM persons WHERE person_id = ?",
                (person_id,),
            )
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Person not found")
        else:
            # Create new person
            person_id = str(uuid.uuid4())
            name = request.name or f"Person {person_id[:8]}"

            await db.execute(
                """
                INSERT INTO persons (person_id, name, face_count, thumbnail_face_id, created_at_ms, updated_at_ms)
                VALUES (?, ?, 0, ?, ?, ?)
                """,
                (person_id, name, request.face_ids[0], now_ms, now_ms),
            )

        # Assign all faces to person
        for face_id in request.face_ids:
            await db.execute(
                "UPDATE faces SET person_id = ? WHERE face_id = ?",
                (person_id, face_id),
            )

        # Update face count
        await db.execute(
            """
            UPDATE persons
            SET face_count = (SELECT COUNT(*) FROM faces WHERE person_id = ?),
                updated_at_ms = ?
            WHERE person_id = ?
            """,
            (person_id, now_ms, person_id),
        )

        await db.commit()

        return {
            "success": True,
            "person_id": person_id,
            "faces_merged": len(request.face_ids),
        }

    raise HTTPException(status_code=500, detail="Database error")


@router.post("/cluster", response_model=ClustersResponse)
async def cluster_faces(
    request: ClusterFacesRequest,
    _token: str = Depends(verify_token),
) -> ClustersResponse:
    """
    Cluster unassigned faces by similarity.
    Uses simple agglomerative clustering.
    """
    async for db in get_db():
        # Get unassigned faces with embeddings
        conditions = ["person_id IS NULL"]
        params: list = []

        if request.video_id:
            conditions.append("video_id = ?")
            params.append(request.video_id)

        where_clause = " AND ".join(conditions)

        cursor = await db.execute(
            f"""
            SELECT face_id, embedding, video_id, frame_id, timestamp_ms,
                   bbox_x, bbox_y, bbox_w, bbox_h, confidence,
                   crop_path, age, gender, cluster_id, created_at_ms
            FROM faces
            WHERE {where_clause}
            """,
            params,
        )
        rows = await cursor.fetchall()

        if not rows:
            return ClustersResponse(clusters=[], total=0)

        # Convert to list for clustering
        faces_data = []
        for row in rows:
            faces_data.append({
                "face_id": row["face_id"],
                "embedding": bytes_to_embedding(row["embedding"]),
                "row": row,
            })

        # Simple greedy clustering
        clusters: dict[str, list[dict]] = {}
        cluster_embeddings: dict[str, np.ndarray] = {}

        for face in faces_data:
            face_id = face["face_id"]
            embedding = face["embedding"]

            # Find best matching cluster
            best_cluster = None
            best_similarity = request.threshold

            for cluster_id, cluster_embedding in cluster_embeddings.items():
                similarity = compute_face_similarity(embedding, cluster_embedding)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_cluster = cluster_id

            if best_cluster:
                # Add to existing cluster
                clusters[best_cluster].append(face)
                # Update cluster centroid (average embedding)
                all_embeddings = [f["embedding"] for f in clusters[best_cluster]]
                cluster_embeddings[best_cluster] = np.mean(all_embeddings, axis=0)
            else:
                # Create new cluster
                new_cluster_id = str(uuid.uuid4())[:8]
                clusters[new_cluster_id] = [face]
                cluster_embeddings[new_cluster_id] = embedding

        # Update cluster IDs in database using batch operation
        update_data = []
        for cluster_id, cluster_faces in clusters.items():
            for face in cluster_faces:
                update_data.append((cluster_id, face["face_id"]))
        
        if update_data:
            async def _update_clusters():
                await db.executemany(
                    "UPDATE faces SET cluster_id = ? WHERE face_id = ?",
                    update_data,
                )
                await db.commit()
            
            # Retry on database locked errors
            for attempt in range(5):
                try:
                    await _update_clusters()
                    break
                except sqlite3.OperationalError as err:
                    if "locked" in str(err).lower() and attempt < 4:
                        await asyncio.sleep(0.1 * (attempt + 1))
                        continue
                    raise

        # Build response
        result_clusters = []
        for cluster_id, cluster_faces in clusters.items():
            sample_faces = [
                Face(
                    face_id=f["row"]["face_id"],
                    video_id=f["row"]["video_id"],
                    frame_id=f["row"]["frame_id"],
                    timestamp_ms=f["row"]["timestamp_ms"],
                    bbox_x=f["row"]["bbox_x"],
                    bbox_y=f["row"]["bbox_y"],
                    bbox_w=f["row"]["bbox_w"],
                    bbox_h=f["row"]["bbox_h"],
                    confidence=f["row"]["confidence"],
                    crop_path=f["row"]["crop_path"],
                    age=f["row"]["age"],
                    gender=f["row"]["gender"],
                    person_id=None,
                    person_name=None,
                    cluster_id=cluster_id,
                    created_at_ms=f["row"]["created_at_ms"],
                )
                for f in cluster_faces[:5]  # Sample up to 5 faces
            ]

            result_clusters.append(
                FaceCluster(
                    cluster_id=cluster_id,
                    face_count=len(cluster_faces),
                    sample_faces=sample_faces,
                )
            )

        # Sort by face count descending
        result_clusters.sort(key=lambda c: c.face_count, reverse=True)

        return ClustersResponse(clusters=result_clusters, total=len(result_clusters))

    return ClustersResponse(clusters=[], total=0)


# =============================================================================
# Learning System Endpoints
# =============================================================================


class MarkReferenceRequest(BaseModel):
    """Mark face as reference request."""
    weight: float = 1.0


class SetRecognitionModeRequest(BaseModel):
    """Set recognition mode request."""
    mode: Literal["average", "reference_only", "weighted"]


class FaceReference(BaseModel):
    """Face reference model."""
    face_id: str
    person_id: str
    weight: float
    crop_path: str | None = None
    created_at_ms: int


class FaceReferencesResponse(BaseModel):
    """Face references response."""
    references: list[FaceReference]
    total: int


class ReviewQueueFace(BaseModel):
    """Face in review queue."""
    face_id: str
    video_id: str
    frame_id: str
    timestamp_ms: int
    crop_path: str | None = None
    person_id: str | None = None
    person_name: str | None = None
    assignment_confidence: float | None = None
    assignment_source: str | None = None


class ReviewQueueResponse(BaseModel):
    """Review queue response."""
    faces: list[ReviewQueueFace]
    total: int


@router.post("/{face_id}/mark-reference")
async def mark_face_as_reference(
    face_id: str,
    request: MarkReferenceRequest = MarkReferenceRequest(),
    _token: str = Depends(verify_token),
) -> dict:
    """
    Mark a face as a canonical reference for its assigned person.

    Reference faces are weighted heavily in recognition and are used
    as the primary comparison targets for 'reference_only' mode.
    """
    now_ms = int(datetime.now().timestamp() * 1000)

    async for db in get_db():
        # Get face and verify it's assigned to a person
        cursor = await db.execute(
            "SELECT face_id, person_id FROM faces WHERE face_id = ?",
            (face_id,),
        )
        face_row = await cursor.fetchone()

        if not face_row:
            raise HTTPException(status_code=404, detail="Face not found")

        if not face_row["person_id"]:
            raise HTTPException(
                status_code=400,
                detail="Face must be assigned to a person before marking as reference"
            )

        person_id = face_row["person_id"]

        # Insert or update reference
        await db.execute(
            """
            INSERT INTO face_references (face_id, person_id, weight, created_at_ms)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(face_id, person_id) DO UPDATE SET weight = ?
            """,
            (face_id, person_id, request.weight, now_ms, request.weight),
        )

        # Update face assignment source to 'reference'
        await db.execute(
            """
            UPDATE faces
            SET assignment_source = 'reference',
                assignment_confidence = 1.0,
                assigned_at_ms = ?
            WHERE face_id = ?
            """,
            (now_ms, face_id),
        )

        await db.commit()

        return {
            "success": True,
            "face_id": face_id,
            "person_id": person_id,
            "weight": request.weight,
        }

    raise HTTPException(status_code=500, detail="Database error")


@router.delete("/{face_id}/mark-reference")
async def unmark_face_as_reference(
    face_id: str,
    _token: str = Depends(verify_token),
) -> dict:
    """Remove reference status from a face."""
    now_ms = int(datetime.now().timestamp() * 1000)

    async for db in get_db():
        # Delete reference
        cursor = await db.execute(
            "DELETE FROM face_references WHERE face_id = ?",
            (face_id,),
        )

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Face reference not found")

        # Update face assignment source back to 'manual'
        await db.execute(
            """
            UPDATE faces
            SET assignment_source = 'manual',
                assigned_at_ms = ?
            WHERE face_id = ?
            """,
            (now_ms, face_id),
        )

        await db.commit()

        return {"success": True, "face_id": face_id}

    raise HTTPException(status_code=500, detail="Database error")


@router.get("/review-queue", response_model=ReviewQueueResponse)
async def get_faces_for_review(
    confidence_threshold: float = Query(0.75, ge=0.0, le=1.0, description="Max confidence to include"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _token: str = Depends(verify_token),
) -> ReviewQueueResponse:
    """
    Get low-confidence face assignments that need review.

    Returns faces that were auto-assigned but have confidence below
    the threshold, sorted by confidence ascending (least confident first).
    """
    async for db in get_db():
        # Get total count
        cursor = await db.execute(
            """
            SELECT COUNT(*) as count FROM faces
            WHERE assignment_source = 'auto'
              AND assignment_confidence IS NOT NULL
              AND assignment_confidence < ?
            """,
            (confidence_threshold,),
        )
        row = await cursor.fetchone()
        total = row["count"] if row else 0

        # Get faces for review
        cursor = await db.execute(
            """
            SELECT f.face_id, f.video_id, f.frame_id, f.timestamp_ms,
                   f.crop_path, f.person_id, f.assignment_confidence, f.assignment_source,
                   p.name as person_name
            FROM faces f
            LEFT JOIN persons p ON f.person_id = p.person_id
            WHERE f.assignment_source = 'auto'
              AND f.assignment_confidence IS NOT NULL
              AND f.assignment_confidence < ?
            ORDER BY f.assignment_confidence ASC
            LIMIT ? OFFSET ?
            """,
            (confidence_threshold, limit, offset),
        )
        rows = await cursor.fetchall()

        faces = [
            ReviewQueueFace(
                face_id=row["face_id"],
                video_id=row["video_id"],
                frame_id=row["frame_id"],
                timestamp_ms=row["timestamp_ms"],
                crop_path=row["crop_path"],
                person_id=row["person_id"],
                person_name=row["person_name"],
                assignment_confidence=row["assignment_confidence"],
                assignment_source=row["assignment_source"],
            )
            for row in rows
        ]

        return ReviewQueueResponse(faces=faces, total=total)

    return ReviewQueueResponse(faces=[], total=0)


@router.put("/persons/{person_id}/recognition-mode")
async def set_person_recognition_mode(
    person_id: str,
    request: SetRecognitionModeRequest,
    _token: str = Depends(verify_token),
) -> dict:
    """
    Set the recognition mode for a person.

    Modes:
    - 'average': Use weighted average of all face embeddings (default)
    - 'reference_only': Only compare against reference faces (best for distinguishing similar people)
    - 'weighted': Weighted average with extra emphasis on reference faces
    """
    now_ms = int(datetime.now().timestamp() * 1000)

    async for db in get_db():
        # Verify person exists
        cursor = await db.execute(
            "SELECT person_id FROM persons WHERE person_id = ?",
            (person_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Person not found")

        # Update recognition mode
        await db.execute(
            """
            UPDATE persons
            SET recognition_mode = ?, updated_at_ms = ?
            WHERE person_id = ?
            """,
            (request.mode, now_ms, person_id),
        )

        await db.commit()

        return {
            "success": True,
            "person_id": person_id,
            "recognition_mode": request.mode,
        }

    raise HTTPException(status_code=500, detail="Database error")


@router.get("/persons/{person_id}/references", response_model=FaceReferencesResponse)
async def get_person_references(
    person_id: str,
    _token: str = Depends(verify_token),
) -> FaceReferencesResponse:
    """Get all reference faces for a person."""
    async for db in get_db():
        # Verify person exists
        cursor = await db.execute(
            "SELECT person_id FROM persons WHERE person_id = ?",
            (person_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Person not found")

        # Get references
        cursor = await db.execute(
            """
            SELECT fr.face_id, fr.person_id, fr.weight, fr.created_at_ms,
                   f.crop_path
            FROM face_references fr
            JOIN faces f ON fr.face_id = f.face_id
            WHERE fr.person_id = ?
            ORDER BY fr.weight DESC, fr.created_at_ms DESC
            """,
            (person_id,),
        )
        rows = await cursor.fetchall()

        references = [
            FaceReference(
                face_id=row["face_id"],
                person_id=row["person_id"],
                weight=row["weight"],
                crop_path=row["crop_path"],
                created_at_ms=row["created_at_ms"],
            )
            for row in rows
        ]

        return FaceReferencesResponse(references=references, total=len(references))

    return FaceReferencesResponse(references=[], total=0)


@router.get("/persons/{person_id}/confusing-pairs", response_model=ConfusingPairsResponse)
async def get_confusing_pairs(
    person_id: str,
    _token: str = Depends(verify_token),
) -> ConfusingPairsResponse:
    """
    Get pairs of people that are frequently confused with this person.

    Returns person pairs with elevated thresholds due to correction history.
    """
    async for db in get_db():
        # Verify person exists
        cursor = await db.execute(
            "SELECT person_id FROM persons WHERE person_id = ?",
            (person_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Person not found")

        # Get pairs involving this person
        cursor = await db.execute(
            """
            SELECT ppt.person_a_id, ppt.person_b_id, ppt.threshold, ppt.correction_count,
                   pa.name as person_a_name, pb.name as person_b_name
            FROM person_pair_thresholds ppt
            JOIN persons pa ON ppt.person_a_id = pa.person_id
            JOIN persons pb ON ppt.person_b_id = pb.person_id
            WHERE ppt.person_a_id = ? OR ppt.person_b_id = ?
            ORDER BY ppt.correction_count DESC
            """,
            (person_id, person_id),
        )
        rows = await cursor.fetchall()

        pairs = [
            ConfusingPair(
                person_a_id=row["person_a_id"],
                person_a_name=row["person_a_name"],
                person_b_id=row["person_b_id"],
                person_b_name=row["person_b_name"],
                threshold=row["threshold"],
                correction_count=row["correction_count"],
            )
            for row in rows
        ]

        return ConfusingPairsResponse(pairs=pairs, total=len(pairs))

    return ConfusingPairsResponse(pairs=[], total=0)


# =============================================================================
# Timeline
# =============================================================================


class VideoAppearance(BaseModel):
    """Video appearance for a person."""

    video_id: str
    filename: str
    duration_ms: int | None = None
    thumbnail_path: str | None = None
    appearances: list[dict]  # List of {timestamp_ms, face_id, crop_path, confidence}
    first_appearance_ms: int
    last_appearance_ms: int
    appearance_count: int


class PersonTimelineResponse(BaseModel):
    """Person timeline response."""

    person_id: str
    person_name: str
    total_appearances: int
    videos: list[VideoAppearance]


@router.get("/persons/{person_id}/timeline", response_model=PersonTimelineResponse)
async def get_person_timeline(
    person_id: str,
    _token: str = Depends(verify_token),
) -> PersonTimelineResponse:
    """Get a timeline of all appearances of a person across videos."""
    async for db in get_db():
        # Get person info
        cursor = await db.execute(
            "SELECT name FROM persons WHERE person_id = ?",
            (person_id,),
        )
        person_row = await cursor.fetchone()

        if not person_row:
            raise HTTPException(status_code=404, detail="Person not found")

        # Get all faces for this person with video info
        cursor = await db.execute(
            """
            SELECT
                f.face_id,
                f.video_id,
                f.timestamp_ms,
                f.confidence,
                f.crop_path,
                v.filename,
                v.duration_ms,
                fr.thumbnail_path
            FROM faces f
            INNER JOIN videos v ON v.video_id = f.video_id
            LEFT JOIN frames fr ON fr.frame_id = f.frame_id
            WHERE f.person_id = ?
            ORDER BY v.filename, f.timestamp_ms
            """,
            (person_id,),
        )
        rows = await cursor.fetchall()

        # Group by video
        videos_map: dict[str, dict] = {}
        total_appearances = 0

        for row in rows:
            video_id = row["video_id"]
            total_appearances += 1

            if video_id not in videos_map:
                # Get a representative thumbnail for the video
                thumb_cursor = await db.execute(
                    """
                    SELECT thumbnail_path FROM frames
                    WHERE video_id = ?
                    ORDER BY timestamp_ms
                    LIMIT 1
                    """,
                    (video_id,),
                )
                thumb_row = await thumb_cursor.fetchone()

                videos_map[video_id] = {
                    "video_id": video_id,
                    "filename": row["filename"],
                    "duration_ms": row["duration_ms"],
                    "thumbnail_path": thumb_row["thumbnail_path"] if thumb_row else None,
                    "appearances": [],
                    "first_appearance_ms": row["timestamp_ms"],
                    "last_appearance_ms": row["timestamp_ms"],
                }

            videos_map[video_id]["appearances"].append({
                "timestamp_ms": row["timestamp_ms"],
                "face_id": row["face_id"],
                "crop_path": row["crop_path"],
                "confidence": row["confidence"],
            })

            # Update time range
            videos_map[video_id]["first_appearance_ms"] = min(
                videos_map[video_id]["first_appearance_ms"],
                row["timestamp_ms"],
            )
            videos_map[video_id]["last_appearance_ms"] = max(
                videos_map[video_id]["last_appearance_ms"],
                row["timestamp_ms"],
            )

        # Build response
        videos = [
            VideoAppearance(
                video_id=v["video_id"],
                filename=v["filename"],
                duration_ms=v["duration_ms"],
                thumbnail_path=v["thumbnail_path"],
                appearances=v["appearances"],
                first_appearance_ms=v["first_appearance_ms"],
                last_appearance_ms=v["last_appearance_ms"],
                appearance_count=len(v["appearances"]),
            )
            for v in videos_map.values()
        ]

        # Sort by appearance count descending
        videos.sort(key=lambda v: v.appearance_count, reverse=True)

        return PersonTimelineResponse(
            person_id=person_id,
            person_name=person_row["name"],
            total_appearances=total_appearances,
            videos=videos,
        )

    raise HTTPException(status_code=500, detail="Database error")
