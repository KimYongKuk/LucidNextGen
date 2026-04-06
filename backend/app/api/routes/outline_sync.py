# -*- coding: utf-8 -*-
"""Outline Wiki 동기화 API 엔드포인트

수동 동기화 트리거 및 상태 조회용.
"""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/outline-sync", tags=["outline-sync"])


@router.post("/trigger")
async def trigger_sync(background_tasks: BackgroundTasks):
    """전체 동기화를 백그라운드로 트리거

    서버 응답은 즉시 반환되고, 동기화는 백그라운드에서 실행됩니다.
    """
    try:
        from app.services.outline_sync_service import get_outline_sync_service
        service = get_outline_sync_service()

        status = service.get_sync_status()
        if status.get("running"):
            return {"message": "동기화가 이미 실행 중입니다.", "status": status}

        background_tasks.add_task(service.full_sync)
        return {"message": "동기화가 시작되었습니다. /status에서 진행 상황을 확인하세요."}
    except Exception as e:
        logger.error(f"[OutlineSync] trigger 실패: {e}")
        return {"error": str(e)}


@router.get("/status")
async def get_sync_status():
    """현재 동기화 상태 조회"""
    try:
        from app.services.outline_sync_service import get_outline_sync_service
        service = get_outline_sync_service()
        return service.get_sync_status()
    except Exception as e:
        logger.error(f"[OutlineSync] status 조회 실패: {e}")
        return {"error": str(e), "running": False}


@router.post("/run")
async def run_sync_now():
    """동기화를 즉시 실행하고 결과를 반환 (동기 방식, 시간 소요 가능)"""
    try:
        from app.services.outline_sync_service import get_outline_sync_service
        service = get_outline_sync_service()
        result = await service.full_sync()
        return result
    except Exception as e:
        logger.error(f"[OutlineSync] run 실패: {e}")
        return {"error": str(e)}
