from pydantic import BaseModel, ConfigDict, field_serializer
from datetime import datetime, timezone
from uuid import UUID
from typing import List


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    gender: str
    gender_probability: float
    age: int
    age_group: str
    country_id: str
    country_name: str
    country_probability: float
    created_at: datetime

    @field_serializer("id")
    def serialize_id(self, v: UUID) -> str:
        return str(v)

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProfileListResponse(BaseModel):
    status: str = "success"
    page: int
    limit: int
    total: int
    data: List[ProfileOut]
