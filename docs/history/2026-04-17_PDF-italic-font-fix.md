# 2026-04-17 PDF 생성 italic 폰트 미등록 수정

## 개요
`create_document_pdf` 호출 시 `Undefined font: malgungothicI` 오류로 subtitle을 포함한 PDF 생성이 실패하던 문제 수정. FPDF는 폰트 style별로 `add_font` 등록이 필요하지만 MalgunGothic에는 `""`(regular)과 `"B"`(bold)만 등록되어 있어 italic(`"I"`) 사용 시 예외가 발생.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/mcp_servers/pdf_generator/server.py` | 수정 | `setup_fonts()` 에 MalgunGothic `"I"`/`"BI"` style을 regular/bold로 폴백 등록 |

## 상세 내용

### 증상
- 운영 로그(`server.log`)에 다음 에러 반복 발생:
  ```
  [TOOL_OUTPUT] create_document_pdf: PDF 생성 실패:
  Undefined font: malgungothicI - Use built-in fonts or FPDF.add_font() beforehand
  ```
- 2026-04-17 오전 A2304013 사용자 세션에서 4회(10:19:09, 10:20:12, 10:21:06, 10:25:27) 확인.

### 2차 증상 (LLM 컨텍스트 오염)
PDF 실패 결과가 UserFilesWorker 에이전트 메시지 히스토리에 누적되면서, 동일 세션의 후속 `create_document_docx` 호출이 모두 성공(6회 전부 40~44KB 파일 정상 생성)했음에도 LLM이 다음과 같이 오응답:
- "PDF 생성 도구에 일시적인 오류가 발생하고 있습니다."
- "현재 문서 생성 도구 전체에 서버 오류가 발생하고 있어 PDF/Word 생성이 불가한 상태입니다."

결과적으로 사용자는 실제 생성된 워드 파일에 접근하지 못함(프론트엔드가 다운로드 링크를 노출하지 않음).

### 원인
`pdf_generator/server.py::setup_fonts()` 에서 MalgunGothic 폰트는 regular(`""`)와 bold(`"B"`) 두 가지 style만 `add_font`로 등록되어 있음. 반면 report/technical 스타일 템플릿에서 subtitle 렌더 시 italic을 사용 → FPDF가 `malgungothicI` 식별자를 찾지 못해 예외 raise.

### 수정
```python
if malgun_regular.exists():
    self.add_font("MalgunGothic", "", str(malgun_regular))
    if malgun_bold.exists():
        self.add_font("MalgunGothic", "B", str(malgun_bold))
    else:
        self.add_font("MalgunGothic", "B", str(malgun_regular))
    # 맑은 고딕은 italic 전용 ttf가 없으므로 regular/bold로 폴백
    self.add_font("MalgunGothic", "I", str(malgun_regular))
    self.add_font("MalgunGothic", "BI", str(malgun_bold if malgun_bold.exists() else malgun_regular))
    self.default_font = "MalgunGothic"
```

맑은 고딕은 Windows 기본 설치본에 italic 전용 ttf 파일이 없으므로 regular/bold ttf를 italic/bold-italic 식별자로 재등록(시각적으로 기울임은 적용되지 않지만 예외는 회피).

## 결정 사항 및 주의점

- **시각적 italic 미적용**: 폰트 파일 자체가 기울임 글리프를 포함하지 않으므로, 결과 PDF에서 subtitle은 정자로 표시됨. 시각적 italic이 필요하면 별도 italic ttf(예: 나눔고딕 Italic 또는 FPDF의 `set_text_color`/`SkewMatrix` 대체)로 교체해야 함.
- **2차 증상(LLM 과일반화)은 별개 이슈**: "한 도구 실패 = 모든 문서 도구 고장" 으로 판단하는 Worker 프롬프트 동작 자체는 이번 수정 범위에 포함하지 않음. 다른 도구 실패 시 동일 증상이 재현될 여지는 남아 있음 → 후속 이터레이션에서 Worker 시스템 프롬프트에 "도구별 실패는 독립적"이라는 지침 추가를 검토.
- **기존 A2304013 세션**: 이전 대화 로그에 에러 메시지가 박혀 있으므로 같은 세션에서 재요청 시 LLM이 과거 실패를 참조할 수 있음. 새 세션으로 재요청 권장.
