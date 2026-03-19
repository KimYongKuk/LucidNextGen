# -*- coding: utf-8 -*-
"""
일일 개발 요약 스케줄러
- 매일 23:00 KST에 CHANGELOG.md + docs/history/ 기반 일일 보고서 생성
- docs/summary/YYYY-MM-DD.md 저장 → git commit+push → HTML 메일 발송
"""
import os
import re
import logging
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# 프로젝트 루트: utils/ → app/ → backend/ → PROJECT_ROOT (파일 기준 4단계 상위)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CHANGELOG_PATH = PROJECT_ROOT / "CHANGELOG.md"
HISTORY_DIR = PROJECT_ROOT / "docs" / "history"
SUMMARY_DIR = PROJECT_ROOT / "docs" / "summary"

KST = ZoneInfo("Asia/Seoul")

# 환경변수
ENABLED = lambda: os.getenv("NIGHTLY_SUMMARY_ENABLED", "true").lower() == "true"
HOUR = lambda: int(os.getenv("NIGHTLY_SUMMARY_HOUR", "23"))
RECIPIENT = lambda: os.getenv("NIGHTLY_SUMMARY_RECIPIENT", "wg0403@landf.co.kr")


class NightlySummaryScheduler:
    """매일 밤 23시 KST 일일 개발 요약 보고서 생성 + 메일 발송"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self):
        """스케줄러 시작"""
        if not ENABLED():
            logger.info("[Nightly Summary] Disabled via NIGHTLY_SUMMARY_ENABLED env")
            return

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self._execute,
            trigger=CronTrigger(
                hour=HOUR(),
                minute=0,
                timezone=KST,
            ),
            id="nightly_summary",
            name="Nightly Development Summary",
            replace_existing=True,
            misfire_grace_time=3600,  # 최대 1시간 지연까지 허용 (기본 1초는 너무 짧음)
        )
        self.scheduler.start()
        logger.info(f"[Nightly Summary] Scheduler started - {HOUR():02d}:00 KST")

    def stop(self):
        """스케줄러 중지"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[Nightly Summary] Scheduler stopped")

    async def run_now(self, target_date: str | None = None) -> dict:
        """
        수동 즉시 실행 (테스트/디버깅용)

        Args:
            target_date: YYYY-MM-DD 형식 (None이면 오늘)
        """
        try:
            d = date.fromisoformat(target_date) if target_date else date.today()
            return await self._execute(d)
        except Exception as e:
            logger.error(f"[Nightly Summary] Manual run failed: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    async def _execute(self, target: date | None = None) -> dict:
        """메인 실행 로직"""
        today = target or date.today()
        today_str = today.strftime("%Y-%m-%d")
        logger.info(f"[Nightly Summary] Executing for {today_str}")

        # 1. CHANGELOG 파싱
        entries = self._parse_changelog(today_str)
        if not entries:
            logger.info(f"[Nightly Summary] No entries for {today_str}, skipping")
            return {"success": True, "message": "No changes today, skipped"}

        # 2. 관련 history 파일 읽기
        history_content = self._read_history_files(entries, today_str)

        # 3. LLM 요약 생성
        summary = await self._generate_summary(today_str, entries, history_content)

        # 4. 파일 저장
        filepath = self._save_summary_file(summary, today_str)

        # 5. git commit + push (실패해도 계속)
        git_result = self._git_commit_push(filepath, today_str)

        # 6. 메일 발송
        email_result = self._send_email(summary, today_str)

        result = {
            "success": True,
            "date": today_str,
            "entries_count": len(entries),
            "summary_file": str(filepath),
            "git": git_result,
            "email": email_result,
        }
        logger.info(f"[Nightly Summary] Completed: {result}")
        return result

    # ─── CHANGELOG 파싱 ───

    def _parse_changelog(self, target_date: str) -> list[dict]:
        """
        CHANGELOG.md에서 특정 날짜의 항목 파싱

        Returns:
            [{"tag": "추가", "module": "Mail", "description": "...", "link": "docs/history/..."}]
        """
        if not CHANGELOG_PATH.exists():
            logger.warning(f"[Nightly Summary] CHANGELOG.md not found: {CHANGELOG_PATH}")
            return []

        content = CHANGELOG_PATH.read_text(encoding="utf-8")

        # ## [YYYY-MM-DD] 섹션 찾기
        pattern = rf"## \[{re.escape(target_date)}\]\s*\n(.*?)(?=\n---|\n## \[|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return []

        section = match.group(1).strip()
        entries = []

        # 각 항목 파싱: - **태그** [모듈] 설명 → [상세](link)
        line_pattern = re.compile(
            r"^- \*\*(\S+)\*\*\s+\[([^\]]+)\]\s+(.*?)$"
        )
        for line in section.split("\n"):
            line = line.strip()
            if not line.startswith("- "):
                continue

            m = line_pattern.match(line)
            if m:
                tag, module, rest = m.group(1), m.group(2), m.group(3)
                # 링크 추출
                link_match = re.search(r"\[상세\]\(([^)]+)\)", rest)
                link = link_match.group(1) if link_match else None
                # 설명에서 링크 제거
                desc = re.sub(r"\s*→?\s*\[상세\]\([^)]+\)", "", rest).strip()
                entries.append({
                    "tag": tag,
                    "module": module,
                    "description": desc,
                    "link": link,
                })
            else:
                # 패턴 매치 안 되는 항목도 포함
                entries.append({
                    "tag": "",
                    "module": "",
                    "description": line.lstrip("- ").strip(),
                    "link": None,
                })

        return entries

    # ─── History 파일 읽기 ───

    def _read_history_files(self, entries: list[dict], target_date: str) -> str:
        """entries에서 링크된 docs/history/*.md 파일 + 당일 날짜 파일 읽기"""
        read_files = set()
        contents = []

        # 1) entries에서 링크된 파일
        for e in entries:
            if e.get("link"):
                fp = PROJECT_ROOT / e["link"]
                if fp.exists() and str(fp) not in read_files:
                    read_files.add(str(fp))
                    contents.append(f"### {fp.name}\n{fp.read_text(encoding='utf-8')}")

        # 2) 당일 날짜로 시작하는 history 파일 (링크 안 된 것도 포함)
        if HISTORY_DIR.exists():
            for fp in HISTORY_DIR.glob(f"{target_date}*.md"):
                if str(fp) not in read_files:
                    read_files.add(str(fp))
                    contents.append(f"### {fp.name}\n{fp.read_text(encoding='utf-8')}")

        return "\n\n".join(contents) if contents else "(상세 기록 없음)"

    # ─── LLM 요약 생성 ───

    async def _generate_summary(
        self, target_date: str, entries: list[dict], history_content: str
    ) -> str:
        """Bedrock Haiku로 일일 보고서 생성"""
        from app.services.bedrock_service import get_bedrock_service

        entries_text = "\n".join(
            f"- [{e['tag']}] [{e['module']}] {e['description']}" for e in entries
        )

        prompt = f"""당신은 소프트웨어 프로젝트의 일일 보고서 작성자입니다.
아래 CHANGELOG 항목과 상세 변경 기록을 바탕으로, {target_date} 하루 진행된 작업을 보고서 형태로 정리하세요.

보고서 형식 (마크다운):
# 일일 개발 보고서 — {target_date}

## 오늘의 요약
(2-3문장으로 핵심 성과 요약)

## 주요 변경사항
(항목별로 정리. 각 항목에 태그와 모듈명 포함)

## 기술적 세부사항
(아키텍처 변경, 주요 구현 방식 등 — 해당 시에만)

## 후속 과제
(추론 가능한 후속 작업이 있으면 기재, 없으면 생략)

---

[CHANGELOG 항목]
{entries_text}

[상세 기록]
{history_content}"""

        bedrock = get_bedrock_service()
        summary = await bedrock.generate_text_haiku(
            prompt=prompt,
            max_tokens=2000,
            temperature=0.3,
        )
        return summary.strip()

    # ─── 파일 저장 ───

    def _save_summary_file(self, summary: str, target_date: str) -> Path:
        """docs/summary/YYYY-MM-DD.md 저장"""
        SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
        filepath = SUMMARY_DIR / f"{target_date}.md"
        filepath.write_text(summary, encoding="utf-8")
        logger.info(f"[Nightly Summary] Saved: {filepath}")
        return filepath

    # ─── Git 자동화 ───

    def _git_commit_push(self, filepath: Path, target_date: str) -> dict:
        """git add → commit → push (실패해도 메일 발송은 계속)"""
        try:
            cwd = str(PROJECT_ROOT)

            # git add
            r = subprocess.run(
                ["git", "add", str(filepath.relative_to(PROJECT_ROOT))],
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                return {"success": False, "step": "add", "error": r.stderr.strip()}

            # git commit
            msg = f"docs: add daily summary {target_date}"
            r = subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                # nothing to commit은 성공으로 처리
                if "nothing to commit" in (r.stdout + r.stderr):
                    return {"success": True, "message": "nothing to commit"}
                return {"success": False, "step": "commit", "error": r.stderr.strip()}

            # git push (origin=GitLab)
            r = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=cwd, capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                return {"success": False, "step": "push", "error": r.stderr.strip()}

            # git push (github=GitHub mirror, 실패해도 무시)
            subprocess.run(
                ["git", "push", "github", "main"],
                cwd=cwd, capture_output=True, text=True, timeout=120,
            )

            return {"success": True, "message": "committed and pushed"}

        except subprocess.TimeoutExpired:
            logger.error("[Nightly Summary] Git operation timed out")
            return {"success": False, "step": "timeout", "error": "operation timed out"}
        except Exception as e:
            logger.error(f"[Nightly Summary] Git error: {e}")
            return {"success": False, "step": "exception", "error": str(e)}

    # ─── 메일 발송 ───

    def _send_email(self, summary: str, target_date: str) -> dict:
        """요약을 HTML 메일로 변환하여 발송"""
        from app.services.email_service import get_email_service

        email_service = get_email_service()
        if not email_service.is_configured():
            logger.warning("[Nightly Summary] Email not configured, skipping")
            return {"success": False, "message": "SMTP not configured"}

        subject = f"[Lucid AI] 일일 개발 보고서 — {target_date}"
        html_body = self._markdown_to_html(summary, target_date)

        return email_service.send(
            to=RECIPIENT(),
            subject=subject,
            html_body=html_body,
            text_body=summary,
        )

    def _markdown_to_html(self, markdown: str, target_date: str) -> str:
        """마크다운을 스타일된 HTML 메일로 변환"""
        # 기본 변환
        html_content = markdown

        # 헤딩
        html_content = re.sub(
            r"^### (.+)$", r"<h3 style='color:#44546A; margin:18px 0 8px;'>\1</h3>",
            html_content, flags=re.MULTILINE,
        )
        html_content = re.sub(
            r"^## (.+)$", r"<h2 style='color:#182F54; border-bottom:2px solid #4472C4; padding-bottom:6px; margin:24px 0 12px;'>\1</h2>",
            html_content, flags=re.MULTILINE,
        )
        html_content = re.sub(
            r"^# (.+)$", r"<h1 style='color:#182F54; margin:0 0 20px;'>\1</h1>",
            html_content, flags=re.MULTILINE,
        )

        # 볼드
        html_content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_content)

        # 인라인 코드
        html_content = re.sub(
            r"`([^`]+)`",
            r"<code style='background:#f0f0f0; padding:2px 6px; border-radius:3px; font-size:13px;'>\1</code>",
            html_content,
        )

        # 리스트 아이템
        html_content = re.sub(
            r"^- (.+)$",
            r"<li style='margin:4px 0; line-height:1.6;'>\1</li>",
            html_content, flags=re.MULTILINE,
        )
        # <li> 그룹을 <ul>로 감싸기
        html_content = re.sub(
            r"((?:<li[^>]*>.*?</li>\s*)+)",
            r"<ul style='margin:8px 0; padding-left:24px;'>\1</ul>",
            html_content, flags=re.DOTALL,
        )

        # 줄바꿈
        html_content = re.sub(r"\n\n", "</p><p>", html_content)
        html_content = re.sub(r"\n", "<br>", html_content)

        # 수평선
        html_content = html_content.replace(
            "---", "<hr style='border:none; border-top:1px solid #ddd; margin:20px 0;'>"
        )

        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; max-width:700px; margin:0 auto; padding:20px; color:#333; line-height:1.7;">

<div style="background:linear-gradient(135deg, #182F54, #4472C4); color:white; padding:24px 30px; border-radius:8px 8px 0 0;">
    <h1 style="margin:0; font-size:22px;">Lucid AI — 일일 개발 보고서</h1>
    <p style="margin:8px 0 0; opacity:0.85; font-size:14px;">{target_date}</p>
</div>

<div style="background:white; border:1px solid #e0e0e0; border-top:none; padding:24px 30px; border-radius:0 0 8px 8px;">
    <p>{html_content}</p>
</div>

<div style="text-align:center; padding:16px; color:#999; font-size:12px;">
    이 메일은 Lucid AI Nightly Summary Scheduler에 의해 자동 생성되었습니다.<br>
    생성 시각: {now_kst} KST
</div>

</body>
</html>"""


# 전역 인스턴스
nightly_summary_scheduler = NightlySummaryScheduler()
