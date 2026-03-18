# -*- coding: utf-8 -*-
"""
주간 리포트 PDF 생성 서비스
- matplotlib 차트 (다크 테마, 대시보드 색상 미러링)
- fpdf2 PDF 레이아웃
- ReportService 데이터 재사용
- 전주 대비(WoW) 비교 + 섹션별 요약 텍스트
- 사용자 정보 (부서/이름) PostgreSQL 조회
"""
import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from fpdf import FPDF

from app.services.report_service import get_report_service

logger = logging.getLogger(__name__)

# ─── 디렉토리 ───
REPORT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "report_output"
REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── 대시보드 색상 팔레트 ───
C_BG_MAIN = (15, 23, 42)         # #0F172A
C_BG_CARD = (30, 41, 59)         # #1E293B
C_BORDER = (51, 65, 85)          # #334155
C_TEXT_PRIMARY = (243, 244, 246)  # #F3F4F6
C_TEXT_SECONDARY = (156, 163, 175) # #9CA3AF
C_BLUE = (59, 130, 246)          # #3B82F6
C_GREEN = (16, 185, 129)         # #10B981
C_ORANGE = (245, 158, 11)        # #F59E0B
C_RED = (239, 68, 68)            # #EF4444
C_PURPLE = (139, 92, 246)        # #8B5CF6
C_CYAN = (6, 182, 212)           # #06B6D4

# Hex 문자열 (matplotlib용)
HEX_BG = "#0F172A"
HEX_CARD = "#1E293B"
HEX_BORDER = "#334155"
HEX_TEXT = "#F3F4F6"
HEX_TEXT2 = "#9CA3AF"
HEX_BLUE = "#3B82F6"
HEX_GREEN = "#10B981"
HEX_ORANGE = "#F59E0B"
HEX_RED = "#EF4444"
HEX_PURPLE = "#8B5CF6"
HEX_CYAN = "#06B6D4"

# 파이 차트 색상 팔레트
PIE_COLORS = [
    "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
    "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1",
    "#14B8A6", "#A855F7",
]

# ─── 한국어 폰트 설정 ───
def _setup_korean_font():
    """맑은 고딕 폰트 경로 찾아서 matplotlib에 등록"""
    font_candidates = [
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]
    for fp in font_candidates:
        if os.path.exists(fp):
            fm.fontManager.addfont(fp)
            prop = fm.FontProperties(fname=fp)
            return prop.get_name()
    return "sans-serif"

KOREAN_FONT = _setup_korean_font()

# matplotlib 다크 테마 기본 설정
CHART_RC = {
    "figure.facecolor": HEX_BG,
    "axes.facecolor": HEX_CARD,
    "axes.edgecolor": HEX_BORDER,
    "axes.labelcolor": HEX_TEXT2,
    "text.color": HEX_TEXT,
    "xtick.color": HEX_TEXT2,
    "ytick.color": HEX_TEXT2,
    "grid.color": HEX_BORDER,
    "grid.alpha": 0.3,
    "font.family": KOREAN_FONT,
    "font.size": 11,
    "axes.grid": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
}

# ─── 사용자 정보 일괄 조회 (PostgreSQL TIMS DB) ───

TIMS_DATABASE_URL = os.environ.get(
    "TIMS_DATABASE_URL",
    "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims"
)


async def _batch_lookup_users(employee_numbers: list) -> dict:
    """employee_number → {"name": "홍길동", "dept_name": "AI개발팀"} 일괄 조회"""
    if not employee_numbers:
        return {}
    try:
        import asyncpg
        conn = await asyncpg.connect(TIMS_DATABASE_URL, timeout=10)
        try:
            rows = await conn.fetch(
                """
                SELECT employee_number, name, dept_name
                FROM v_user_info_mapping
                WHERE employee_number = ANY($1)
                """,
                employee_numbers
            )
            return {
                row["employee_number"]: {
                    "name": row["name"] or row["employee_number"],
                    "dept_name": row["dept_name"] or "",
                }
                for row in rows
            }
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"[ReportPDF] User lookup failed: {e}")
        return {}


def _sync_batch_lookup_users(employee_numbers: list) -> dict:
    """sync wrapper — FastAPI thread pool에서 asyncio.run() 사용"""
    if not employee_numbers:
        return {}
    try:
        return asyncio.run(_batch_lookup_users(employee_numbers))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_batch_lookup_users(employee_numbers))
        finally:
            loop.close()


# ─── DashboardPDF ───

class DashboardPDF(FPDF):
    """대시보드 스타일 PDF — 다크 테마, 한국어 지원"""

    def __init__(self):
        super().__init__(orientation="L", format="A4")  # 가로 A4
        self.set_auto_page_break(auto=False)

        # 한국어 폰트 등록
        font_paths = [
            ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"),
            ("C:/Windows/Fonts/NanumGothic.ttf", "C:/Windows/Fonts/NanumGothicBold.ttf"),
        ]
        for regular, bold in font_paths:
            if os.path.exists(regular):
                self.add_font("korean", "", regular, uni=True)
                if os.path.exists(bold):
                    self.add_font("korean", "B", bold, uni=True)
                else:
                    self.add_font("korean", "B", regular, uni=True)
                break

    def _fill_bg(self):
        """페이지 전체 배경색 채우기"""
        self.set_fill_color(*C_BG_MAIN)
        self.rect(0, 0, self.w, self.h, "F")

    def _draw_card(self, x, y, w, h):
        """카드 배경 + 테두리"""
        self.set_fill_color(*C_BG_CARD)
        self.set_draw_color(*C_BORDER)
        self.rect(x, y, w, h, "DF")

    def _text(self, x, y, text, size=10, color=C_TEXT_PRIMARY, bold=False):
        """텍스트 출력"""
        self.set_font("korean", "B" if bold else "", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.cell(0, 0, text)

    def _section_title(self, title, y=12):
        """섹션 타이틀 (상단)"""
        self._text(15, y, title, size=14, color=C_TEXT_PRIMARY, bold=True)
        # 밑줄
        self.set_draw_color(*C_BLUE)
        self.set_line_width(0.5)
        self.line(15, y + 5, 50, y + 5)

    def _summary_text(self, x, card_y, text, width=260, card_h=27, size=10, color=C_TEXT_PRIMARY, line_height=5):
        """multi_cell 기반 요약 텍스트 블록 (카드 내 상하좌우 가운데 정렬)

        Args:
            card_y: 카드의 상단 Y 좌표
            card_h: 카드 높이
        """
        self.set_font("korean", "", size)
        self.set_text_color(*color)
        # 텍스트 높이 계산 (줄 수 추정)
        lines = self.multi_cell(width, line_height, text, align="C", dry_run=True, output="LINES")
        text_h = len(lines) * line_height
        # 카드 내 세로 중앙 배치
        start_y = card_y + max(0, (card_h - text_h) / 2)
        self.set_xy(x, start_y)
        self.multi_cell(width, line_height, text, align="C")
        return self.get_y()

    def _fit_image(self, img_path, x, y, max_w, max_h):
        """이미지를 max_w x max_h 영역 내에 fit (비율 유지, 상하좌우 중앙 정렬)"""
        try:
            from PIL import Image as PILImage
            with PILImage.open(img_path) as img:
                iw, ih = img.size
        except Exception:
            self.image(img_path, x=x, y=y, w=max_w)
            return

        ratio = iw / ih
        fit_w = max_w
        fit_h = fit_w / ratio

        if fit_h > max_h:
            fit_h = max_h
            fit_w = fit_h * ratio

        offset_x = (max_w - fit_w) / 2
        offset_y = (max_h - fit_h) / 2
        self.image(img_path, x=x + offset_x, y=y + offset_y, w=fit_w, h=fit_h)


# ─── ReportPDFService ───

class ReportPDFService:
    """주간 리포트 PDF 생성"""

    def __init__(self):
        self.report_service = get_report_service()

    def generate(self, date_from: str, date_to: str) -> str:
        """주간 리포트 PDF 생성. 반환: 생성된 PDF 파일 경로"""
        logger.info(f"[ReportPDF] Generating report: {date_from} ~ {date_to}")

        # 1. 데이터 수집 (현재 주 + 전주 + 사용자 정보)
        data = self._collect_data(date_from, date_to)

        # 2. 차트 생성 (임시 PNG 파일들)
        chart_files = self._generate_charts(data)

        # 3. PDF 조합
        pdf = DashboardPDF()
        try:
            self._page_cover(pdf, date_from, date_to)
            self._page_executive_summary(pdf, data)
            self._page_usage_trend(pdf, data, chart_files)
            self._page_intent_distribution(pdf, data, chart_files)
            self._page_user_ranking(pdf, data, chart_files)
            self._page_artifacts(pdf, data, chart_files)
            self._page_performance(pdf, data, chart_files)

            # 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"weekly_report_{date_from}_to_{date_to}_{timestamp}.pdf"
            pdf_path = str(REPORT_OUTPUT_DIR / filename)
            pdf.output(pdf_path)
            logger.info(f"[ReportPDF] Generated: {pdf_path}")
            return pdf_path
        finally:
            for f in chart_files.values():
                try:
                    if os.path.exists(f):
                        os.unlink(f)
                except Exception:
                    pass

    # ─── 데이터 수집 ───

    def _collect_data(self, date_from: str, date_to: str) -> dict:
        """ReportService에서 현재 주 + 전주 데이터 수집, 사용자 정보 조회"""
        svc = self.report_service

        # 현재 주 데이터
        data = {
            "overview": svc.get_overview(date_from, date_to),
            "intents": svc.get_intents(date_from, date_to),
            "quality": svc.get_quality(date_from, date_to),
            "workspaces": svc.get_workspaces(date_from, date_to),
            "artifacts": svc.get_artifacts(date_from, date_to),
            "performance": svc.get_performance(date_from, date_to),
            "users": svc.get_user_ranking(date_from, date_to),
        }

        # 전주 데이터 (WoW 비교용)
        from_dt = datetime.strptime(date_from, "%Y-%m-%d")
        prev_to = (from_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        prev_from = (from_dt - timedelta(days=7)).strftime("%Y-%m-%d")

        try:
            data["prev"] = {
                "overview": svc.get_overview(prev_from, prev_to),
                "intents": svc.get_intents(prev_from, prev_to),
                "quality": svc.get_quality(prev_from, prev_to),
                "artifacts": svc.get_artifacts(prev_from, prev_to),
                "performance": svc.get_performance(prev_from, prev_to),
                "users": svc.get_user_ranking(prev_from, prev_to),
            }
        except Exception as e:
            logger.warning(f"[ReportPDF] Previous week data fetch failed: {e}")
            data["prev"] = {
                "overview": {"total_messages": 0, "total_sessions": 0, "active_users": 0, "daily_trend": []},
                "intents": {"distribution": []},
                "quality": {"failCount": 0, "failRate": 0, "failByCategory": [], "recentFailures": []},
                "artifacts": {"fileUploads": 0, "imageUploads": 0, "pdfCount": 0, "xlsxCount": 0, "pptCount": 0, "dailyTrend": []},
                "performance": {"avgResponseMs": 0, "p95ResponseMs": 0, "byWorker": [], "dailyTrend": []},
                "users": {"totalUsers": 0, "totalMessages": 0, "ranking": []},
            }

        # 사용자 정보 일괄 조회 (부서/이름)
        ranking = data["users"].get("ranking", [])
        emp_numbers = [r["userId"] for r in ranking[:30]]
        data["user_info_map"] = _sync_batch_lookup_users(emp_numbers)

        # LLM 기반 섹션별 분석 요약 생성 (Haiku)
        data["llm_summaries"] = self._generate_llm_summaries(data)

        return data

    # ─── WoW 계산 ───

    def _calc_wow(self, current: float, previous: float) -> dict:
        """전주 대비 변동 계산. 증가=green, 감소=red"""
        if previous == 0:
            pct = 100.0 if current > 0 else 0.0
        else:
            pct = round((current - previous) / previous * 100, 1)

        if pct > 0:
            return {"pct": pct, "symbol": "\u25b2", "color": C_GREEN}
        elif pct < 0:
            return {"pct": abs(pct), "symbol": "\u25bc", "color": C_RED}
        else:
            return {"pct": 0, "symbol": "-", "color": C_TEXT_SECONDARY}

    def _calc_wow_inverted(self, current: float, previous: float) -> dict:
        """감소가 좋은 지표용 (실패율, 응답시간). 감소=green, 증가=red"""
        result = self._calc_wow(current, previous)
        if result["symbol"] == "\u25b2":
            result["color"] = C_RED
        elif result["symbol"] == "\u25bc":
            result["color"] = C_GREEN
        return result

    def _wow_text(self, wow: dict) -> str:
        """WoW dict → 텍스트 문자열"""
        return f"{wow['symbol']}{wow['pct']}%"

    # ─── 요약 텍스트 생성 ───

    def _summary_executive(self, data: dict) -> str:
        ov = data["overview"]
        prev_ov = data["prev"]["overview"]
        q = data["quality"]
        perf = data["performance"]
        prev_perf = data["prev"]["performance"]

        msg_wow = self._calc_wow(ov["total_messages"], prev_ov["total_messages"])
        user_wow = self._calc_wow(ov["active_users"], prev_ov["active_users"])
        avg_sec = perf["avgResponseMs"] / 1000
        prev_avg_sec = prev_perf["avgResponseMs"] / 1000
        time_wow = self._calc_wow_inverted(avg_sec, prev_avg_sec)

        lines = [
            f"이번 주 총 {ov['total_messages']:,}건의 메시지가 처리되었으며, "
            f"전주 대비 {self._wow_text(msg_wow)} 변동하였습니다.",
            f"활성 사용자 {ov['active_users']:,}명 (전주 {prev_ov['active_users']:,}명, {self._wow_text(user_wow)}), "
            f"평균 응답 {avg_sec:.1f}초 (전주 {prev_avg_sec:.1f}초, {self._wow_text(time_wow)}).",
        ]
        if q["failRate"] > 5:
            lines.append(f"실패율 {q['failRate']}%는 주의가 필요한 수준입니다. 품질 지표를 확인하시기 바랍니다.")
        elif q["failRate"] <= 2:
            lines.append(f"실패율 {q['failRate']}%로 안정적인 서비스 운영 상태입니다.")
        else:
            lines.append(f"실패율 {q['failRate']}%로 양호한 수준입니다.")

        return " ".join(lines)

    def _summary_usage_trend(self, data: dict) -> str:
        ov = data["overview"]
        prev_ov = data["prev"]["overview"]
        trend = ov.get("daily_trend", [])

        if not trend:
            return "해당 기간 데이터가 없습니다."

        days = max(len(trend), 1)
        daily_avg = ov["total_messages"] // days
        prev_trend = prev_ov.get("daily_trend", [])
        prev_days = max(len(prev_trend), 1)
        prev_daily_avg = prev_ov["total_messages"] // prev_days
        wow = self._calc_wow(daily_avg, prev_daily_avg)

        peak_day = max(trend, key=lambda d: d["messages"])
        daily_users = sum(d["users"] for d in trend) // days

        return (
            f"일평균 메시지 {daily_avg:,}건 (전주 {prev_daily_avg:,}건, {self._wow_text(wow)}). "
            f"피크: {peak_day['date']} ({peak_day['messages']:,}건). "
            f"일평균 사용자 {daily_users:,}명."
        )

    def _summary_intents(self, data: dict) -> str:
        dist = data["intents"].get("distribution", [])
        if not dist:
            return "인텐트 분포 데이터가 없습니다."

        top3 = dist[:3]
        top3_str = ", ".join(f"{d['name']}({d['ratio']}%)" for d in top3)

        prev_dist = data["prev"]["intents"].get("distribution", [])
        prev_map = {d["name"]: d["count"] for d in prev_dist}
        growth_insights = []
        for d in dist[:5]:
            prev_count = prev_map.get(d["name"], 0)
            if prev_count > 0:
                wow = self._calc_wow(d["count"], prev_count)
                if wow["pct"] >= 20:
                    growth_insights.append(f"{d['name']} {self._wow_text(wow)}")

        summary = f"상위 3개 인텐트: {top3_str}."
        if growth_insights:
            summary += f" 주목할 변동: {', '.join(growth_insights[:3])}."
        return summary

    def _summary_quality(self, data: dict) -> str:
        q = data["quality"]
        prev_q = data["prev"]["quality"]
        wow = self._calc_wow_inverted(q["failRate"], prev_q["failRate"])

        cats = q.get("failByCategory", [])
        worst = cats[0] if cats and cats[0]["failCount"] > 0 else None

        summary = (
            f"실패 {q['failCount']:,}건 (실패율 {q['failRate']}%), "
            f"전주({prev_q['failRate']}%) 대비 {self._wow_text(wow)}."
        )
        if worst:
            summary += f" 실패율 최고 카테고리: {worst['category']} ({worst['failRate']}%)."
        return summary

    def _summary_users(self, data: dict) -> str:
        users = data["users"]
        prev_users = data["prev"]["users"]
        wow = self._calc_wow(users["totalUsers"], prev_users["totalUsers"])

        avg_msg = users["totalMessages"] // max(users["totalUsers"], 1)
        prev_avg = prev_users["totalMessages"] // max(prev_users["totalUsers"], 1)
        avg_wow = self._calc_wow(avg_msg, prev_avg)

        ranking = users.get("ranking", [])
        top_user = ranking[0] if ranking else None
        user_info_map = data.get("user_info_map", {})

        summary = (
            f"활성 사용자 {users['totalUsers']:,}명 (전주 대비 {self._wow_text(wow)}), "
            f"인당 평균 {avg_msg:,}건 ({self._wow_text(avg_wow)})."
        )
        if top_user:
            info = user_info_map.get(top_user["userId"], {})
            name = info.get("name", top_user["userId"])
            summary += f" Top 1: {name} ({top_user['messageCount']:,}건)."
        return summary

    def _summary_artifacts(self, data: dict) -> str:
        ws = data["workspaces"]
        art = data["artifacts"]
        prev_art = data["prev"]["artifacts"]

        total_gen = art["pdfCount"] + art["xlsxCount"] + art["pptCount"]
        prev_total = prev_art["pdfCount"] + prev_art["xlsxCount"] + prev_art["pptCount"]
        wow = self._calc_wow(total_gen, prev_total)

        return (
            f"활성 워크스페이스 {ws['activeWorkspaces']}개, "
            f"문서 생성 총 {total_gen}건 (PDF {art['pdfCount']}, XLSX {art['xlsxCount']}, PPT {art['pptCount']}). "
            f"전주 대비 {self._wow_text(wow)}."
        )

    def _summary_performance(self, data: dict) -> str:
        perf = data["performance"]
        prev_perf = data["prev"]["performance"]

        avg_sec = perf["avgResponseMs"] / 1000
        p95_sec = perf["p95ResponseMs"] / 1000
        prev_avg = prev_perf["avgResponseMs"] / 1000
        wow = self._calc_wow_inverted(avg_sec, prev_avg)

        by_worker = perf.get("byWorker", [])
        slow_workers = [w for w in by_worker if w["avgMs"] > 10000]

        summary = (
            f"평균 응답 {avg_sec:.1f}초, P95 {p95_sec:.1f}초 "
            f"(전주 평균 {prev_avg:.1f}초, {self._wow_text(wow)})."
        )
        if slow_workers:
            slow_names = ", ".join(f"{w['worker']}({w['avgMs']/1000:.1f}초)" for w in slow_workers[:3])
            summary += f" 느린 Worker: {slow_names}. 최적화 검토 권장."
        else:
            summary += " 전체적으로 양호한 응답 속도입니다."
        return summary

    # ─── LLM 기반 요약 텍스트 생성 (Haiku) ───

    def _generate_llm_summaries(self, data: dict) -> dict:
        """Haiku LLM으로 섹션별 분석 요약 생성. 실패 시 빈 dict 반환 (템플릿 fallback)"""
        try:
            return self._sync_llm_summaries(data)
        except Exception as e:
            logger.warning(f"[ReportPDF] LLM summary generation failed, using template fallback: {e}")
            return {}

    def _sync_llm_summaries(self, data: dict) -> dict:
        """sync wrapper for async Sonnet call"""
        try:
            return asyncio.run(self._async_llm_summaries(data))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._async_llm_summaries(data))
            finally:
                loop.close()

    async def _async_llm_summaries(self, data: dict) -> dict:
        """Sonnet 모델로 모든 섹션 분석 코멘트를 한 번에 생성"""
        import json as _json
        import re as _re
        from app.services.bedrock_service import get_bedrock_service

        ov = data["overview"]
        prev_ov = data["prev"]["overview"]
        q = data["quality"]
        prev_q = data["prev"]["quality"]
        perf = data["performance"]
        prev_perf = data["prev"]["performance"]
        art = data["artifacts"]
        prev_art = data["prev"]["artifacts"]
        users_data = data["users"]
        prev_users = data["prev"]["users"]
        intents_data = data["intents"]
        ws = data["workspaces"]
        user_info_map = data.get("user_info_map", {})

        # Top users with names
        ranking = users_data.get("ranking", [])[:5]
        top_users_lines = []
        for r in ranking:
            info = user_info_map.get(r["userId"], {})
            name = info.get("name", r["userId"])
            dept = info.get("dept_name", "")
            label = f"{dept} {name}" if dept else name
            top_users_lines.append(f"  - {label}: {r['messageCount']}건")
        top_users_str = "\n".join(top_users_lines) or "  (데이터 없음)"

        # Intent distribution
        dist = intents_data.get("distribution", [])[:7]
        intent_str = "\n".join(f"  - {d['name']}: {d['count']}건 ({d['ratio']}%)" for d in dist) or "  (데이터 없음)"

        prev_dist = data["prev"]["intents"].get("distribution", [])[:7]
        prev_intent_str = "\n".join(f"  - {d['name']}: {d['count']}건 ({d['ratio']}%)" for d in prev_dist) or "  (데이터 없음)"

        # Worker performance
        by_worker = perf.get("byWorker", [])[:8]
        worker_str = "\n".join(
            f"  - {w['worker']}: 평균 {w['avgMs']/1000:.1f}초, P95 {w['p95Ms']/1000:.1f}초, {w['count']}건"
            for w in by_worker
        ) or "  (데이터 없음)"

        # Fail by category
        fail_cats = q.get("failByCategory", [])[:5]
        fail_str = "\n".join(
            f"  - {c['category']}: {c['failCount']}건 (실패율 {c['failRate']}%)"
            for c in fail_cats if c.get("failCount", 0) > 0
        ) or "  (실패 없음)"

        # Daily trend summary
        trend = ov.get("daily_trend", [])
        trend_summary = ""
        if trend:
            peak = max(trend, key=lambda d: d["messages"])
            low = min(trend, key=lambda d: d["messages"])
            trend_summary = f"- 피크일: {peak['date']} ({peak['messages']}건), 최저일: {low['date']} ({low['messages']}건)\n"

        total_docs = art["pdfCount"] + art["xlsxCount"] + art["pptCount"]
        prev_total_docs = prev_art["pdfCount"] + prev_art["xlsxCount"] + prev_art["pptCount"]

        prompt = f"""당신은 AI 챗봇 서비스 운영 분석 전문가입니다.
아래 주간 서비스 운영 데이터를 기반으로 리포트의 각 섹션에 들어갈 전문적인 분석 코멘트를 작성하세요.

## 작성 규칙
1. 각 섹션별 2~3문장으로 작성
2. 단순 숫자 나열이 아닌 의미/시사점/트렌드 중심 분석
3. 전주 대비 변동이 크면 원인 추정이나 의미를 해석
4. **반드시 존댓말(합니다체)로 작성** ("~입니다", "~되었습니다", "~것으로 분석됩니다", "~필요합니다" 등)
5. 수치 인용 시 정확한 숫자 사용, 퍼센트 변동은 ▲(증가)/▼(감소) 기호 활용

## 현재 주 데이터
- 총 메시지: {ov['total_messages']:,}건 / 세션: {ov['total_sessions']:,}건 / 활성 사용자: {ov['active_users']}명
{trend_summary}- 실패: {q['failCount']}건 (실패율 {q['failRate']}%)
- 평균 응답: {perf['avgResponseMs']/1000:.1f}초 / P95: {perf['p95ResponseMs']/1000:.1f}초
- 생성 문서: PDF {art['pdfCount']}건, XLSX {art['xlsxCount']}건, PPT {art['pptCount']}건 (합계 {total_docs}건)
- 파일 업로드: {art['fileUploads']}건 / 활성 WS: {ws['activeWorkspaces']}개

## 전주 데이터
- 총 메시지: {prev_ov['total_messages']:,}건 / 세션: {prev_ov['total_sessions']:,}건 / 활성 사용자: {prev_ov['active_users']}명
- 실패: {prev_q['failCount']}건 (실패율 {prev_q['failRate']}%)
- 평균 응답: {prev_perf['avgResponseMs']/1000:.1f}초 / P95: {prev_perf['p95ResponseMs']/1000:.1f}초
- 생성 문서: 합계 {prev_total_docs}건 / 활성 사용자: {prev_users['totalUsers']}명

## 인텐트 분포 (현재 주)
{intent_str}

## 인텐트 분포 (전주)
{prev_intent_str}

## 카테고리별 실패
{fail_str}

## Worker별 성능
{worker_str}

## Top 5 사용자
{top_users_str}

## 출력
아래 JSON 형식으로만 응답하세요. JSON 외의 텍스트는 절대 포함하지 마세요.
{{"executive": "종합 분석 코멘트 (3~4문장, 전체 서비스 상태 요약 + 핵심 변동 지표 + 주의 사항이나 긍정 포인트)", "usage_trend": "이용량 트렌드 분석 (일평균 처리량, 피크일 분석, 전주 대비 추세 해석)", "intents": "인텐트 분포 분석 (주요 인텐트 비중 변화, 신규/성장 인텐트, 의미 해석)", "quality": "품질 지표 분석 (실패율 추이, 주요 실패 원인 카테고리, 개선 방향)", "users": "사용자 활동 분석 (활성 사용자 변동, 이용 패턴, 파워 유저 현황)", "artifacts": "워크스페이스/생성 콘텐츠 분석 (문서 생성 추이, 유형별 활용도)", "performance": "응답 성능 분석 (응답 시간 추이, 병목 Worker 식별, 최적화 소견)"}}"""

        bedrock = get_bedrock_service()
        response = await bedrock.generate_text(
            prompt=prompt,
            max_tokens=2000,
            temperature=0.4
        )

        logger.info(f"[ReportPDF] LLM summary response length: {len(response)}")

        # Parse JSON from response
        text = response.strip()

        # Try direct parse
        try:
            result = _json.loads(text)
            if isinstance(result, dict) and "executive" in result:
                return result
        except _json.JSONDecodeError:
            pass

        # Try extracting from code block
        match = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, _re.DOTALL)
        if match:
            try:
                result = _json.loads(match.group(1))
                if isinstance(result, dict):
                    return result
            except _json.JSONDecodeError:
                pass

        # Try finding JSON by balanced braces
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx >= 0 and end_idx > start_idx:
            try:
                result = _json.loads(text[start_idx:end_idx + 1])
                if isinstance(result, dict):
                    return result
            except _json.JSONDecodeError:
                pass

        logger.warning(f"[ReportPDF] Failed to parse LLM response: {text[:200]}")
        return {}

    def _get_summary(self, data: dict, key: str) -> str:
        """LLM 생성 요약 사용, 실패 시 템플릿 fallback"""
        llm_summaries = data.get("llm_summaries", {})
        if llm_summaries.get(key):
            return llm_summaries[key]
        # Template fallback
        fallback = {
            "executive": self._summary_executive,
            "usage_trend": self._summary_usage_trend,
            "intents": self._summary_intents,
            "quality": self._summary_quality,
            "users": self._summary_users,
            "artifacts": self._summary_artifacts,
            "performance": self._summary_performance,
        }
        method = fallback.get(key)
        return method(data) if method else ""

    # ─── 차트 생성 ───

    def _generate_charts(self, data: dict) -> dict:
        """모든 차트를 PNG로 생성, {이름: 파일경로} 반환"""
        charts = {}
        with plt.rc_context(CHART_RC):
            charts["usage_trend"] = self._chart_usage_trend(data["overview"])
            charts["intent_donut"] = self._chart_intent_donut(data["intents"])
            charts["user_bar"] = self._chart_user_bar(data["users"], data.get("user_info_map", {}))
            charts["artifacts_stack"] = self._chart_artifacts_stack(data["artifacts"])
            charts["performance_trend"] = self._chart_performance_trend(data["performance"])
        return charts

    def _save_chart(self, fig) -> str:
        """matplotlib Figure를 임시 PNG로 저장"""
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir=str(REPORT_OUTPUT_DIR))
        fig.savefig(tmp.name, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        return tmp.name

    def _chart_usage_trend(self, overview: dict) -> str:
        """일별 메시지/세션/사용자 라인 차트"""
        trend = overview.get("daily_trend", [])
        if not trend:
            return self._empty_chart("이용량 트렌드 (데이터 없음)")

        dates = [d["date"] for d in trend]
        messages = [d["messages"] for d in trend]
        sessions = [d["sessions"] for d in trend]
        users = [d["users"] for d in trend]

        fig, ax = plt.subplots(figsize=(10, 4.2))
        ax.grid(True, alpha=0.3, color=HEX_BORDER)
        ax.plot(dates, messages, color=HEX_BLUE, linewidth=2, marker="o", markersize=4, label="메시지")
        ax.plot(dates, sessions, color=HEX_GREEN, linewidth=2, marker="s", markersize=4, label="세션")
        ax.plot(dates, users, color=HEX_ORANGE, linewidth=2, marker="^", markersize=4, label="사용자")
        ax.set_title("일별 이용량 트렌드", fontsize=13, pad=10, fontweight="bold")
        ax.legend(loc="upper left", fontsize=10, facecolor=HEX_CARD, edgecolor=HEX_BORDER, labelcolor=HEX_TEXT)
        if len(dates) > 10:
            ax.set_xticks(range(0, len(dates), max(1, len(dates) // 7)))
        return self._save_chart(fig)

    def _chart_intent_donut(self, intents: dict) -> str:
        """인텐트 분포 도넛 차트 (대시보드 스타일)"""
        dist = intents.get("distribution", [])
        if not dist:
            return self._empty_chart("인텐트 분포 (데이터 없음)")

        top = dist[:8]
        if len(dist) > 8:
            others = sum(d["count"] for d in dist[8:])
            top.append({"name": "기타", "count": others})

        labels = [d["name"] for d in top]
        sizes = [d["count"] for d in top]
        colors = PIE_COLORS[:len(top)]
        total = sum(sizes)

        fig, ax = plt.subplots(figsize=(5.5, 5))
        wedges, texts, autotexts = ax.pie(
            sizes, labels=None,
            autopct=lambda p: f"{p:.1f}%" if p > 5 else "",
            colors=colors, startangle=90,
            wedgeprops={"width": 0.4, "linewidth": 2, "edgecolor": HEX_BG},
            pctdistance=0.78,
        )
        for t in autotexts:
            t.set_color(HEX_TEXT)
            t.set_fontsize(10)
            t.set_fontweight("bold")

        # 도넛 중앙 텍스트
        ax.text(0, 0.06, f"{total:,}", ha="center", va="center",
                fontsize=22, fontweight="bold", color=HEX_TEXT)
        ax.text(0, -0.12, "건", ha="center", va="center",
                fontsize=11, color=HEX_TEXT2)

        # 하단 범례 (2줄)
        ax.legend(
            wedges, labels, loc="upper center", bbox_to_anchor=(0.5, -0.02),
            ncol=min(5, len(labels)), fontsize=9,
            facecolor=HEX_CARD, edgecolor="none", labelcolor=HEX_TEXT,
            handlelength=1.0, handletextpad=0.4, columnspacing=1.0,
        )
        fig.subplots_adjust(bottom=0.15)
        return self._save_chart(fig)

    def _chart_quality_bar(self, quality: dict) -> str:
        """카테고리별 실패율 수평 바 차트"""
        cats = quality.get("failByCategory", [])
        cats = [c for c in cats if c["failCount"] > 0]
        if not cats:
            return self._empty_chart("품질 지표 (실패 없음)")

        cats = cats[:10]
        labels = [c["category"] for c in reversed(cats)]
        rates = [c["failRate"] for c in reversed(cats)]
        highlights = [c.get("isHighlight", False) for c in reversed(cats)]
        colors = [HEX_RED if h else HEX_BLUE for h in highlights]

        fig, ax = plt.subplots(figsize=(10, max(3, len(labels) * 0.5)))
        bars = ax.barh(labels, rates, color=colors, height=0.6)
        ax.set_xlabel("실패율 (%)", fontsize=11)
        ax.set_title("카테고리별 실패율", fontsize=13, pad=10, fontweight="bold")
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)

        for bar, rate in zip(bars, rates):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                    f"{rate}%", va="center", fontsize=10, color=HEX_TEXT)
        return self._save_chart(fig)

    def _chart_user_bar(self, users: dict, user_info_map: dict = None) -> str:
        """Top 10 사용자 수평 바 차트 — 부서/이름 라벨"""
        ranking = users.get("ranking", [])[:10]
        if not ranking:
            return self._empty_chart("사용자 랭킹 (데이터 없음)")

        labels = []
        for r in reversed(ranking):
            uid = r["userId"]
            info = (user_info_map or {}).get(uid)
            if info and info.get("name"):
                dept = info.get("dept_name", "")
                if len(dept) > 8:
                    dept = dept[:8] + ".."
                labels.append(f"{dept} {info['name']}" if dept else info["name"])
            else:
                labels.append(uid)
        counts = [r["messageCount"] for r in reversed(ranking)]

        fig, ax = plt.subplots(figsize=(10, max(3.5, len(labels) * 0.5)))
        bars = ax.barh(labels, counts, color=HEX_BLUE, height=0.6)
        ax.set_xlabel("메시지 수", fontsize=11)
        ax.set_title("Top 10 사용자", fontsize=13, pad=10, fontweight="bold")
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)

        for bar, cnt in zip(bars, counts):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                    str(cnt), va="center", fontsize=10, color=HEX_TEXT)
        return self._save_chart(fig)

    def _chart_artifacts_stack(self, artifacts: dict) -> str:
        """일별 PDF/XLSX/PPT 생성 스택 바 차트"""
        trend = artifacts.get("dailyTrend", [])
        if not trend:
            return self._empty_chart("생성 콘텐츠 트렌드 (데이터 없음)")

        dates = [d["date"] for d in trend]
        pdfs = [d["pdf"] for d in trend]
        xlsxs = [d["xlsx"] for d in trend]
        ppts = [d["ppt"] for d in trend]

        fig, ax = plt.subplots(figsize=(10, 4.2))
        ax.bar(dates, pdfs, label="PDF", color=HEX_ORANGE)
        ax.bar(dates, xlsxs, bottom=pdfs, label="XLSX", color=HEX_PURPLE)
        bottoms = [p + x for p, x in zip(pdfs, xlsxs)]
        ax.bar(dates, ppts, bottom=bottoms, label="PPT", color=HEX_BLUE)
        ax.set_title("일별 생성 콘텐츠", fontsize=13, pad=10, fontweight="bold")
        ax.legend(loc="upper left", fontsize=10, facecolor=HEX_CARD, edgecolor=HEX_BORDER, labelcolor=HEX_TEXT)
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)
        if len(dates) > 10:
            ax.set_xticks(range(0, len(dates), max(1, len(dates) // 7)))
        return self._save_chart(fig)

    def _chart_performance_trend(self, perf: dict) -> str:
        """평균/P95 응답시간 라인 차트"""
        trend = perf.get("dailyTrend", [])
        if not trend:
            return self._empty_chart("성능 트렌드 (데이터 없음)")

        dates = [d["date"] for d in trend]
        avgs = [d["avgResponse"] for d in trend]
        p95s = [d["p95Response"] for d in trend]

        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.grid(True, alpha=0.3, color=HEX_BORDER)
        ax.plot(dates, avgs, color=HEX_BLUE, linewidth=2, marker="o", markersize=4, label="평균")
        ax.plot(dates, p95s, color=HEX_ORANGE, linewidth=2, linestyle="--", marker="s", markersize=4, label="P95")
        ax.set_ylabel("응답 시간 (초)", fontsize=11)
        ax.set_title("응답 성능 트렌드", fontsize=13, pad=10, fontweight="bold")
        ax.legend(loc="upper left", fontsize=10, facecolor=HEX_CARD, edgecolor=HEX_BORDER, labelcolor=HEX_TEXT)
        if len(dates) > 10:
            ax.set_xticks(range(0, len(dates), max(1, len(dates) // 7)))
        return self._save_chart(fig)

    def _empty_chart(self, title: str) -> str:
        """데이터가 없을 때 빈 차트"""
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, title, ha="center", va="center", fontsize=12, color=HEX_TEXT2)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        return self._save_chart(fig)

    # ─── PDF 페이지 조합 ───

    def _page_cover(self, pdf: DashboardPDF, date_from: str, date_to: str):
        """1페이지: 표지"""
        pdf.add_page()
        pdf._fill_bg()

        cy = pdf.h / 2 - 20

        # LUCID AI 타이틀 (중앙 정렬, 1번만 렌더)
        pdf.set_font("korean", "B", 36)
        pdf.set_text_color(*C_BLUE)
        pdf.set_xy(0, cy - 15)
        pdf.cell(pdf.w, 0, "LUCID AI", align="C")

        pdf.set_font("korean", "B", 20)
        pdf.set_text_color(*C_TEXT_PRIMARY)
        pdf.set_xy(0, cy + 10)
        pdf.cell(pdf.w, 0, "Weekly Service Report", align="C")

        pdf.set_font("korean", "", 14)
        pdf.set_text_color(*C_TEXT_SECONDARY)
        pdf.set_xy(0, cy + 28)
        pdf.cell(pdf.w, 0, f"{date_from}  ~  {date_to}", align="C")

        pdf.set_font("korean", "", 10)
        pdf.set_xy(0, cy + 42)
        generated = datetime.now().strftime("%Y-%m-%d %H:%M")
        pdf.cell(pdf.w, 0, f"Generated: {generated}", align="C")

        # 하단 라인
        pdf.set_draw_color(*C_BLUE)
        pdf.set_line_width(1)
        lw = 80
        pdf.line(pdf.w / 2 - lw / 2, cy + 55, pdf.w / 2 + lw / 2, cy + 55)

    def _page_executive_summary(self, pdf: DashboardPDF, data: dict):
        """2페이지: Executive Summary — KPI 카드 6개 + WoW 배지 + 분석 텍스트"""
        pdf.add_page()
        pdf._fill_bg()
        pdf._section_title("Executive Summary")

        ov = data["overview"]
        prev_ov = data["prev"]["overview"]
        q = data["quality"]
        prev_q = data["prev"]["quality"]
        perf = data["performance"]
        prev_perf = data["prev"]["performance"]
        art = data["artifacts"]
        prev_art = data["prev"]["artifacts"]

        total_docs = art["pdfCount"] + art["xlsxCount"] + art["pptCount"]
        prev_docs = prev_art["pdfCount"] + prev_art["xlsxCount"] + prev_art["pptCount"]

        kpis = [
            ("총 메시지", f"{ov['total_messages']:,}", C_BLUE,
             self._calc_wow(ov["total_messages"], prev_ov["total_messages"])),
            ("총 세션", f"{ov['total_sessions']:,}", C_GREEN,
             self._calc_wow(ov["total_sessions"], prev_ov["total_sessions"])),
            ("활성 사용자", f"{ov['active_users']:,}", C_ORANGE,
             self._calc_wow(ov["active_users"], prev_ov["active_users"])),
            ("실패율", f"{q['failRate']}%", C_RED,
             self._calc_wow_inverted(q["failRate"], prev_q["failRate"])),
            ("평균 응답", f"{perf['avgResponseMs'] / 1000:.1f}초", C_PURPLE,
             self._calc_wow_inverted(perf["avgResponseMs"], prev_perf["avgResponseMs"])),
            ("생성 문서", f"{total_docs:,}", C_CYAN,
             self._calc_wow(total_docs, prev_docs)),
        ]

        card_w, card_h = 86, 50
        start_x, start_y, gap = 15, 25, 8

        for i, (label, value, color, wow) in enumerate(kpis):
            col = i % 3
            row = i // 3
            x = start_x + col * (card_w + gap)
            y = start_y + row * (card_h + gap)

            pdf._draw_card(x, y, card_w, card_h)
            pdf.set_fill_color(*color)
            pdf.rect(x, y, card_w, 3, "F")
            pdf._text(x + 8, y + 13, label, size=10, color=C_TEXT_SECONDARY)
            pdf._text(x + 8, y + 28, value, size=20, color=color, bold=True)
            # WoW 배지
            pdf._text(x + 8, y + 40, f"{wow['symbol']} {wow['pct']}%", size=8, color=wow["color"])

        # 분석 텍스트 카드 (LLM 생성, 하단 배치)
        summary = self._get_summary(data, "executive")
        total_w = 3 * card_w + 2 * gap  # KPI 그리드와 동일 너비 (274)
        pdf._draw_card(start_x, 140, total_w, 52)
        pdf._summary_text(start_x + 5, 140, summary, width=total_w - 10, card_h=52, line_height=5)

    def _page_usage_trend(self, pdf: DashboardPDF, data: dict, charts: dict):
        """3페이지: 이용량 트렌드 — 차트 + 분석 (하단)"""
        pdf.add_page()
        pdf._fill_bg()
        pdf._section_title("이용량 트렌드")

        # 차트 (카드 안에 배치)
        pdf._draw_card(15, 22, 267, 142)
        chart_path = charts.get("usage_trend")
        if chart_path and os.path.exists(chart_path):
            pdf._fit_image(chart_path, 30, 25, 237, 136)

        # 분석 카드 (하단 고정)
        summary = self._get_summary(data, "usage_trend")
        pdf._draw_card(15, 170, 267, 27)
        pdf._summary_text(20, 170, summary, width=257)

    def _page_intent_distribution(self, pdf: DashboardPDF, data: dict, charts: dict):
        """4페이지: 인텐트 분포 — 대시보드 스타일 (도넛 차트 카드 + 상세 테이블 카드)"""
        pdf.add_page()
        pdf._fill_bg()
        pdf._section_title("의도 분류 분포")

        # ── 좌측 카드: 카테고리별 비율 (도넛 차트) ──
        left_x, card_y, left_w, card_h = 15, 27, 135, 138
        pdf._draw_card(left_x, card_y, left_w, card_h)
        pdf._text(left_x + 8, card_y + 6, "카테고리별 비율", size=10, color=C_TEXT_SECONDARY)

        chart_path = charts.get("intent_donut")
        if chart_path and os.path.exists(chart_path):
            pdf._fit_image(chart_path, left_x + 5, card_y + 12, left_w - 10, card_h - 16)

        # ── 우측 카드: 카테고리별 상세 테이블 ──
        right_x, right_w = 155, 127
        pdf._draw_card(right_x, card_y, right_w, card_h)
        pdf._text(right_x + 8, card_y + 6, "카테고리별 상세", size=10, color=C_TEXT_SECONDARY)

        dist = data["intents"].get("distribution", [])
        if dist:
            table_x = right_x + 6
            table_y = card_y + 14
            col_name_w = 54
            col_count_w = 26
            col_ratio_w = 24
            row_h = 8.2

            # 테이블 헤더
            pdf.set_font("korean", "B", 9)
            pdf.set_text_color(*C_TEXT_SECONDARY)
            pdf.set_xy(table_x + 10, table_y)
            pdf.cell(col_name_w, 5, "카테고리")
            pdf.cell(col_count_w, 5, "건수", align="R")
            pdf.cell(col_ratio_w, 5, "비율", align="R")

            # 헤더 구분선
            pdf.set_draw_color(*C_BORDER)
            pdf.set_line_width(0.3)
            pdf.line(table_x, table_y + 6, table_x + col_name_w + col_count_w + col_ratio_w + 10, table_y + 6)

            # 테이블 본문 (카드 높이 내 맞춤: card_h=138, 헤더~14px, row_h=8.2 → max 13행)
            max_rows = min(len(dist), 13)
            pdf.set_font("korean", "", 9)
            for i, d in enumerate(dist[:max_rows]):
                row_y = table_y + 8 + i * row_h
                pdf.set_text_color(*C_TEXT_PRIMARY)

                # 컬러 도트
                color_idx = i if i < len(PIE_COLORS) else len(PIE_COLORS) - 1
                hex_c = PIE_COLORS[color_idx]
                r_c = int(hex_c[1:3], 16)
                g_c = int(hex_c[3:5], 16)
                b_c = int(hex_c[5:7], 16)
                pdf.set_fill_color(r_c, g_c, b_c)
                dot_y = row_y + 1.8
                pdf.ellipse(table_x + 2, dot_y, 3, 3, "F")

                # 카테고리명
                pdf.set_xy(table_x + 10, row_y)
                pdf.cell(col_name_w, 5, d["name"])

                # 건수 (볼드)
                pdf.set_font("korean", "B", 9)
                pdf.cell(col_count_w, 5, f"{d['count']:,}", align="R")

                # 비율
                pdf.set_font("korean", "", 9)
                pdf.set_text_color(*C_TEXT_SECONDARY)
                pdf.cell(col_ratio_w, 5, f"{d['ratio']}%", align="R")

        # ── 분석 카드 (하단 고정) ──
        summary = self._get_summary(data, "intents")
        pdf._draw_card(15, 170, 267, 27)
        pdf._summary_text(20, 170, summary, width=257)

    def _page_quality(self, pdf: DashboardPDF, data: dict, charts: dict):
        """5페이지: 품질 지표 — KPI + 차트 + 분석 (하단)"""
        pdf.add_page()
        pdf._fill_bg()
        pdf._section_title("품질 지표")

        quality = data["quality"]
        prev_q = data["prev"]["quality"]

        # KPI 카드 2개 (WoW 배지 포함)
        kpis = [
            ("실패 건수", f"{quality['failCount']:,}건", C_RED,
             self._calc_wow_inverted(quality["failCount"], prev_q["failCount"])),
            ("실패율", f"{quality['failRate']}%", C_RED,
             self._calc_wow_inverted(quality["failRate"], prev_q["failRate"])),
        ]
        for i, (label, value, color, wow) in enumerate(kpis):
            x = 15 + i * 70
            pdf._draw_card(x, 22, 60, 32)
            pdf.set_fill_color(*color)
            pdf.rect(x, 22, 60, 2, "F")
            pdf._text(x + 5, 30, label, size=9, color=C_TEXT_SECONDARY)
            pdf._text(x + 5, 40, value, size=14, color=color, bold=True)
            pdf._text(x + 5, 48, f"{wow['symbol']} {wow['pct']}%", size=8, color=wow["color"])

        # 차트 (카드 안에 중앙 배치, 좌우 여유 확보)
        pdf._draw_card(15, 58, 267, 107)
        chart_path = charts.get("quality_bar")
        if chart_path and os.path.exists(chart_path):
            pdf._fit_image(chart_path, 30, 61, 237, 100)

        # 분석 카드 (하단 고정)
        summary = self._get_summary(data, "quality")
        pdf._draw_card(15, 170, 267, 27)
        pdf._summary_text(20, 170, summary, width=257)

    def _page_user_ranking(self, pdf: DashboardPDF, data: dict, charts: dict):
        """6페이지: 사용자 랭킹 — KPI + WoW + 요약 + 부서/이름 차트"""
        pdf.add_page()
        pdf._fill_bg()
        pdf._section_title("사용자 랭킹")

        users = data["users"]
        prev_users = data["prev"]["users"]
        ov = data["overview"]
        prev_ov = data["prev"]["overview"]

        # KPI 카드 3개 (WoW 포함)
        card_w, card_gap = 80, 10

        # 1) 전체 사용자
        user_wow = self._calc_wow(users["totalUsers"], prev_users["totalUsers"])
        x1 = 15
        pdf._draw_card(x1, 22, card_w, 28)
        pdf._text(x1 + 5, 28, "전체 사용자", size=9, color=C_TEXT_SECONDARY)
        pdf._text(x1 + 5, 37, f"{users['totalUsers']:,}명", size=14, color=C_BLUE, bold=True)
        pdf._text(x1 + 5, 44, f"{user_wow['symbol']} {user_wow['pct']}%", size=8, color=user_wow["color"])

        # 2) 인당 평균 메시지
        avg_msg = users["totalMessages"] // max(users["totalUsers"], 1)
        prev_avg = prev_users["totalMessages"] // max(prev_users["totalUsers"], 1)
        avg_wow = self._calc_wow(avg_msg, prev_avg)
        x2 = x1 + card_w + card_gap
        pdf._draw_card(x2, 22, card_w, 28)
        pdf._text(x2 + 5, 28, "인당 평균 메시지", size=9, color=C_TEXT_SECONDARY)
        pdf._text(x2 + 5, 37, f"{avg_msg:,}건", size=14, color=C_GREEN, bold=True)
        pdf._text(x2 + 5, 44, f"{avg_wow['symbol']} {avg_wow['pct']}%", size=8, color=avg_wow["color"])

        # 3) 인당 평균 세션
        avg_sess = ov["total_sessions"] // max(ov["active_users"], 1)
        prev_avg_sess = prev_ov["total_sessions"] // max(prev_ov["active_users"], 1)
        sess_wow = self._calc_wow(avg_sess, prev_avg_sess)
        x3 = x2 + card_w + card_gap
        pdf._draw_card(x3, 22, card_w, 28)
        pdf._text(x3 + 5, 28, "인당 평균 세션", size=9, color=C_TEXT_SECONDARY)
        pdf._text(x3 + 5, 37, f"{avg_sess:,}건", size=14, color=C_ORANGE, bold=True)
        pdf._text(x3 + 5, 44, f"{sess_wow['symbol']} {sess_wow['pct']}%", size=8, color=sess_wow["color"])

        # 차트 (카드 안에 배치 - 부서/이름 라벨)
        pdf._draw_card(15, 55, 267, 110)
        chart_path = charts.get("user_bar")
        if chart_path and os.path.exists(chart_path):
            pdf._fit_image(chart_path, 30, 58, 237, 103)

        # 분석 카드 (하단 고정)
        summary = self._get_summary(data, "users")
        pdf._draw_card(15, 170, 267, 27)
        pdf._summary_text(20, 170, summary, width=257)

    def _page_artifacts(self, pdf: DashboardPDF, data: dict, charts: dict):
        """7페이지: 워크스페이스 & 생성 콘텐츠 — KPI + 요약 + 차트"""
        pdf.add_page()
        pdf._fill_bg()
        pdf._section_title("워크스페이스 & 생성 콘텐츠")

        ws = data["workspaces"]
        art = data["artifacts"]

        # KPI 카드 5개
        kpis = [
            ("활성 WS", f"{ws['activeWorkspaces']}", C_BLUE),
            ("파일 업로드", f"{art['fileUploads']}", C_GREEN),
            ("PDF", f"{art['pdfCount']}", C_ORANGE),
            ("XLSX", f"{art['xlsxCount']}", C_PURPLE),
            ("PPT", f"{art['pptCount']}", C_BLUE),
        ]
        for i, (label, value, color) in enumerate(kpis):
            x = 15 + i * 55
            pdf._draw_card(x, 22, 48, 25)
            pdf.set_fill_color(*color)
            pdf.rect(x, 22, 48, 2, "F")
            pdf._text(x + 4, 28, label, size=8, color=C_TEXT_SECONDARY)
            pdf._text(x + 4, 38, value, size=14, color=color, bold=True)

        # 차트 (카드 안에 배치)
        pdf._draw_card(15, 52, 267, 113)
        chart_path = charts.get("artifacts_stack")
        if chart_path and os.path.exists(chart_path):
            pdf._fit_image(chart_path, 30, 55, 237, 106)

        # 분석 카드 (하단 고정)
        summary = self._get_summary(data, "artifacts")
        pdf._draw_card(15, 170, 267, 27)
        pdf._summary_text(20, 170, summary, width=257)

    def _page_performance(self, pdf: DashboardPDF, data: dict, charts: dict):
        """8페이지: 응답 성능 — KPI + WoW + 요약/분석 + 차트 + Worker 테이블"""
        pdf.add_page()
        pdf._fill_bg()
        pdf._section_title("응답 성능")

        perf = data["performance"]
        prev_perf = data["prev"]["performance"]
        by_worker = perf.get("byWorker", [])

        # KPI 카드 4개
        avg_sec = perf["avgResponseMs"] / 1000
        p95_sec = perf["p95ResponseMs"] / 1000
        prev_avg_sec = prev_perf["avgResponseMs"] / 1000
        prev_p95_sec = prev_perf["p95ResponseMs"] / 1000

        # 최다 호출 에이전트 (count 기준)
        most_called = max(by_worker, key=lambda w: w["count"]) if by_worker else None
        # 최대 지연 에이전트 (avgMs 기준, 이미 DESC 정렬)
        slowest = by_worker[0] if by_worker else None

        card_w, card_gap = 63, 5
        # 1) 평균 응답
        x = 15
        avg_wow = self._calc_wow_inverted(avg_sec, prev_avg_sec)
        pdf._draw_card(x, 22, card_w, 32)
        pdf.set_fill_color(*C_BLUE)
        pdf.rect(x, 22, card_w, 2, "F")
        pdf._text(x + 5, 30, "평균 응답", size=9, color=C_TEXT_SECONDARY)
        pdf._text(x + 5, 40, f"{avg_sec:.1f}초", size=14, color=C_BLUE, bold=True)
        pdf._text(x + 5, 48, f"{avg_wow['symbol']} {avg_wow['pct']}%", size=8, color=avg_wow["color"])

        # 2) P95 응답
        x = 15 + (card_w + card_gap)
        p95_wow = self._calc_wow_inverted(p95_sec, prev_p95_sec)
        pdf._draw_card(x, 22, card_w, 32)
        pdf.set_fill_color(*C_ORANGE)
        pdf.rect(x, 22, card_w, 2, "F")
        pdf._text(x + 5, 30, "P95 응답", size=9, color=C_TEXT_SECONDARY)
        pdf._text(x + 5, 40, f"{p95_sec:.1f}초", size=14, color=C_ORANGE, bold=True)
        pdf._text(x + 5, 48, f"{p95_wow['symbol']} {p95_wow['pct']}%", size=8, color=p95_wow["color"])

        # 3) 최다 호출 에이전트
        x = 15 + 2 * (card_w + card_gap)
        pdf._draw_card(x, 22, card_w, 32)
        pdf.set_fill_color(*C_GREEN)
        pdf.rect(x, 22, card_w, 2, "F")
        pdf._text(x + 5, 30, "최다 호출", size=9, color=C_TEXT_SECONDARY)
        if most_called:
            mc_name = most_called["worker"]
            if len(mc_name) > 10:
                mc_name = mc_name[:10] + ".."
            pdf._text(x + 5, 39, mc_name, size=10, color=C_GREEN, bold=True)
            pdf._text(x + 5, 48, f"{most_called['count']:,}건", size=8, color=C_TEXT_SECONDARY)
        else:
            pdf._text(x + 5, 39, "-", size=14, color=C_TEXT_SECONDARY, bold=True)

        # 4) 최대 지연 에이전트
        x = 15 + 3 * (card_w + card_gap)
        pdf._draw_card(x, 22, card_w, 32)
        pdf.set_fill_color(*C_RED)
        pdf.rect(x, 22, card_w, 2, "F")
        pdf._text(x + 5, 30, "최대 지연", size=9, color=C_TEXT_SECONDARY)
        if slowest:
            sl_name = slowest["worker"]
            if len(sl_name) > 10:
                sl_name = sl_name[:10] + ".."
            pdf._text(x + 5, 39, sl_name, size=10, color=C_RED, bold=True)
            pdf._text(x + 5, 48, f"평균 {slowest['avgMs']/1000:.1f}초", size=8, color=C_TEXT_SECONDARY)
        else:
            pdf._text(x + 5, 39, "-", size=14, color=C_TEXT_SECONDARY, bold=True)

        # 차트 (왼쪽 카드)
        pdf._draw_card(15, 58, 150, 107)
        chart_path = charts.get("performance_trend")
        if chart_path and os.path.exists(chart_path):
            pdf._fit_image(chart_path, 20, 61, 140, 100)

        # Worker별 테이블 (오른쪽 카드 — 다크 테마)
        if by_worker:
            pdf._draw_card(170, 58, 112, 107)
            table_x = 173
            table_y = 62
            col_w = [44, 23, 23, 15]

            # 헤더
            pdf.set_font("korean", "B", 8.5)
            pdf.set_text_color(*C_TEXT_SECONDARY)
            pdf.set_xy(table_x, table_y)
            pdf.cell(col_w[0], 4, "Worker")
            pdf.cell(col_w[1], 4, "평균(ms)", align="R")
            pdf.cell(col_w[2], 4, "P95(ms)", align="R")
            pdf.cell(col_w[3], 4, "건수", align="R")

            # 헤더 구분선
            pdf.set_draw_color(*C_BORDER)
            pdf.set_line_width(0.3)
            pdf.line(table_x, table_y + 5.5, table_x + sum(col_w), table_y + 5.5)

            pdf.set_font("korean", "", 8)
            for i, w in enumerate(by_worker[:13]):
                row_y = table_y + 7 + i * 7.5
                pdf.set_text_color(*C_TEXT_PRIMARY)

                worker_name = w["worker"]
                if len(worker_name) > 18:
                    worker_name = worker_name[:18] + ".."
                pdf.set_xy(table_x, row_y)
                pdf.cell(col_w[0], 4, worker_name)

                pdf.set_font("korean", "B", 8)
                pdf.cell(col_w[1], 4, f"{w['avgMs']:,}", align="R")
                pdf.cell(col_w[2], 4, f"{w['p95Ms']:,}", align="R")

                pdf.set_font("korean", "", 8)
                pdf.set_text_color(*C_TEXT_SECONDARY)
                pdf.cell(col_w[3], 4, f"{w['count']:,}", align="R")

        # 분석 카드 (하단 고정)
        summary = self._get_summary(data, "performance")
        pdf._draw_card(15, 170, 267, 27)
        pdf._summary_text(20, 170, summary, width=257)


# ─── 싱글턴 ───
_report_pdf_service: Optional[ReportPDFService] = None


def get_report_pdf_service() -> ReportPDFService:
    global _report_pdf_service
    if _report_pdf_service is None:
        _report_pdf_service = ReportPDFService()
    return _report_pdf_service
