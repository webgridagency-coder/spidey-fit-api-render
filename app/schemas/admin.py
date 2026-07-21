"""Validated payloads for privileged Ojas administration actions."""

from typing import Literal

from pydantic import BaseModel, Field


class AdminPlanUpdate(BaseModel):
    plan: Literal["base", "flow", "orbit"]
    reason: str = Field(..., min_length=3, max_length=240)


class AdminStatusUpdate(BaseModel):
    is_active: bool
    reason: str = Field(..., min_length=3, max_length=240)


class AdminQuotaReset(BaseModel):
    reason: str = Field(..., min_length=3, max_length=240)
