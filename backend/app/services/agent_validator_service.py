# -*- coding: utf-8 -*-
"""
Agent Validator Service — 매니페스트 자동 검증

설계: docs/agent-hub/04_registration_flow.md, 07_security.md

검증 카테고리:
- quality: 매니페스트 형식, description 명료성 (LLM)
- security: SSRF, Path Traversal, 명령어 주입, Secret Leak

흐름:
1. Agent 등록/수정 시 trigger_validation(agent_id) 호출
2. quality + security 두 카테고리 각각 실행
3. 결과를 agent_review_reports INSERT
4. agents.status 갱신:
   - 양쪽 모두 passed/warnings → pending_approval
   - 한쪽이라도 failed → rejected
"""
import asyncio
import json
import logging
import re
import uuid
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

from app.core.database import get_database_connection

logger = logging.getLogger(__name__)


VALIDATOR_VERSION = "validator-v1"
LLM_TIMEOUT_SEC = 30

# 사설 IP 패턴 (SSRF 차단용)
PRIVATE_IP_PATTERNS = [
    re.compile(r"^127\."),
    re.compile(r"^10\."),
    re.compile(r"^172\.(1[6-9]|2[0-9]|3[0-1])\."),
    re.compile(r"^192\.168\."),
    re.compile(r"^169\.254\."),  # link-local (AWS metadata)
    re.compile(r"^0\.0\.0\.0"),
    re.compile(r"^localhost", re.IGNORECASE),
]

# 위험한 매크로 패턴 (Runner)
DANGEROUS_RUNNER_PATTERNS = [
    re.compile(r"\.\./"),                    # path traversal
    re.compile(r"^/|^[A-Za-z]:\\"),          # absolute path
    re.compile(r";|&&|\|\||`|\$\("),          # command injection
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),  # disk format
    re.compile(r"rm\s+-rf|rmdir\s+/s", re.IGNORECASE),
]

# 매니페스트 평문에 들어가면 안 되는 secret 패턴
SECRET_LEAK_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{4,}"),
    re.compile(r"(?i)(api[-_]?key|secret[-_]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
]

# 사번 위조 방지 — inputs에 못 쓸 이름
FORBIDDEN_INPUT_NAMES = {
    "employee_number", "사번", "user_id", "empno",
    "caller_id", "caller_user_id"
}


class AgentValidatorService:
    def __init__(self):
        self.db = get_database_connection()

    # ============================================================
    # Public — 검증 트리거
    # ============================================================

    async def trigger_validation(self, agent_id: str) -> Dict:
        """Agent 검증 실행 — quality + security 두 카테고리.

        호출 후 background task로 실행 권장:
            asyncio.create_task(validator.trigger_validation(agent_id))
        """
        agent = self._fetch_agent(agent_id)
        if not agent:
            logger.warning(f"[Validator] agent {agent_id} not found")
            return {"error": "agent not found"}

        # 두 카테고리 병렬 실행
        try:
            results = await asyncio.gather(
                self._run_quality_validation(agent),
                self._run_security_validation(agent),
                return_exceptions=True,
            )
        except Exception as e:
            logger.exception(f"[Validator] gather failed for agent {agent_id}: {e}")
            return {"error": str(e)}

        # 두 카테고리 결과 합산하여 status 결정
        any_failed = any(
            isinstance(r, dict) and r.get("status") == "failed"
            for r in results if not isinstance(r, Exception)
        )
        new_status = "rejected" if any_failed else "pending_approval"
        self._update_agent_status(agent_id, new_status)

        logger.info(f"[Validator] agent {agent['slug']} -> {new_status}")
        return {
            "agent_id": agent_id,
            "new_status": new_status,
            "results": [r if not isinstance(r, Exception) else {"error": str(r)} for r in results],
        }

    # ============================================================
    # Quality validation
    # ============================================================

    async def _run_quality_validation(self, agent: Dict) -> Dict:
        """매니페스트 형식 + description 명료성"""
        findings: List[Dict] = []

        # 1. 필수 필드 체크
        manifest = agent.get("manifest") or {}
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except json.JSONDecodeError:
                findings.append({
                    "severity": "critical",
                    "category": "manifest_format",
                    "message": "manifest is not valid JSON",
                })

        for field in ("runtime",):
            if field not in manifest:
                findings.append({
                    "severity": "error",
                    "category": "manifest_format",
                    "message": f"missing required field: manifest.{field}",
                })

        # 2. platform과 runtime.platform 일치 체크
        runtime = manifest.get("runtime") or {}
        if isinstance(runtime, dict):
            mf_platform = runtime.get("platform")
            if mf_platform and mf_platform != agent.get("platform"):
                findings.append({
                    "severity": "error",
                    "category": "manifest_consistency",
                    "message": f"platform mismatch: agent.platform={agent['platform']}, manifest.runtime.platform={mf_platform}",
                })

        # 3. inputs에 사번 위조 시도 방지
        inputs = manifest.get("inputs") or []
        if isinstance(inputs, list):
            for inp in inputs:
                if isinstance(inp, dict):
                    name = (inp.get("name") or "").lower()
                    if name in FORBIDDEN_INPUT_NAMES:
                        findings.append({
                            "severity": "critical",
                            "category": "security",
                            "message": f"forbidden input name '{name}' (system-injected only)",
                        })

        # 4. description 길이 (Phase 1은 단순 체크, LLM 평가는 추후)
        desc = (agent.get("description") or "").strip()
        if len(desc) < 10:
            findings.append({
                "severity": "warn",
                "category": "clarity",
                "message": "description is too short (< 10 chars)",
            })
        elif len(desc) > 1000:
            findings.append({
                "severity": "info",
                "category": "clarity",
                "message": "description is very long (> 1000 chars)",
            })

        # 5. intent_hints 존재 체크 (워크스페이스 합성에 중요)
        intent_hints = manifest.get("intent_hints") or {}
        if not intent_hints.get("system_prompt"):
            findings.append({
                "severity": "warn",
                "category": "clarity",
                "message": "intent_hints.system_prompt is empty (Workspace prompt composition will skip this agent)",
            })

        return self._save_report(
            agent=agent,
            category="quality",
            findings=findings,
        )

    # ============================================================
    # Security validation
    # ============================================================

    async def _run_security_validation(self, agent: Dict) -> Dict:
        """SSRF / Path Traversal / 명령어 주입 / Secret Leak"""
        findings: List[Dict] = []
        manifest = agent.get("manifest") or {}
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except json.JSONDecodeError:
                manifest = {}
        runtime = manifest.get("runtime") or {}
        platform = agent.get("platform")

        # 1. Webhook URL SSRF 체크
        if platform == "webhook" and runtime.get("url"):
            findings.extend(self._check_url_ssrf(runtime["url"]))

        # 2. Runner entry/args Path Traversal + 주입 체크
        if platform == "runner":
            entry = runtime.get("entry") or ""
            args = runtime.get("args") or []
            for pattern in DANGEROUS_RUNNER_PATTERNS:
                if pattern.search(entry):
                    findings.append({
                        "severity": "critical",
                        "category": "path_traversal",
                        "message": f"runner.entry contains dangerous pattern: {entry}",
                    })
                for arg in args:
                    if isinstance(arg, str) and pattern.search(arg):
                        findings.append({
                            "severity": "critical",
                            "category": "command_injection",
                            "message": f"runner.args contains dangerous pattern: {arg}",
                        })

        # 3. Secret Leak — 매니페스트 전체 직렬화해서 패턴 매칭
        # MISO 플랫폼은 runtime.api_key 평문 저장 허용 (UI/응답 단에서 마스킹).
        manifest_for_scan = json.dumps(manifest, ensure_ascii=False)
        if platform == "miso" and isinstance(runtime.get("api_key"), str):
            scan_runtime = {k: v for k, v in runtime.items() if k != "api_key"}
            scan_manifest = {**manifest, "runtime": scan_runtime}
            manifest_for_scan = json.dumps(scan_manifest, ensure_ascii=False)

        for pattern in SECRET_LEAK_PATTERNS:
            match = pattern.search(manifest_for_scan)
            if match:
                findings.append({
                    "severity": "critical",
                    "category": "secret_leak",
                    "message": f"possible secret in manifest: {match.group(0)[:30]}... (use auth_ref instead)",
                })

        # 4. auth_ref 형식 체크 (Phase 1 = ssm:/lucid-hub/* 권장)
        auth_ref = runtime.get("auth_ref")
        if auth_ref and not auth_ref.startswith(("ssm:/lucid-hub/", "env:")):
            findings.append({
                "severity": "warn",
                "category": "credential_storage",
                "message": f"auth_ref should use ssm:/lucid-hub/* or env: prefix (got: {auth_ref[:40]})",
            })

        return self._save_report(
            agent=agent,
            category="security",
            findings=findings,
        )

    def _check_url_ssrf(self, url: str) -> List[Dict]:
        """URL이 사설 IP/내부망 가리키는지 체크"""
        findings = []
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if not host:
                return [{
                    "severity": "critical",
                    "category": "ssrf",
                    "message": f"webhook URL has no host: {url[:80]}",
                }]
            for pattern in PRIVATE_IP_PATTERNS:
                if pattern.match(host):
                    findings.append({
                        "severity": "critical",
                        "category": "ssrf",
                        "message": f"webhook URL points to private/loopback host: {host}",
                    })
                    break
            if parsed.scheme not in ("http", "https"):
                findings.append({
                    "severity": "error",
                    "category": "ssrf",
                    "message": f"webhook URL scheme must be http or https (got: {parsed.scheme})",
                })
        except Exception as e:
            findings.append({
                "severity": "error",
                "category": "ssrf",
                "message": f"webhook URL parse error: {e}",
            })
        return findings

    # ============================================================
    # 리포트 저장
    # ============================================================

    def _save_report(self, agent: Dict, category: str, findings: List[Dict]) -> Dict:
        """agent_review_reports에 INSERT.

        status 결정:
        - critical 1개 이상 → failed
        - error/warn 1개 이상 → warnings
        - 그 외 → passed
        """
        severity_max = self._compute_severity_max(findings)
        if severity_max == "critical":
            status = "failed"
        elif severity_max in ("error", "warn"):
            status = "warnings"
        else:
            status = "passed"

        score = self._compute_score(findings)
        report_id = str(uuid.uuid4())

        # review_round 계산 (같은 agent_id + version의 가장 큰 round + 1)
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(MAX(review_round), 0) + 1 AS next_round
                FROM agent_review_reports
                WHERE agent_id = %s AND agent_version = %s AND category = %s
                """,
                (agent["id"], agent["version"], category),
            )
            row = cursor.fetchone()
            review_round = row["next_round"] if row else 1

            cursor.execute(
                """
                INSERT INTO agent_review_reports
                  (id, agent_id, agent_version, review_round, category,
                   reviewer_kind, reviewer_id, score, severity_max,
                   findings, status, completed_at)
                VALUES (%s, %s, %s, %s, %s, 'auto', %s, %s, %s, %s, %s, NOW())
                """,
                (
                    report_id, agent["id"], agent["version"], review_round, category,
                    VALIDATOR_VERSION, score, severity_max,
                    json.dumps(findings, ensure_ascii=False), status,
                ),
            )

        return {
            "report_id": report_id,
            "category": category,
            "status": status,
            "severity_max": severity_max,
            "findings_count": len(findings),
            "score": score,
        }

    def _compute_severity_max(self, findings: List[Dict]) -> str:
        order = {"critical": 4, "error": 3, "warn": 2, "info": 1}
        if not findings:
            return "info"
        return max(findings, key=lambda f: order.get(f.get("severity", "info"), 0)).get("severity", "info")

    def _compute_score(self, findings: List[Dict]) -> int:
        """간단한 점수: 100 - (severity별 감점)"""
        weights = {"critical": 100, "error": 30, "warn": 10, "info": 2}
        penalty = sum(weights.get(f.get("severity", "info"), 0) for f in findings)
        return max(0, 100 - penalty)

    # ============================================================
    # DB 조작
    # ============================================================

    def _fetch_agent(self, agent_id: str) -> Optional[Dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM agents WHERE id = %s", (agent_id,))
            row = cursor.fetchone()
            if row and isinstance(row.get("manifest"), str):
                try:
                    row["manifest"] = json.loads(row["manifest"])
                except json.JSONDecodeError:
                    pass
            return row

    def _update_agent_status(self, agent_id: str, new_status: str) -> None:
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE agents SET status = %s WHERE id = %s",
                (new_status, agent_id),
            )


# ============================================================
# Dependency injection
# ============================================================
_validator_instance: Optional[AgentValidatorService] = None


def get_agent_validator_service() -> AgentValidatorService:
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = AgentValidatorService()
    return _validator_instance
