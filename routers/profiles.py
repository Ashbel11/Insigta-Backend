from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc
from typing import Optional
import csv
import io

from database import get_db
from models import Profile
from schemas import ProfileOut
from services.nlp_parser import parse_nlp_query
from dependencies.auth import get_current_user, require_admin
from models import User
from utils import generate_uuid7
from datetime import datetime, timezone

router = APIRouter()

VALID_SORT_FIELDS = {"age", "created_at", "gender_probability"}
VALID_ORDERS = {"asc", "desc"}
VALID_GENDERS = {"male", "female"}
VALID_AGE_GROUPS = {"child", "teenager", "adult", "senior"}


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message},
    )


def apply_filters(query, filters: dict):
    if filters.get("gender"):
        query = query.filter(Profile.gender == filters["gender"])
    if filters.get("age_group"):
        query = query.filter(Profile.age_group == filters["age_group"])
    if filters.get("country_id"):
        query = query.filter(Profile.country_id == filters["country_id"].upper())
    if filters.get("min_age") is not None:
        query = query.filter(Profile.age >= filters["min_age"])
    if filters.get("max_age") is not None:
        query = query.filter(Profile.age <= filters["max_age"])
    if filters.get("min_gender_probability") is not None:
        query = query.filter(Profile.gender_probability >= filters["min_gender_probability"])
    if filters.get("min_country_probability") is not None:
        query = query.filter(Profile.country_probability >= filters["min_country_probability"])
    return query


def paginate_and_sort(query, sort_by: str, order: str, page: int, limit: int):
    total = query.count()
    sort_column = getattr(Profile, sort_by)
    query = query.order_by(desc(sort_column) if order == "desc" else asc(sort_column))
    items = query.offset((page - 1) * limit).limit(limit).all()
    return items, total


def build_list_response(items, total: int, page: int, limit: int, base_url: str = "") -> dict:
    import math
    total_pages = math.ceil(total / limit) if limit else 1

    links = {
        "first": f"{base_url}?page=1&limit={limit}",
        "last": f"{base_url}?page={total_pages}&limit={limit}",
        "prev": f"{base_url}?page={page - 1}&limit={limit}" if page > 1 else None,
        "next": f"{base_url}?page={page + 1}&limit={limit}" if page < total_pages else None,
    }

    return {
        "status": "success",
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "links": links,
        "data": [ProfileOut.model_validate(p).model_dump() for p in items],
    }


# ── GET /api/profiles ─────────────────────────────────────────────────────────
@router.get("/profiles")
def get_profiles(
    gender: Optional[str] = Query(None),
    age_group: Optional[str] = Query(None),
    country_id: Optional[str] = Query(None),
    min_age: Optional[int] = Query(None, ge=0),
    max_age: Optional[int] = Query(None, ge=0),
    min_gender_probability: Optional[float] = Query(None, ge=0.0, le=1.0),
    min_country_probability: Optional[float] = Query(None, ge=0.0, le=1.0),
    sort_by: str = Query("created_at"),
    order: str = Query("asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # ← AUTH REQUIRED
):
    if sort_by not in VALID_SORT_FIELDS:
        return error_response(400, "Invalid query parameters")
    if order not in VALID_ORDERS:
        return error_response(400, "Invalid query parameters")
    if gender and gender.lower() not in VALID_GENDERS:
        return error_response(400, "Invalid query parameters")
    if age_group and age_group.lower() not in VALID_AGE_GROUPS:
        return error_response(400, "Invalid query parameters")

    filters = {
        "gender": gender.lower() if gender else None,
        "age_group": age_group.lower() if age_group else None,
        "country_id": country_id,
        "min_age": min_age,
        "max_age": max_age,
        "min_gender_probability": min_gender_probability,
        "min_country_probability": min_country_probability,
    }

    query = db.query(Profile)
    query = apply_filters(query, filters)
    items, total = paginate_and_sort(query, sort_by, order, page, limit)

    return JSONResponse(
        status_code=200,
        content=build_list_response(items, total, page, limit, "/api/profiles"),
    )


# ── GET /api/profiles/export ──────────────────────────────────────────────────
@router.get("/profiles/export")
def export_profiles(
    format: str = Query("csv"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # ← AUTH REQUIRED
):
    if format != "csv":
        return error_response(400, "Only format=csv is supported")

    profiles = db.query(Profile).order_by(asc(Profile.created_at)).all()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "name", "gender", "gender_probability",
        "age", "age_group", "country_id", "country_name",
        "country_probability", "created_at",
    ])
    writer.writeheader()
    for p in profiles:
        writer.writerow({
            "id": str(p.id),
            "name": p.name,
            "gender": p.gender,
            "gender_probability": p.gender_probability,
            "age": p.age,
            "age_group": p.age_group,
            "country_id": p.country_id,
            "country_name": p.country_name,
            "country_probability": p.country_probability,
            "created_at": p.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=profiles.csv"},
    )


# ── GET /api/profiles/search ──────────────────────────────────────────────────
@router.get("/profiles/search")
def search_profiles(
    q: str = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    sort_by: str = Query("created_at"),
    order: str = Query("asc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # ← AUTH REQUIRED
):
    if not q or not q.strip():
        return error_response(400, "Missing or empty query parameter")
    if sort_by not in VALID_SORT_FIELDS:
        return error_response(400, "Invalid query parameters")
    if order not in VALID_ORDERS:
        return error_response(400, "Invalid query parameters")

    filters = parse_nlp_query(q)
    if filters is None:
        return JSONResponse(
            status_code=422,
            content={"status": "error", "message": "Unable to interpret query"},
        )

    query = db.query(Profile)
    query = apply_filters(query, filters)
    items, total = paginate_and_sort(query, sort_by, order, page, limit)

    return JSONResponse(
        status_code=200,
        content=build_list_response(items, total, page, limit, "/api/profiles/search"),
    )


# ── GET /api/profiles/{id} ────────────────────────────────────────────────────
@router.get("/profiles/{profile_id}")
def get_profile_by_id(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # ← AUTH REQUIRED
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return error_response(404, "Profile not found")

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "data": ProfileOut.model_validate(profile).model_dump(),
        },
    )


# ── POST /api/profiles ────────────────────────────────────────────────────────
@router.post("/profiles")
def create_profile(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # ← ADMIN ONLY
):
    required_fields = ["name", "gender", "gender_probability", "age",
                       "age_group", "country_id", "country_name", "country_probability"]

    for field in required_fields:
        if field not in payload:
            return error_response(400, f"Missing required field: {field}")

    if payload["gender"].lower() not in VALID_GENDERS:
        return error_response(400, "Invalid gender value")
    if payload["age_group"].lower() not in VALID_AGE_GROUPS:
        return error_response(400, "Invalid age_group value")

    existing = db.query(Profile).filter(Profile.name == payload["name"]).first()
    if existing:
        return error_response(409, "A profile with this name already exists")

    profile = Profile(
        id=generate_uuid7(),
        name=payload["name"],
        gender=payload["gender"].lower(),
        gender_probability=float(payload["gender_probability"]),
        age=int(payload["age"]),
        age_group=payload["age_group"].lower(),
        country_id=payload["country_id"].upper(),
        country_name=payload["country_name"],
        country_probability=float(payload["country_probability"]),
        created_at=datetime.now(timezone.utc),
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return JSONResponse(
        status_code=201,
        content={
            "status": "success",
            "data": ProfileOut.model_validate(profile).model_dump(),
        },
    )