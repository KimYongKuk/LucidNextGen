import { fetchWithErrorHandlers } from '@/lib/utils';
import { Workspace, WorkspaceFile } from './workspaces';

export interface ChunkData {
    index: number;
    text: string;
    metadata: Record<string, any>;
}

export interface ChunksResponse {
    total: number;
    offset: number;
    limit: number;
    chunks: ChunkData[];
}

export interface ChunkSearchResult {
    workspace_id: number;
    workspace_name: string;
    user_id: string;
    file_id: string;
    filename: string;
    chunk_index: number;
    chunk_text: string;
    matched_text: string;
}

export interface ChunkSearchResponse {
    total: number;
    offset: number;
    limit: number;
    pattern_type: string | null;
    pattern_label: string;
    results: ChunkSearchResult[];
}

export interface WorkspacesListResponse {
    workspaces: Workspace[];
}

export interface WorkspaceFilesResponse {
    workspace: Workspace;
    files: WorkspaceFile[];
}

const BASE_URL = '/api/v1/admin/workspaces';

export const adminWorkspaceApi = {
    /**
     * 모든 워크스페이스 조회 (Admin 전용)
     */
    listAll: async (): Promise<Workspace[]> => {
        const response = await fetchWithErrorHandlers(BASE_URL);
        const data: WorkspacesListResponse = await response.json();
        return data.workspaces;
    },

    /**
     * 워크스페이스의 파일 목록 조회
     */
    getFiles: async (workspaceId: number): Promise<WorkspaceFilesResponse> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/${workspaceId}/files`);
        return response.json();
    },

    /**
     * 파일의 청크 조회 (미리보기용)
     */
    getChunks: async (
        workspaceId: number,
        fileId: string,
        limit: number = 10,
        offset: number = 0
    ): Promise<ChunksResponse> => {
        const response = await fetchWithErrorHandlers(
            `${BASE_URL}/${workspaceId}/files/${fileId}/chunks?limit=${limit}&offset=${offset}`
        );
        return response.json();
    },

    /**
     * 워크스페이스 삭제 (Admin 전용)
     */
    deleteWorkspace: async (workspaceId: number): Promise<any> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/${workspaceId}`, {
            method: 'DELETE',
        });
        return response.json();
    },

    /**
     * 파일 삭제 (Admin 전용)
     */
    deleteFile: async (workspaceId: number, fileId: string): Promise<any> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/${workspaceId}/files/${fileId}`, {
            method: 'DELETE',
        });
        return response.json();
    },

    /**
     * PII 패턴으로 청크 검색 (Admin 전용)
     */
    searchChunks: async (params: {
        pattern_type?: string;
        workspace_id?: number;
        limit?: number;
        offset?: number;
    }): Promise<ChunkSearchResponse> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/search-chunks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
        return response.json();
    },
};
