"""A2A 스트리밍 로직 - chat.py에서 호출"""

import asyncio
import json
import time
import re
from typing import Dict, AsyncIterator, List, Optional

from app.agents import get_orchestrator
from app.agents.state import RequestContext


# ============================================================================
# Heartbeat 설정 - 긴 작업 중 사용자 피드백 제공
# ============================================================================
HEARTBEAT_INTERVAL = 5.0  # 초
HEARTBEAT_MESSAGES = [
    "📝 문서를 작성하고 있습니다...",
    "📝 내용을 정리하고 있습니다...",
    "📝 거의 완료되었습니다...",
    "📝 마무리 중입니다...",
]

# Heartbeat를 활성화할 도구 목록 (긴 작업이 예상되는 도구)
HEARTBEAT_TOOLS = [
    "create_document_pdf",
    "create_table_spec_pdf",
    "create_line_chart",
    "create_bar_chart",
    "create_pie_chart",
    "create_multi_chart",
]


async def heartbeat_producer(
    event_queue: asyncio.Queue,
    interval: float,
    stop_event: asyncio.Event,
):
    """
    백그라운드에서 주기적 heartbeat 메시지를 이벤트 큐에 넣음

    Args:
        event_queue: 통합 이벤트 큐 (orchestrator + heartbeat)
        interval: heartbeat 간격 (초)
        stop_event: 중지 시그널
    """
    idx = 0
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            # stop_event가 set되면 루프 종료
            break
        except asyncio.TimeoutError:
            # 타임아웃 = interval 경과 → heartbeat 전송
            if not stop_event.is_set():
                msg = HEARTBEAT_MESSAGES[idx % len(HEARTBEAT_MESSAGES)]
                await event_queue.put({"_source": "heartbeat", "message": msg, "index": idx})
                idx += 1


async def orchestrator_producer(
    event_queue: asyncio.Queue,
    orchestrator,
    message: str,
    context: dict,
    all_tools: list,
    message_history: list,
    images: list,
):
    """
    Orchestrator 스트림 이벤트를 큐에 넣음
    """
    try:
        async for event in orchestrator.stream(
            message=message,
            context=context,
            all_tools=all_tools,
            message_history=message_history,
            images=images,
        ):
            await event_queue.put({"_source": "orchestrator", **event})
    finally:
        # 스트림 완료 시 종료 신호
        await event_queue.put({"_source": "done"})

# Corp 모드 RAG 도구 목록 (출처 표시용)
CORP_RAG_TOOLS = [
    "search_hr_docs",
    "search_ac_docs",
    "search_it_docs",
    "search_safety_docs",
]

# 도구 실행 상태 메시지
TOOL_STATUS_MESSAGES = {
    "tavily_search": "🌌 웹을 검색해보고 있습니다. 조금만 기다려주세요!",
    "search_user_files": "📄 파일 검색해보고 있습니다. 조금만 기다려주세요!",
    "youtube_summarize": "📺 YouTube 영상을 요약하고 있습니다. 조금만 기다려주세요!",
    "search_workspace_docs": "📁 워크스페이스에 업로드 된 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    # Corp RAG 도구
    "search_hr_docs": "📋 인사 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    "search_ac_docs": "💰 재경 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    "search_it_docs": "💻 IT 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    "search_safety_docs": "⚠️ 안전환경 문서를 검색하고 있습니다. 조금만 기다려주세요!",
    # PDF 생성 도구
    "create_document_pdf": "📄 PDF 문서를 생성하고 있습니다. 조금만 기다려주세요!",
    "create_table_spec_pdf": "📋 테이블 정의서 PDF를 생성하고 있습니다. 조금만 기다려주세요!",
    "list_generated_pdfs": "📂 생성된 PDF 목록을 조회하고 있습니다.",
    # 차트 생성 도구
    "create_line_chart": "📈 라인 차트를 생성하고 있습니다. 조금만 기다려주세요!",
    "create_bar_chart": "📊 막대 차트를 생성하고 있습니다. 조금만 기다려주세요!",
    "create_pie_chart": "🥧 파이 차트를 생성하고 있습니다. 조금만 기다려주세요!",
    "create_multi_chart": "📉 복합 차트를 생성하고 있습니다. 조금만 기다려주세요!",
}


async def stream_a2a_response(
    message: str,
    user_id: str,
    session_id: Optional[str],
    workspace_id: Optional[int],
    workspace_context: Optional[Dict],
    has_files: bool,
    chat_mode: str,
    message_history: Optional[List[Dict]],
    images: Optional[List[Dict]],
    all_tools: List,
    start_time: float,
) -> AsyncIterator[str]:
    """
    A2A Hierarchical Agent 스트리밍 응답 생성

    Returns:
        SSE 형식의 문자열 스트림
    """
    # 응답 수집 변수
    collected_response = ""
    collected_sources = []
    collected_youtube_summary = None
    collected_chart_data = None  # 차트 데이터 (display 모드)
    all_searched_corp_sources = []  # 검색된 모든 문서 (Tool 결과)
    chunk_count = 0
    first_chunk_time = None
    tool_calls_made = []
    tool_end_time = None  # 도구 완료 시간 (지연 분석용)
    last_content_time = None  # 마지막 콘텐츠 청크 시간 (지연 분석용)

    # 통합 이벤트 큐 (orchestrator + heartbeat 이벤트 병합)
    event_queue: asyncio.Queue = asyncio.Queue()
    heartbeat_stop_event = asyncio.Event()
    heartbeat_task: Optional[asyncio.Task] = None
    heartbeat_active = False  # heartbeat가 활성화된 상태인지

    # 로그는 chat.py에서 이미 출력하므로 여기서는 생략

    # RequestContext 구성
    req_context: RequestContext = {
        "session_id": session_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "workspace_uuid": workspace_context.get("uuid") if workspace_context else None,
        "workspace_instructions": workspace_context.get("instructions") if workspace_context else None,
        "workspace_has_files": workspace_context.get("has_files", False) if workspace_context else False,
        "has_files": has_files,
        "chat_mode": chat_mode,
    }

    # Orchestrator 스트리밍
    orchestrator = get_orchestrator()

    # Orchestrator producer 태스크 시작
    orchestrator_task = asyncio.create_task(
        orchestrator_producer(
            event_queue=event_queue,
            orchestrator=orchestrator,
            message=message,
            context=req_context,
            all_tools=all_tools,
            message_history=message_history,
            images=images,
        )
    )

    # 통합 큐에서 이벤트 처리
    try:
        while True:
            event = await event_queue.get()

            # 스트림 종료 체크
            if event.get("_source") == "done":
                break

            # Heartbeat 이벤트 처리
            if event.get("_source") == "heartbeat":
                yield f"data: {json.dumps({'type': 'tool_status', 'tool': 'heartbeat', 'message': event['message']})}\n\n"
                continue

            # Orchestrator 이벤트 처리
            event_type = event.get("type") or event.get("event")

            # A2A 전용 이벤트 처리
            if event_type == "intent_classified":
                yield f"data: {json.dumps(event)}\n\n"
                continue

            if event_type == "orchestrator_timing":
                yield f"data: {json.dumps({'type': 'timing', 'step': 'orchestrator', 'timing': event})}\n\n"
                continue

            # Worker 이벤트 처리
            if event_type == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", {})
                tool_start_ms = int((time.time() - start_time) * 1000)
                print(f"[TIMING] Tool '{tool_name}' started at {tool_start_ms}ms")
                # SQL 쿼리 도구인 경우 쿼리 내용 로깅
                if tool_name == "execute_it_voc_query" and tool_input:
                    sql_query = tool_input.get("sql_query", str(tool_input))
                    print(f"[SQL QUERY] {sql_query}")
                if tool_name not in tool_calls_made:
                    tool_calls_made.append(tool_name)
                    status_msg = TOOL_STATUS_MESSAGES.get(tool_name, f"🔧 {tool_name} 실행 중...")
                    yield f"data: {json.dumps({'type': 'tool_status', 'tool': tool_name, 'message': status_msg})}\n\n"

                # HEARTBEAT_TOOLS에 해당하면 하트비트 시작 (도구 실행 중 사용자 피드백)
                if tool_name in HEARTBEAT_TOOLS and not heartbeat_active:
                    heartbeat_stop_event.clear()
                    heartbeat_task = asyncio.create_task(
                        heartbeat_producer(event_queue, HEARTBEAT_INTERVAL, heartbeat_stop_event)
                    )
                    heartbeat_active = True
                    print(f"[HEARTBEAT] Started for tool '{tool_name}'")

            elif event_type == "on_tool_end":
                tool_name = event.get("name", "unknown")
                tool_output = event.get("data", {}).get("output", "")

                # 도구 완료 시간 기록 (지연 분석용)
                tool_end_time = time.time()
                tool_end_ms = int((tool_end_time - start_time) * 1000)
                print(f"[TIMING] Tool '{tool_name}' completed at {tool_end_ms}ms")

                # HEARTBEAT_TOOLS 도구 완료 시 하트비트 중지
                if tool_name in HEARTBEAT_TOOLS and heartbeat_active:
                    heartbeat_stop_event.set()
                    heartbeat_active = False
                    print(f"[HEARTBEAT] Stopped (tool '{tool_name}' completed)")

                # 응답 생성 중 상태 메시지
                yield f"data: {json.dumps({'type': 'tool_status', 'tool': tool_name, 'message': '✨ 검색 완료! 응답 생성 중... 잠시만 기다려주세요.', 'status': 'generating'})}\n\n"

                # Corp 문서 출처 수집 (검색된 모든 문서)
                if tool_name in CORP_RAG_TOOLS:
                    output_str = str(tool_output.content if hasattr(tool_output, 'content') else tool_output)
                    # 유사도 정보 포함된 새 패턴: [인사 문서 1: filename (유사도: 0.72)]
                    pattern = r'\[(인사|재경|IT|안전환경) 문서 \d+: (.+?) \(유사도: ([\d.]+)\)\]'
                    matches = re.findall(pattern, output_str)
                    if not matches:
                        # 유사도 없는 기존 패턴 폴백
                        pattern = r'\[(인사|재경|IT|안전환경) 문서 \d+: (.+?)\]\n'
                        matches = [(cat, fn, "0") for cat, fn in re.findall(pattern, output_str)]
                    for category, filename, similarity in matches:
                        all_searched_corp_sources.append({
                            "filename": filename.strip(),
                            "category": category,
                            "tool": tool_name,
                            "similarity": float(similarity) if similarity else 0
                        })

                # Tavily 출처 수집
                if "tavily" in tool_name.lower():
                    output_str = tool_output.content if hasattr(tool_output, 'content') else tool_output
                    if isinstance(output_str, str):
                        pattern = r'Title:\s*(.+?)\s*\nURL:\s*(.+?)(?:\s*\nContent:|$)'
                        matches = re.findall(pattern, output_str, re.MULTILINE | re.DOTALL)
                        sources_data = []
                        for i, (title, url) in enumerate(matches[:5]):
                            if url.strip().startswith('http'):
                                sources_data.append({
                                    'url': url.strip(),
                                    'title': title.strip(),
                                    'score': 1.0 - (i * 0.1)
                                })
                        if sources_data:
                            collected_sources.extend(sources_data)
                            yield f"data: {json.dumps({'type': 'search_sources', 'sources': sources_data}, ensure_ascii=False)}\n\n"

                # YouTube 요약 수집
                if tool_name == "youtube_summarize":
                    try:
                        content_str = tool_output.content if hasattr(tool_output, 'content') else str(tool_output)
                        youtube_data = json.loads(content_str) if isinstance(content_str, str) else content_str
                        if isinstance(youtube_data, dict) and not youtube_data.get("error"):
                            collected_youtube_summary = youtube_data
                    except Exception:
                        pass

                # 차트 데이터 수집 (display 모드)
                if tool_name in ["create_line_chart", "create_bar_chart", "create_pie_chart", "create_multi_chart"]:
                    try:
                        # tool_output 형식 디버깅
                        print(f"[CHART DEBUG] tool_output type: {type(tool_output)}")
                        print(f"[CHART DEBUG] tool_output repr: {repr(tool_output)[:500]}")

                        # content 속성이 있으면 사용, 없으면 str 변환
                        if hasattr(tool_output, 'content'):
                            content_str = tool_output.content
                            print(f"[CHART DEBUG] Using .content attribute")
                        else:
                            content_str = str(tool_output)
                            print(f"[CHART DEBUG] Using str() conversion")

                        print(f"[CHART DEBUG] content_str: {content_str[:300] if content_str else 'None'}...")

                        # JSON 파싱
                        if isinstance(content_str, str) and content_str.strip():
                            chart_data = json.loads(content_str)
                        else:
                            chart_data = content_str

                        print(f"[CHART DEBUG] Parsed chart_data type: {type(chart_data)}")
                        if isinstance(chart_data, dict):
                            print(f"[CHART DEBUG] chart_data keys: {list(chart_data.keys())}")
                            print(f"[CHART DEBUG] chart_data.get('type'): {chart_data.get('type')}")

                        # chart_data 타입 체크 및 SSE 전송
                        if isinstance(chart_data, dict) and chart_data.get("type") == "chart_data":
                            print(f"[CHART] Sending chart_data SSE event for {chart_data.get('chart_type')}")
                            collected_chart_data = chart_data  # DB 저장용으로 수집
                            yield f"data: {json.dumps({'type': 'chart_data', 'chart': chart_data}, ensure_ascii=False)}\n\n"
                        else:
                            print(f"[CHART DEBUG] Skipped - not chart_data type or not dict")
                    except Exception as e:
                        print(f"[CHART ERROR] Failed to process chart data: {e}")
                        import traceback
                        traceback.print_exc()

            elif event_type == "on_chat_model_stream":
                chunk_data = event.get("data", {})
                if "chunk" in chunk_data:
                    msg_chunk = chunk_data["chunk"]
                    content = ""
                    has_tool_use = False

                    if hasattr(msg_chunk, "content"):
                        if isinstance(msg_chunk.content, str):
                            content = msg_chunk.content
                        elif isinstance(msg_chunk.content, list):
                            for item in msg_chunk.content:
                                if isinstance(item, dict):
                                    if "text" in item:
                                        content += item["text"]
                                    elif item.get("type") == "tool_use":
                                        has_tool_use = True
                                elif isinstance(item, str):
                                    content += item
                        # tool_use 블록이 별도 속성으로 올 수 있음
                        if hasattr(msg_chunk, "tool_use") or hasattr(msg_chunk, "tool_calls"):
                            has_tool_use = True

                    # tool_use 블록 생성 감지 시 상태 메시지 전송 및 heartbeat 시작
                    if has_tool_use and "tool_use_detected" not in tool_calls_made:
                        tool_calls_made.append("tool_use_detected")
                        yield f"data: {json.dumps({'type': 'tool_status', 'tool': 'preparing', 'message': '🔧 도구를 준비하고 있습니다...'})}\n\n"

                        # Heartbeat 시작 (긴 tool_use 생성 중 사용자 피드백)
                        if not heartbeat_active:
                            heartbeat_stop_event.clear()
                            heartbeat_task = asyncio.create_task(
                                heartbeat_producer(event_queue, HEARTBEAT_INTERVAL, heartbeat_stop_event)
                            )
                            heartbeat_active = True
                            print(f"[HEARTBEAT] Started heartbeat task")

                    if content:
                        # Note: Heartbeat는 on_tool_end에서만 중지됨
                        # tool_use arguments 생성 중에는 content가 없으므로 하트비트 유지

                        if first_chunk_time is None:
                            first_chunk_time = int((time.time() - start_time) * 1000)
                            # 도구 완료 후 첫 청크까지의 지연 시간 계산
                            if tool_end_time:
                                delay_after_tool = int((time.time() - tool_end_time) * 1000)
                                print(f"[TIMING] First chunk received: {first_chunk_time}ms (delay after tool: {delay_after_tool}ms)")
                                yield f"data: {json.dumps({'type': 'timing', 'step': 'first_chunk', 'timing': {'ms': first_chunk_time, 'delay_after_tool_ms': delay_after_tool}})}\n\n"
                            else:
                                print(f"[TIMING] First chunk received: {first_chunk_time}ms (no tool call)")
                                yield f"data: {json.dumps({'type': 'timing', 'step': 'first_chunk', 'timing': {'ms': first_chunk_time}})}\n\n"

                        chunk_count += 1
                        collected_response += content
                        last_content_time = time.time()  # 마지막 콘텐츠 시간 기록
                        yield f"data: {json.dumps({'type': 'content', 'chunk': content})}\n\n"

    finally:
        # Orchestrator 태스크 정리
        if not orchestrator_task.done():
            orchestrator_task.cancel()
            try:
                await orchestrator_task
            except asyncio.CancelledError:
                pass

    # Heartbeat cleanup
    if heartbeat_active or heartbeat_task:
        heartbeat_stop_event.set()
        if heartbeat_task and not heartbeat_task.done():
            try:
                await asyncio.wait_for(heartbeat_task, timeout=1.0)
            except asyncio.TimeoutError:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
        print(f"[HEARTBEAT] Cleanup completed")

    # 완료 처리
    complete_start_time = time.time()
    if last_content_time:
        delay_to_complete = int((complete_start_time - last_content_time) * 1000)
        print(f"[TIMING] Delay from last content to complete: {delay_to_complete}ms")  # ← 핵심 지연!

    if collected_youtube_summary:
        yield f"data: {json.dumps({'type': 'youtube_summary', 'summary': collected_youtube_summary}, ensure_ascii=False)}\n\n"

    # 검색된 Corp 문서를 UI에 전송 (유사도 필터링은 RAG 레벨에서 이미 적용됨)
    if all_searched_corp_sources:
        source_map = {}
        for item in all_searched_corp_sources:
            key = item["filename"]
            if key not in source_map:
                source_map[key] = {
                    "filename": item["filename"],
                    "category": item["category"],
                    "similarity": item.get("similarity", 0),
                    "count": 0
                }
            source_map[key]["count"] += 1
        yield f"data: {json.dumps({'type': 'corp_sources', 'sources': list(source_map.values())}, ensure_ascii=False)}\n\n"

    total_time = int((time.time() - start_time) * 1000)
    print(f"[CHAT_STREAM] A2A Completed: {chunk_count} chunks, {total_time}ms")
    yield f"data: {json.dumps({'type': 'timing', 'step': 'complete', 'timing': {'chunk_count': chunk_count, 'total_ms': total_time}, 'chat_mode': chat_mode})}\n\n"
    yield f"data: {json.dumps({'complete': True, 'chat_mode': chat_mode})}\n\n"

    # 수집된 데이터 반환 (로그 저장용)
    yield f"data: {json.dumps({'type': '_internal_collected', 'response': collected_response, 'sources': collected_sources, 'youtube_summary': collected_youtube_summary, 'corp_sources': all_searched_corp_sources, 'chart_data': collected_chart_data})}\n\n"
