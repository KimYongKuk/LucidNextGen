# -*- coding: utf-8 -*-
"""IT VOC → L&F Wiki 자동 축적 관리 API"""
from fastapi import APIRouter, Query

from app.utils.voc_wiki_scheduler import voc_wiki_scheduler

router = APIRouter(prefix="/v1/admin/voc-wiki", tags=["voc-wiki"])


@router.post("/sync")
async def voc_wiki_sync(
    since: str = Query(None, description="Start date YYYY-MM-DD (None=auto)"),
):
    """수동 1회 동기화 실행"""
    return await voc_wiki_scheduler.run_now(target_date=since)


@router.post("/initial-load")
async def voc_wiki_initial_load(
    months: int = Query(1, description="적재할 개월 수"),
):
    """초기 적재 실행 (1주 단위 순차 처리)"""
    return await voc_wiki_scheduler.run_initial_load(months=months)