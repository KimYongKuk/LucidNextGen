"use client";

import { useState } from "react";
import useSWR from "swr";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus, Settings, Folder, ChevronRight, ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    SidebarGroup,
    SidebarGroupLabel,
    SidebarGroupContent,
    SidebarMenu,
    SidebarMenuItem,
    SidebarMenuButton,
    SidebarMenuAction,
} from "@/components/ui/sidebar";
import { WorkspaceSettingsModal } from "@/components/workspace-settings-modal";
import { workspaceApi, type Workspace } from "@/lib/api/workspaces";
import { getUserId } from "@/lib/utils";

export function SidebarWorkspaces() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const currentWorkspaceId = searchParams.get("workspace_id");

    const [isOpen, setIsOpen] = useState(true);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [selectedWorkspace, setSelectedWorkspace] = useState<Workspace | null>(null);

    const userId = getUserId() ?? "";

    const { data: workspaces, mutate } = useSWR<Workspace[]>(
        userId ? `/api/v1/workspaces?user_id=${userId}` : null,
        () => workspaceApi.list(userId)
    );

    const handleCreateClick = (e: React.MouseEvent) => {
        e.stopPropagation(); // Prevent toggling collapsible
        setSelectedWorkspace(null);
        setIsModalOpen(true);
    };

    const handleSettingsClick = (e: React.MouseEvent, workspace: Workspace) => {
        e.stopPropagation();
        e.preventDefault();
        setSelectedWorkspace(workspace);
        setIsModalOpen(true);
    };

    const handleWorkspaceClick = (workspace: Workspace) => {
        // Navigate to new chat with workspace context (using UUID for security)
        router.push(`/?workspace_id=${workspace.uuid}`);
        router.refresh();
    };

    return (
        <>
            <Collapsible open={isOpen} onOpenChange={setIsOpen} className="group/collapsible">
                <SidebarGroup>
                    <SidebarGroupLabel className="group/label flex items-center justify-between pr-0">
                        <CollapsibleTrigger className="flex flex-1 items-center gap-2 text-sm font-medium">
                            {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            My Workspace
                        </CollapsibleTrigger>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-5 w-5 p-0 hover:bg-muted"
                            onClick={handleCreateClick}
                        >
                            <Plus className="h-4 w-4" />
                            <span className="sr-only">Create Workspace</span>
                        </Button>
                    </SidebarGroupLabel>
                    <CollapsibleContent>
                        <SidebarGroupContent>
                            <SidebarMenu>
                                {workspaces?.map((workspace) => (
                                    <SidebarMenuItem key={workspace.uuid}>
                                        <SidebarMenuButton
                                            isActive={currentWorkspaceId === workspace.uuid}
                                            onClick={() => handleWorkspaceClick(workspace)}
                                            className="group/item"
                                        >
                                            <Folder className="h-4 w-4 text-muted-foreground" />
                                            <span>{workspace.name}</span>
                                        </SidebarMenuButton>
                                        <SidebarMenuAction
                                            showOnHover
                                            onClick={(e) => handleSettingsClick(e, workspace)}
                                        >
                                            <Settings className="h-4 w-4" />
                                            <span className="sr-only">Settings</span>
                                        </SidebarMenuAction>
                                    </SidebarMenuItem>
                                ))}

                                {(!workspaces || workspaces.length === 0) && (
                                    <div className="px-4 py-2 text-xs text-muted-foreground">
                                        No workspaces yet. Click + to create one.
                                    </div>
                                )}
                            </SidebarMenu>
                        </SidebarGroupContent>
                    </CollapsibleContent>
                </SidebarGroup>
            </Collapsible>

            <WorkspaceSettingsModal
                open={isModalOpen}
                onOpenChange={setIsModalOpen}
                workspace={selectedWorkspace}
                onSaved={() => mutate()}
                onDeleted={(deletedUuid) => {
                    mutate();
                    // 현재 선택된 워크스페이스가 삭제된 경우 메인 화면으로 이동
                    if (currentWorkspaceId === deletedUuid) {
                        router.push("/");
                    }
                }}
            />
        </>
    );
}
