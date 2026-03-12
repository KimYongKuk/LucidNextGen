import type { InferUITool, UIMessage } from "ai";
import { z } from "zod";
import type { ArtifactKind } from "@/components/artifact";
import type { createDocument } from "./ai/tools/create-document";
import type { getWeather } from "./ai/tools/get-weather";
import type { requestSuggestions } from "./ai/tools/request-suggestions";
import type { updateDocument } from "./ai/tools/update-document";
// import type { Suggestion } from "./db/schema";
import type { AppUsage } from "./usage";

export interface Vote {
  chatId: string;
  messageId: string;
  isUpvoted: boolean;
}

export interface Document {
  id: string;
  title: string;
  content: string;
  kind: ArtifactKind;
  createdAt: Date;
  userId: string;
}

export interface User {
  id: string;
  email: string;
  name?: string;
  image?: string;
  type?: "regular" | "admin";
}

export interface Session {
  user?: User;
  expires?: string;
}

export type DataPart = { type: "append-message"; message: string };

export const messageMetadataSchema = z.object({
  createdAt: z.string(),
});

export type MessageMetadata = z.infer<typeof messageMetadataSchema>;

type weatherTool = InferUITool<typeof getWeather>;
type createDocumentTool = InferUITool<ReturnType<typeof createDocument>>;
type updateDocumentTool = InferUITool<ReturnType<typeof updateDocument>>;
type requestSuggestionsTool = InferUITool<
  ReturnType<typeof requestSuggestions>
>;

export type ChatTools = {
  getWeather: weatherTool;
  createDocument: createDocumentTool;
  updateDocument: updateDocumentTool;
  requestSuggestions: requestSuggestionsTool;
};

export type SearchSource = {
  url: string;
  title: string;
  score: number;
};

export type YoutubeSegment = {
  start_time: number;
  title: string;
  content: string;
};

export type YoutubeSummary = {
  video_id: string;
  title: string;
  original_link: string;
  summary: string;
  insight?: string;
  keywords?: string[];
  segments?: YoutubeSegment[];
};

export type CorpSourceChunk = {
  text: string;
  similarity: number;
};

export type CorpSource = {
  filename: string;
  category: string;  // "인사", "재경", "IT", "공통", "안전환경"
  count: number;
  similarity?: number;
  chunks?: CorpSourceChunk[];
};

export type CustomUIDataTypes = {
  textDelta: string;
  imageDelta: string;
  sheetDelta: string;
  codeDelta: string;
  suggestion: any; // Suggestion;
  appendMessage: string;
  id: string;
  title: string;
  kind: ArtifactKind;
  clear: null;
  finish: null;
  usage: AppUsage;
  searchSources: SearchSource[];
  // Custom types for search results (non-data prefix)
  sources: { sources: SearchSource[] };
  youtubeSummary: YoutubeSummary;
  "youtube-summary": { summary: YoutubeSummary };
  corpSources: CorpSource[];
  "corp-sources": { sources: CorpSource[] };
};

export type ChatMessage = UIMessage<
  MessageMetadata,
  CustomUIDataTypes,
  ChatTools
> & {
  sources?: SearchSource[]; // History에서 복원된 출처
  youtubeSummary?: YoutubeSummary; // History에서 복원된 유튜브 요약
  corpSources?: CorpSource[]; // History에서 복원된 사내 문서 출처
  createdAt?: Date;
  workerName?: string; // Intent 분류 결과 워커 이름 (아티팩트 감지 조건부 실행용)
};

export type Attachment = {
  name: string;
  url: string;
  contentType: string;
  status?: 'uploading' | 'processing' | 'ready' | 'error';
  error?: string;
  storedFilename?: string;
};

// Anonymous feedback types
export interface FeedbackMessage {
  feedback_id: string;
  message: string;
  created_at: string;
}
