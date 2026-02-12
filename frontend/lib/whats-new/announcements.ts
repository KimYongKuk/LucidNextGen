export interface WhatsNewStep {
  titleKo: string;
  descriptionKo: string;
  mediaUrl?: string;
  mediaType?: "gif" | "video" | "image";
  icon: string;
  features?: string[];
}

export interface WhatsNewAnnouncement {
  id: string;
  version: string;
  date: string;
  steps: WhatsNewStep[];
}

// 최신 항목을 맨 위에 추가
export const WHATS_NEW_ANNOUNCEMENTS: WhatsNewAnnouncement[] = [
  // 예시: 새 기능 공지를 여기에 추가하세요
  // {
  //   id: "2026-02-ppt-generation",
  //   version: "v1.4.0",
  //   date: "2026-02-10",
  //   steps: [
  //     {
  //       titleKo: "PPT 자동 생성",
  //       descriptionKo: "대화 내용이나 데이터를 기반으로 전문적인 PowerPoint를 자동 생성합니다.",
  //       mediaUrl: "/whats-new/ppt-generation.svg",
  //       mediaType: "image",
  //       icon: "Presentation",
  //       features: ["PPT 생성", "템플릿 기반", "차트 포함"],
  //     },
  //   ],
  // },
];

export const WHATS_NEW_STORAGE_PREFIX = "lucid-ai-whats-new-seen:";
