// Dummy schema types (artifact 기능 미사용)
export interface Document {
  id: string;
  title: string;
  content: string;
  kind: "text" | "code" | "image" | "sheet";
  createdAt: Date;
  userId: string;
}

export interface Suggestion {
  id: string;
  documentId: string;
  content: string;
  description?: string;
  originalText: string;
  suggestedText: string;
  userId: string;
  createdAt: Date;
}
