# chat_sessions 테이블에 데이터가 안 들어가는 문제 디버깅

## 현재 상황
- ✅ `chat_log_new` 테이블에는 데이터가 정상 저장됨
- ✅ `session_id`가 제대로 전달됨 (84acb9a4-5430-449c-a0c7-23278f2500d6)
- ❌ `chat_sessions` 테이블에 해당 세션이 생성되지 않음

## 디버깅 절차

### 1. 백엔드 서버 재시작 (필수!)
```bash
# 기존 프로세스 종료 (Ctrl+C)
cd backend
python app/main.py
```

### 2. 프론트엔드에서 새 메시지 전송
- 브라우저에서 http://localhost:3001 접속
- **새로운 메시지** 입력 (예: "테스트 메시지")
- 전송

### 3. 백엔드 콘솔 로그 확인

**정상 케이스** (chat_sessions 생성 성공):
```
[ChatLogService] Ensuring session: <session_id>, user: A2304013, mode: normal
[ChatLogService] Session ensured, now touching...
[ChatLogService] Session touched
[ChatLogService] Setting title: 테스트 메시지
[ChatLogService] Saved chat log for session: <session_id>
```

**오류 케이스** (실패 시):
```
[ChatLogService] Ensuring session: <session_id>, user: A2304013, mode: normal
[ChatLogService] Error saving chat log: <에러 메시지>
[ChatLogService] Full traceback: <상세 스택 트레이스>
```

### 4. 에러 메시지 유형별 대응

#### Case 1: "Cursor closed" 에러
**원인**: `get_cursor()` 컨텍스트 매니저 문제
**해결**: `chat_session_service.py`의 커서 사용 방식 수정 필요

#### Case 2: "Duplicate entry" 에러
**원인**: 세션이 이미 존재하는데 INSERT 시도
**해결**: `ensure_session()`의 `ON DUPLICATE KEY UPDATE` 확인

#### Case 3: 로그 없음
**원인**: `save_chat_log()`가 호출되지 않음
**해결**: `chat.py`의 `await chat_log.save_chat_log()` 호출 확인

### 5. DB 직접 확인
```bash
cd backend
python debug_sessions.py
```

**예상 출력**:
```
[CRITICAL] Found 1 sessions in logs that are MISSING from chat_sessions:
  Missing session_id: <새로운 session_id>
```

### 6. 수동 세션 생성 테스트
```bash
cd backend
python -c "from app.services.chat_session_service import get_chat_session_service; svc = get_chat_session_service(); svc.ensure_session('test-manual-session', 'A2304013', 'normal', 'Test'); print('Manual session created')"
```

**성공하면**:
- DB에서 확인: `SELECT * FROM chat_sessions WHERE session_id='test-manual-session';`
- 결과 있으면 → `save_chat_log()`에서 호출 안 되는 문제
- 결과 없으면 → `ensure_session()` 자체에 문제

---

## 예상 원인 및 해결책

### 원인 1: 트랜잭션 커밋 누락
`chat_log_new` INSERT는 성공하지만 `chat_sessions` INSERT/UPDATE가 커밋되지 않음

**확인**:
- `app/core/database.py`에서 `autocommit` 설정 확인
- `get_cursor()` 컨텍스트 매니저가 커밋하는지 확인

**해결**:
```python
# ensure_session(), touch_session() 후 명시적 커밋 추가
self.db.connection.commit()
```

### 원인 2: 다른 DB 커넥션 사용
`chat_log_service`와 `chat_session_service`가 다른 DB 커넥션을 사용하여 트랜잭션 격리

**확인**:
```python
# chat_log_service.py에서
print(f"ChatLog DB: {id(self.db)}")
print(f"Sessions DB: {id(self.sessions.db)}")
```

**해결**:
- 동일한 DB 커넥션 공유하도록 수정

### 원인 3: 예외 발생 후 무시
`ensure_session()`에서 예외 발생했지만 try-catch에 잡혀 무시됨

**확인**:
- 위 디버깅 로그에서 "Error saving chat log" 출력 확인

**해결**:
- 로그에 표시된 예외 메시지로 구체적 대응

---

## 다음 단계

백엔드 콘솔 로그를 확인한 후:
1. **정상 로그가 보이면**: DB 커밋 문제 확인
2. **에러 로그가 보이면**: 에러 메시지 공유
3. **아무 로그도 없으면**: `save_chat_log()` 호출 자체가 안 되는 것 → `chat.py` 확인

**백엔드 콘솔 로그를 복사해서 공유해 주세요!**
