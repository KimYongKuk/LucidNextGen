# -*- coding: utf-8 -*-
"""
Anonymous feedback API routes
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.feedback_service import FeedbackService, get_feedback_service
from app.api.dependencies.auth_jwt import get_current_user
from app.api.dependencies.authz import get_current_admin

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================

class FeedbackCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class FeedbackResponse(BaseModel):
    feedback_id: str
    message: str
    created_at: Optional[str] = None


class FeedbackListResponse(BaseModel):
    feedbacks: list[FeedbackResponse]
    has_more: bool
    next_cursor: Optional[str] = None


class FeedbackSinceResponse(BaseModel):
    feedbacks: list[FeedbackResponse]
    latest_timestamp: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/v1/feedback", response_model=FeedbackResponse)
async def create_feedback(
    request: FeedbackCreate,
    current_user: dict = Depends(get_current_user),
    service: FeedbackService = Depends(get_feedback_service)
):
    """Create a new feedback (인증된 사번 자동 저장, 응답에는 노출 안 함)"""
    try:
        result = service.create_feedback(message=request.message, user_id=current_user["empno"])
        return FeedbackResponse(**result)
    except Exception as e:
        logger.error(f"Failed to create feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to create feedback")


@router.get("/v1/feedback", response_model=FeedbackListResponse)
async def list_feedbacks(
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="ISO datetime cursor for pagination"),
    _admin: dict = Depends(get_current_admin),
    service: FeedbackService = Depends(get_feedback_service)
):
    """List feedbacks (운영자 전용, cursor-based pagination, newest first)"""
    try:
        result = service.list_feedbacks(limit=limit, cursor=cursor)
        return FeedbackListResponse(
            feedbacks=[FeedbackResponse(**f) for f in result["feedbacks"]],
            has_more=result["has_more"],
            next_cursor=result["next_cursor"]
        )
    except Exception as e:
        logger.error(f"Failed to list feedbacks: {e}")
        raise HTTPException(status_code=500, detail="Failed to list feedbacks")


@router.get("/v1/feedback/since/{timestamp}", response_model=FeedbackSinceResponse)
async def get_feedbacks_since(
    timestamp: str,
    _admin: dict = Depends(get_current_admin),
    service: FeedbackService = Depends(get_feedback_service)
):
    """Get feedbacks created after the given timestamp (운영자 전용, polling)"""
    try:
        result = service.get_feedbacks_since(timestamp=timestamp)
        return FeedbackSinceResponse(
            feedbacks=[FeedbackResponse(**f) for f in result["feedbacks"]],
            latest_timestamp=result["latest_timestamp"]
        )
    except Exception as e:
        logger.error(f"Failed to get feedbacks since {timestamp}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feedbacks")
