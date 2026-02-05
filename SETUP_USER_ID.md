# User ID 설정 가이드

세션 기반 채팅 히스토리가 정상 작동하려면 **user_id**가 올바르게 설정되어야 합니다.

## 방법 1: 환경 변수 설정 (권장)

`frontend/.env.local` 파일에 추가:

```bash
NEXT_PUBLIC_USER_ID=A2304013
```

> 실제 사용자 ID로 변경하세요 (예: A2304013, USER001 등)

## 방법 2: localStorage 설정 (동적)

브라우저 개발자 도구(F12) 콘솔에서:

```javascript
localStorage.setItem('user_id', 'A2304013');
```

## 우선순위

시스템은 다음 순서로 user_id를 확인합니다:

1. **localStorage** `user_id` (브라우저 저장)
2. **환경 변수** `NEXT_PUBLIC_USER_ID`
3. **기본값** `'anonymous'`

## 검증 방법

브라우저 콘솔에서 확인:

```javascript
// 현재 설정된 user_id 확인
console.log(localStorage.getItem('user_id'));

// 또는 프론트엔드에서
import { getUserId } from '@/lib/utils';
console.log(getUserId());
```

## 주의사항

- 백엔드 로그에서도 동일한 user_id가 사용되는지 확인하세요
- DB에 저장된 user_id와 일치해야 히스토리가 조회됩니다
- 'anonymous'는 테스트용이며, 프로덕션에서는 실제 인증 시스템과 통합하세요
