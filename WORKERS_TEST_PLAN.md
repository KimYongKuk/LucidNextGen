# Workers 성능 비교 테스트 계획

## 목표
Workers 1개 vs 4개의 실제 성능 차이 검증

## 테스트 설정

### 공통 조건
- 동일한 PC
- 동일한 시간대 (AWS 부하 동일)
- 동일한 테스트 (30명, 2분)

### 테스트 1: Workers 1개
```bash
# 1. 백엔드 시작
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# 2. Locust 실행
locust -f locustfile.py --headless --users 30 --spawn-rate 5 --run-time 2m --host http://localhost:8000

# 3. 결과 기록
```

**기록 항목:**
- [ ] TTFB 평균: ____ms
- [ ] Total 평균: ____ms
- [ ] 95th percentile: ____ms
- [ ] RPS: ____
- [ ] Semaphore Wait: ____회

### 테스트 2: Workers 4개
```bash
# 1. 백엔드 시작
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# 2. Locust 실행
locust -f locustfile.py --headless --users 30 --spawn-rate 5 --run-time 2m --host http://localhost:8000

# 3. 결과 기록
```

**기록 항목:**
- [ ] TTFB 평균: ____ms
- [ ] Total 평균: ____ms
- [ ] 95th percentile: ____ms
- [ ] RPS: ____
- [ ] Semaphore Wait: ____회

## 예상 결과

### 가설 1: Workers 1개가 더 안정적 (70% 확률)
```
Workers 1개:
  - 95th percentile: 5-8초
  - RPS: 2.0-2.5
  - Semaphore Wait: 일부 발생

Workers 4개:
  - 95th percentile: 8-10초
  - RPS: 2.0
  - Semaphore Wait: 거의 없음 (200개 한도)
```

**이유:** 세마포어가 정확히 작동 → AWS 부하 분산 → 안정적

### 가설 2: 거의 동일 (25% 확률)
```
Workers 1개 ≈ Workers 4개
평균 7-8초, 차이 10% 이내
```

**이유:** AWS Bedrock이 주 병목 → Workers 수는 무관

### 가설 3: Workers 4개가 더 빠름 (5% 확률)
```
Workers 4개 < Workers 1개
(평균 6초 vs 8초)
```

**이유:** 예상 밖의 CPU 병목 존재

## 결론 도출

### Workers 1개가 더 나으면:
→ 운영 환경 Workers 1개 권장
→ 세마포어 값 30-40으로 조정

### 거의 동일하면:
→ Workers 4개 유지 (안정성 이점)
→ AWS Bedrock 최적화에 집중

### Workers 4개가 더 나으면:
→ Workers 4개 유지
→ 세마포어를 12로 조정 (50÷4)

## 추가 확인 사항

### 백엔드 로그에서 확인:
```
[SEMAPHORE] Queue is full  ← 이 메시지 횟수 비교
[SEMAPHORE] Waited XXXms   ← 대기 시간 비교
```

### 시스템 모니터링:
- CPU 사용률 (Task Manager)
- 메모리 사용량
- Python 프로세스 수

## 실행 순서

1. ✅ Workers 1개 테스트
2. ⏸️ 5분 대기 (AWS 쿨다운)
3. ✅ Workers 4개 테스트
4. 📊 결과 비교
5. 📝 결론 작성
