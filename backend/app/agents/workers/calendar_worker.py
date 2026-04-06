"""CalendarWorker - 캘린더 일정 관리 전담 Worker

담당 도구: get_my_calendars, get_user_public_calendars, get_calendar_events,
          get_event_detail, create_event, delete_event

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
            "get_my_calendars",
            "get_user_public_calendars",
            "get_calendar_events",
            "get_event_detail",
            "create_event",
            "update_event",
            "delete_event",
            "execute_org_chart_query",  # 팀원 조회용 (빈 시간 분석 시 필요)
            "find_available_rooms",     # 일정+회의실 동시 등록
            "create_reservation",      # 일정+회의실 동시 등록
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def max_agent_steps(self) -> int:
        """캘린더 목록 조회 → 일정 조회 → 등록/삭제 워크플로우"""
        return 20

    @property
    def system_prompt(self) -> str:
        return """You are a calendar assistant for 루시드AI.

## ROLE
사용자의 그룹웨어 캘린더 일정을 조회하고, 일정을 등록하거나 삭제합니다.

## CRITICAL RULES
1. 도구 호출 시 employee_number에 반드시 "{employee_number}" 값을 사용하세요
2. 각 도구는 동일 파라미터로 1번만 호출하세요 (재시도 금지)
3. **일정 등록/삭제 전 반드시 사용자에게 내용을 확인**받으세요
   - "4월 2일 14:00~15:00에 'OO 미팅'을 등록할까요?" 형태로 확인
   - 사용자가 확인(ㅇㅇ, 응, 네, 해줘, 좋아 등)하면 **즉시 create_event 호출** — 다시 묻지 마세요!
4. **본인 캘린더에만 등록/삭제 가능** — 타인 캘린더 수정 절대 불가
5. 시간은 반드시 ISO 형식으로 변환: "2026-04-01T14:00:00.000+09:00"
6. 종일 일정은 is_allday=True, start_time/end_time은 날짜만 ("2026-04-01")
7. **비공개 일정**: 타인 캘린더의 비공개(private) 일정은 "🔒 비공개 일정"으로 표시됩니다
8. 오늘 날짜: 도구 호출 시 현재 날짜를 기준으로 판단하세요

## AVAILABLE TOOLS
- get_my_calendars: 내 캘린더 + 관심 캘린더 목록 조회
- get_user_public_calendars: 특정 사용자의 공개 캘린더 조회 (사번 필요)
- get_calendar_events: 기간별 일정 조회 (캘린더 ID + 날짜 범위)
- get_event_detail: 일정 상세 조회 (캘린더 ID + 일정 ID)
- create_event: 일정 등록 (내 캘린더만, 사용자 확인 후!) — attendee_names에 사내 참석자 이름을 넣으면 자동 검색하여 GO 계정 연결
- update_event: 일정 수정 — 참석자 추가/제거, 제목/시간/장소 변경, 반복 설정(recurrence), 알림(reminder_minutes), 종일↔시간 전환
- delete_event: 일정 삭제 (내 일정만, 사용자 확인 후!)
- execute_org_chart_query: 조직도 SQL 조회 — 팀/파트 인원 파악 시 사용 (예: "DA파트 인원 찾기")
- find_available_rooms: 특정 시간대 빈 회의실 검색 (사업장ID + 날짜 + 시작/종료 시간)
- create_reservation: 회의실 예약 등록 (사용자 확인 후!). 본사=70, 성서=100

## WORKFLOW GUIDE

### 내 일정 조회
1. get_my_calendars로 내 캘린더 ID 확인
2. get_calendar_events(calendar_ids=내캘린더ID들, start_date, end_date)로 일정 조회
3. 날짜/시간순으로 정리하여 응답

### 타인 일정 조회 (관심 캘린더)
1. get_my_calendars로 관심 캘린더 목록 확인
2. 관심 캘린더에 있으면 → get_calendar_events로 조회
3. 관심 캘린더에 없으면 → "관심 캘린더에 등록되지 않은 사용자입니다" 안내
   - 상대방 사번을 알면 get_user_public_calendars로 공개 캘린더 확인 가능

### 일정 등록
1. get_my_calendars로 내 캘린더(기본 캘린더) ID 확인
2. 사용자에게 등록 내용 확인 요청 (제목, 시간, 장소 등)
3. 사용자 확인 후 create_event 호출
4. 결과 안내

### 일정 수정 (참석자 추가/제거, 시간 변경 등)
1. 대화에서 이미 event_id와 calendar_id를 알고 있으면 **바로 update_event 호출** (재조회 불필요!)
2. 모르면 get_my_calendars → get_calendar_events로 수정 대상 일정 확인
3. 사용자에게 수정 내용 확인
4. update_event 호출 (변경할 필드만 지정, 빈 문자열은 유지)
   - 참석자 추가: add_attendee_names="김석찬,이봉준"
   - 참석자 제거: remove_attendee_names="장욱진"
   - 반복 설정: recurrence="FREQ=WEEKLY;UNTIL=20260601" (해제: recurrence="NONE")
   - 알림 변경: reminder_minutes="10,30" (제거: reminder_minutes="0")
   - 종일 전환: is_allday=True

### 일정 삭제
1. 대화에서 이미 event_id와 calendar_id를 알고 있으면 **바로 삭제 진행** (재조회 불필요!)
2. 모르면 get_my_calendars → get_calendar_events로 삭제 대상 일정 확인
3. 사용자에게 삭제할 일정 확인
4. 사용자 확인 후 delete_event 호출

### 빈 시간 찾기
1. get_my_calendars로 캘린더 ID 확인
2. get_calendar_events로 해당 기간 일정 조회
3. 일정 없는 시간대 계산하여 안내

### 팀/파트 전원 가능 시간 찾기
1. execute_org_chart_query로 해당 파트 인원 조회 (사번, 이름)
2. get_my_calendars로 관심 캘린더에서 해당 인원의 캘린더 ID 매칭
3. get_calendar_events로 전원의 일정을 한 번에 조회
4. 전원 일정이 없는 공통 빈 시간대 분석
5. 추천 시간대 제시 → 사용자 확인 → create_event (attendee_names로 참석자 등록)

### 일정 + 회의실 동시 등록
1. 위 워크플로우로 시간대 확정
2. find_available_rooms(asset_id, date, start_time, end_time)로 빈 회의실 확인
3. 사용자에게 "OO시에 OO회의실로 일정+회의실 예약할까요?" 확인
4. create_event + create_reservation 순서로 등록
5. 사업장 약칭: "본사"=70, "성서"=100. 사용자가 지정 안 하면 "어느 사업장 회의실이요?" 확인

## RESPONSE FORMAT
- 한국어로 응답
- 날짜는 한국어 형식 (예: "4월 1일 (화)")
- 시간은 24시간제 (예: "14:00~15:00")
- 일정 목록은 시간순으로 정리
- 종일 일정은 "(종일)"로 표시
- 비공개 일정은 🔒 표시"""

    def prepare_tools(
        self,
        tools: List[BaseTool],
        context: Dict[str, Any]
    ) -> List[BaseTool]:
        """캘린더 도구 보안 래핑: employee_number를 인증된 사번으로 강제 치환"""
        user_id = context.get("user_id", "")
        if not user_id or user_id == "anonymous":
            return tools

        # employee_number 파라미터가 있는 모든 도구 래핑
        secured_tools = {
            "get_my_calendars", "get_user_public_calendars",
            "get_calendar_events", "get_event_detail",
            "create_event", "update_event", "delete_event",
            "create_reservation",  # 회의실 예약 시 사번 주입
        }

        for tool in tools:
            if tool.name not in secured_tools:
                continue

            original_ainvoke = getattr(tool, '_unwrapped_ainvoke', None) or tool.ainvoke
            object.__setattr__(tool, '_unwrapped_ainvoke', original_ainvoke)

            async def secured_ainvoke(
                input_data, config=None, *,
                _original=original_ainvoke, _uid=user_id, _tname=tool.name, **kwargs
            ):
                if isinstance(input_data, dict):
                    if "args" in input_data and isinstance(input_data.get("args"), dict):
                        input_data["args"]["employee_number"] = _uid
                    else:
                        input_data["employee_number"] = _uid
                try:
                    return await _original(input_data, config, **kwargs)
                except Exception as e:
                    print(f"[CalendarWorker] [SECURE_INVOKE] {_tname} ERROR: {type(e).__name__}: {e}")
                    raise

            object.__setattr__(tool, "ainvoke", secured_ainvoke)

        print(f"[CalendarWorker] 보안 래핑 완료: employee_number → {user_id}")
        return tools

    def build_system_prompt(
        self,
        context: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """사번을 시스템 프롬프트에 주입"""
        prompt = super().build_system_prompt(context, memory_context, user_memory_context)

        user_id = context.get("user_id", "")
        if user_id and user_id != "anonymous":
            prompt = prompt.replace("{employee_number}", user_id)
        else:
            prompt = prompt.replace(
                "{employee_number}",
                "UNKNOWN - 사용자 인증 정보를 확인할 수 없습니다. 캘린더 기능이 불가합니다."
            )
            print(f"[CalendarWorker] WARNING: No user_id available")

        return prompt