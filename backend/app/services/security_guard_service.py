# -*- coding: utf-8 -*-
"""
Security Guard Service (2026-04-20)

악의적인 사용자 입력을 탐지하고, 누적 위반 시 차단하는 보안 서비스.

3-Layer 검사:
1. Rule-based: 정규식/키워드 (모든 요청)
2. Rate-limit: 시간당 호출 빈도 (메모리, sliding window)
3. LLM-based: Haiku 기반 문맥 판정 (의심 시만, 일일 한도 있음)

5-Tier 대응:
- PASS (0-29)
- WARN (30-49): 로그만 기록, 요청은 정상 처리
- BLOCK_REQUEST (50-69): 해당 요청만 거부
- TEMP_BLOCK (70-84): 24시간 차단
- PERM_BLOCK (85-100): 영구 차단 (관리자 해제 필요)

누적 승격:
- WARN 5회(24h) → TEMP_BLOCK
- TEMP_BLOCK 3회(30d) → PERM_BLOCK
"""
import os
import re
import json
import time
import logging
import asyncio
from collections import deque, defaultdict
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Tuple, Any

from app.core.database import get_database_connection

logger = logging.getLogger(__name__)


# ============================================================
# 환경변수
# ============================================================
SECURITY_GUARD_ENABLED = os.getenv("SECURITY_GUARD_ENABLED", "true").lower() == "true"

# 임계값
SECURITY_LLM_THRESHOLD = int(os.getenv("SECURITY_LLM_THRESHOLD", "30"))
SECURITY_WARN_THRESHOLD = int(os.getenv("SECURITY_WARN_THRESHOLD", "30"))
SECURITY_BLOCK_REQUEST_THRESHOLD = int(os.getenv("SECURITY_BLOCK_REQUEST_THRESHOLD", "50"))
SECURITY_TEMP_BLOCK_THRESHOLD = int(os.getenv("SECURITY_TEMP_BLOCK_THRESHOLD", "70"))
SECURITY_PERM_BLOCK_THRESHOLD = int(os.getenv("SECURITY_PERM_BLOCK_THRESHOLD", "85"))

# 누적 규칙
SECURITY_WARN_LIMIT = int(os.getenv("SECURITY_WARN_LIMIT", "5"))
SECURITY_TEMP_BLOCK_LIMIT = int(os.getenv("SECURITY_TEMP_BLOCK_LIMIT", "3"))
SECURITY_TEMP_BLOCK_HOURS = int(os.getenv("SECURITY_TEMP_BLOCK_HOURS", "24"))

# Rate limit
SECURITY_RATE_WARN_PER_MIN = int(os.getenv("SECURITY_RATE_WARN_PER_MIN", "20"))
SECURITY_RATE_BLOCK_PER_MIN = int(os.getenv("SECURITY_RATE_BLOCK_PER_MIN", "40"))
SECURITY_RATE_DUPLICATE_LIMIT = int(os.getenv("SECURITY_RATE_DUPLICATE_LIMIT", "5"))

# 화이트리스트
_whitelist_env = os.getenv("SECURITY_WHITELIST_USER_IDS", "").strip()
SECURITY_WHITELIST = set(u.strip() for u in _whitelist_env.split(",") if u.strip())

# 차단 상태 캐시 TTL
BLOCK_CACHE_TTL_SEC = 60


# ============================================================
# Enum
# ============================================================
class ThreatType(str, Enum):
    INJECTION = "INJECTION"
    JAILBREAK = "JAILBREAK"
    DATA_EXFIL = "DATA_EXFIL"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    ABUSE = "ABUSE"
    MALICIOUS_CONTENT = "MALICIOUS_CONTENT"
    OTHER = "OTHER"


class ActionTaken(str, Enum):
    LOGGED = "LOGGED"
    WARNED = "WARNED"
    BLOCKED_REQUEST = "BLOCKED_REQUEST"
    TEMP_BLOCKED = "TEMP_BLOCKED"
    PERM_BLOCKED = "PERM_BLOCKED"


class DetectionLayer(str, Enum):
    RULE = "RULE"
    RATE = "RATE"
    LLM = "LLM"
    COMBINED = "COMBINED"


# ============================================================
# Rule 패턴
# ============================================================
# 한국어/영어 혼합 위협 패턴 — (패턴, 위협 타입, 가중치)
RULE_PATTERNS: List[Tuple[re.Pattern, ThreatType, int]] = [
    # INJECTION
    (re.compile(r"이전\s*(지시|명령|프롬프트|규칙)\s*(을|를)?\s*(무시|잊|버려|잊어)", re.IGNORECASE), ThreatType.INJECTION, 60),
    (re.compile(r"(모든|위의|기존).*(지시|instruction|rule|prompt).*?(무시|ignore|forget)", re.IGNORECASE), ThreatType.INJECTION, 60),
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)", re.IGNORECASE), ThreatType.INJECTION, 70),
    (re.compile(r"(시스템|system)\s*(프롬프트|prompt|instruction).*(보여|출력|알려|공개|print|show|reveal|display)", re.IGNORECASE), ThreatType.INJECTION, 65),
    (re.compile(r"(reveal|print|show|display)\s+(your|the)\s+(system\s+)?(prompt|instruction)", re.IGNORECASE), ThreatType.INJECTION, 65),
    (re.compile(r"원본\s*(프롬프트|지시문)", re.IGNORECASE), ThreatType.INJECTION, 55),

    # JAILBREAK
    (re.compile(r"\bDAN\s*(모드|mode)?\b", re.IGNORECASE), ThreatType.JAILBREAK, 70),
    (re.compile(r"developer\s*mode", re.IGNORECASE), ThreatType.JAILBREAK, 60),
    (re.compile(r"개발자\s*모드", re.IGNORECASE), ThreatType.JAILBREAK, 55),
    (re.compile(r"(검열|제약|제한|필터)\s*(없이|해제|풀어|우회)", re.IGNORECASE), ThreatType.JAILBREAK, 60),
    (re.compile(r"jailbreak", re.IGNORECASE), ThreatType.JAILBREAK, 75),
    (re.compile(r"(unrestricted|uncensored|no\s+filter)", re.IGNORECASE), ThreatType.JAILBREAK, 60),
    (re.compile(r"pretend\s+(you\s+are|to\s+be)\s+(not\s+bound|unrestricted)", re.IGNORECASE), ThreatType.JAILBREAK, 65),

    # PRIVILEGE_ESCALATION
    (re.compile(r"(다른|타인|남의|other)\s*(사람|직원|사용자|user).*?(메일|mail|결재|approval|기안)", re.IGNORECASE), ThreatType.PRIVILEGE_ESCALATION, 70),
    (re.compile(r"관리자\s*권한\s*으로", re.IGNORECASE), ThreatType.PRIVILEGE_ESCALATION, 55),
    (re.compile(r"(다른|타)\s*사번\s*으로", re.IGNORECASE), ThreatType.PRIVILEGE_ESCALATION, 75),
    (re.compile(r"(as|pretend).*(admin|administrator|root|superuser)", re.IGNORECASE), ThreatType.PRIVILEGE_ESCALATION, 60),

    # DATA_EXFIL
    (re.compile(r"(전체|모든|all)\s*(직원|사용자|user|employee).*?(메일|정보|데이터|주소|email)", re.IGNORECASE), ThreatType.DATA_EXFIL, 60),
    (re.compile(r"(덤프|dump|추출).*?(전체|모두|all|everything)", re.IGNORECASE), ThreatType.DATA_EXFIL, 55),
    (re.compile(r"SELECT\s+\*\s+FROM", re.IGNORECASE), ThreatType.DATA_EXFIL, 50),
    (re.compile(r"DROP\s+(TABLE|DATABASE)", re.IGNORECASE), ThreatType.DATA_EXFIL, 85),
    (re.compile(r"TRUNCATE\s+TABLE", re.IGNORECASE), ThreatType.DATA_EXFIL, 80),
    (re.compile(r"UNION\s+SELECT", re.IGNORECASE), ThreatType.DATA_EXFIL, 75),

    # MALICIOUS_CONTENT
    (re.compile(r"(피싱|phishing)\s*(메일|mail|email)", re.IGNORECASE), ThreatType.MALICIOUS_CONTENT, 65),
    (re.compile(r"(악성코드|malware|ransomware|랜섬웨어)\s*(작성|만들|생성|create|write)", re.IGNORECASE), ThreatType.MALICIOUS_CONTENT, 75),
    (re.compile(r"(해킹|hacking).*?(도구|tool|스크립트|script)", re.IGNORECASE), ThreatType.MALICIOUS_CONTENT, 60),
    (re.compile(r"(keylogger|키로거)", re.IGNORECASE), ThreatType.MALICIOUS_CONTENT, 70),
]


# ============================================================
# 데이터 클래스
# ============================================================
@dataclass
class RuleCheckResult:
    suspicion_score: int = 0
    threat_type: Optional[ThreatType] = None
    matched_patterns: List[str] = field(default_factory=list)


@dataclass
class SecurityCheckResult:
    allowed: bool
    action: ActionTaken
    severity: int
    threat_type: Optional[ThreatType] = None
    user_message: Optional[str] = None
    reason: Optional[str] = None
    event_id: Optional[int] = None
    expires_at: Optional[datetime] = None


@dataclass
class BlockStatus:
    blocked: bool
    block_type: Optional[str] = None  # 'TEMPORARY' | 'PERMANENT'
    reason: Optional[str] = None
    threat_type: Optional[str] = None
    blocked_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


# ============================================================
# Rate Limiter (in-memory)
# ============================================================
class _RateLimiter:
    """사용자별 sliding window rate limiter (프로세스 메모리)."""

    def __init__(self):
        self._windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self._last_messages: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        self._lock = asyncio.Lock()

    async def record_and_check(self, user_id: str, message: str) -> Tuple[int, int]:
        """
        요청 기록 + 분당 횟수 및 동일 메시지 연속 횟수 반환.

        Returns:
            (per_minute_count, duplicate_count)
        """
        async with self._lock:
            now = time.time()
            window = self._windows[user_id]
            window.append(now)

            # 1분 이전 항목 제거
            while window and now - window[0] > 60:
                window.popleft()

            per_minute = len(window)

            # 중복 메시지 체크 (최근 10개 중)
            last_msgs = self._last_messages[user_id]
            last_msgs.append(message.strip())
            duplicate = sum(1 for m in last_msgs if m == message.strip())

            return per_minute, duplicate


# ============================================================
# Security Guard Service
# ============================================================
class SecurityGuardService:
    def __init__(self):
        self.db = get_database_connection()
        self._rate_limiter = _RateLimiter()
        self._block_cache: Dict[str, Tuple[BlockStatus, float]] = {}  # user_id -> (status, cached_at)
        self._cache_lock = asyncio.Lock()

    # ────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────
    async def check_request(
        self,
        user_id: str,
        session_id: Optional[str],
        message: str,
        workspace_id: Optional[str] = None,
    ) -> SecurityCheckResult:
        """
        전체 보안 검사 파이프라인.
        """
        # 0. On/Off 및 화이트리스트
        if not SECURITY_GUARD_ENABLED:
            return SecurityCheckResult(allowed=True, action=ActionTaken.LOGGED, severity=0)
        if user_id in SECURITY_WHITELIST or user_id == "anonymous":
            return SecurityCheckResult(allowed=True, action=ActionTaken.LOGGED, severity=0)

        # 1. 기존 차단 상태 확인
        block_status = await self.get_block_status(user_id)
        if block_status.blocked:
            return SecurityCheckResult(
                allowed=False,
                action=ActionTaken.PERM_BLOCKED if block_status.block_type == "PERMANENT" else ActionTaken.TEMP_BLOCKED,
                severity=100,
                threat_type=ThreatType(block_status.threat_type) if block_status.threat_type else None,
                user_message=self._build_blocked_message(block_status),
                reason=block_status.reason,
                expires_at=block_status.expires_at,
            )

        # 2. Rule-based 검사
        rule_result = self._rule_check(message)

        # 3. Rate-limit 검사
        per_min, duplicate = await self._rate_limiter.record_and_check(user_id, message)
        rate_severity = 0
        rate_reason = None
        if per_min >= SECURITY_RATE_BLOCK_PER_MIN:
            rate_severity = 75
            rate_reason = f"분당 {per_min}회 호출 (한도: {SECURITY_RATE_BLOCK_PER_MIN})"
        elif duplicate >= SECURITY_RATE_DUPLICATE_LIMIT:
            rate_severity = 75
            rate_reason = f"동일 메시지 {duplicate}회 반복"
        elif per_min >= SECURITY_RATE_WARN_PER_MIN:
            rate_severity = 35
            rate_reason = f"분당 {per_min}회 호출 (경고 한도 초과)"

        # 4. LLM 검사 (rule 의심 시만 + 일일 한도 내)
        llm_severity = 0
        llm_threat = None
        llm_reason = None
        llm_raw = None
        if rule_result.suspicion_score >= SECURITY_LLM_THRESHOLD:
            try:
                from app.agents.security_guard_agent import get_security_guard_agent
                agent = get_security_guard_agent()
                if agent.can_call_today():
                    llm_result = await agent.classify(message)
                    if llm_result:
                        llm_severity = llm_result.get("severity", 0)
                        t = llm_result.get("threat_type")
                        if t and t != "NONE":
                            try:
                                llm_threat = ThreatType(t)
                            except ValueError:
                                llm_threat = ThreatType.OTHER
                        llm_reason = llm_result.get("reason")
                        llm_raw = json.dumps(llm_result, ensure_ascii=False)
            except Exception as e:
                logger.error(f"[SecurityGuard] LLM check failed: {e}")

        # 5. 결합 점수 (max 기준)
        scores = [
            (rule_result.suspicion_score, rule_result.threat_type, "rule"),
            (rate_severity, ThreatType.ABUSE if rate_severity else None, "rate"),
            (llm_severity, llm_threat, "llm"),
        ]
        scores.sort(key=lambda x: x[0], reverse=True)
        final_severity, final_threat, primary_layer = scores[0]

        if final_severity == 0:
            return SecurityCheckResult(allowed=True, action=ActionTaken.LOGGED, severity=0)

        # 6. 대응 결정
        if final_severity >= SECURITY_PERM_BLOCK_THRESHOLD:
            action = ActionTaken.PERM_BLOCKED
        elif final_severity >= SECURITY_TEMP_BLOCK_THRESHOLD:
            action = ActionTaken.TEMP_BLOCKED
        elif final_severity >= SECURITY_BLOCK_REQUEST_THRESHOLD:
            action = ActionTaken.BLOCKED_REQUEST
        elif final_severity >= SECURITY_WARN_THRESHOLD:
            action = ActionTaken.WARNED
        else:
            action = ActionTaken.LOGGED

        # 7. 이벤트 로그 기록
        layer = DetectionLayer.COMBINED if sum(1 for s, _, _ in scores if s > 0) > 1 else (
            DetectionLayer.LLM if primary_layer == "llm" else
            DetectionLayer.RATE if primary_layer == "rate" else
            DetectionLayer.RULE
        )
        reason_parts = [r for r in [
            f"rule: {rule_result.matched_patterns}" if rule_result.matched_patterns else None,
            f"rate: {rate_reason}" if rate_reason else None,
            f"llm: {llm_reason}" if llm_reason else None,
        ] if r]
        combined_reason = " | ".join(reason_parts) or "Detected"

        event_id = self._log_event(
            user_id=user_id,
            session_id=session_id,
            workspace_id=workspace_id,
            threat_type=final_threat or ThreatType.OTHER,
            severity=final_severity,
            action=action,
            layer=layer,
            message=message,
            reason=combined_reason,
            matched_patterns=rule_result.matched_patterns,
            llm_raw=llm_raw,
        )

        # 8. 누적 승격 체크 (WARN이면 Temp로 승격될 수 있음)
        promoted_action, expires_at = await self._check_escalation(user_id, action, event_id, final_threat, combined_reason)

        # 9. 차단 테이블 반영
        if promoted_action in (ActionTaken.TEMP_BLOCKED, ActionTaken.PERM_BLOCKED):
            self._apply_block(
                user_id=user_id,
                action=promoted_action,
                reason=combined_reason,
                threat_type=final_threat,
                event_id=event_id,
                expires_at=expires_at,
            )
            # 캐시 무효화
            async with self._cache_lock:
                self._block_cache.pop(user_id, None)

            # 노티 발송 (비동기)
            asyncio.create_task(self._send_notification(
                user_id=user_id,
                action=promoted_action,
                threat_type=final_threat,
                severity=final_severity,
                reason=combined_reason,
                message=message,
                event_id=event_id,
            ))

        # 10. 결과 반환
        allowed = promoted_action in (ActionTaken.LOGGED, ActionTaken.WARNED)
        return SecurityCheckResult(
            allowed=allowed,
            action=promoted_action,
            severity=final_severity,
            threat_type=final_threat,
            user_message=None if allowed else self._build_user_message(promoted_action, final_threat, combined_reason, expires_at),
            reason=combined_reason,
            event_id=event_id,
            expires_at=expires_at,
        )

    async def get_block_status(self, user_id: str) -> BlockStatus:
        """차단 상태 조회 (캐시 TTL 60s)."""
        async with self._cache_lock:
            cached = self._block_cache.get(user_id)
            if cached:
                status, cached_at = cached
                if time.time() - cached_at < BLOCK_CACHE_TTL_SEC:
                    return status

        # DB 조회
        status = self._fetch_block_status(user_id)
        async with self._cache_lock:
            self._block_cache[user_id] = (status, time.time())
        return status

    async def unblock(self, user_id: str, admin_id: str, reason: str) -> bool:
        """관리자 해제."""
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE user_blocks
                    SET unblocked_at = NOW(), unblocked_by = %s, unblock_reason = %s
                    WHERE user_id = %s AND unblocked_at IS NULL
                """, (admin_id, reason, user_id))
                conn.commit()
                # 차단 테이블에서 제거
                cursor.execute("DELETE FROM user_blocks WHERE user_id = %s", (user_id,))
                conn.commit()
            finally:
                cursor.close()
            # 캐시 무효화
            async with self._cache_lock:
                self._block_cache.pop(user_id, None)
            logger.info(f"[SecurityGuard] Unblocked user={user_id} by admin={admin_id}")
            return True
        except Exception as e:
            logger.error(f"[SecurityGuard] Unblock failed: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    # ────────────────────────────────────────────────────────
    # Internal helpers
    # ────────────────────────────────────────────────────────
    def _rule_check(self, message: str) -> RuleCheckResult:
        """정규식 패턴 매칭."""
        matched: List[str] = []
        max_score = 0
        top_threat: Optional[ThreatType] = None

        for pattern, threat, weight in RULE_PATTERNS:
            if pattern.search(message):
                matched.append(pattern.pattern[:100])
                if weight > max_score:
                    max_score = weight
                    top_threat = threat

        return RuleCheckResult(
            suspicion_score=max_score,
            threat_type=top_threat,
            matched_patterns=matched,
        )

    def _fetch_block_status(self, user_id: str) -> BlockStatus:
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT block_type, reason, threat_type, blocked_at, expires_at
                    FROM user_blocks
                    WHERE user_id = %s
                      AND unblocked_at IS NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                    LIMIT 1
                """, (user_id,))
                row = cursor.fetchone()
            finally:
                cursor.close()

            if not row:
                return BlockStatus(blocked=False)

            return BlockStatus(
                blocked=True,
                block_type=row["block_type"],
                reason=row["reason"],
                threat_type=row.get("threat_type"),
                blocked_at=row["blocked_at"],
                expires_at=row["expires_at"],
            )
        except Exception as e:
            logger.error(f"[SecurityGuard] fetch_block_status failed: {e}")
            return BlockStatus(blocked=False)
        finally:
            if conn:
                conn.close()

    def _log_event(
        self,
        user_id: str,
        session_id: Optional[str],
        workspace_id: Optional[str],
        threat_type: ThreatType,
        severity: int,
        action: ActionTaken,
        layer: DetectionLayer,
        message: str,
        reason: str,
        matched_patterns: List[str],
        llm_raw: Optional[str] = None,
    ) -> Optional[int]:
        """이벤트 로그 저장, 삽입된 ID 반환."""
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO user_security_events
                    (user_id, session_id, workspace_id, threat_type, severity,
                     action_taken, detection_layer, user_message, reason,
                     matched_patterns, llm_raw_response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    session_id,
                    workspace_id,
                    threat_type.value,
                    severity,
                    action.value,
                    layer.value,
                    message[:500],  # snippet
                    reason[:1000],
                    json.dumps(matched_patterns, ensure_ascii=False) if matched_patterns else None,
                    llm_raw[:2000] if llm_raw else None,
                ))
                event_id = cursor.lastrowid
                conn.commit()
                return event_id
            finally:
                cursor.close()
        except Exception as e:
            logger.error(f"[SecurityGuard] log_event failed: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    async def _check_escalation(
        self,
        user_id: str,
        action: ActionTaken,
        event_id: Optional[int],
        threat: Optional[ThreatType],
        reason: str,
    ) -> Tuple[ActionTaken, Optional[datetime]]:
        """
        누적 규칙 확인:
        - WARN 5회/24h → TEMP_BLOCK
        - TEMP_BLOCK 3회/30d → PERM_BLOCK
        """
        expires_at = None

        if action == ActionTaken.WARNED:
            count = self._count_recent_events(
                user_id, hours=24,
                actions=[ActionTaken.WARNED.value]
            )
            if count >= SECURITY_WARN_LIMIT:
                action = ActionTaken.TEMP_BLOCKED
                expires_at = datetime.now() + timedelta(hours=SECURITY_TEMP_BLOCK_HOURS)
                logger.warning(f"[SecurityGuard] Escalated WARN→TEMP_BLOCK for user={user_id}, count={count}")

        elif action == ActionTaken.TEMP_BLOCKED:
            expires_at = datetime.now() + timedelta(hours=SECURITY_TEMP_BLOCK_HOURS)
            count = self._count_recent_events(
                user_id, hours=24 * 30,
                actions=[ActionTaken.TEMP_BLOCKED.value]
            )
            if count >= SECURITY_TEMP_BLOCK_LIMIT:
                action = ActionTaken.PERM_BLOCKED
                expires_at = None
                logger.warning(f"[SecurityGuard] Escalated TEMP→PERM for user={user_id}, count={count}")

        return action, expires_at

    def _count_recent_events(
        self,
        user_id: str,
        hours: int,
        actions: List[str],
    ) -> int:
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            try:
                placeholders = ",".join(["%s"] * len(actions))
                cursor.execute(f"""
                    SELECT COUNT(*) AS cnt
                    FROM user_security_events
                    WHERE user_id = %s
                      AND action_taken IN ({placeholders})
                      AND created_at >= NOW() - INTERVAL %s HOUR
                """, (user_id, *actions, hours))
                row = cursor.fetchone()
                return int(row["cnt"]) if row else 0
            finally:
                cursor.close()
        except Exception as e:
            logger.error(f"[SecurityGuard] count_events failed: {e}")
            return 0
        finally:
            if conn:
                conn.close()

    def _apply_block(
        self,
        user_id: str,
        action: ActionTaken,
        reason: str,
        threat_type: Optional[ThreatType],
        event_id: Optional[int],
        expires_at: Optional[datetime],
    ):
        """차단 테이블 upsert."""
        block_type = "PERMANENT" if action == ActionTaken.PERM_BLOCKED else "TEMPORARY"
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            try:
                # 기존 TEMP_BLOCK 카운트 가져오기
                cursor.execute(
                    "SELECT temp_block_count FROM user_blocks WHERE user_id = %s",
                    (user_id,)
                )
                prev = cursor.fetchone()
                prev_temp_count = int(prev["temp_block_count"]) if prev else 0

                new_temp_count = prev_temp_count
                if action == ActionTaken.TEMP_BLOCKED:
                    new_temp_count += 1

                cursor.execute("""
                    INSERT INTO user_blocks
                    (user_id, block_type, reason, threat_type, blocked_at,
                     expires_at, triggering_event_id, temp_block_count)
                    VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        block_type = VALUES(block_type),
                        reason = VALUES(reason),
                        threat_type = VALUES(threat_type),
                        blocked_at = VALUES(blocked_at),
                        expires_at = VALUES(expires_at),
                        triggering_event_id = VALUES(triggering_event_id),
                        temp_block_count = VALUES(temp_block_count),
                        unblocked_at = NULL,
                        unblocked_by = NULL,
                        unblock_reason = NULL
                """, (
                    user_id,
                    block_type,
                    reason[:1000],
                    threat_type.value if threat_type else None,
                    expires_at,
                    event_id,
                    new_temp_count,
                ))
                conn.commit()
            finally:
                cursor.close()
        except Exception as e:
            logger.error(f"[SecurityGuard] apply_block failed: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    # ────────────────────────────────────────────────────────
    # 메시지 빌더
    # ────────────────────────────────────────────────────────
    THREAT_LABELS = {
        ThreatType.INJECTION: "프롬프트 인젝션 시도",
        ThreatType.JAILBREAK: "제약 우회(jailbreak) 시도",
        ThreatType.DATA_EXFIL: "비정상 데이터 추출 시도",
        ThreatType.PRIVILEGE_ESCALATION: "권한 탈취 시도",
        ThreatType.ABUSE: "비정상 호출 패턴",
        ThreatType.MALICIOUS_CONTENT: "악성 콘텐츠 생성 요청",
        ThreatType.OTHER: "보안 정책 위반",
    }

    def _build_user_message(
        self,
        action: ActionTaken,
        threat: Optional[ThreatType],
        reason: str,
        expires_at: Optional[datetime],
    ) -> str:
        label = self.THREAT_LABELS.get(threat, "보안 정책 위반") if threat else "보안 정책 위반"

        if action == ActionTaken.PERM_BLOCKED:
            return (
                f"⚠️ 계정이 영구 차단되었습니다.\n\n"
                f"사유: {label}\n"
                f"반복된 보안 정책 위반으로 영구 차단 처리되었습니다.\n"
                f"문의: 관리자에게 연락하세요."
            )
        if action == ActionTaken.TEMP_BLOCKED:
            exp = expires_at.strftime("%Y-%m-%d %H:%M") if expires_at else "24시간"
            return (
                f"⛔ 계정이 일시 차단되었습니다.\n\n"
                f"사유: {label}\n"
                f"해제 예정: {exp}\n"
                f"반복 시 영구 차단될 수 있습니다."
            )
        if action == ActionTaken.BLOCKED_REQUEST:
            return (
                f"🚫 이 요청은 처리할 수 없습니다.\n\n"
                f"사유: {label}\n"
                f"정책에 위배되는 요청입니다. 업무와 관련된 다른 질문을 해주세요."
            )
        return "요청이 제한되었습니다."

    def _build_blocked_message(self, status: BlockStatus) -> str:
        threat = None
        if status.threat_type:
            try:
                threat = ThreatType(status.threat_type)
            except ValueError:
                pass
        label = self.THREAT_LABELS.get(threat, "보안 정책 위반") if threat else "보안 정책 위반"

        if status.block_type == "PERMANENT":
            return (
                f"⚠️ 계정이 영구 차단되어 있습니다.\n\n"
                f"사유: {label}\n"
                f"문의: 관리자에게 연락하세요."
            )
        exp = status.expires_at.strftime("%Y-%m-%d %H:%M") if status.expires_at else "-"
        return (
            f"⛔ 계정이 일시 차단되어 있습니다.\n\n"
            f"사유: {label}\n"
            f"해제 예정: {exp}"
        )

    # ────────────────────────────────────────────────────────
    # 노티
    # ────────────────────────────────────────────────────────
    async def _send_notification(
        self,
        user_id: str,
        action: ActionTaken,
        threat_type: Optional[ThreatType],
        severity: int,
        reason: str,
        message: str,
        event_id: Optional[int],
    ):
        """관리자 이메일 노티 (TEMP/PERM_BLOCK만)."""
        try:
            min_sev = int(os.getenv("SECURITY_NOTIFY_MIN_SEVERITY", "70"))
            if severity < min_sev:
                return

            admins_env = os.getenv("SECURITY_ADMIN_EMAILS", "").strip()
            if not admins_env:
                logger.warning("[SecurityGuard] SECURITY_ADMIN_EMAILS not set, skipping notification")
                return

            admin_emails = [e.strip() for e in admins_env.split(",") if e.strip()]

            from app.services.email_service import get_email_service
            email_service = get_email_service()
            if not email_service.is_configured():
                logger.warning("[SecurityGuard] SMTP not configured, skipping notification")
                return

            threat_label = self.THREAT_LABELS.get(threat_type, "기타") if threat_type else "기타"
            action_label = {
                ActionTaken.TEMP_BLOCKED: "24시간 차단",
                ActionTaken.PERM_BLOCKED: "영구 차단",
            }.get(action, action.value)

            subject = f"[보안 경고] {action_label} 발생 — {user_id} ({threat_label})"

            html = f"""
            <div style="font-family: 맑은 고딕, sans-serif; max-width: 640px;">
              <h2 style="color: #dc2626; border-bottom: 2px solid #dc2626; padding-bottom: 8px;">
                ⚠️ 보안 위협 탐지
              </h2>
              <table style="border-collapse: collapse; width: 100%; margin-top: 16px;">
                <tr style="background: #fef2f2;">
                  <td style="padding: 8px; border: 1px solid #fecaca; font-weight: bold; width: 120px;">사용자</td>
                  <td style="padding: 8px; border: 1px solid #fecaca;">{user_id}</td>
                </tr>
                <tr>
                  <td style="padding: 8px; border: 1px solid #fecaca; font-weight: bold;">조치</td>
                  <td style="padding: 8px; border: 1px solid #fecaca;">{action_label}</td>
                </tr>
                <tr style="background: #fef2f2;">
                  <td style="padding: 8px; border: 1px solid #fecaca; font-weight: bold;">위협 유형</td>
                  <td style="padding: 8px; border: 1px solid #fecaca;">{threat_label}</td>
                </tr>
                <tr>
                  <td style="padding: 8px; border: 1px solid #fecaca; font-weight: bold;">심각도</td>
                  <td style="padding: 8px; border: 1px solid #fecaca;">{severity}/100</td>
                </tr>
                <tr style="background: #fef2f2;">
                  <td style="padding: 8px; border: 1px solid #fecaca; font-weight: bold;">이벤트 ID</td>
                  <td style="padding: 8px; border: 1px solid #fecaca;">#{event_id or '-'}</td>
                </tr>
                <tr>
                  <td style="padding: 8px; border: 1px solid #fecaca; font-weight: bold;">발생 시각</td>
                  <td style="padding: 8px; border: 1px solid #fecaca;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td>
                </tr>
              </table>

              <div style="margin-top: 20px;">
                <h3 style="color: #374151;">탐지 사유</h3>
                <div style="padding: 12px; background: #f3f4f6; border-radius: 6px; font-family: monospace; font-size: 13px; white-space: pre-wrap;">{reason}</div>
              </div>

              <div style="margin-top: 20px;">
                <h3 style="color: #374151;">사용자 메시지 (일부)</h3>
                <div style="padding: 12px; background: #f3f4f6; border-radius: 6px; font-family: monospace; font-size: 13px; white-space: pre-wrap;">{message[:500]}</div>
              </div>

              <p style="margin-top: 24px; color: #6b7280; font-size: 12px;">
                관리자 대시보드: /admin/report (보안 탭)<br>
                이 메일은 자동 발송되었습니다.
              </p>
            </div>
            """

            result = email_service.send(
                to=admin_emails,
                subject=subject,
                html_body=html,
                from_name="Lucid AI Security Guard",
            )
            logger.info(f"[SecurityGuard] Notification sent: {result}")
        except Exception as e:
            logger.error(f"[SecurityGuard] Notification failed: {e}")


# ────────────────────────────────────────────────────────
# 싱글턴
# ────────────────────────────────────────────────────────
_instance: Optional[SecurityGuardService] = None


def get_security_guard_service() -> SecurityGuardService:
    global _instance
    if _instance is None:
        _instance = SecurityGuardService()
    return _instance
