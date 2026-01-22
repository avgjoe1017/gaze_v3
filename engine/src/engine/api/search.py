"""Search endpoints."""

from collections import OrderedDict
import json
import os
from pathlib import Path
from threading import Lock
from typing import Literal

import numpy as np

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..db.connection import get_db
from ..ml.colors import extract_color_from_query
from ..ml.embedder import embed_text
from ..middleware.auth import verify_token
from ..utils.logging import get_logger
from ..utils.paths import get_faiss_dir

logger = get_logger(__name__)

_FAISS_CACHE_MAX = int(os.environ.get("GAZE_FAISS_CACHE_MAX", "8"))
_FAISS_INDEX_CACHE: "OrderedDict[str, faiss.Index]" = OrderedDict()
_FAISS_CACHE_LOCK = Lock()


def _set_faiss_cache_max(value: int) -> None:
    """Update the FAISS cache size and evict if needed."""
    global _FAISS_CACHE_MAX
    clamped = max(1, int(value))
    if clamped == _FAISS_CACHE_MAX:
        return
    _FAISS_CACHE_MAX = clamped
    with _FAISS_CACHE_LOCK:
        while len(_FAISS_INDEX_CACHE) > _FAISS_CACHE_MAX:
            evicted, _ = _FAISS_INDEX_CACHE.popitem(last=False)
            logger.debug(f"FAISS cache evicted: {evicted}")


def _get_faiss_index(path: Path):
    """Load a FAISS index with a small LRU cache to avoid repeated disk reads."""
    key = str(path)
    with _FAISS_CACHE_LOCK:
        cached = _FAISS_INDEX_CACHE.get(key)
        if cached is not None:
            _FAISS_INDEX_CACHE.move_to_end(key)
            logger.debug(f"FAISS cache hit: {key}")
            return cached
        logger.debug(f"FAISS cache miss: {key}")

    index = faiss.read_index(key)
    with _FAISS_CACHE_LOCK:
        _FAISS_INDEX_CACHE[key] = index
        _FAISS_INDEX_CACHE.move_to_end(key)
        while len(_FAISS_INDEX_CACHE) > _FAISS_CACHE_MAX:
            evicted, _ = _FAISS_INDEX_CACHE.popitem(last=False)
            logger.debug(f"FAISS cache evicted: {evicted}")
    return index


async def _get_setting(db, key: str, default):
    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,),
    )
    row = await cursor.fetchone()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]
    return default

# COCO object categories that SSDLite can detect
# Used to determine if a query should use object detection instead of CLIP
COCO_CATEGORIES = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush"
}

# Common aliases/synonyms for COCO categories
COCO_ALIASES = {
    "cars": "car", "auto": "car", "automobile": "car", "vehicle": "car",
    "vehicles": "car", "bikes": "bicycle", "bike": "bicycle", "cycle": "bicycle",
    "motorbike": "motorcycle", "plane": "airplane", "planes": "airplane",
    "buses": "bus", "trains": "train", "trucks": "truck", "boats": "boat",
    "people": "person", "human": "person", "humans": "person", "man": "person",
    "woman": "person", "men": "person", "women": "person", "child": "person",
    "children": "person", "kid": "person", "kids": "person",
    "dogs": "dog", "puppy": "dog", "puppies": "dog",
    "cats": "cat", "kitten": "cat", "kittens": "cat",
    "birds": "bird", "horses": "horse", "cows": "cow", "sheep": "sheep",
    "elephants": "elephant", "bears": "bear", "zebras": "zebra", "giraffes": "giraffe",
    "phone": "cell phone", "cellphone": "cell phone", "mobile": "cell phone",
    "television": "tv", "monitor": "tv", "screen": "tv",
    "sofa": "couch", "settee": "couch",
    "computer": "laptop", "notebook": "laptop",
    "food": None,  # Too generic
}

# Visual search similarity threshold (CLIP results below this are filtered out)
VISUAL_SIMILARITY_THRESHOLD = 0.18

def get_coco_category(query: str) -> str | None:
    """Check if query matches a COCO category (or alias). Returns canonical category name."""
    query_lower = query.lower().strip()

    # Direct match
    if query_lower in COCO_CATEGORIES:
        return query_lower

    # Alias match
    if query_lower in COCO_ALIASES:
        return COCO_ALIASES[query_lower]

    # Check if query contains a category as a word
    query_words = set(query_lower.split())
    for word in query_words:
        if word in COCO_CATEGORIES:
            return word
        if word in COCO_ALIASES and COCO_ALIASES[word]:
            return COCO_ALIASES[word]

    return None

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    """Search request."""

    query: str
    mode: Literal["transcript", "visual", "both"] = "both"
    labels: list[str] | None = None
    person_ids: list[str] | None = None  # Filter by persons (face recognition)
    library_id: str | None = None
    limit: int = 50
    offset: int = 0


class PersonMatch(BaseModel):
    """Person match in a search result."""

    person_id: str
    name: str
    face_count: int = 1


class SearchResult(BaseModel):
    """Single search result."""

    video_id: str
    timestamp_ms: int
    score: float
    transcript_snippet: str | None = None
    thumbnail_path: str | None = None
    labels: list[str] | None = None
    persons: list[PersonMatch] | None = None  # Persons detected near this timestamp
    match_type: Literal["transcript", "visual", "both"]


class SearchResponse(BaseModel):
    """Search response."""

    results: list[SearchResult]
    total: int
    query_time_ms: int | None = None


@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest, _token: str = Depends(verify_token)) -> SearchResponse:
    """Perform multi-modal search."""
    import time

    start_time = time.time()
    results: list[SearchResult] = []
    total = 0

    async for db in get_db():
        label_only = bool(request.labels) and not request.query.strip()

        if request.mode in ("visual", "both"):
            cache_max = await _get_setting(db, "faiss_cache_max", _FAISS_CACHE_MAX)
            try:
                _set_faiss_cache_max(int(cache_max))
            except Exception:
                _set_faiss_cache_max(_FAISS_CACHE_MAX)

        if label_only:
            placeholders = ",".join("?" * len(request.labels or []))
            base_params: list[object] = list(request.labels or [])

            # Count total distinct moments for labels (optionally within library)
            if request.library_id:
                count_query = f"""
                    SELECT COUNT(*) as total FROM (
                        SELECT d.video_id, d.timestamp_ms
                        FROM detections d
                        INNER JOIN videos v ON v.video_id = d.video_id
                        WHERE d.label IN ({placeholders})
                        AND v.library_id = ?
                        GROUP BY d.video_id, d.timestamp_ms
                    ) t
                """
                count_params = [*base_params, request.library_id]
            else:
                count_query = f"""
                    SELECT COUNT(*) as total FROM (
                        SELECT d.video_id, d.timestamp_ms
                        FROM detections d
                        WHERE d.label IN ({placeholders})
                        GROUP BY d.video_id, d.timestamp_ms
                    ) t
                """
                count_params = base_params

            count_cursor = await db.execute(count_query, count_params)
            count_row = await count_cursor.fetchone()
            total = count_row["total"] if count_row else 0

            # Fetch results
            if request.library_id:
                query_sql = f"""
                    SELECT
                        d.video_id,
                        d.timestamp_ms,
                        f.thumbnail_path,
                        GROUP_CONCAT(DISTINCT d.label) as labels,
                        COUNT(DISTINCT d.label) as label_hits
                    FROM detections d
                    INNER JOIN videos v ON v.video_id = d.video_id
                    LEFT JOIN frames f ON f.frame_id = d.frame_id
                    WHERE d.label IN ({placeholders})
                    AND v.library_id = ?
                    GROUP BY d.video_id, d.timestamp_ms, f.thumbnail_path
                    ORDER BY label_hits DESC, d.timestamp_ms ASC
                    LIMIT ? OFFSET ?
                """
                params = [*base_params, request.library_id, request.limit, request.offset]
            else:
                query_sql = f"""
                    SELECT
                        d.video_id,
                        d.timestamp_ms,
                        f.thumbnail_path,
                        GROUP_CONCAT(DISTINCT d.label) as labels,
                        COUNT(DISTINCT d.label) as label_hits
                    FROM detections d
                    LEFT JOIN frames f ON f.frame_id = d.frame_id
                    WHERE d.label IN ({placeholders})
                    GROUP BY d.video_id, d.timestamp_ms, f.thumbnail_path
                    ORDER BY label_hits DESC, d.timestamp_ms ASC
                    LIMIT ? OFFSET ?
                """
                params = [*base_params, request.limit, request.offset]

            cursor = await db.execute(query_sql, params)
            rows = await cursor.fetchall()

            for row in rows:
                labels = (row["labels"] or "").split(",") if row["labels"] else []
                label_hits = row["label_hits"] or 0
                score = float(label_hits) / max(len(request.labels or []), 1)
                results.append(
                    SearchResult(
                        video_id=row["video_id"],
                        timestamp_ms=row["timestamp_ms"],
                        score=score,
                        thumbnail_path=row["thumbnail_path"],
                        labels=labels,
                        match_type="visual",
                    )
                )
        else:
            # Transcript search using FTS5
            if request.mode in ("transcript", "both"):
                fts_query = f'"{request.query}"'  # Phrase search

                # Build query with optional library filter
                if request.library_id:
                    # Join with videos table to filter by library_id
                    # FTS5 requires table name (not alias) for MATCH and snippet()
                    query_sql = """
                        SELECT
                            transcript_fts.video_id,
                            transcript_fts.start_ms as timestamp_ms,
                            snippet(transcript_fts, 3, '<mark>', '</mark>', '...', 20) as snippet,
                            bm25(transcript_fts) as rank
                        FROM transcript_fts
                        INNER JOIN videos ON videos.video_id = transcript_fts.video_id
                        WHERE transcript_fts MATCH ?
                        AND videos.library_id = ?
                        ORDER BY rank
                        LIMIT ?
                    """
                    params = (fts_query, request.library_id, request.limit)
                else:
                    query_sql = """
                        SELECT
                            video_id,
                            start_ms as timestamp_ms,
                            snippet(transcript_fts, 3, '<mark>', '</mark>', '...', 20) as snippet,
                            bm25(transcript_fts) as rank
                        FROM transcript_fts
                        WHERE transcript_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    """
                    params = (fts_query, request.limit)

                cursor = await db.execute(query_sql, params)
                rows = await cursor.fetchall()

                for row in rows:
                    # Normalize rank to 0-1 score (FTS5 ranks are negative)
                    score = 1.0 / (1.0 + abs(row["rank"]))
                    results.append(
                        SearchResult(
                            video_id=row["video_id"],
                            timestamp_ms=row["timestamp_ms"],
                            score=score,
                            transcript_snippet=row["snippet"],
                            match_type="transcript",
                        )
                    )

            # Visual search using FAISS + Object Detection + Color
            if request.mode in ("visual", "both"):
                # Check if query matches a COCO object category
                detected_category = get_coco_category(request.query)
                detection_results: dict[tuple[str, int], SearchResult] = {}

                # Check if query contains a color
                query_color = extract_color_from_query(request.query)
                if query_color:
                    logger.info(f"Query contains color '{query_color}'")

                # If query is an object query, first get results from object detection
                if detected_category:
                    logger.info(f"Query '{request.query}' matched COCO category '{detected_category}', using detection-first search")

                    # Query detections for this object
                    if request.library_id:
                        det_query = """
                            SELECT
                                d.video_id,
                                d.timestamp_ms,
                                f.thumbnail_path,
                                MAX(d.confidence) as max_confidence,
                                GROUP_CONCAT(DISTINCT d.label) as labels
                            FROM detections d
                            INNER JOIN videos v ON v.video_id = d.video_id
                            LEFT JOIN frames f ON f.frame_id = d.frame_id
                            WHERE d.label = ?
                            AND v.library_id = ?
                            AND v.status = 'DONE'
                            GROUP BY d.video_id, d.timestamp_ms
                            ORDER BY max_confidence DESC
                            LIMIT ?
                        """
                        det_params = [detected_category, request.library_id, request.limit * 2]
                    else:
                        det_query = """
                            SELECT
                                d.video_id,
                                d.timestamp_ms,
                                f.thumbnail_path,
                                MAX(d.confidence) as max_confidence,
                                GROUP_CONCAT(DISTINCT d.label) as labels
                            FROM detections d
                            INNER JOIN videos v ON v.video_id = d.video_id
                            LEFT JOIN frames f ON f.frame_id = d.frame_id
                            WHERE d.label = ?
                            AND v.status = 'DONE'
                            GROUP BY d.video_id, d.timestamp_ms
                            ORDER BY max_confidence DESC
                            LIMIT ?
                        """
                        det_params = [detected_category, request.limit * 2]

                    det_cursor = await db.execute(det_query, det_params)
                    det_rows = await det_cursor.fetchall()

                    for row in det_rows:
                        labels = (row["labels"] or "").split(",") if row["labels"] else []
                        # Score based on detection confidence (0.25-1.0 -> 0.5-1.0)
                        confidence = float(row["max_confidence"] or 0.25)
                        score = 0.5 + (confidence * 0.5)  # Map to 0.5-1.0 range

                        key = (row["video_id"], row["timestamp_ms"])
                        detection_results[key] = SearchResult(
                            video_id=row["video_id"],
                            timestamp_ms=row["timestamp_ms"],
                            score=score,
                            thumbnail_path=row["thumbnail_path"],
                            labels=labels,
                            match_type="visual",
                        )

                    logger.info(f"Found {len(detection_results)} detection results for '{detected_category}'")

                # Also run CLIP visual search (for semantic matching or to supplement detection)
                if not _FAISS_AVAILABLE:
                    logger.warning("FAISS not available, skipping CLIP visual search")
                else:
                    try:
                        # Encode text query as embedding
                        query_embedding = await embed_text(request.query)
                        query_embedding = query_embedding.astype(np.float32).reshape(1, -1)

                        # Normalize for cosine similarity (inner product)
                        faiss.normalize_L2(query_embedding)

                        # Get videos to search (optionally filtered by library)
                        video_query = "SELECT video_id FROM videos WHERE status = 'DONE'"
                        video_params: list = []
                        if request.library_id:
                            video_query += " AND library_id = ?"
                            video_params.append(request.library_id)

                        cursor = await db.execute(video_query, video_params)
                        video_rows = await cursor.fetchall()

                        # Search each video's FAISS shard
                        faiss_dir = get_faiss_dir()
                        k = min(20, request.limit)  # Top-k per video

                        for video_row in video_rows:
                            video_id = video_row["video_id"]
                            faiss_path = faiss_dir / f"{video_id}.faiss"

                            if not faiss_path.exists():
                                continue

                            try:
                                # Load FAISS index (cached)
                                index = _get_faiss_index(faiss_path)

                                # Search for similar frames
                                distances, indices = index.search(query_embedding, k)

                                # Batch fetch frame metadata for all matched indices
                                valid_indices = [int(idx) for idx in indices[0] if idx >= 0]
                                if not valid_indices:
                                    continue

                                # Single query for all frames (including colors)
                                placeholders = ",".join("?" * len(valid_indices))
                                frame_cursor = await db.execute(
                                    f"""
                                    SELECT frame_index, timestamp_ms, thumbnail_path, colors
                                    FROM frames
                                    WHERE video_id = ? AND frame_index IN ({placeholders})
                                    """,
                                    (video_id, *valid_indices),
                                )
                                frame_rows = await frame_cursor.fetchall()

                                # Create lookup map
                                frame_map = {row["frame_index"]: row for row in frame_rows}

                                # Build results from matched frames
                                for dist, idx in zip(distances[0], indices[0]):
                                    if idx < 0 or int(idx) not in frame_map:
                                        continue

                                    frame_row = frame_map[int(idx)]
                                    # Convert distance to similarity score (0-1)
                                    # Inner product for normalized vectors gives cosine similarity
                                    similarity = float(dist)

                                    # Apply similarity threshold to filter weak CLIP matches
                                    # For object queries, use stricter threshold since we have detection results
                                    threshold = VISUAL_SIMILARITY_THRESHOLD
                                    if detected_category:
                                        threshold = 0.22  # Stricter for object queries

                                    if similarity < threshold:
                                        continue

                                    # Check color match
                                    frame_colors = (frame_row["colors"] or "").split(",") if frame_row["colors"] else []
                                    color_match = query_color and query_color in frame_colors

                                    # Boost or penalize based on color
                                    if query_color:
                                        if color_match:
                                            similarity = min(1.0, similarity + 0.15)  # Boost for color match
                                        else:
                                            similarity *= 0.7  # Penalize if color was requested but doesn't match

                                    key = (video_id, frame_row["timestamp_ms"])

                                    # Check if this result also has a detection match
                                    if key in detection_results:
                                        # Boost: combine CLIP score with detection score
                                        det_result = detection_results[key]
                                        boosted_score = max(similarity, det_result.score) + 0.1
                                        if color_match:
                                            boosted_score += 0.1  # Extra boost for color + detection
                                        det_result.score = min(1.0, boosted_score)
                                        # Already in detection_results, will be added later
                                    else:
                                        # Pure CLIP result (no detection match)
                                        # For object queries, penalize results without detection
                                        if detected_category:
                                            similarity *= 0.6  # Reduce score for non-detection matches

                                        results.append(
                                            SearchResult(
                                                video_id=video_id,
                                                timestamp_ms=frame_row["timestamp_ms"],
                                                score=similarity,
                                                thumbnail_path=frame_row["thumbnail_path"],
                                                match_type="visual",
                                            )
                                        )
                            except Exception as e:
                                logger.warning(f"Failed to search FAISS shard for {video_id}: {e}")
                                continue

                    except Exception as e:
                        logger.error(f"Visual search failed: {e}")
                        # Continue with transcript results if visual search fails

                # Add detection results to the main results list
                # Detection results have priority (higher scores)
                for det_result in detection_results.values():
                    results.append(det_result)

            # Label filtering
            if request.labels:
                # Filter results to only include those with matching detections
                filtered_results = []
                for result in results:
                    cursor = await db.execute(
                        """
                        SELECT DISTINCT label
                        FROM detections
                        WHERE video_id = ?
                        AND timestamp_ms BETWEEN ? - 3000 AND ? + 3000
                        AND label IN ({})
                        """.format(
                            ",".join("?" * len(request.labels))
                        ),
                        (result.video_id, result.timestamp_ms, result.timestamp_ms, *request.labels),
                    )
                    matching_labels = [row["label"] for row in await cursor.fetchall()]

                    if matching_labels:
                        result.labels = matching_labels
                        # Boost score for matching labels
                        result.score += min(0.15, 0.05 * len(matching_labels))
                        filtered_results.append(result)

                results = filtered_results

            # Person filtering (face recognition)
            if request.person_ids:
                # Get all videos containing faces of the specified persons
                placeholders = ",".join("?" * len(request.person_ids))
                person_cursor = await db.execute(
                    f"""
                    SELECT DISTINCT f.video_id, f.timestamp_ms, f.person_id, p.name
                    FROM faces f
                    INNER JOIN persons p ON p.person_id = f.person_id
                    WHERE f.person_id IN ({placeholders})
                    ORDER BY f.video_id, f.timestamp_ms
                    """,
                    request.person_ids,
                )
                person_rows = await person_cursor.fetchall()

                # Build lookup of (video_id, timestamp_window) -> [(person_id, name)]
                video_person_map: dict[str, dict[int, list[tuple[str, str]]]] = {}
                for row in person_rows:
                    video_id = row["video_id"]
                    timestamp_ms = row["timestamp_ms"]
                    person_id = row["person_id"]
                    name = row["name"]

                    if video_id not in video_person_map:
                        video_person_map[video_id] = {}

                    # Round timestamp to 5-second windows for matching
                    window = (timestamp_ms // 5000) * 5000
                    if window not in video_person_map[video_id]:
                        video_person_map[video_id][window] = []
                    video_person_map[video_id][window].append((person_id, name))

                # If no query provided, return all moments with these persons
                if not request.query.strip():
                    # Generate results from person face timestamps
                    person_results: list[SearchResult] = []
                    for video_id, windows in video_person_map.items():
                        for window_ts, persons_in_window in windows.items():
                            # Get thumbnail for this timestamp
                            frame_cursor = await db.execute(
                                """
                                SELECT thumbnail_path FROM frames
                                WHERE video_id = ? AND timestamp_ms >= ? AND timestamp_ms < ?
                                ORDER BY timestamp_ms LIMIT 1
                                """,
                                (video_id, window_ts, window_ts + 5000),
                            )
                            frame_row = await frame_cursor.fetchone()

                            # Build person matches
                            person_counts: dict[str, tuple[str, int]] = {}
                            for pid, pname in persons_in_window:
                                if pid in person_counts:
                                    person_counts[pid] = (pname, person_counts[pid][1] + 1)
                                else:
                                    person_counts[pid] = (pname, 1)

                            person_matches = [
                                PersonMatch(person_id=pid, name=pname, face_count=count)
                                for pid, (pname, count) in person_counts.items()
                            ]

                            # Score based on how many requested persons appear
                            match_count = len(set(p[0] for p in persons_in_window) & set(request.person_ids))
                            score = match_count / len(request.person_ids)

                            person_results.append(
                                SearchResult(
                                    video_id=video_id,
                                    timestamp_ms=window_ts,
                                    score=score,
                                    thumbnail_path=frame_row["thumbnail_path"] if frame_row else None,
                                    persons=person_matches,
                                    match_type="visual",
                                )
                            )
                    results = person_results
                else:
                    # Filter existing results to only include videos with these persons
                    filtered_results = []
                    for result in results:
                        if result.video_id not in video_person_map:
                            continue

                        # Find persons near this timestamp (within 5 seconds)
                        window = (result.timestamp_ms // 5000) * 5000
                        nearby_windows = [window - 5000, window, window + 5000]

                        persons_found: dict[str, tuple[str, int]] = {}
                        for w in nearby_windows:
                            if w in video_person_map[result.video_id]:
                                for pid, pname in video_person_map[result.video_id][w]:
                                    if pid in request.person_ids:
                                        if pid in persons_found:
                                            persons_found[pid] = (pname, persons_found[pid][1] + 1)
                                        else:
                                            persons_found[pid] = (pname, 1)

                        if persons_found:
                            result.persons = [
                                PersonMatch(person_id=pid, name=pname, face_count=count)
                                for pid, (pname, count) in persons_found.items()
                            ]
                            # Boost score for person matches
                            result.score += min(0.2, 0.1 * len(persons_found))
                            filtered_results.append(result)

                    results = filtered_results

            # Merge results from same video/timestamp when mode is "both"
            if request.mode == "both":
                # Group by (video_id, timestamp_ms)
                merged_results: dict[tuple[str, int], SearchResult] = {}

                for result in results:
                    key = (result.video_id, result.timestamp_ms)
                    if key in merged_results:
                        # Merge: combine match types, take best score, combine snippets
                        existing = merged_results[key]
                        existing.match_type = "both"
                        existing.score = max(existing.score, result.score)
                        if result.transcript_snippet and not existing.transcript_snippet:
                            existing.transcript_snippet = result.transcript_snippet
                        if result.thumbnail_path and not existing.thumbnail_path:
                            existing.thumbnail_path = result.thumbnail_path
                    else:
                        merged_results[key] = result

                results = list(merged_results.values())

            # Enrich results with face/person info (if not already filtered by person)
            if not request.person_ids and results:
                # Get all faces with person assignments for the videos in results
                result_video_ids = list(set(r.video_id for r in results))
                if result_video_ids:
                    placeholders = ",".join("?" * len(result_video_ids))
                    face_cursor = await db.execute(
                        f"""
                        SELECT f.video_id, f.timestamp_ms, f.person_id, p.name
                        FROM faces f
                        INNER JOIN persons p ON p.person_id = f.person_id
                        WHERE f.video_id IN ({placeholders})
                        ORDER BY f.video_id, f.timestamp_ms
                        """,
                        result_video_ids,
                    )
                    face_rows = await face_cursor.fetchall()

                    # Build lookup: video_id -> timestamp_window -> [(person_id, name)]
                    video_faces_map: dict[str, dict[int, list[tuple[str, str]]]] = {}
                    for row in face_rows:
                        vid = row["video_id"]
                        ts = row["timestamp_ms"]
                        pid = row["person_id"]
                        pname = row["name"]

                        if vid not in video_faces_map:
                            video_faces_map[vid] = {}

                        window = (ts // 5000) * 5000
                        if window not in video_faces_map[vid]:
                            video_faces_map[vid][window] = []
                        video_faces_map[vid][window].append((pid, pname))

                    # Enrich each result
                    for result in results:
                        if result.video_id in video_faces_map:
                            window = (result.timestamp_ms // 5000) * 5000
                            nearby_windows = [window - 5000, window, window + 5000]

                            persons_found: dict[str, tuple[str, int]] = {}
                            for w in nearby_windows:
                                if w in video_faces_map[result.video_id]:
                                    for pid, pname in video_faces_map[result.video_id][w]:
                                        if pid in persons_found:
                                            persons_found[pid] = (pname, persons_found[pid][1] + 1)
                                        else:
                                            persons_found[pid] = (pname, 1)

                            if persons_found:
                                result.persons = [
                                    PersonMatch(person_id=pid, name=pname, face_count=count)
                                    for pid, (pname, count) in persons_found.items()
                                ]

            # Sort by score and apply pagination
            results.sort(key=lambda r: r.score, reverse=True)
            total = len(results)
            results = results[request.offset : request.offset + request.limit]

    query_time_ms = int((time.time() - start_time) * 1000)

    return SearchResponse(
        results=results,
        total=total,
        query_time_ms=query_time_ms,
    )


@router.get("/export/captions/{video_id}")
async def export_captions(
    video_id: str,
    format: Literal["srt", "vtt"] = Query("srt"),
    _token: str = Depends(verify_token),
) -> str:
    """Export captions as SRT or VTT."""
    async for db in get_db():
        cursor = await db.execute(
            """
            SELECT start_ms, end_ms, text
            FROM transcript_segments
            WHERE video_id = ?
            ORDER BY start_ms
            """,
            (video_id,),
        )
        rows = await cursor.fetchall()

        if not rows:
            return ""

        if format == "vtt":
            lines = ["WEBVTT", ""]
            for i, row in enumerate(rows, 1):
                start = format_timestamp_vtt(row["start_ms"])
                end = format_timestamp_vtt(row["end_ms"])
                lines.extend([f"{start} --> {end}", row["text"], ""])
        else:
            lines = []
            for i, row in enumerate(rows, 1):
                start = format_timestamp_srt(row["start_ms"])
                end = format_timestamp_srt(row["end_ms"])
                lines.extend([str(i), f"{start} --> {end}", row["text"], ""])

        return "\n".join(lines)


def format_timestamp_srt(ms: int) -> str:
    """Format milliseconds as SRT timestamp (HH:MM:SS,mmm)."""
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def format_timestamp_vtt(ms: int) -> str:
    """Format milliseconds as VTT timestamp (HH:MM:SS.mmm)."""
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
