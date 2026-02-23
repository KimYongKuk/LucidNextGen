"""MailWorker - 메일 조회 전담 Worker

담당 도구: get_inbox_mail, get_sent_mail, search_mail,
          get_mail_folders, get_unread_mail

Sonnet 모델 사용: 메일 결과를 자연어로 요약하는 고품질 응답 필요
"""

from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool
from .base_worker import BaseWorker


class MailWorker(BaseWorker):

    @property
    def name(self) -> str:
        return "MailWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            "get_inbox_mail",
            "get_sent_mail",
            "search_mail",
            "get_mail_folders",
            "get_unread_mail",
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def system_prompt(self) -> str:
        return """You are a mail assistant for 루시드AI.

## ROLE
사용자의 사내 메일함을 조회하고, 결과를 보기 좋게 정리하여 안내합니다.

## CRITICAL RULES
1. 도구 호출 시 employee_number에 반드시 "{employee_number}" 값을 사용하세요
2. 도구를 즉시 호출하세요. "조회하겠습니다"와 같은 사전 안내 없이 바로 호출
3. 각 도구는 1번만 호출하세요 (재시도 금지)
4. 메일 내용은 미리보기만 제공됩니다. 전체 본문은 조회할 수 없습니다.
5. 한 번에 조회 가능한 메일은 최대 100건입니다. 사용자가 더 많은 메일을 원하면 이 제한을 안내하세요.
6. 본인 인증된 계정의 메일함만 조회할 수 있습니다. 다른 사람의 메일함 조회 요청은 정중히 거절하세요.

## AVAILABLE TOOLS
- get_inbox_mail: 받은편지함 최근 메일 조회
- get_sent_mail: 보낸편지함 최근 메일 조회
- search_mail: 키워드로 메일 검색 (제목, 발신자, 미리보기)
- get_mail_folders: 메일함 목록 및 메일 수 조회
- get_unread_mail: 안 읽은 메일 조회

## TOOL SELECTION GUIDE
- "받은 메일", "최근 메일", "메일 보여줘" → get_inbox_mail
- "보낸 메일" → get_sent_mail
- "OOO에서 온 메일", "OOO 관련 메일" → search_mail(keyword="OOO")
- "안 읽은 메일", "새 메일" → get_unread_mail
- "메일함 목록", "폴더" → get_mail_folders

## RESPONSE FORMAT
- 한국어로 응답
- 마크다운 테이블 또는 번호 목록으로 메일 정리
- 날짜는 한국어 형식으로 변환 (예: "2026년 2월 13일 (목)")
- 발신자/수신자는 "이름 <이메일>" 형식 유지
- 메일이 많으면 주요 메일만 하이라이트하고 나머지는 요약
- 안 읽은 메일이 있으면 건수를 강조"""

    def prepare_tools(
        self,
        tools: List[BaseTool],
        context: Dict[str, Any]
    ) -> List[BaseTool]:
        """메일 도구 보안 래핑: employee_number를 인증된 사번으로 강제 치환"""
        user_id = context.get("user_id", "")
        if not user_id or user_id == "anonymous":
            return tools

        for tool in tools:
            # 글로벌 캐시 도구의 래핑 체인 방지: 항상 원본 ainvoke 사용
            original_ainvoke = getattr(tool, '_unwrapped_ainvoke', None) or tool.ainvoke
            object.__setattr__(tool, '_unwrapped_ainvoke', original_ainvoke)

            async def secured_ainvoke(
                input_data, config=None, *,
                _original=original_ainvoke, _uid=user_id, _tname=tool.name, **kwargs
            ):
                if isinstance(input_data, dict):
                    # ToolCall format: {name, args, id, type} → args 내부에 주입
                    if "args" in input_data and isinstance(input_data.get("args"), dict):
                        input_data["args"]["employee_number"] = _uid
                    else:
                        # Plain dict format (직접 호출)
                        input_data["employee_number"] = _uid
                try:
                    result = await _original(input_data, config, **kwargs)
                    return result
                except Exception as e:
                    print(f"[MailWorker] [SECURE_INVOKE] {_tname} ERROR: {type(e).__name__}: {e}")
                    raise

            object.__setattr__(tool, "ainvoke", secured_ainvoke)

        print(f"[MailWorker] 보안 래핑 완료: employee_number → {user_id}")
        return tools

    def build_system_prompt(
        self,
        context: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """사번을 시스템 프롬프트에 주입"""
        prompt = super().build_system_prompt(context, memory_context)

        user_id = context.get("user_id", "")
        if user_id and user_id != "anonymous":
            prompt = prompt.replace("{employee_number}", user_id)
        else:
            prompt = prompt.replace(
                "{employee_number}",
                "UNKNOWN - 사용자 인증 정보를 확인할 수 없습니다. 메일 조회가 불가합니다."
            )
            print(f"[MailWorker] WARNING: No user_id available for mail query")

        return prompt
