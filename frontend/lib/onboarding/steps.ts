export interface OnboardingStep {
  id: string;
  title: string;
  titleKo: string;
  description: string;
  descriptionKo: string;
  mediaUrl: string;
  mediaType: "gif" | "video" | "image";
  icon: string;
  features?: string[];
  examples?: string[];
}

export const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: "chat-basics",
    title: "Chat with Lucid AI",
    titleKo: "Lucid AI와 대화하기✨",
    description: "Start a conversation by typing your message. Lucid AI will respond in real-time with streaming text.",
    descriptionKo: "메시지를 입력하여 대화를 시작하세요. 최신성능의 모델을 탑재한 Lucid AI가 실시간 스트리밍으로 응답합니다.",
    mediaUrl: "/onboarding/01-chat-basics.svg",
    mediaType: "image",
    icon: "MessageSquare",
    features: ["실시간 응답", "스트리밍"],
    examples: ["마케팅 전략 아이디어 줘", "이메일 작성해줘"],
  },
  {
    id: "file-upload",
    title: "Upload Documents & Images",
    titleKo: "문서 및 이미지 업로드",
    description: "Upload PDF, DOCX, XLSX, PPTX files or images. AI can analyze and answer questions about your uploaded content.",
    descriptionKo: "PDF, DOCX, XLSX, PPTX등 모든 파일, 이미지를 업로드하세요. 컨텐츠 내 이미지가 함께 있어도 텍스트를 추출해냅니다.",
    mediaUrl: "/onboarding/02-file-upload.svg",
    mediaType: "image",
    icon: "Upload",
    features: ["PDF", "DOCX", "XLSX", "html", "이미지"],
    examples: ["첨부한 파일 분석해줘", "이 이미지 내용 설명해줘"],
  },
  {
    id: "workspace",
    title: "Workspace Management",
    titleKo: "워크스페이스 관리",
    description: "Create independent workspaces for organized document management. Customize AI settings for each workspace.",
    descriptionKo: "독립적인 워크스페이스를 생성하여 나만의 Assistant를 체계적으로 관리하세요. 워크스페이스별로 설정(Instruction, Knowledge)을 커스터마이징할 수 있습니다.",
    mediaUrl: "/onboarding/03-workspace.svg",
    mediaType: "image",
    icon: "FolderOpen",
    features: ["작업 공간", "문서 관리", "맞춤 설정"],
    examples: ["커스텀 Assistant 지침, Knowledge 설정 후 필요할 때 마다 찾아 대화 하세요."],
  },
  {
    id: "corp-docs",
    title: "Internal Document Search",
    titleKo: "사내 문서 검색",
    description: "Search internal company documents including HR, IT, Safety, and Accounting materials with AI-powered RAG.",
    descriptionKo: "HR, IT, 안전, 회계 등 학습된 600여건의 사내지식 기반 문서를 빠르게 검색하세요.",
    mediaUrl: "/onboarding/04-corp-docs.svg",
    mediaType: "image",
    icon: "FileSearch",
    features: ["HR 문서", "IT 문서", "안전 문서", "회계 문서"],
    examples: ["개인 유류비 전표 어떻게 처리해?", "회계 결산 절차 알려줘"],
  },
  {
    id: "lfon-voc",
    title: "LFON VOC Inquiry",
    titleKo: "LFON VOC 조회",
    description: "Access IT and Accounting VOC cases in real-time through LFON WORKS integration.",
    descriptionKo: "LFON WORKS 연동으로 IT/회계통합 VOC 사례를 실시간으로 조회하세요.",
    mediaUrl: "/onboarding/05-lfon-voc.svg",
    mediaType: "image",
    icon: "Headphones",
    features: ["IT VOC", "회계 VOC", "실시간 조회"],
    examples: ["SAP 비밀번호 재설정", "출장비 정산 문의"],
  },
  {
    id: "visualization",
    title: "Generate PDF & Charts",
    titleKo: "PDF 파일 및 차트 생성",
    description: "Create professional PDF documents and various charts (line, bar, pie, combo) from your data or conversations.",
    descriptionKo: "데이터나 대화 내용으로 전문적인 PDF 문서와 다양한 차트(라인, 막대, 파이, 복합)를 생성하세요.",
    mediaUrl: "/onboarding/06-pdf-chart.svg",
    mediaType: "image",
    icon: "BarChart3",
    features: ["PDF 생성", "라인 차트", "막대 차트", "파이 차트"],
    examples: ["지금까지 나눈 내용을 요약하여 pdf 생성해줘", "업로드한 csv파일로 차트를 생성해줘"],
  },
  {
    id: "youtube",
    title: "YouTube Summarization",
    titleKo: "YouTube 영상 요약",
    description: "Paste a YouTube URL to get a structured summary with timestamps, key insights, and segments.",
    descriptionKo: "YouTube URL을 붙여넣으면 타임스탬프, 핵심 인사이트, 세그먼트가 포함된 구조화된 요약을 받을 수 있습니다.",
    mediaUrl: "/onboarding/07-youtube.svg",
    mediaType: "image",
    icon: "Youtube",
    features: ["타임스탬프", "핵심 인사이트"],
    examples: ["이 유튜브 링크 요약해줘"],
  },
  {
    id: "url-fetch",
    title: "Web Page Summary",
    titleKo: "웹 페이지 요약",
    description: "Paste any URL (news, blog, GitHub) to get a summary of the page content.",
    descriptionKo: "뉴스, 블로그, GitHub 등 URL을 붙여넣으면 페이지 내용을 자동으로 요약해줍니다.",
    mediaUrl: "/onboarding/08-url-fetch.svg",
    mediaType: "image",
    icon: "Link",
    features: ["뉴스 요약", "블로그 요약", "GitHub 요약"],
    examples: ["https://github.com/... 이 페이지 요약해줘", "이 뉴스 기사 핵심 내용 알려줘"],
  },
  {
    id: "web-search",
    title: "Real-time Web Search",
    titleKo: "실시간 웹 검색",
    description: "Get up-to-date information with integrated web search. Sources are displayed with clickable links.",
    descriptionKo: "통합 웹 검색으로 최신 정보를 얻으세요. 출처가 클릭 가능한 링크로 표시됩니다.",
    mediaUrl: "/onboarding/09-web-search.svg",
    mediaType: "image",
    icon: "Globe",
    features: ["웹 검색", "출처 표시"],
    examples: ["엘앤에프 최근 뉴스 알려줘", "오늘 대구 날씨 어때?"],
  },
];

export const LOCALSTORAGE_KEY = "lucid-ai-onboarding-completed";
export const LOCALSTORAGE_VERSION_KEY = "lucid-ai-onboarding-version";
export const CURRENT_ONBOARDING_VERSION = "1.3.0";