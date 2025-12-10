# LFChatbot v2.0 Backend

## 🚀 빠른 시작

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일 편집

# 서버 실행
python app/main.py
```

## 📁 구조

```
backend-new/
├── app/
│   ├── main.py          # FastAPI 앱
│   ├── api/routes/      # API 엔드포인트
│   ├── services/        # 비즈니스 로직
│   └── models/          # Pydantic 모델
├── data/chromadb/       # ChromaDB 데이터
└── requirements.txt
```

## 🎯 기능

- ✅ AWS Bedrock 스트리밍 채팅
- ✅ ChromaDB 파일 업로드/검색
- ✅ MySQL 채팅 이력

## 📡 API

- `GET /` - 헬스 체크
- `POST /api/chat` - 채팅 (스트리밍)
- `POST /api/upload` - 파일 업로드
- `GET /api/search` - 파일 검색
