"""UserFilesWorker - 사용자 파일 및 워크스페이스 문서 검색 Worker"""

from typing import List, Dict, Any, Optional
from .base_worker import BaseWorker


class UserFilesWorker(BaseWorker):
    """
    사용자 파일 검색 Worker (Sonnet)

    담당 도구: search_user_files, search_workspace_docs
    용도: 업로드된 파일 검색, 워크스페이스 문서 검색

    Sonnet 사용 이유: 문서 분석 결과를 종합하여 고품질 응답 생성 필요

    우선순위 로직:
    - has_files=True (사용자 파일 업로드됨) → search_user_files 먼저
    - has_files=False (워크스페이스만 존재) → search_workspace_docs 먼저
    """

    @property
    def name(self) -> str:
        return "UserFilesWorker"

    @property
    def tool_names(self) -> List[str]:
        return [
            "search_user_files",            # 세션 업로드 파일 (청크 검색)
            "search_workspace_docs",        # 워크스페이스 문서 (청크 검색)
            "get_uploaded_file_content",    # 파일 전문 조회 (요약/번역용)
        ]

    @property
    def shared_tool_names(self) -> List[str]:
        """공유 도구: 차트(Recharts), PDF, DOCX 생성"""
        return [
            "create_line_chart", "create_bar_chart", "create_pie_chart", "create_multi_chart",
            "create_document_pdf", "create_table_spec_pdf", "create_document_docx",
        ]

    @property
    def use_sonnet(self) -> bool:
        """Sonnet 모델 사용 (문서 분석 종합을 위해)"""
        return True

    @property
    def system_prompt(self) -> str:
        """기본 시스템 프롬프트 (동적 생성 시 build_system_prompt 사용)"""
        return self._base_prompt

    @property
    def _base_prompt(self) -> str:
        """공통 기본 프롬프트"""
        return """You are a helpful AI assistant with access to document search tools.

YOUR ROLE:
- Answer questions using your knowledge, conversation history, and workspace instructions
- Use file search tools ONLY when the question genuinely requires document content
- For general conversation, respond directly without tool calls

TOOL DECISION GUIDELINES:

■ 전체 파악이 필요한 요청 → get_uploaded_file_content(filename=파일명)
  "요약해줘", "번역해줘", "전체 분석", "이 파일 뭐야", "핵심 정리", "전문 읽어줘"
  "전체 내용 알려줘", "처음부터 끝까지", "파일 내용 정리해줘"
  ※ 한 번에 하나의 파일만 조회 가능
  ※ 파일명을 정확히 지정해야 합니다 (업로드 파일 목록 참고)

■ 특정 내용 검색 → search_user_files / search_workspace_docs
  "OO 부분 찾아줘", "어디에 써있어?", "OO 관련 내용", "몇 페이지에?"
  "특정 키워드", "특정 수치", "특정 항목 검색"

■ 도구 호출 불필요:
  - Greetings ("안녕하세요", "hello", "hi")
  - General knowledge questions ("Python이 뭐야?", "AI 설명해줘")
  - Follow-up about YOUR previous response (not file content)
  - Conversational exchanges ("고마워", "좋아", "알겠어")

WHEN UNCERTAIN:
- If you're unsure whether the question needs file search, prefer to search
- For "요약/번역/전체 분석" → get_uploaded_file_content (전문 전달)
- For specific search queries → search_user_files (부분 검색)

{priority_rules}

TOOL USAGE RULES:
1. Call tools without any preamble text (no "검색하겠습니다")
2. Call each tool ONLY ONCE per turn
3. After getting results, provide the answer directly

RESPONSE FORMAT:
- Answer in Korean with markdown formatting
- When using tool results, reference specific file names and sections
- Be professional without emojis"""

    def build_system_prompt(
        self,
        context: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None,
        user_memory_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        컨텍스트를 반영한 시스템 프롬프트 생성 (동적 우선순위 적용)

        Args:
            context: 세션, 워크스페이스, has_files 등 컨텍스트 정보
            memory_context: 워크스페이스 메모리 (요약, 핵심 사실)
        """
        session_id = context.get("session_id")
        workspace_uuid = context.get("workspace_uuid")
        workspace_instructions = context.get("workspace_instructions")
        has_files = context.get("has_files", False)
        workspace_has_files = context.get("workspace_has_files", False)

        # 동적 우선순위 규칙 생성
        # 파일명 목록 (get_uploaded_file_content에서 사용)
        session_file_names = context.get("session_file_names", [])
        workspace_file_names = context.get("workspace_file_names", [])
        all_file_names = session_file_names + workspace_file_names
        file_list_str = ", ".join(all_file_names) if all_file_names else "(파일명 미확인)"

        if has_files and session_id:
            # 사용자 파일이 업로드된 경우
            if workspace_uuid and workspace_has_files:
                # 워크스페이스에도 파일이 있는 경우
                priority_rules = f"""AVAILABLE TOOLS:
- get_uploaded_file_content(session_id="{session_id}", filename="파일명") - 파일 전문 조회 (요약/번역/전체분석용)
- search_user_files(session_id="{session_id}") - 업로드 파일 부분 검색 (키워드/특정내용 찾기)
- search_workspace_docs(workspace_uuid="{workspace_uuid}") - 워크스페이스 문서 부분 검색

업로드된 파일: {file_list_str}

DECISION EXAMPLES:
"파일 요약해줘" / "번역해줘" / "전체 분석" → get_uploaded_file_content(filename=해당파일명)
"문서에서 매출 찾아줘" → search_user_files
"Python이 뭐야?" → Respond directly"""
            else:
                # 워크스페이스에 파일이 없으면 user_files만 사용
                priority_rules = f"""AVAILABLE TOOLS:
- get_uploaded_file_content(session_id="{session_id}", filename="파일명") - 파일 전문 조회 (요약/번역/전체분석용)
- search_user_files(session_id="{session_id}") - 업로드 파일 부분 검색 (키워드/특정내용 찾기)

업로드된 파일: {file_list_str}

DECISION EXAMPLES:
"파일 요약해줘" / "번역해줘" / "전체 분석" → get_uploaded_file_content(filename=해당파일명)
"이 내용 설명해줘" / "OO 찾아줘" → search_user_files
"Python이 뭐야?" → Respond directly"""
        elif workspace_uuid and workspace_has_files:
            # 워크스페이스에 문서가 있는 경우
            priority_rules = f"""AVAILABLE TOOLS:
- search_workspace_docs(workspace_uuid="{workspace_uuid}") - 워크스페이스 문서 검색

업로드된 파일: {file_list_str}

DECISION EXAMPLES:
"문서 요약해줘" → search_workspace_docs
"여기 올린 자료에서 찾아줘" → search_workspace_docs
"Python이 뭐야?" → Respond directly"""
        elif workspace_uuid and not workspace_has_files:
            # 워크스페이스는 있지만 문서가 없는 경우 → 도구 호출 안 함
            priority_rules = """WORKSPACE STATUS:
- User is in a workspace but NO documents have been uploaded yet
- Do NOT call search_workspace_docs (no documents available)
- Answer using your general knowledge
- If user asks about workspace documents, inform them no files have been uploaded yet"""
        elif session_id:
            # 세션만 존재하는 경우 (워크스페이스 없이 파일만 업로드)
            priority_rules = f"""AVAILABLE TOOLS:
- get_uploaded_file_content(session_id="{session_id}", filename="파일명") - 파일 전문 조회 (요약/번역/전체분석용)
- search_user_files(session_id="{session_id}") - 업로드 파일 부분 검색 (키워드/특정내용 찾기)

업로드된 파일: {file_list_str}

DECISION EXAMPLES:
"파일 요약해줘" / "번역해줘" / "전체 분석" → get_uploaded_file_content(filename=해당파일명)
"이 내용 설명해줘" / "OO 찾아줘" → search_user_files
"Python이 뭐야?" → Respond directly"""
        else:
            # 컨텍스트 없음 (이 경우는 거의 발생하지 않음)
            priority_rules = """NO FILE CONTEXT:
- No specific file or workspace context available
- Answer using your general knowledge"""

        # 프롬프트 템플릿에 우선순위 규칙 삽입
        prompt = self._base_prompt.replace("{priority_rules}", priority_rules)

        # 세션 ID 주입 (남은 플레이스홀더)
        if session_id:
            prompt = prompt.replace("{session_id}", session_id)

        # 워크스페이스 UUID 주입 (남은 플레이스홀더)
        if workspace_uuid:
            prompt = prompt.replace("{workspace_uuid}", workspace_uuid)

        # 워크스페이스 instructions 주입 (맨 앞에 추가)
        if workspace_instructions:
            prompt = f"WORKSPACE INSTRUCTIONS:\n{workspace_instructions}\n\n{prompt}"

        # 전역 사용자 메모리 주입
        if user_memory_context and user_memory_context.get("key_facts"):
            facts = user_memory_context["key_facts"]
            facts_text = "\n".join(f"  - {fact}" for fact in facts)
            prompt = f"## User Profile (사용자 개인 특성)\n\n이 사용자에 대해 알려진 정보:\n{facts_text}\n\n{prompt}"

        print(f"[UserFilesWorker] Priority: has_files={has_files}, workspace={bool(workspace_uuid)}, workspace_has_files={workspace_has_files}, session={bool(session_id)}")

        return prompt
