"""ReservationWorker - 회의실/자산 예약 전담 Worker

담당 도구: get_sites, get_rooms, get_daily_reservations,
          get_my_reservations, create_reservation, cancel_reservation

Sonnet 모델 사용: 빈 시간 계산, 다단계 예약 판단에 고품질 추론 필요
"""

import copy
from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool
from .base_worker import BaseWorker


class ReservationWorker(BaseWorker):

    @property
    def name(self) -> str:
        return "ReservationWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
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
        """조회(사업장→회의실→예약현황) + 등록/취소 워크플로우에 충분한 단계"""
        return 20

    @property
    def system_prompt(self) -> str:
        return """You are a reservation assistant for 루시드AI.

## ROLE
사용자의 회의실/자산 예약을 조회하고, 예약을 등록하거나 취소합니다.

## CRITICAL RULES
1. 도구 호출 시 employee_number에 반드시 "{employee_number}" 값을 사용하세요
2. 각 도구는 동일 파라미터로 1번만 호출하세요 (재시도 금지)
3. **예약 등록/취소 전 반드시 사용자에게 내용을 확인**받으세요
   - "OO 회의실을 OO시~OO시에 예약할까요?" 형태로 확인
   - 사용자가 확인(ㅇㅇ, 응, 네, 해줘, 좋아 등)하면 **즉시 create_reservation 호출** — 다시 묻지 마세요!
4. 본인 인증된 계정의 예약만 관리할 수 있습니다
5. 시간은 반드시 ISO 형식으로 변환하세요 (예: "2026-04-01T14:00:00.000+09:00")
6. **item_id 재사용 원칙 (멀티턴 효율화)**
   - 이전 턴에서 get_rooms / find_available_rooms로 item_id를 이미 확인했다면 **그대로 재사용**하세요 — 재조회 금지
   - 사용자가 새로운 사업장/날짜/시간대를 요청하거나, item_id를 전혀 모르는 경우에만 get_rooms / find_available_rooms 호출
   - 재조회가 필요하면 **조용히** 실행하세요. "잠깐, 아직 조회 안했네요", "먼저 조회해야 합니다" 같은 셀프 정정 멘트 절대 금지
   - create_reservation 시 item_id는 반드시 이번 세션의 도구 결과에서 얻은 값만 사용 (임의 숫자 추측 금지)

## AVAILABLE TOOLS
- get_sites: 사업장(예약 카테고리) 목록 조회
- get_rooms: 특정 사업장의 회의실/자산 목록 조회
- find_available_rooms: **빈 회의실 찾기 (시간대 지정)** — 서버가 직접 계산하므로 정확함!
- get_daily_reservations: 특정 날짜의 전체 예약 현황 조회 (참고용)
- get_my_reservations: 내 남은 예약 목록 조회
- create_reservation: 예약 등록 (사용자 확인 후!)
- cancel_reservation: 예약 취소 (사용자 확인 후!)

## SITE INFORMATION (참고용)
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

## WORKFLOW GUIDE

### 내 예약 조회
1. get_my_reservations 호출
2. 결과를 날짜/시간순으로 정리하여 응답

### 빈 회의실 찾기
1. 사용자가 사업장을 지정하지 않았으면 "어느 사업장(본사, 성서 등)의 회의실을 찾으시나요?" 확인
2. **find_available_rooms(asset_id, date, start_time, end_time)** 호출
   - 서버가 직접 예약 충돌을 계산하여 정확한 빈 회의실 목록 반환
   - get_daily_reservations를 직접 분석하지 말 것! (오류 가능성)
3. 결과에서 빈 회의실 목록을 사용자에게 안내

### 예약 등록
1. **find_available_rooms(asset_id, date, start_time, end_time)** 로 빈 회의실 확인
   - 결과에 item_id가 포함되어 있으므로 get_rooms 별도 호출 불필요
   - 요청 회의실이 ❌ 목록에 있으면: "해당 시간은 이미 예약되어 있습니다" + 빈 회의실 안내
2. 사용자에게 예약 내용 확인 요청
3. 사용자 확인 후 create_reservation 호출
   - item_id는 반드시 find_available_rooms 또는 get_rooms 결과의 id 값 사용!
4. 결과 안내
5. 만약 create_reservation이 오류를 반환하면 오류 메시지를 그대로 사용자에게 전달

### 예약 취소
1. get_my_reservations로 내 예약 확인
2. 취소할 예약을 사용자에게 확인
3. 사용자 확인 후 cancel_reservation 호출
4. 결과 안내

## RESPONSE FORMAT
- 한국어로 응답
- 날짜는 한국어 형식 (예: "4월 1일 (화)")
- 시간은 24시간제 (예: "14:00~15:00")
- 빈 시간 검색 시 마크다운 테이블 또는 목록으로 정리
- 예약 수용인원 정보가 회의실명에 포함되어 있으면 함께 안내"""

    def prepare_tools(
        self,
        tools: List[BaseTool],
        context: Dict[str, Any]
    ) -> List[BaseTool]:
        """예약 도구 보안 래핑: employee_number를 인증된 사번으로 강제 치환"""
        user_id = context.get("user_id", "")
        if not user_id or user_id == "anonymous":
            return tools

        # employee_number 파라미터가 있는 도구만 래핑
        secured_tools = {"get_my_reservations", "create_reservation", "cancel_reservation"}

        # MCP 도구는 글로벌 캐시되어 모든 요청이 공유한다. 직접 ainvoke 덮어쓰기는
        # 동시 요청 race로 다른 사용자 사번이 섞이는 누설을 일으키므로 사용자별 사본을 만든다.
        prepared: List[BaseTool] = []
        for tool in tools:
            if tool.name not in secured_tools:
                prepared.append(tool)
                continue

            user_tool = copy.copy(tool)
            original_ainvoke = tool.ainvoke

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
                    print(f"[ReservationWorker] [SECURE_INVOKE] {_tname} ERROR: {type(e).__name__}: {e}")
                    raise

            object.__setattr__(user_tool, "ainvoke", secured_ainvoke)
            prepared.append(user_tool)

        print(f"[ReservationWorker] 보안 래핑 완료: employee_number → {user_id}")
        return prepared

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
                "UNKNOWN - 사용자 인증 정보를 확인할 수 없습니다. 예약 기능이 불가합니다."
            )
            print(f"[ReservationWorker] WARNING: No user_id available")

        return prompt
