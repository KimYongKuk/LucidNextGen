"use client";

import { useState } from "react";
import useSWR from "swr";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus, Settings, Folder, Globe, ChevronRight, ChevronDown } from "lucide-react";

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

    const [isMyOpen, setIsMyOpen] = useState(true);
    const [isPublicOpen, setIsPublicOpen] = useState(true);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [selectedWorkspace, setSelectedWorkspace] = useState<Workspace | null>(null);

    const userId = getUserId() ?? "";

    const { data: myWorkspaces, mutate: mutateMy } = useSWR<Workspace[]>(
        userId ? `/api/v1/workspaces?user_id=${userId}` : null,
        () => workspaceApi.list(userId)
    );

    const { data: publicWorkspaces, mutate: mutatePublic } = useSWR<Workspace[]>(
        `/api/v1/workspaces/public`,
        () => workspaceApi.listPublic()
    );

    const refreshAll = () => {
        mutateMy();
        mutatePublic();
    };

    const handleCreateClick = (e: React.MouseEvent) => {
        e.stopPropagation();
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
        router.push(`/?workspace_id=${workspace.uuid}`);
        router.refresh();
    };

    return (
        <>
            {/* 내 워크스페이스 */}
            <Collapsible open={isMyOpen} onOpenChange={setIsMyOpen} className="group/collapsible">
                <SidebarGroup>
                    <SidebarGroupLabel className="group/label flex items-center justify-between pr-0">
                        <CollapsibleTrigger className="flex flex-1 items-center gap-2 text-sm font-medium">
                            {isMyOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            내 워크스페이스
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
                                {myWorkspaces?.map((workspace) => (
                                    <SidebarMenuItem key={workspace.uuid}>
                                        <SidebarMenuButton
                                            isActive={currentWorkspaceId === workspace.uuid}
                                            onClick={() => handleWorkspaceClick(workspace)}
                                            className="group/item"
                                        >
                                            {workspace.is_public ? (
                                                <Globe className="h-4 w-4 text-muted-foreground" />
                                            ) : (
                                                <Folder className="h-4 w-4 text-muted-foreground" />
                                            )}
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

                                {(!myWorkspaces || myWorkspaces.length === 0) && (
                                    <div className="px-4 py-2 text-xs text-muted-foreground">
                                        워크스페이스가 없습니다. + 버튼으로 생성하세요.
                                    </div>
                                )}
                            </SidebarMenu>
                        </SidebarGroupContent>
                    </CollapsibleContent>
                </SidebarGroup>
            </Collapsible>

            {/* 공용 워크스페이스 (항상 노출) */}
            <Collapsible open={isPublicOpen} onOpenChange={setIsPublicOpen} className="group/collapsible">
                <SidebarGroup>
                    <SidebarGroupLabel className="group/label flex items-center justify-between pr-0">
                        <CollapsibleTrigger className="flex flex-1 items-center gap-2 text-sm font-medium">
                            {isPublicOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            공용 워크스페이스
                        </CollapsibleTrigger>
                    </SidebarGroupLabel>
                    <CollapsibleContent>
                        <SidebarGroupContent>
                            <SidebarMenu>
                                {publicWorkspaces?.map((workspace) => (
                                    <SidebarMenuItem key={`public-${workspace.uuid}`}>
                                        <SidebarMenuButton
                                            isActive={currentWorkspaceId === workspace.uuid}
                                            onClick={() => handleWorkspaceClick(workspace)}
                                            className="group/item"
                                        >
                                            <Globe className="h-4 w-4 text-muted-foreground" />
                                            <span>{workspace.name}</span>
                                        </SidebarMenuButton>
                                    </SidebarMenuItem>
                                ))}

                                {(!publicWorkspaces || publicWorkspaces.length === 0) && (
                                    <div className="px-4 py-2 text-xs text-muted-foreground">
                                        공개된 워크스페이스가 없습니다.
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
                onSaved={refreshAll}
                onDeleted={(deletedUuid) => {
                    refreshAll();
                    if (currentWorkspaceId === deletedUuid) {
                        router.push("/");
                    }
                }}
            />
        </>
    );
}
