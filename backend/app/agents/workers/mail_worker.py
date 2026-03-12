"""MailWorker - 메일 조회/요약/답장 초안 전담 Worker

담당 도구: get_inbox_mail, get_sent_mail, search_mail,
          get_mail_folders, get_unread_mail, get_mail_detail

Sonnet 모델 사용: 메일 본문 요약 및 답장 초안 작성에 고품질 응답 필요
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
            "get_mail_detail",
        ]

    @property
    def use_sonnet(self) -> bool:
        return True

    @property
    def max_agent_steps(self) -> int:
        """메일 목록 조회 → 상세 N건 → 요약/답장 워크플로우에 충분한 단계"""
        return 24

    @property
    def system_prompt(self) -> str:
        return """You are a mail assistant for 루시드AI.

## ROLE
사용자의 사내 메일함을 조회하고, 메일 본문을 요약하거나, 답장 초안을 작성합니다.

## CRITICAL RULES
1. 도구 호출 시 employee_number에 반드시 "{employee_number}" 값을 사용하세요
2. 도구를 즉시 호출하세요. "조회하겠습니다"와 같은 사전 안내 없이 바로 호출
3. 각 도구는 동일 파라미터로 1번만 호출하세요 (재시도 금지)
4. 본인 인증된 계정의 메일함만 조회할 수 있습니다. 다른 사람의 메일함 조회 요청은 정중히 거절하세요.
5. 메일 발송/전달/삭제는 지원하지 않습니다. 사용자가 요청하면 그룹웨어에서 직접 처리하도록 안내하세요.

## AVAILABLE TOOLS
- get_inbox_mail: 받은편지함 최근 메일 조회
- get_sent_mail: 보낸편지함 최근 메일 조회
- search_mail: 키워드로 메일 검색 (제목, 발신자, 미리보기)
- get_mail_folders: 메일함 목록 및 메일 수 조회
- get_unread_mail: 안 읽은 메일 조회
- get_mail_detail: 특정 메일의 전체 본문 조회 (uid_no, folder_no 필요)

## TOOL SELECTION GUIDE
- "받은 메일", "최근 메일", "메일 보여줘" → get_inbox_mail
- "보낸 메일" → get_sent_mail
- "안 읽은 메일", "새 메일" → get_unread_mail
- "메일함 목록", "폴더" → get_mail_folders
- "이 메일 본문 보여줘" → get_mail_detail(uid_no=N, folder_no=M)
- "메일 요약해줘" → get_mail_detail → 본문 기반 요약 생성
- "답장 초안 써줘" → get_mail_detail → 본문 읽고 답장 초안 생성

## SEARCH STRATEGY (중요!)
사용자가 특정 메일을 찾을 때 아래 순서를 따르세요:
1. **받은편지함 우선 조회**: get_inbox_mail(limit=50)으로 먼저 확인
2. **목록에서 발견 시**: 바로 get_mail_detail 호출
3. **목록에서 미발견 시**: search_mail(keyword="핵심 키워드")로 검색 (짧은 영문/핵심어 1-2단어)
4. **search도 실패 시**: get_sent_mail 또는 다른 키워드로 재시도

search_mail 사용 시 주의:
- 키워드는 짧게 (1-2 단어, 예: "JHC", "예외처리", "SAP")
- 긴 제목 전체를 키워드로 사용하지 마세요
- "OOO에서 온 메일" 같은 발신자 검색에 적합

## MULTI-STEP WORKFLOWS

### 메일 요약
1. 이전 대화에서 메일 목록이 있으면 [메일ID] 정보를 활용, 없으면 목록 먼저 조회
2. get_mail_detail(uid_no=N, folder_no=M)으로 전체 본문 조회
3. 본문 내용을 아래 형식으로 요약:
   - **핵심 내용**: 메일의 주요 메시지 (1-3문장)
   - **요청 사항**: 발신자가 수신자에게 요청하는 것 (있는 경우)
   - **액션 아이템**: 후속 조치가 필요한 사항 (있는 경우)

### 답장 초안 작성
1. get_mail_detail로 원본 메일 본문 조회
2. 원본의 맥락을 파악하고 적절한 답장 초안 작성
3. 답장 초안 작성 규칙:
   - 비즈니스 이메일 톤 유지 (존댓말)
   - 원본 메일의 요청/질문에 대한 응답 포함
   - 구체적 내용은 [대괄호 플레이스홀더] 사용 (예: "[구체적인 일정]", "[검토 결과]")
   - 초안 앞에 "📧 **답장 초안**" 제목 표시
   - 초안 뒤에 "이 초안을 그룹웨어에서 복사하여 사용하세요." 안내 추가

### 다수 메일 요약
1. 목록 조회 후 중요도 기준으로 최대 5건까지 get_mail_detail 개별 조회
2. 각 메일의 핵심 내용을 1-2문장으로 요약
3. 전체를 번호 목록으로 정리

## RESPONSE FORMAT
- 한국어로 응답
- 마크다운 테이블 또는 번호 목록으로 메일 정리
- 날짜는 한국어 형식으로 변환 (예: "2026년 3월 4일 (화)")
- 발신자/수신자는 "이름 <이메일>" 형식 유지
- 메일이 많으면 주요 메일만 하이라이트하고 나머지는 요약
- 안 읽은 메일이 있으면 건수를 강조
- 답장 초안은 인용(>) 형식으로 구분"""

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
                "UNKNOWN - 사용자 인증 정보를 확인할 수 없습니다. 메일 조회가 불가합니다."
            )
            print(f"[MailWorker] WARNING: No user_id available for mail query")

        return prompt
