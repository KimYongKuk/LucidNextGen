from locust import HttpUser, task, between, events
import json
import time

# 🔥 핵심 메트릭 수집용 글로벌 변수
waiting_times = []  # 세마포어 대기 시간
ttfb_times = []     # 첫 청크 도착 시간
total_times = []    # 전체 응답 시간
db_insert_detected = []  # DB INSERT 완료 여부

class ChatUser(HttpUser):
    # 사용자 간 대기 시간: 1~3초 (실제 채팅 사용 패턴)
    wait_time = between(1, 3)

    def on_start(self):
        # 각 유저마다 고유 ID 생성 (DB PK 중복 방지)
        import uuid
        self.user_id = f"load_test_{uuid.uuid4().hex[:8]}"
        self.session_id = f"session_{uuid.uuid4().hex[:8]}"

    @task
    def chat_stream_test(self):
        """
        실제 사용자 시나리오:
        1. 메시지 전송
        2. 세마포어 대기 (다른 사용자 처리 중이면)
        3. 첫 청크 수신 (TTFB)
        4. 스트림 완료 (DB INSERT 포함)
        """
        headers = {"Content-Type": "application/json"}
        payload = {
            "message": "부하 테스트 점검입니다. 짧게 답변해주세요.",
            "chat_mode": "normal",
            "user_id": self.user_id,
            "session_id": self.session_id
        }

        request_start = time.time()
        first_chunk_time = None
        waiting_time = None
        chunk_count = 0

        # 스트리밍 응답 요청
        with self.client.post(
            "/api/v1/chat/message/stream",
            json=payload,
            headers=headers,
            stream=True,
            catch_response=True,
            name="/api/v1/chat/message/stream"
        ) as response:

            if response.status_code != 200:
                response.failure(f"Status code: {response.status_code}")
                return

            try:
                buffer = ""

                for chunk in response.iter_content(chunk_size=None, decode_unicode=False):
                    if not chunk:
                        continue

                    # 첫 청크 도착 시간 측정 (TTFB)
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
                        ttfb = (first_chunk_time - request_start) * 1000
                        ttfb_times.append(ttfb)

                    # SSE 파싱
                    try:
                        buffer += chunk.decode('utf-8')
                        lines = buffer.split('\n')
                        buffer = lines.pop() if lines else ""

                        for line in lines:
                            if line.startswith('data: '):
                                try:
                                    data = json.loads(line[6:])

                                    # 세마포어 대기 시간 측정
                                    if data.get('type') == 'waiting':
                                        print(f"[{self.user_id}] Waiting in queue...")

                                    if data.get('type') == 'waiting_complete':
                                        waiting_time = data.get('wait_time_ms', 0)
                                        waiting_times.append(waiting_time)
                                        print(f"[{self.user_id}] Waited {waiting_time}ms")

                                    # 컨텐츠 청크 카운트
                                    if data.get('type') == 'content':
                                        chunk_count += 1

                                    # 완료 체크
                                    if data.get('complete'):
                                        db_insert_detected.append(True)

                                except json.JSONDecodeError:
                                    pass
                    except UnicodeDecodeError:
                        pass

                # 전체 응답 시간
                total_time = (time.time() - request_start) * 1000
                total_times.append(total_time)

                # 성공 여부 판별
                if chunk_count > 0:
                    response.success()
                    print(f"[{self.user_id}] ✓ Completed: {chunk_count} chunks, {total_time:.0f}ms total, TTFB: {ttfb_times[-1]:.0f}ms")
                else:
                    response.failure("No content chunks received")

            except Exception as e:
                response.failure(f"Stream error: {str(e)}")
        
        # 1회 실행 후 종료 (비용 절감)
        from locust.exception import StopUser
        raise StopUser()

# 커스텀 이벤트 리스너 - 최종 리포트 생성
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "="*80)
    print("🚀 LOAD TEST STARTED - Simulating Real Users")
    print("="*80 + "\n")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "="*80)
    print("📊 LOAD TEST RESULTS - Server-Side Performance")
    print("="*80)

    if ttfb_times:
        print(f"\n⏱️  Time To First Byte (TTFB):")
        print(f"   평균: {sum(ttfb_times)/len(ttfb_times):.0f}ms")
        print(f"   최소: {min(ttfb_times):.0f}ms")
        print(f"   최대: {max(ttfb_times):.0f}ms")
        print(f"   중앙값: {sorted(ttfb_times)[len(ttfb_times)//2]:.0f}ms")

    if total_times:
        print(f"\n⏱️  Total Response Time (DB INSERT 포함):")
        print(f"   평균: {sum(total_times)/len(total_times):.0f}ms")
        print(f"   최소: {min(total_times):.0f}ms")
        print(f"   최대: {max(total_times):.0f}ms")
        print(f"   중앙값: {sorted(total_times)[len(total_times)//2]:.0f}ms")

    if waiting_times:
        print(f"\n⏳ Semaphore Wait Times (세마포어 대기):")
        print(f"   발생 횟수: {len(waiting_times)}/{len(total_times)} 요청")
        print(f"   평균 대기: {sum(waiting_times)/len(waiting_times):.0f}ms")
        print(f"   최대 대기: {max(waiting_times):.0f}ms")
    else:
        print(f"\n✅ No Semaphore Waits - All requests processed immediately")

    print(f"\n💾 DB INSERT Success Rate: {len(db_insert_detected)}/{len(total_times)} ({len(db_insert_detected)/len(total_times)*100:.1f}%)")

    # 성능 평가
    if ttfb_times:
        avg_ttfb = sum(ttfb_times)/len(ttfb_times)
        avg_total = sum(total_times)/len(total_times)

        print(f"\n🎯 Performance Evaluation:")
        if avg_ttfb < 500:
            print(f"   ✅ TTFB 우수 ({avg_ttfb:.0f}ms < 500ms)")
        elif avg_ttfb < 1000:
            print(f"   ⚠️  TTFB 보통 ({avg_ttfb:.0f}ms)")
        else:
            print(f"   ❌ TTFB 느림 ({avg_ttfb:.0f}ms > 1000ms)")

        if avg_total < 10000:
            print(f"   ✅ 전체 응답 시간 우수 ({avg_total:.0f}ms < 10s)")
        elif avg_total < 20000:
            print(f"   ⚠️  전체 응답 시간 보통 ({avg_total:.0f}ms)")
        else:
            print(f"   ❌ 전체 응답 시간 느림 ({avg_total:.0f}ms > 20s)")

    print("\n" + "="*80 + "\n")
