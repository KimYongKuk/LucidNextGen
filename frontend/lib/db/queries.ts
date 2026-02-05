// Dummy queries (artifact 기능 미사용)
import type { Document, Suggestion } from "./schema";

export async function saveDocument(params: {
  id: string;
  title: string;
  content: string;
  kind: "text" | "code" | "image" | "sheet";
  userId: string;
}): Promise<Document> {
  console.warn("saveDocument called but not implemented");
  return {
    id: params.id,
    title: params.title,
    content: params.content,
    kind: params.kind,
    userId: params.userId,
    createdAt: new Date(),
  };
}

export async function getDocumentById(params: { id: string }): Promise<Document | null> {
  console.warn("getDocumentById called but not implemented");
  return null;
}

export async function getSuggestionsByDocumentId(params: { documentId: string }): Promise<Suggestion[]> {
  console.warn("getSuggestionsByDocumentId called but not implemented");
  return [];
}

export async function getDocumentsById(params: { id: string }): Promise<Document[]> {
  console.warn("getDocumentsById called but not implemented");
  return [];
}

export async function deleteDocumentsByIdAfterTimestamp(params: { id: string; timestamp: Date }): Promise<number> {
  console.warn("deleteDocumentsByIdAfterTimestamp called but not implemented");
  return 0;
}
