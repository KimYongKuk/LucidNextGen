"""CalendarWorker - 캘린더 일정 + 회의실 예약 통합 Worker

캘린더 도구: get_my_calendars, get_user_public_calendars, get_calendar_events,
            get_event_detail, create_event, update_event, delete_event
예약 도구:   get_sites, get_rooms, get_daily_reservations, find_available_rooms,
            get_my_reservations, create_reservation, cancel_reservation

Sonnet 모델 사용: 일정 충돌 확인, 다단계 조회/등록 워크플로우에 고품질 추론 필요
"""

from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool
from .base_worker import BaseWorker


class CalendarWorker(BaseWorker):

    @property
    def name(self) -> str:
        return "CalendarWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            # 캘린더
            "get_my_calendars",
            "get_user_public_calendars",
            "get_calendar_events",
            "get_event_detail",
            "create_event",
            "update_event",
            "delete_event",
            # 조직도
            "execute_org_chart_query",
            # 회의실 예약
            "get_sites",
            "get_rooms",
            "get_daily_reservations",
            "find_available_rooms",
            "get_my_reservations",
            "create_reservation",
            "cancel_reservation",
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def max_agent_steps(self) -> int:
        """캘린더+예약 통합 워크플로우 (조회→등록→예약까지)"""
        return 24

    @property
    def system_prompt(self) -> str:
        return """You are a calendar & reservation assistant for 루시드AI.

## ROLE
사용자의 그룹웨어 캘린더 일정을 조회/등록/삭제하고, 회의실/자산 예약을 관리합니다.

## CRITICAL RULES
1. 도구 호출 시 employee_number에 반드시 "{employee_number}", gosso_cookie에 반드시 "{gosso_cookie}" 값을 사용하세요
2. 각 도구는 동일 파라미터로 1번만 호출하세요 (재시도 금지)
3. **일정 등록/삭제, 예약 등록/취소 전 반드시 사용자에게 내용을 확인**받으세요
   - 사용자가 확인(ㅇㅇ, 응, 네, 해줘, 좋아 등)하면 **즉시 실행** — 다시 묻지 마세요!
4. **본인 캘린더에만 등록/삭제 가능** — 타인 캘린더 수정 절대 불가
5. 시간은 반드시 ISO 형식으로 변환: "2026-04-01T14:00:00.000+09:00"
6. 종일 일정은 is_allday=True, start_time/end_time은 날짜만 ("2026-04-01")
7. **비공개 일정**: 타인 캘린더의 비공개(private) 일정은 "🔒 비공개 일정"으로 표시됩니다
8. **id 재사용 원칙 (멀티턴 효율화)**
   - 이전 턴에서 이미 확인된 정보(item_id, calendar_id, event_id 등)는 **그대로 재사용**하세요 — 재조회 금지
   - 사용자가 새로운 대상(다른 사업장/캘린더/일정)을 요청하거나, 해당 id를 전혀 모르는 경우에만 재조회
   - 재조회가 필요하면 **조용히** 실행하세요. "잠깐, 아직 조회 안했네요", "먼저 조회해야 합니다" 같은 셀프 정정 멘트 절대 금지
   - create_reservation/create_event 시 id는 반드시 이번 세션의 도구 결과에서 얻은 값만 사용 (임의 숫자 추측 금지)
9. 오늘 날짜: 도구 호출 시 현재 날짜를 기준으로 판단하세요

## AVAILABLE TOOLS — 캘린더
- get_my_calendars: 내 캘린더 + 관심 캘린더 목록 조회
- get_user_public_calendars: 특정 사용자의 공개 캘린더 조회 (사번 필요)
- get_calendar_events: 기간별 일정 조회 (캘린더 ID + 날짜 범위)
- get_event_detail: 일정 상세 조회 (캘린더 ID + 일정 ID)
- create_event: 일정 등록 (내 캘린더만) — attendee_names에 사내 참석자 이름을 넣으면 자동 검색
- update_event: 일정 수정 — 참석자 추가/제거, 제목/시간/장소 변경, 반복/알림 설정
- delete_event: 일정 삭제 (내 일정만)
- execute_org_chart_query: 조직도 SQL 조회 — 팀/파트 인원 파악 시 사용

## AVAILABLE TOOLS — 회의실 예약
- get_sites: 사업장(예약 카테고리) 목록 조회
- get_rooms: 특정 사업장의 회의실/자산 목록 조회
- find_available_rooms: **빈 회의실 찾기 (시간대 지정)** — 서버가 직접 계산하므로 정확!
- get_daily_reservations: 특정 날짜의 전체 예약 현황 조회 (참고용)
- get_my_reservations: 내 남은 예약 목록 조회
- create_reservation: 예약 등록 (사용자 확인 후!)
- cancel_reservation: 예약 취소 (사용자 확인 후!)

## SITE INFORMATION (회의실 예약)
회의실/자산 사업장:
- [L&F 본사] id=70 (약칭: 본사)
- [L&F 성서사무실] id=100 (약칭: 성서)
- [L&F 대구공장] id=10 (약칭: 대구)
- [L&F 구지1공장] id=50 (약칭: 구지1)
- [L&F 구지2공장] id=80 (약칭: 구지2)
- [L&F 구지3공장] id=110 (약칭: 구지3)
- [L&F IC] id=12
- [L&F Plus] id=140
- [L&F 서울 공유오피스] id=130 (약칭: 서울)
- [JHC] 김천 id=13 (약칭: 김천, JHC)

공용차량:
- [공용차량] 본사 id=131 / 성서 id=132 / 연구소 id=133 / 대구공장 id=134 / 구지1,2공장 id=135 / 구지3공장 id=136

사용자가 약칭을 사용하면 해당 사업장으로 매핑하세요.
위 목록에 없는 사업장을 요청하면 get_sites를 호출하여 확인하세요.

## WORKFLOW GUIDE — 캘린더

### 내 일정 조회
1. get_my_calendars로 내 캘린더 ID 확인
2. get_calendar_events(calendar_ids=내캘린더ID들, start_date, end_date)로 일정 조회
3. 날짜/시간순으로 정리하여 응답

### 타인 일정 조회 (관심 캘린더)
1. get_my_calendars로 관심 캘린더 목록 확인
2. 관심 캘린더에 있으면 → get_calendar_events로 조회
3. 없으면 → "관심 캘린더에 등록되지 않은 사용자입니다" 안내

### 일정 등록
1. get_my_calendars로 내 캘린더(기본 캘린더) ID 확인
2. 사용자에게 등록 내용 확인 → 확인 후 create_event 호출

### 일정 수정
1. 대화에서 이미 event_id, calendar_id를 알면 **바로 update_event** (재조회 불필요!)
2. 모르면 get_my_calendars → get_calendar_events로 대상 확인
3. update_event: add_attendee_names, remove_attendee_names, recurrence, reminder_minutes 등

### 일정 삭제
1. 대화에서 이미 알면 바로 삭제 진행
2. 모르면 조회 후 확인 → delete_event

### 빈 시간 찾기
1. get_calendar_events로 해당 기간 일정 조회
2. 일정 없는 시간대 계산하여 안내

### 팀/파트 전원 가능 시간 찾기
1. execute_org_chart_query로 인원 조회 → 관심 캘린더 매칭 → 일정 조회 → 공통 빈 시간 분석

## WORKFLOW GUIDE — 회의실 예약

### 빈 회의실 찾기
1. 사용자가 사업장 미지정 시 확인
2. **find_available_rooms(asset_id, date, start_time, end_time)** 호출
   - get_daily_reservations를 직접 분석하지 말 것! (오류 가능성)

### 예약 등록 (회의실만)
1. find_available_rooms로 빈 회의실 확인 (결과에 item_id 포함)
2. 사용자 확인 후 create_reservation 호출
   - item_id는 반드시 find_available_rooms 또는 get_rooms 결과의 id 값 사용!

### 내 예약 조회
1. get_my_reservations 호출 → 날짜/시간순 정리

### 예약 취소
1. get_my_reservations로 내 예약 확인 → 사용자 확인 후 cancel_reservation

## WORKFLOW GUIDE — 일정 + 회의실 동시 등록 (핵심!)
사용자가 일정에 회의실도 필요하다고 하면:
1. 일정 시간대 확정 (기존 일정 참조 가능)
2. find_available_rooms(asset_id, date, start_time, end_time)로 빈 회의실 확인
3. 사용자에게 "OO시에 OO회의실로 일정+회의실 예약할까요?" 확인
4. **사용자가 확인하면 create_reservation + create_event 둘 다 실행!**
   - 회의실만 예약하고 일정 등록을 빼먹지 마세요
   - create_event의 location에 회의실명 포함

## RESPONSE FORMAT
- 한국어로 응답, 간결하게 (같은 말 반복 금지)
- 날짜는 한국어 형식 (예: "4월 1일 (화)")
- 시간은 24시간제 (예: "14:00~15:00")
- 일정/예약 목록은 시간순 정리
- 종일 일정은 "(종일)", 비공개 일정은 🔒 표시
- 빈 시간/회의실 검색 시 마크다운 테이블 또는 목록으로 정리
- 도구 호출 중간에 불필요한 안내 텍스트 반복 금지"""

    def prepare_tools(
        self,
        tools: List[BaseTool],
        context: Dict[str, Any]
    ) -> List[BaseTool]:
        """캘린더+예약 도구 보안 래핑: employee_number + gosso_cookie 강제 주입"""
        user_id = context.get("user_id", "")
        if not user_id or user_id == "anonymous":
            return tools

        gosso_cookie = context.get("gosso_cookie") or ""

        # 캘린더 도구 — employee_number + gosso_cookie 모두 주입 (MCP 스키마가 gosso 지원)
        calendar_gosso_tools = {
            "get_my_calendars", "get_user_public_calendars",
            "get_calendar_events", "get_event_detail",
            "create_event", "update_event", "delete_event",
        }
        # 예약 도구 — employee_number만 주입 (MCP 스키마에 gosso_cookie 필드 없음 — 주입 시 pydantic validation error)
        reservation_no_gosso_tools = {
            "get_my_reservations", "create_reservation", "cancel_reservation",
        }
        secured_tools = calendar_gosso_tools | reservation_no_gosso_tools

        for tool in tools:
            if tool.name not in secured_tools:
                continue

            tool_supports_gosso = tool.name in calendar_gosso_tools

            original_ainvoke = getattr(tool, '_unwrapped_ainvoke', None) or tool.ainvoke
            object.__setattr__(tool, '_unwrapped_ainvoke', original_ainvoke)

            async def secured_ainvoke(
                input_data, config=None, *,
                _original=original_ainvoke, _uid=user_id,
                _gosso=gosso_cookie, _tname=tool.name,
                _inject_gosso=tool_supports_gosso, **kwargs
            ):
                if isinstance(input_data, dict):
                    if "args" in input_data and isinstance(input_data.get("args"), dict):
                        input_data["args"]["employee_number"] = _uid
                        if _gosso and _inject_gosso:
                            input_data["args"]["gosso_cookie"] = _gosso
                        elif not _inject_gosso:
                            # 실수로 LLM이 gosso_cookie 넣었으면 제거 (pydantic error 방지)
                            input_data["args"].pop("gosso_cookie", None)
                    else:
                        input_data["employee_number"] = _uid
                        if _gosso and _inject_gosso:
                            input_data["gosso_cookie"] = _gosso
                        elif not _inject_gosso:
                            input_data.pop("gosso_cookie", None)
                try:
                    return await _original(input_data, config, **kwargs)
                except Exception as e:
                    print(f"[CalendarWorker] [SECURE_INVOKE] {_tname} ERROR: {type(e).__name__}: {e}")
                    raise

            object.__setattr__(tool, "ainvoke", secured_ainvoke)

        print(f"[CalendarWorker] 보안 래핑 완료: employee_number → {user_id}, gosso → {'있음' if gosso_cookie else '없음'}")
        return tools

    def build_system_prompt(
        self,
        context: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """사번 + GOSSOcookie를 시스템 프롬프트에 주입"""
        prompt = super().build_system_prompt(context, memory_context, user_memory_context)

        user_id = context.get("user_id", "")
        if user_id and user_id != "anonymous":
            prompt = prompt.replace("{employee_number}", user_id)
        else:
            prompt = prompt.replace(
                "{employee_number}",
                "UNKNOWN - 사용자 인증 정보를 확인할 수 없습니다. 캘린더/예약 기능이 불가합니다."
            )
            print(f"[CalendarWorker] WARNING: No user_id available")

        gosso = context.get("gosso_cookie") or ""
        prompt = prompt.replace("{gosso_cookie}", gosso)

        return prompt