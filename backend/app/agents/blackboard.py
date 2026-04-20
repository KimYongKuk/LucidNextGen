"""Blackboard — Planner-Executor 아키텍처의 Task 결과 공유 저장소

각 Task의 실행 결과를 in-memory로 저장하고, 후속 Task(및 Synthesizer)가 참조.
요청 생명주기 동안만 유효 (세션 간 격리).

설계 원칙:
- 단일 요청 처리 시 1개의 Blackboard 인스턴스가 Executor/Synthesizer에 공유됨
- asyncio.Lock으로 동시 쓰기 보호 (병렬 task 완료 순서 race 방지)
- 구조화 메타데이터는 별도 dict에 (result 텍스트와 분리)
"""

import asyncio
from typing import Dict, Any, Optional, List


class Blackboard:
    """Task 결과 공유 저장소 (요청 생명주기)"""

    def __init__(self):
        self._results: Dict[str, str] = {}       # task_id → result text
        self._metadata: Dict[str, Dict[str, Any]] = {}  # task_id → 구조화 데이터
        self._lock = asyncio.Lock()

    async def put(
        self,
        task_id: str,
        result: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Task 실행 결과 저장

        Args:
            task_id: Task의 고유 id
            result: 워커 출력 텍스트 (사용자 응답 조각 또는 데이터 스냅샷)
            metadata: 구조화 부가 정보 (예: {"source_ids": [...], "tool_calls": N})
        """
        async with self._lock:
            self._results[task_id] = result
            if metadata:
                self._metadata[task_id] = metadata

    async def get(self, task_id: str) -> Optional[str]:
        """Task 결과 조회. 없으면 None."""
        async with self._lock:
            return self._results.get(task_id)

    async def get_metadata(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Task 메타데이터 조회"""
        async with self._lock:
            return self._metadata.get(task_id)

    async def get_many(self, task_ids: List[str]) -> Dict[str, str]:
        """여러 task 결과를 dict로 반환 (없는 id는 제외)"""
        async with self._lock:
            return {tid: self._results[tid]
                    for tid in task_ids
                    if tid in self._results}

    async def get_all(self) -> Dict[str, str]:
        """모든 결과 스냅샷 (Synthesizer 용)"""
        async with self._lock:
            return dict(self._results)

    async def has(self, task_id: str) -> bool:
        """해당 task_id에 결과가 저장되어 있는지"""
        async with self._lock:
            return task_id in self._results

    def size(self) -> int:
        """저장된 task 수 (lock 없이 스냅샷, 디버그/로그용)"""
        return len(self._results)

    def __repr__(self) -> str:
        return f"Blackboard(tasks={list(self._results.keys())})"
