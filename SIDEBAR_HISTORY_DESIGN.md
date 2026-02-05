# Sidebar History & Session Design

## Scope
- Show chat sessions in sidebar (no project/folder tree).
- Initial load: last 7 days only; "More" loads all older sessions.
- Session title: one-time summary from first user message, max 15 chars; fallback to truncation.

## Data Model (reuse existing)
- Table `chat_sessions(session_id PK, user_id, chat_mode, title, created_at, updated_at)`.
- Messages: `chat_log_new` (already used by save_chat_log).
- Ordering/cursor: `ORDER BY updated_at DESC, session_id DESC`; cursor format `"<updated_at_iso>|<session_id>"`.
- Optional enrichment: latest message snippet from `chat_log_new` for display.

## Backend API
### GET /api/chat/sessions
- Query: `user_id` (required), `range` = `recent7|all` (default recent7), `limit` (default 20), `cursor` (optional, from previous nextCursor).
- Filters: recent7 → `updated_at >= now()-7d`; all → no date filter.
- Sort: `updated_at DESC, session_id DESC`.
- Response shape:
  ```json
  {
    "sessions": [
      {
        "session_id": "...",
        "user_id": "...",
        "chat_mode": "normal|corp",
        "title": "...",
        "created_at": "ISO",
        "updated_at": "ISO",
        "last_message_snippet": "..." // optional
      }
    ],
    "hasMore": true,
    "nextCursor": "<updated_at>|<session_id>" | null
  }
  ```
- Pagination: if cursor provided, fetch `updated_at < cursor.updated_at OR (updated_at = cursor.updated_at AND session_id < cursor.session_id)`.

### PATCH /api/chat/sessions/{session_id}
- Body: `{ "title"?: string, "chat_mode"?: string }`.
- Updates mutable fields; title change is manual override.

### DELETE /api/chat/sessions/{session_id}
- Delete session metadata; call existing delete_session (includes Chroma/file cleanup if any).

## Logging Integration
- In save_chat_log:
  - If session missing, create chat_sessions row (title empty, created_at/updated_at now).
  - After each message, update `updated_at` to now.
  - If title empty, trigger title summarization (async) and update title once.

## Title Summarization
- Trigger: first user message (after it is stored). Only when `chat_sessions.title` is empty.
- Prompt guideline: "주어진 사용자 첫 질문을 15자 이내 한국어 한 줄로 요약. 따옴표/마침표 없이 핵심만." Input = first user message (optionally first assistant reply if needed).
- Post-process: trim whitespace, strip quotes/punctuation, cut to 15 chars max.
- Failure handling: fallback = first user message truncated to 20-30 chars.
- Call path: async task to avoid blocking chat_stream; store result via UPDATE chat_sessions SET title=... WHERE title IS NULL.

## Frontend API Route
- File: `frontend/app/(chat)/api/history/route.ts`.
- Behavior: proxy to backend `/api/chat/sessions` with default `range=recent7&limit=20`; pass through cursor/range from query; handle errors to JSON.

## Sidebar Data Flow (sidebar-history.tsx)
- Initial SWR fetch: recent7 list.
- "More" click: request `range=all` with cursor pagination; append results to existing list; stop when hasMore=false.
- Grouping: keep existing date buckets (Today/Yesterday/Last 7 days/Last 30 days/Older).
- State: loading skeleton for initial; spinner for More; end-of-list message when hasMore=false.
- Actions: delete → DELETE /api/chat/sessions/{id}; title edit (if UI added) → PATCH /api/chat/sessions/{id}.

## UX Copy
- Banner: "Showing last 7 days" + More button.
- Loading More: show spinner + "Loading older chats...".
- End: "All history loaded".

## Edge Cases
- No sessions: empty state message in sidebar.
- Missing title: show placeholder like "(제목 없음)" or first message snippet.
- Cursor tampering: validate parse; on failure, fall back to first page.

## Testing
- Backend: unit/integration for GET with/without cursor, range recent7/all; PATCH/DELETE happy/edge paths; title summarization fallback.
- Frontend: manual flows — initial recent7 load, More pagination, delete, title change (if exposed).

## Work Plan
1) Backend: implement GET/PATCH/DELETE endpoints; hook save_chat_log to create/update chat_sessions and trigger async title summarization.
2) Frontend: replace history API route with backend proxy; adjust SWR pagination (recent7 + More); wire delete/title actions.
3) Polish: UX copy/states, optional last_message_snippet, basic tests/manual verification.
