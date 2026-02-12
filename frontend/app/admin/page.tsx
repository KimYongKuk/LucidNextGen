"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { ArrowLeft, ChevronDown, ChevronRight, Eye, Trash2, FolderOpen, RefreshCw, Search, Shield } from "lucide-react";
import Link from "next/link";
import { adminWorkspaceApi, ChunkData, ChunkSearchResult } from "@/lib/api/admin-workspaces";
import { Workspace, WorkspaceFile } from "@/lib/api/workspaces";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

type DocItem = {
  id: string;
  name: string;
  collection: string;
  status: "ready" | "processing" | "error";
  size: string;
  updatedAt: string;
};

const NAV_TABS = [
  { key: "rag", label: "RAG 관리", hint: "문서 업로드 · 임베딩 · 컬렉션" },
  { key: "workspaces", label: "워크스페이스 관리", hint: "사용자별 파일 관리" },
  { key: "pii-search", label: "개인정보 검색", hint: "PII 패턴 모니터링" },
];

// PII 패턴 정의
const PII_PATTERNS = [
  { key: "resident_number", label: "주민등록번호", description: "6자리-7자리 형식" },
  { key: "account_number", label: "계좌번호", description: "은행 계좌번호 형식" },
  { key: "phone_number", label: "전화번호", description: "휴대폰 번호 형식" },
  { key: "credit_card", label: "신용카드", description: "16자리 카드번호" },
  { key: "email", label: "이메일", description: "이메일 주소 형식" },
];

function TabButton({
  tabKey,
  label,
  hint,
  active,
  onClick,
}: {
  tabKey: string;
  label: string;
  hint?: string;
  active: boolean;
  onClick: (key: string) => void;
}) {
  return (
    <button
      onClick={() => onClick(tabKey)}
      className={[
        "flex flex-col gap-1 border-b-2 px-2 pb-2 text-left transition-colors sm:px-3",
        active
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
      ].join(" ")}
    >
      <span className="text-sm font-semibold">{label}</span>
      {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
    </button>
  );
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-full border bg-muted/40 px-3 py-1 text-xs text-foreground">
      <span className="text-muted-foreground">{label}</span>
      <span className="ml-2 font-semibold">{value}</span>
    </div>
  );
}

function UploadDropZone({
  onSelectFiles,
  isUploading,
}: {
  onSelectFiles: (files: FileList) => void;
  isUploading: boolean;
}) {
  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      onSelectFiles(event.target.files);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/30 px-6 py-10 text-center">
      <div className="rounded-full bg-background px-3 py-1 text-xs text-muted-foreground">
        Drag & Drop
      </div>
      <div className="text-sm text-muted-foreground">
        사내 문서를 업로드하여 임베딩 파이프라인에 보낼 수 있습니다.
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
        <Badge variant="secondary">PDF</Badge>
        <Badge variant="secondary">DOCX</Badge>
        <Badge variant="secondary">PPTX</Badge>
        <Badge variant="secondary">TXT</Badge>
      </div>
      <div className="flex items-center gap-2">
        <label className="inline-flex">
          <input
            type="file"
            multiple
            className="hidden"
            onChange={handleInputChange}
            disabled={isUploading}
          />
          <Button size="sm" asChild>
            <span>파일 선택</span>
          </Button>
        </label>
        <Button size="sm" variant="ghost">
          폴더 업로드
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        ※ 실제 업로드/임베딩 연동은 추후 백엔드 연결 후 활성화됩니다.
      </p>
    </div>
  );
}

function DocList({
  docs,
  onDelete,
  deletingId,
}: {
  docs: DocItem[];
  onDelete?: (fileId: string) => void;
  deletingId?: string | null;
}) {
  return (
    <div className="space-y-2">
      {docs.map((doc) => (
        <div
          key={doc.id}
          className="flex items-center justify-between rounded-lg border bg-card px-4 py-3"
        >
          <div>
            <div className="text-sm font-semibold">{doc.name}</div>
            <div className="text-xs text-muted-foreground">
              {doc.collection} · {doc.size} · {doc.updatedAt}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge
              variant={
                doc.status === "ready"
                  ? "secondary"
                  : doc.status === "processing"
                    ? "outline"
                    : "destructive"
              }
            >
              {doc.status === "ready"
                ? "준비 완료"
                : doc.status === "processing"
                  ? "처리 중"
                  : "오류"}
            </Badge>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onDelete?.(doc.id)}
              disabled={!onDelete || deletingId === doc.id}
            >
              {deletingId === doc.id ? "삭제 중..." : "삭제"}
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}

const ADMIN_API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// 컬렉션 정보 타입 (이름 + 문서 수)
type CollectionInfo = {
  name: string;
  count: number;
};

function RagContent() {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  // Single source of truth for collection selection
  const [selectedCollection, setSelectedCollection] = useState<string>("");
  const [collections, setCollections] = useState<string[]>([]);
  const [collectionInfo, setCollectionInfo] = useState<CollectionInfo[]>([]);
  const [totalChunks, setTotalChunks] = useState<number>(0);

  // Mode and input states (completely separate)
  const [collectionMode, setCollectionMode] = useState<"existing" | "create">("existing");
  const [newCollectionName, setNewCollectionName] = useState("");

  // Validation states
  const [validationError, setValidationError] = useState<string>("");

  // Loading states
  const [isFetchingCollections, setIsFetchingCollections] = useState(false);
  const [isDeletingCollection, setIsDeletingCollection] = useState(false);
  const [isCreatingCollection, setIsCreatingCollection] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  const sessionId = useMemo(
    () => (typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `admin-${Date.now()}`),
    []
  );

  const handleSelectFiles = (files: FileList) => {
    setSelectedFiles(Array.from(files));
  };

  const validateCollectionName = (name: string): string | null => {
    if (!name || !name.trim()) {
      return "컬렉션 이름을 입력하세요.";
    }

    if (name.length > 50) {
      return "컬렉션 이름은 50자를 초과할 수 없습니다.";
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
      return "영문, 숫자, 하이픈(-), 언더스코어(_)만 사용할 수 있습니다.";
    }

    if (collections.includes(name)) {
      return `'${name}' 컬렉션이 이미 존재합니다.`;
    }

    return null; // Valid
  };

  const fetchCollections = async (autoSelect: boolean = true) => {
    setIsFetchingCollections(true);
    try {
      const res = await fetch(`${ADMIN_API_BASE}/api/v1/admin/upload/collections`);
      if (!res.ok) return;
      const data = await res.json();
      const names = Array.isArray(data.collections)
        ? data.collections.filter((name: unknown) => typeof name === "string" && name.trim().length > 0)
        : [];
      setCollections(names);

      // 컬렉션 정보 (이름 + 문서 수) 저장
      const info = Array.isArray(data.collection_info) ? data.collection_info : [];
      setCollectionInfo(info);

      // 컬렉션이 없으면 생성 모드로 전환
      if (names.length === 0) {
        setCollectionMode("create");
        setSelectedCollection("");
        return;
      }

      // autoSelect가 true이고 existing 모드일 때만 자동 선택
      if (autoSelect && collectionMode === "existing") {
        if (!selectedCollection) {
          setSelectedCollection(names[0]);
        } else if (!names.includes(selectedCollection)) {
          setSelectedCollection(names[0]);
        }
      }
    } catch (error) {
      console.error("Failed to fetch collections:", error);
    } finally {
      setIsFetchingCollections(false);
    }
  };

  // 상대 시간 포맷 함수
  const formatRelativeTime = (isoString: string | null | undefined): string => {
    if (!isoString) return "-";
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffSec = Math.floor(diffMs / 1000);
      const diffMin = Math.floor(diffSec / 60);
      const diffHour = Math.floor(diffMin / 60);
      const diffDay = Math.floor(diffHour / 24);

      if (diffSec < 60) return "방금 전";
      if (diffMin < 60) return `${diffMin}분 전`;
      if (diffHour < 24) return `${diffHour}시간 전`;
      if (diffDay < 7) return `${diffDay}일 전`;
      return date.toLocaleDateString("ko-KR");
    } catch {
      return "-";
    }
  };

  const fetchDocs = async () => {
    if (!selectedCollection) return;
    try {
      const url = new URL(`${ADMIN_API_BASE}/api/v1/admin/upload/list`);
      url.searchParams.set("collection", selectedCollection);
      const res = await fetch(url.toString());
      if (!res.ok) return;
      const data = await res.json();

      // 전체 청크 수 저장
      setTotalChunks(data.total_chunks || 0);

      const items = Array.isArray(data.files)
        ? data.files.map((f: any, idx: number) => ({
            id: f.file_id || `placeholder-${idx}`,
            name: f.filename || "unknown",
            collection: f.collection || selectedCollection,
            status: "ready" as const,
            size: f.chunk_count ? `${f.chunk_count} chunks` : "-",
            updatedAt: formatRelativeTime(f.updated_at),
          }))
        : [];
      setDocs(items);
    } catch {
      // placeholder 실패 시 조용히 무시
    }
  };

  const handleCreateCollection = async () => {
    const error = validateCollectionName(newCollectionName);
    if (error) {
      setValidationError(error);
      toast.error(error);
      return;
    }

    setIsCreatingCollection(true);
    setValidationError("");
    toast.info(`'${newCollectionName}' 컬렉션 생성 중...`);

    try {
      const formData = new FormData();
      formData.append("collection_name", newCollectionName);

      const res = await fetch(`${ADMIN_API_BASE}/api/v1/admin/upload/collection`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || "컬렉션 생성 실패");
      }

      toast.success(`컬렉션 '${newCollectionName}' 생성 완료`);

      // 생성 후 existing 모드로 전환 및 선택
      setCollectionMode("existing");
      setSelectedCollection(newCollectionName);
      setNewCollectionName("");

      // 컬렉션 목록 갱신 (자동 선택 안함 - 이미 수동으로 선택했으므로)
      await fetchCollections(false);
    } catch (error: any) {
      toast.error(error?.message || "컬렉션 생성 중 오류가 발생했습니다.");
      setValidationError(error?.message || "생성 실패");
    } finally {
      setIsCreatingCollection(false);
    }
  };

  const handleUpload = async () => {
    if (!selectedFiles.length) {
      toast.warning("업로드할 파일을 선택하세요.");
      return;
    }

    // 생성 모드에서는 업로드 차단
    if (collectionMode === "create") {
      toast.warning("먼저 '저장' 버튼을 눌러 컬렉션을 생성하세요.");
      return;
    }

    if (!selectedCollection || !selectedCollection.trim()) {
      toast.warning("컬렉션을 선택하세요.");
      return;
    }
    setIsUploading(true);
    toast.info("업로드/임베딩 중...");
    try {
      for (const file of selectedFiles) {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("user_id", "admin");
        formData.append("session_id", sessionId);
        formData.append("collection", selectedCollection);

        const res = await fetch(`${ADMIN_API_BASE}/api/v1/admin/upload/file`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const detail = await res.text();
          throw new Error(detail || "업로드 실패");
        }
      }
      toast.info("백그라운드에서 ���베딩 처리 중... 잠시 후 새로고침하세요.");
      setSelectedFiles([]);
      fetchDocs();
    } catch (error: any) {
      toast.error(error?.message || "업로드 중 오류가 발생했습니다.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleReset = async () => {
    setIsResetting(true);
    try {
      // 명시적 컬렉션을 사용할 때는 세션 삭제 대신 컬렉션 초기화가 필요할 수 있지만,
      // 현재는 세션 삭제 API를 호출 후 로컬 상태만 초기화.
      await fetch(`${ADMIN_API_BASE}/api/v1/admin/upload/session/${sessionId}`, { method: "DELETE" });
      setSelectedFiles([]);
      setDocs([]);
      setTotalChunks(0);
      toast.success("세션 초기화 완료");
    } catch {
      toast.error("초기화 중 오류가 발생했습니다.");
    } finally {
      setIsResetting(false);
    }
  };

  const handleDeleteDoc = async (fileId: string) => {
    if (!selectedCollection) {
      toast.warning("컬렉션을 선택하세요.");
      return;
    }
    setDeletingId(fileId);
    toast.info("문서 삭제 중...");
    try {
      const res = await fetch(
        `${ADMIN_API_BASE}/api/v1/admin/upload/file/${encodeURIComponent(selectedCollection)}/${encodeURIComponent(fileId)}`,
        { method: "DELETE" }
      );
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || "삭제 실패");
      }
      toast.success("문서 삭제 완료");
      fetchDocs();
    } catch (error: any) {
      toast.error(error?.message || "삭제 중 오류가 발생했습니다.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleDeleteCollection = async () => {
    if (collectionMode !== "existing" || !selectedCollection) {
      toast.warning("삭제할 컬렉션을 선택하세요.");
      return;
    }
    const target = selectedCollection;
    // 간단 확인
    if (typeof window !== "undefined") {
      const confirmed = window.confirm(
        `컬렉션 '${target}'을(를) 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없으며, 컬렉션 내의 모든 문서가 삭제됩니다.`
      );
      if (!confirmed) return;
    }
    setIsDeletingCollection(true);
    toast.info("컬렉션 삭제 중...");
    try {
      const res = await fetch(
        `${ADMIN_API_BASE}/api/v1/admin/upload/collection/${encodeURIComponent(target)}`,
        { method: "DELETE" }
      );
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || "컬렉션 삭제 실패");
      }
      toast.success("컬렉션 삭제 완료");
      setSelectedCollection("");
      setDocs([]);
      setSelectedFiles([]);
      setTotalChunks(0);
      await fetchCollections();
    } catch (error: any) {
      toast.error(error?.message || "컬렉션 삭제 중 오류가 발생했습니다.");
    } finally {
      setIsDeletingCollection(false);
    }
  };

  useEffect(() => {
    fetchCollections();
  }, []);

  useEffect(() => {
    if (selectedCollection && collectionMode === "existing") {
      fetchDocs();
    }
  }, [selectedCollection, collectionMode]);


  return (
    <div className="space-y-6">
      {/* <div className="grid gap-4 sm:grid-cols-2">
        <StatPill label="활성 컬렉션" value="5" />
        <StatPill label="최근 24h 임베딩" value="32 문서" />
      </div> */}

      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-1 flex-col gap-3">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2">
                문서 업로드 & 임베딩
                {collectionMode === "create" && (
                  <Badge variant="outline" className="text-xs font-normal">
                    생성 모드
                  </Badge>
                )}
              </CardTitle>
              {/* <CardDescription>
                업로드된 문서는 추출 → 청크 → 임베딩 → 컬렉션 저장 파이프라인을 거칩니다.
              </CardDescription> */}
            </div>

            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => {
                  setCollectionMode((prev) => {
                    const next = prev === "create" ? "existing" : "create";

                    if (next === "create") {
                      setNewCollectionName("");
                      setValidationError("");
                    } else if (collections.length > 0) {
                      setSelectedCollection(collections[0]);
                    }

                    return next;
                  });
                }}
              >
                {collectionMode === "create" ? "목록에서 선택" : "컬렉션 생성"}
              </Button>

              {collectionMode === "existing" ? (
                <>
                  <Select
                    value={selectedCollection && collections.includes(selectedCollection) ? selectedCollection : undefined}
                    onValueChange={(value) => {
                      setSelectedCollection(value);
                      setValidationError("");
                    }}
                    disabled={isFetchingCollections}
                  >
                    <SelectTrigger id="collection" className="h-8 w-full max-w-xs text-xs">
                      <SelectValue placeholder="컬렉션을 선택하세요" />
                    </SelectTrigger>
                    <SelectContent>
                      {collections.map((name) => {
                        const info = collectionInfo.find((c) => c.name === name);
                        return (
                          <SelectItem key={name} value={name}>
                            {name} {info ? `(${info.count} chunks)` : ""}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                  {selectedCollection && totalChunks > 0 && (
                    <Badge variant="secondary" className="h-6 text-xs">
                      {totalChunks} chunks
                    </Badge>
                  )}
                </>
              ) : (
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <Input
                      id="collection"
                      className={`h-8 max-w-xs text-xs ${
                        validationError ? "border-red-500 focus-visible:ring-red-500" : ""
                      }`}
                      value={newCollectionName}
                      onChange={(e) => {
                        const value = e.target.value;
                        setNewCollectionName(value);

                        // 실시간 검증
                        const error = validateCollectionName(value);
                        setValidationError(error || "");
                      }}
                      placeholder="예: admin-hr, admin-finance"
                      disabled={isCreatingCollection}
                    />
                    <Button
                      type="button"
                      size="sm"
                      className="h-7 px-3 text-xs"
                      onClick={handleCreateCollection}
                      disabled={isCreatingCollection || !!validationError || !newCollectionName.trim()}
                    >
                      {isCreatingCollection ? "생성 중..." : "저장"}
                    </Button>
                  </div>
                  {validationError ? (
                    <p className="text-xs text-red-500">{validationError}</p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      영문, 숫자, 하이픈(-), 언더스코어(_)만 사용 가능 (최대 50자)
                    </p>
                  )}
                </div>
              )}

              {collectionMode === "existing" && selectedCollection ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 px-2 text-xs sm:ml-2"
                  onClick={handleDeleteCollection}
                  disabled={isDeletingCollection}
                >
                  {isDeletingCollection ? "삭제 중..." : "컬렉션 삭제"}
                </Button>
              ) : null}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleReset} disabled={isUploading || isResetting}>
              초기화
            </Button>
            <Button
              size="sm"
              onClick={handleUpload}
              disabled={
                isUploading ||
                collectionMode === "create" ||
                !selectedCollection ||
                selectedFiles.length === 0
              }
            >
              {isUploading ? "진행 중..." : "임베딩 시작"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <UploadDropZone onSelectFiles={handleSelectFiles} isUploading={isUploading} />
          {selectedFiles.length > 0 ? (
            <div className="rounded-md border bg-muted/40 p-3 text-left text-xs text-muted-foreground">
              <div className="mb-1 font-semibold text-foreground">선택된 파일</div>
              <ul className="list-disc pl-4">
                {selectedFiles.map((file) => (
                  <li key={file.name}>{file.name}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {/* <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="collection">컬렉션 선택</Label>
              <Input id="collection" placeholder="예: hr-handbook" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="chunk">청크 사이즈 / 오버랩</Label>
              <Input id="chunk" placeholder="예: 1024 / 128" />
            </div>
          </div> */}
          {/* <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="outline">OCR</Badge>
            <Badge variant="outline">테이블 유지</Badge>
            <Badge variant="outline">PII 마스킹</Badge>
            <span>옵션은 추후 설정 페이지에서 연결됩니다.</span>
          </div> */}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>임베딩된 문서</CardTitle>
          <CardDescription>
            최근 인덱싱된 문서와 상태를 확인하고, 필요 시 컬렉션에서 제거합니다.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <DocList docs={docs} onDelete={handleDeleteDoc} deletingId={deletingId} />
          <div className="flex justify-end">
            <Button variant="ghost" size="sm">
              전체 보기
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* <Card>
        <CardHeader>
          <CardTitle>컬렉션 관리</CardTitle>
          <CardDescription>컬렉션별 메타데이터와 정책을 설정합니다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="target-collection">컬렉션</Label>
              <Input id="target-collection" placeholder="예: finance-2024" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="retention">보관 기간 (일)</Label>
              <Input id="retention" placeholder="예: 180" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="embedding-model">임베딩 모델</Label>
              <Input id="embedding-model" placeholder="예: titan-embed-text-v2" />
            </div>
          </div>
          <Separator />
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary">자동 재임베딩</Badge>
            <Badge variant="secondary">중복 제거</Badge>
            <Badge variant="secondary">보안 등급 태깅</Badge>
            <span>추후 설정 값은 백엔드 연결 시 저장됩니다.</span>
          </div>
          <div className="flex gap-2">
            <Button size="sm">컬렉션 생성/업데이트</Button>
            <Button size="sm" variant="ghost">
              컬렉션 비우기
            </Button>
            <Button size="sm" variant="outline">
              삭제
            </Button>
          </div>
        </CardContent>
      </Card> */}
    </div>
  );
}

// ============================================================================
// 워크스페이스 관리 컴포넌트
// ============================================================================

interface GroupedWorkspaces {
  [userId: string]: Workspace[];
}

function WorkspaceAdminContent() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedUsers, setExpandedUsers] = useState<Set<string>>(new Set());

  // 사용자 필터링 + 페이지네이션
  const [userFilter, setUserFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const USERS_PER_PAGE = 10;

  // 선택된 워크스페이스 (파일 목록 표시용)
  const [selectedWorkspace, setSelectedWorkspace] = useState<Workspace | null>(null);
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFile[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);

  // 청크 미리보기 모달
  const [chunkPreviewOpen, setChunkPreviewOpen] = useState(false);
  const [previewFile, setPreviewFile] = useState<WorkspaceFile | null>(null);
  const [chunks, setChunks] = useState<ChunkData[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [chunkOffset, setChunkOffset] = useState(0);
  const [isLoadingChunks, setIsLoadingChunks] = useState(false);
  const CHUNKS_PER_PAGE = 5;

  // 삭제 확인 다이얼로그
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ type: "workspace" | "file"; workspace: Workspace; file?: WorkspaceFile } | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // 사용자별 그룹화
  const groupedWorkspaces = useMemo(() => {
    const grouped: GroupedWorkspaces = {};
    workspaces.forEach((ws) => {
      if (!grouped[ws.user_id]) {
        grouped[ws.user_id] = [];
      }
      grouped[ws.user_id].push(ws);
    });
    return grouped;
  }, [workspaces]);

  // 필터링된 결과
  const filteredGroupedWorkspaces = useMemo(() => {
    if (!userFilter.trim()) return groupedWorkspaces;
    return Object.fromEntries(
      Object.entries(groupedWorkspaces).filter(([userId]) =>
        userId.toLowerCase().includes(userFilter.toLowerCase())
      )
    );
  }, [groupedWorkspaces, userFilter]);

  // 페이지네이션 계산
  const userIds = Object.keys(filteredGroupedWorkspaces);
  const totalUsers = userIds.length;
  const totalPages = Math.ceil(totalUsers / USERS_PER_PAGE);
  const paginatedUserIds = userIds.slice(
    (currentPage - 1) * USERS_PER_PAGE,
    currentPage * USERS_PER_PAGE
  );

  // 필터 변경 시 페이지 리셋
  useEffect(() => {
    setCurrentPage(1);
  }, [userFilter]);

  const fetchWorkspaces = async () => {
    setIsLoading(true);
    try {
      const data = await adminWorkspaceApi.listAll();
      setWorkspaces(data);
      // 첫 번째 사용자 자동 확장
      if (data.length > 0) {
        const firstUserId = data[0].user_id;
        setExpandedUsers(new Set([firstUserId]));
      }
    } catch (error) {
      console.error("Failed to fetch workspaces:", error);
      toast.error("워크스페이스 목록을 불러오는데 실패했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  const fetchWorkspaceFiles = async (workspace: Workspace) => {
    setIsLoadingFiles(true);
    try {
      const data = await adminWorkspaceApi.getFiles(workspace.id);
      setWorkspaceFiles(data.files);
    } catch (error) {
      console.error("Failed to fetch files:", error);
      toast.error("파일 목록을 불러오는데 실패했습니다.");
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const fetchChunks = async (workspaceId: number, fileId: string, offset: number = 0) => {
    setIsLoadingChunks(true);
    try {
      const data = await adminWorkspaceApi.getChunks(workspaceId, fileId, CHUNKS_PER_PAGE, offset);
      setChunks(data.chunks);
      setTotalChunks(data.total);
      setChunkOffset(offset);
    } catch (error) {
      console.error("Failed to fetch chunks:", error);
      toast.error("청크를 불러오는데 실패했습니다.");
    } finally {
      setIsLoadingChunks(false);
    }
  };

  const handleOpenWorkspace = (workspace: Workspace) => {
    setSelectedWorkspace(workspace);
    fetchWorkspaceFiles(workspace);
  };

  const handleBackToList = () => {
    setSelectedWorkspace(null);
    setWorkspaceFiles([]);
  };

  const handlePreviewChunks = (file: WorkspaceFile) => {
    if (!selectedWorkspace) return;
    setPreviewFile(file);
    setChunkPreviewOpen(true);
    fetchChunks(selectedWorkspace.id, file.file_id, 0);
  };

  const handleDeleteClick = (type: "workspace" | "file", workspace: Workspace, file?: WorkspaceFile) => {
    setDeleteTarget({ type, workspace, file });
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;

    setIsDeleting(true);
    try {
      if (deleteTarget.type === "workspace") {
        await adminWorkspaceApi.deleteWorkspace(deleteTarget.workspace.id);
        toast.success(`워크스페이스 '${deleteTarget.workspace.name}' 삭제 완료`);
        fetchWorkspaces();
        if (selectedWorkspace?.id === deleteTarget.workspace.id) {
          handleBackToList();
        }
      } else if (deleteTarget.file) {
        await adminWorkspaceApi.deleteFile(deleteTarget.workspace.id, deleteTarget.file.file_id);
        toast.success(`파일 '${deleteTarget.file.filename}' 삭제 완료`);
        fetchWorkspaceFiles(deleteTarget.workspace);
      }
    } catch (error) {
      console.error("Failed to delete:", error);
      toast.error("삭제에 실패했습니다.");
    } finally {
      setIsDeleting(false);
      setDeleteDialogOpen(false);
      setDeleteTarget(null);
    }
  };

  const toggleUserExpand = (userId: string) => {
    setExpandedUsers((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) {
        next.delete(userId);
      } else {
        next.add(userId);
      }
      return next;
    });
  };

  useEffect(() => {
    fetchWorkspaces();
  }, []);

  // 파일 목록 뷰
  if (selectedWorkspace) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={handleBackToList}>
            ← 뒤로
          </Button>
          <div>
            <h2 className="text-lg font-semibold">{selectedWorkspace.name}</h2>
            <p className="text-xs text-muted-foreground">
              {selectedWorkspace.user_id} · {workspaceFiles.length}개 파일
            </p>
          </div>
        </div>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between py-3">
            <CardTitle className="text-base">파일 목록</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => fetchWorkspaceFiles(selectedWorkspace)}
              disabled={isLoadingFiles}
            >
              <RefreshCw className={`h-4 w-4 ${isLoadingFiles ? "animate-spin" : ""}`} />
            </Button>
          </CardHeader>
          <CardContent>
            {isLoadingFiles ? (
              <div className="py-8 text-center text-sm text-muted-foreground">로딩 중...</div>
            ) : workspaceFiles.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">파일이 없습니다.</div>
            ) : (
              <div className="space-y-2">
                {workspaceFiles.map((file) => (
                  <div
                    key={file.file_id}
                    className="flex items-center justify-between rounded-lg border bg-card px-4 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{file.filename}</div>
                      <div className="text-xs text-muted-foreground">
                        {file.chunk_count} chunks
                        {file.uploaded_at && ` · ${new Date(file.uploaded_at).toLocaleDateString()}`}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handlePreviewChunks(file)}
                      >
                        <Eye className="mr-1 h-4 w-4" />
                        미리보기
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => handleDeleteClick("file", selectedWorkspace, file)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 청크 미리보기 모달 */}
        <Dialog open={chunkPreviewOpen} onOpenChange={setChunkPreviewOpen}>
          <DialogContent className="max-h-[80vh] max-w-2xl overflow-hidden">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <span className="truncate">청크 미리보기: {previewFile?.filename}</span>
                <Badge variant="secondary">{totalChunks} chunks</Badge>
              </DialogTitle>
            </DialogHeader>
            <div className="max-h-[60vh] space-y-3 overflow-y-auto pr-2">
              {isLoadingChunks ? (
                <div className="py-8 text-center text-sm text-muted-foreground">로딩 중...</div>
              ) : chunks.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">청크가 없습니다.</div>
              ) : (
                chunks.map((chunk, idx) => (
                  <div key={chunk.index} className="space-y-1">
                    <div className="text-xs font-medium text-muted-foreground">
                      Chunk {chunkOffset + idx + 1}
                    </div>
                    <div className="max-h-32 overflow-y-auto rounded-md border bg-muted/30 p-3 text-sm">
                      {chunk.text}
                    </div>
                  </div>
                ))
              )}
            </div>
            {totalChunks > CHUNKS_PER_PAGE && (
              <div className="flex items-center justify-center gap-2 border-t pt-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (selectedWorkspace && previewFile) {
                      fetchChunks(selectedWorkspace.id, previewFile.file_id, Math.max(0, chunkOffset - CHUNKS_PER_PAGE));
                    }
                  }}
                  disabled={chunkOffset === 0 || isLoadingChunks}
                >
                  이전
                </Button>
                <span className="text-sm text-muted-foreground">
                  {Math.floor(chunkOffset / CHUNKS_PER_PAGE) + 1} / {Math.ceil(totalChunks / CHUNKS_PER_PAGE)}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (selectedWorkspace && previewFile) {
                      fetchChunks(selectedWorkspace.id, previewFile.file_id, chunkOffset + CHUNKS_PER_PAGE);
                    }
                  }}
                  disabled={chunkOffset + CHUNKS_PER_PAGE >= totalChunks || isLoadingChunks}
                >
                  다음
                </Button>
              </div>
            )}
          </DialogContent>
        </Dialog>

        {/* 삭제 확인 다이얼로그 */}
        <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>삭제 확인</AlertDialogTitle>
              <AlertDialogDescription>
                {deleteTarget?.type === "workspace"
                  ? `워크스페이스 '${deleteTarget.workspace.name}'을(를) 삭제하시겠습니까? 이 작업은 되돌릴 수 없으며, 모든 파일이 삭제됩니다.`
                  : `파일 '${deleteTarget?.file?.filename}'을(를) 삭제하시겠습니까?`}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isDeleting}>취소</AlertDialogCancel>
              <AlertDialogAction onClick={handleConfirmDelete} disabled={isDeleting}>
                {isDeleting ? "삭제 중..." : "삭제"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  }

  // 워크스페이스 목록 뷰
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">사용자별 워크스페이스</h2>
          <span className="text-sm text-muted-foreground">
            총 {totalUsers}명
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Input
            placeholder="사용자 ID 검색..."
            value={userFilter}
            onChange={(e) => setUserFilter(e.target.value)}
            className="h-8 w-48"
          />
          <Button variant="outline" size="sm" onClick={fetchWorkspaces} disabled={isLoading}>
            <RefreshCw className={`mr-1 h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            새로고침
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-sm text-muted-foreground">로딩 중...</div>
      ) : totalUsers === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          {userFilter ? "검색 결과가 없습니다." : "등록된 워크스페이스가 없습니다."}
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {paginatedUserIds.map((userId) => {
              const userWorkspaces = filteredGroupedWorkspaces[userId];
              return (
                <Card key={userId}>
                  <div
                    className="flex cursor-pointer items-center justify-between px-4 py-3"
                    onClick={() => toggleUserExpand(userId)}
                  >
                    <div className="flex items-center gap-2">
                      {expandedUsers.has(userId) ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                      <span className="font-medium">{userId}</span>
                      <Badge variant="secondary">{userWorkspaces.length}개 워크스페이스</Badge>
                    </div>
                  </div>

                  {expandedUsers.has(userId) && (
                    <CardContent className="border-t pt-3">
                      <div className="space-y-2">
                        {userWorkspaces.map((ws) => (
                          <div
                            key={ws.id}
                            className="flex items-center justify-between rounded-lg border bg-muted/30 px-4 py-3"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="truncate font-medium">{ws.name}</div>
                              <div className="text-xs text-muted-foreground">
                                {ws.description || "설명 없음"} · {new Date(ws.updated_at).toLocaleDateString()}
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleOpenWorkspace(ws)}
                              >
                                <FolderOpen className="mr-1 h-4 w-4" />
                                열기
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-destructive hover:text-destructive"
                                onClick={() => handleDeleteClick("workspace", ws)}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  )}
                </Card>
              );
            })}
          </div>

          {/* 페이지네이션 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                이전
              </Button>
              <span className="text-sm text-muted-foreground">
                {currentPage} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
              >
                다음
              </Button>
            </div>
          )}
        </>
      )}

      {/* 삭제 확인 다이얼로그 (목록 뷰용) */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>삭제 확인</AlertDialogTitle>
            <AlertDialogDescription>
              워크스페이스 &apos;{deleteTarget?.workspace.name}&apos;을(를) 삭제하시겠습니까?
              이 작업은 되돌릴 수 없으며, 모든 파일이 삭제됩니다.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>취소</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmDelete} disabled={isDeleting}>
              {isDeleting ? "삭제 중..." : "삭제"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ============================================================================
// 개인정보 검색 컴포넌트
// ============================================================================

function PIISearchContent() {
  const [selectedPattern, setSelectedPattern] = useState<string | null>(null);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<number | null>(null);
  const [searchResults, setSearchResults] = useState<ChunkSearchResult[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [isSearching, setIsSearching] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const RESULTS_PER_PAGE = 10;

  // 워크스페이스 목록 로드
  useEffect(() => {
    const loadWorkspaces = async () => {
      try {
        const data = await adminWorkspaceApi.listAll();
        setWorkspaces(data);
      } catch (error) {
        console.error("Failed to load workspaces:", error);
      }
    };
    loadWorkspaces();
  }, []);

  const handleSearch = async (patternType: string) => {
    setSelectedPattern(patternType);
    setCurrentPage(1);
    setIsSearching(true);

    try {
      const response = await adminWorkspaceApi.searchChunks({
        pattern_type: patternType,
        workspace_id: selectedWorkspaceId ?? undefined,
        limit: RESULTS_PER_PAGE,
        offset: 0,
      });

      setSearchResults(response.results);
      setTotalResults(response.total);
    } catch (error) {
      console.error("Search failed:", error);
      toast.error("검색에 실패했습니다.");
    } finally {
      setIsSearching(false);
    }
  };

  const handlePageChange = async (newPage: number) => {
    if (!selectedPattern) return;

    setIsSearching(true);
    setCurrentPage(newPage);

    try {
      const response = await adminWorkspaceApi.searchChunks({
        pattern_type: selectedPattern,
        workspace_id: selectedWorkspaceId ?? undefined,
        limit: RESULTS_PER_PAGE,
        offset: (newPage - 1) * RESULTS_PER_PAGE,
      });

      setSearchResults(response.results);
      setTotalResults(response.total);
    } catch (error) {
      console.error("Search failed:", error);
      toast.error("검색에 실패했습니다.");
    } finally {
      setIsSearching(false);
    }
  };

  const handleDeleteFile = async (result: ChunkSearchResult) => {
    if (!window.confirm(`파일 '${result.filename}'을(를) 삭제하시겠습니까?`)) return;

    try {
      await adminWorkspaceApi.deleteFile(result.workspace_id, result.file_id);
      toast.success("파일이 삭제되었습니다.");
      // 검색 결과 새로고침
      if (selectedPattern) {
        handleSearch(selectedPattern);
      }
    } catch (error) {
      console.error("Delete failed:", error);
      toast.error("삭제에 실패했습니다.");
    }
  };

  const totalPages = Math.ceil(totalResults / RESULTS_PER_PAGE);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            개인정보 패턴 검색
          </CardTitle>
          <CardDescription>
            워크스페이스에 저장된 문서에서 개인정보 패턴을 검색합니다.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 워크스페이스 필터 */}
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">검색 범위:</span>
            <Select
              value={selectedWorkspaceId?.toString() ?? "all"}
              onValueChange={(value) => {
                setSelectedWorkspaceId(value === "all" ? null : Number(value));
                setSearchResults([]);
                setTotalResults(0);
                setSelectedPattern(null);
              }}
            >
              <SelectTrigger className="w-64">
                <SelectValue placeholder="전체 워크스페이스" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">전체 워크스페이스</SelectItem>
                {workspaces.map((ws) => (
                  <SelectItem key={ws.id} value={ws.id.toString()}>
                    {ws.user_id} / {ws.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 패턴 버튼 */}
          <div className="flex flex-wrap gap-2">
            {PII_PATTERNS.map((pattern) => (
              <Button
                key={pattern.key}
                variant={selectedPattern === pattern.key ? "default" : "outline"}
                size="sm"
                onClick={() => handleSearch(pattern.key)}
                disabled={isSearching}
                className="gap-2"
              >
                <Search className="h-4 w-4" />
                {pattern.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 검색 결과 */}
      {(searchResults.length > 0 || isSearching) && (
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-base flex items-center justify-between">
              <span>
                검색 결과
                {totalResults > 0 && (
                  <Badge variant="secondary" className="ml-2">
                    {totalResults}건
                  </Badge>
                )}
              </span>
              {isSearching && (
                <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isSearching && searchResults.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                검색 중...
              </div>
            ) : searchResults.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                검색 결과가 없습니다.
              </div>
            ) : (
              <div className="space-y-3">
                {searchResults.map((result, idx) => (
                  <div
                    key={`${result.workspace_id}-${result.file_id}-${result.chunk_index}-${idx}`}
                    className="rounded-lg border bg-card p-4"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex items-center gap-2 text-sm">
                          <Badge variant="outline">{result.user_id}</Badge>
                          <span className="text-muted-foreground">/</span>
                          <span className="font-medium">{result.workspace_name}</span>
                          <span className="text-muted-foreground">/</span>
                          <span>{result.filename}</span>
                          <Badge variant="secondary" className="text-xs">
                            청크 #{result.chunk_index}
                          </Badge>
                        </div>
                        {result.matched_text && (
                          <div className="text-sm">
                            <span className="text-muted-foreground">매칭: </span>
                            <code className="rounded bg-destructive/10 px-1.5 py-0.5 text-destructive">
                              {result.matched_text}
                            </code>
                          </div>
                        )}
                        <div className="max-h-24 overflow-y-auto rounded bg-muted/50 p-2 text-xs text-muted-foreground">
                          {result.chunk_text}
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="shrink-0 text-destructive hover:text-destructive"
                        onClick={() => handleDeleteFile(result)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}

                {/* 페이지네이션 */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-center gap-2 pt-4">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handlePageChange(currentPage - 1)}
                      disabled={currentPage === 1 || isSearching}
                    >
                      이전
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      {currentPage} / {totalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handlePageChange(currentPage + 1)}
                      disabled={currentPage === totalPages || isSearching}
                    >
                      다음
                    </Button>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Placeholder({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border bg-muted/40 px-6 py-16 text-center">
      <div className="text-sm font-semibold">{label}</div>
      <div className="text-sm text-muted-foreground">준비 중입니다.</div>
    </div>
  );
}

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<string>("rag");

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm">
              <Link href="/">
                <ArrowLeft className="mr-1 h-4 w-4" />
                채팅으로
              </Link>
            </Button>
          </div>
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold">Index Documents</h1>
              {/* <p className="text-sm text-muted-foreground">
                문서 업로드, 임베딩을 한 곳에서 관리
              </p> */}
            </div>
            {/* <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">Preview</Badge>
              <Button variant="outline" size="sm">
                변경사항 초안
              </Button>
            </div> */}
          </div>
        </div>

        <div className="flex gap-4 border-b">
          {NAV_TABS.map((tab) => (
            <TabButton
              key={tab.key}
              tabKey={tab.key}
              label={tab.label}
              hint={tab.hint}
              active={activeTab === tab.key}
              onClick={setActiveTab}
            />
          ))}
        </div>

        {activeTab === "rag" && <RagContent />}
        {activeTab === "workspaces" && <WorkspaceAdminContent />}
        {activeTab === "pii-search" && <PIISearchContent />}
      </div>
    </div>
  );
}
