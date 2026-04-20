"use client";

import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import { mutate } from "swr";
import { Loader2, Upload, FileText, Trash2, Plus } from "lucide-react";

import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
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
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";

import { workspaceApi, type Workspace, type WorkspaceFile, type UploadStatus } from "@/lib/api/workspaces";
import { getUserId } from "@/lib/utils";
import { WorkspaceAgentsTab } from "@/components/workspace-agents-tab";
import { getWorkspaceAgentIds } from "@/lib/agent-store/workspace-agents";

interface WorkspaceSettingsModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    workspace?: Workspace | null; // If null, create mode
    onSaved?: () => void;
    onDeleted?: (workspaceUuid: string) => void;
}

export function WorkspaceSettingsModal({
    open,
    onOpenChange,
    workspace,
    onSaved,
    onDeleted,
}: WorkspaceSettingsModalProps) {
    const [activeTab, setActiveTab] = useState<"general" | "knowledge" | "agents">("general");
    const [isLoading, setIsLoading] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [attachedAgentCount, setAttachedAgentCount] = useState(0);

    // Radix UI bug workaround: nested AlertDialog inside Dialog can leave
    // pointer-events: none stuck on document.body after close
    const forceCleanupPointerEvents = () => {
        setTimeout(() => {
            document.body.style.pointerEvents = '';
        }, 0);
        // Double-check after animations complete
        setTimeout(() => {
            document.body.style.pointerEvents = '';
        }, 300);
    };

    // Form State
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [instructions, setInstructions] = useState("");

    // Alert Dialog State
    const [fileToDelete, setFileToDelete] = useState<string | null>(null);
    const [showWorkspaceDeleteAlert, setShowWorkspaceDeleteAlert] = useState(false);

    // Files State
    const [files, setFiles] = useState<WorkspaceFile[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Load data when workspace changes or modal opens
    useEffect(() => {
        if (open) {
            if (workspace) {
                setName(workspace.name);
                setDescription(workspace.description || "");
                setInstructions(workspace.instructions || "");
                loadFiles(workspace.uuid);
                setAttachedAgentCount(getWorkspaceAgentIds(workspace.uuid).length);
            } else {
                // Reset for create mode
                setName("");
                setDescription("");
                setInstructions("");
                setFiles([]);
                setActiveTab("general");
                setAttachedAgentCount(0);
            }
        }
    }, [open, workspace]);

    const loadFiles = async (workspaceUuid: string) => {
        try {
            const userId = getUserId() ?? "";
            const data = await workspaceApi.listFiles(workspaceUuid, userId);
            setFiles(data);
        } catch (error) {
            console.error("Failed to load files:", error);
            toast.error("Failed to load files");
        }
    };

    const handleSave = async () => {
        if (!name.trim()) {
            toast.error("Workspace name is required");
            return;
        }

        setIsLoading(true);
        try {
            const userId = getUserId() ?? "";

            if (workspace) {
                // Update
                await workspaceApi.update(workspace.uuid, userId, {
                    name,
                    description,
                    instructions,
                });
                // Invalidate workspace cache to update Chat component
                mutate(`/api/v1/workspaces/${workspace.uuid}`);
                toast.success("Workspace updated successfully");
            } else {
                // Create
                await workspaceApi.create({
                    user_id: userId,
                    name,
                    description,
                    instructions,
                });
                toast.success("Workspace created successfully");
            }

            onSaved?.();
            onOpenChange(false);
        } catch (error) {
            console.error("Failed to save workspace:", error);
            toast.error("Failed to save workspace");
        } finally {
            setIsLoading(false);
        }
    };

    const [uploadProgress, setUploadProgress] = useState<string>("");

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const fileList = e.target.files;
        if (!fileList || fileList.length === 0) return;

        if (!workspace) {
            toast.error("Please save the workspace first before uploading files.");
            return;
        }

        setIsUploading(true);
        setUploadProgress("");

        try {
            const userId = getUserId() ?? "";
            const diskOnlyFiles: string[] = [];
            // Upload files sequentially with polling
            for (let i = 0; i < fileList.length; i++) {
                const file = fileList[i];
                setUploadProgress(`Uploading ${file.name} (${i + 1}/${fileList.length})...`);

                const result = await workspaceApi.uploadFileWithPolling(
                    workspace.uuid,
                    userId,
                    file,
                    (status: UploadStatus) => {
                        // Progress callback
                        if (status.status === 'processing') {
                            setUploadProgress(`Processing ${file.name}...`);
                        }
                    }
                );
                if (result?.disk_only) {
                    diskOnlyFiles.push(`${file.name} (${result.warning || "인덱싱 스킵"})`);
                }
            }
            if (diskOnlyFiles.length > 0) {
                toast.info("업로드 완료", {
                    description: `※주의:\n암호화된 파일은 IT VOC 등록을 위한 파일 업로드만 가능합니다.\n암호화된 파일은 분석/요약이 불가하므로, 복호화 후 재업로드 하세요.\n\n해당 파일:\n${diskOnlyFiles.map(f => f.split(" (")[0]).join(", ")}`,
                    duration: 10000,
                });
            } else {
                toast.success("Files uploaded successfully");
            }
            loadFiles(workspace.uuid);
        } catch (error) {
            console.error("Failed to upload files:", error);
            toast.error(error instanceof Error ? error.message : "Failed to upload files");
        } finally {
            setIsUploading(false);
            setUploadProgress("");
            // Reset input
            if (fileInputRef.current) {
                fileInputRef.current.value = "";
            }
        }
    };

    const handleDeleteFile = (fileId: string) => {
        setFileToDelete(fileId);
    };

    const confirmDeleteFile = async () => {
        if (!workspace || !fileToDelete) return;

        try {
            const userId = getUserId() ?? "";
            await workspaceApi.deleteFile(workspace.uuid, userId, fileToDelete);
            toast.success("File deleted");
            loadFiles(workspace.uuid);
        } catch (error) {
            console.error("Failed to delete file:", error);
            toast.error("Failed to delete file");
        } finally {
            setFileToDelete(null);
            forceCleanupPointerEvents();
        }
    };

    const handleDeleteWorkspace = () => {
        setShowWorkspaceDeleteAlert(true);
    };

    const confirmDeleteWorkspace = async () => {
        if (!workspace) return;

        setIsLoading(true);
        try {
            const userId = getUserId() ?? "";
            const deletedUuid = workspace.uuid;
            await workspaceApi.delete(deletedUuid, userId);
            toast.success("Workspace deleted successfully");

            // Close both dialogs and force cleanup pointer-events
            setShowWorkspaceDeleteAlert(false);
            onOpenChange(false);
            forceCleanupPointerEvents();

            onSaved?.();
            onDeleted?.(deletedUuid);
        } catch (error) {
            console.error("Failed to delete workspace:", error);
            toast.error("Failed to delete workspace");
            setShowWorkspaceDeleteAlert(false);
            forceCleanupPointerEvents();
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={(newOpen) => {
            onOpenChange(newOpen);
            if (!newOpen) forceCleanupPointerEvents();
        }}>
            <DialogContent className="sm:max-w-[800px] h-[600px] flex flex-col p-0 gap-0">
                <DialogHeader className="p-6 pb-4 border-b">
                    <DialogTitle>{workspace ? "Workspace 설정" : "Workspace 생성"}</DialogTitle>
                    <DialogDescription>
                        Configure your AI assistant's persona and knowledge base.
                    </DialogDescription>
                </DialogHeader>

                <div className="flex flex-1 overflow-hidden">
                    {/* Sidebar Tabs */}
                    <div className="w-[200px] bg-muted/30 border-r p-4 flex flex-col gap-2">
                        <Button
                            variant={activeTab === "general" ? "secondary" : "ghost"}
                            className="justify-start"
                            onClick={() => setActiveTab("general")}
                        >
                            General
                        </Button>
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div className="w-full">
                                        <Button
                                            variant={activeTab === "knowledge" ? "secondary" : "ghost"}
                                            className="justify-start w-full"
                                            onClick={() => setActiveTab("knowledge")}
                                            disabled={!workspace}
                                        >
                                            Knowledge
                                            {files.length > 0 && (
                                                <Badge variant="secondary" className="ml-auto text-xs">
                                                    {files.length}
                                                </Badge>
                                            )}
                                        </Button>
                                    </div>
                                </TooltipTrigger>
                                {!workspace && (
                                    <TooltipContent side="right">
                                        <p>Save workspace first to add knowledge files</p>
                                    </TooltipContent>
                                )}
                            </Tooltip>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div className="w-full">
                                        <Button
                                            variant={activeTab === "agents" ? "secondary" : "ghost"}
                                            className="justify-start w-full"
                                            onClick={() => setActiveTab("agents")}
                                            disabled={!workspace}
                                        >
                                            Agents
                                            {attachedAgentCount > 0 && (
                                                <Badge variant="secondary" className="ml-auto text-xs">
                                                    {attachedAgentCount}
                                                </Badge>
                                            )}
                                        </Button>
                                    </div>
                                </TooltipTrigger>
                                {!workspace && (
                                    <TooltipContent side="right">
                                        <p>Save workspace first to attach agents</p>
                                    </TooltipContent>
                                )}
                            </Tooltip>
                        </TooltipProvider>
                    </div>

                    {/* Content Area */}
                    <div className="flex-1 p-6 overflow-y-auto">
                        {activeTab === "agents" && workspace ? (
                            <WorkspaceAgentsTab
                                workspaceUuid={workspace.uuid}
                                onCountChange={setAttachedAgentCount}
                            />
                        ) : activeTab === "general" ? (
                            <div className="space-y-6">
                                <div className="space-y-2">
                                    <Label htmlFor="name">Workspace Name</Label>
                                    <Input
                                        id="name"
                                        placeholder="[예시] 회계처리 Assistant"
                                        value={name}
                                        onChange={(e) => setName(e.target.value)}
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="description">Description</Label>
                                    <Input
                                        id="description"
                                        placeholder="[예시] 회계처리 사례집을 학습하여 도움을 주는 어시스턴트"
                                        value={description}
                                        onChange={(e) => setDescription(e.target.value)}
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="instructions">
                                        Instructions (System Prompt)
                                    </Label>
                                    <Textarea
                                        id="instructions"
                                        className="min-h-[200px] font-mono text-sm"
                                        placeholder="[예시] 당신은 회계처리 어시스턴트입니다. 지식문서를 참고하여 회계관련된 특화된 답변을 하세요."
                                        value={instructions}
                                        onChange={(e) => setInstructions(e.target.value)}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        These instructions will be injected into the AI's system prompt.
                                    </p>
                                </div>

                                {workspace && (
                                    <div className="pt-4 border-t flex justify-end">
                                        <Button
                                            variant="destructive"
                                            size="sm"
                                            onClick={handleDeleteWorkspace}
                                            disabled={isLoading}
                                        >
                                            <Trash2 className="mr-2 h-4 w-4" />
                                            Delete Workspace
                                        </Button>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="space-y-4 h-full flex flex-col">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-sm font-medium">Workspace Files</h3>
                                    <div>
                                        <input
                                            type="file"
                                            multiple
                                            className="hidden"
                                            ref={fileInputRef}
                                            onChange={handleFileUpload}
                                            accept=".pdf,.txt,.docx,.pptx,.xlsx,.md,.html,.htm,.csv"
                                        />
                                        <div className="flex items-center gap-2">
                                            {isUploading && uploadProgress && (
                                                <span className="text-xs text-muted-foreground">
                                                    {uploadProgress}
                                                </span>
                                            )}
                                            <Button
                                                size="sm"
                                                onClick={() => fileInputRef.current?.click()}
                                                disabled={isUploading}
                                            >
                                                {isUploading ? (
                                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                ) : (
                                                    <Upload className="mr-2 h-4 w-4" />
                                                )}
                                                Upload Files
                                            </Button>
                                        </div>
                                    </div>
                                </div>

                                <div className="border rounded-md flex-1 overflow-hidden flex flex-col">
                                    {files.length === 0 ? (
                                        <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground p-8">
                                            <Upload className="h-10 w-10 mb-4 opacity-20" />
                                            <p>No files uploaded yet.</p>
                                            <p className="text-sm">Upload documents to give your AI context.</p>
                                        </div>
                                    ) : (
                                        <ScrollArea className="flex-1">
                                            <div className="p-4 space-y-2">
                                                {files.map((file) => (
                                                    <div
                                                        key={file.file_id}
                                                        className="grid grid-cols-[1fr_auto] items-center gap-3 p-3 border rounded-md bg-background hover:bg-muted/50 transition-colors group"
                                                    >
                                                        <div className="flex items-center gap-3 min-w-0 overflow-hidden">
                                                            <div className="h-8 w-8 rounded bg-primary/10 flex items-center justify-center shrink-0">
                                                                <FileText className="h-4 w-4 text-primary" />
                                                            </div>
                                                            <div className="flex flex-col min-w-0 overflow-hidden">
                                                                <p className="text-sm font-medium truncate">
                                                                    {file.filename}
                                                                </p>
                                                                <p className="text-xs text-muted-foreground">
                                                                    {file.chunk_count} chunks
                                                                </p>
                                                            </div>
                                                        </div>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="invisible group-hover:visible transition-all text-destructive hover:text-destructive hover:bg-destructive/10"
                                                            onClick={() => handleDeleteFile(file.file_id)}
                                                        >
                                                            <Trash2 className="h-4 w-4" />
                                                        </Button>
                                                    </div>
                                                ))}
                                            </div>
                                        </ScrollArea>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                <DialogFooter className="p-4 border-t bg-muted/10">
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Cancel
                    </Button>
                    <Button onClick={handleSave} disabled={isLoading}>
                        {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Save Changes
                    </Button>
                </DialogFooter>
            </DialogContent>

            <AlertDialog open={!!fileToDelete} onOpenChange={(open) => {
                if (!open) {
                    setFileToDelete(null);
                    forceCleanupPointerEvents();
                }
            }}>
                <AlertDialogContent onCloseAutoFocus={(e) => e.preventDefault()}>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete File?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete this file? This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={confirmDeleteFile} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                            Delete
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            <AlertDialog open={showWorkspaceDeleteAlert} onOpenChange={(open) => {
                setShowWorkspaceDeleteAlert(open);
                if (!open) forceCleanupPointerEvents();
            }}>
                <AlertDialogContent onCloseAutoFocus={(e) => e.preventDefault()}>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Workspace?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete this workspace? This action cannot be undone and all associated data will be lost.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={confirmDeleteWorkspace} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                            Delete Workspace
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </Dialog >
    );
}
