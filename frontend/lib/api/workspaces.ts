import { fetchWithErrorHandlers } from '@/lib/utils';

export interface Workspace {
    id: number;
    uuid: string;
    user_id: string;
    name: string;
    description?: string;
    instructions?: string;
    created_at: string;
    updated_at: string;
}

export interface WorkspaceCreate {
    user_id: string;
    name: string;
    description?: string;
    instructions?: string;
}

export interface WorkspaceUpdate {
    name?: string;
    description?: string;
    instructions?: string;
}

export interface WorkspaceFile {
    file_id: string;
    filename: string;
    chunk_count: number;
    uploaded_at?: string;
}

export interface UploadStatus {
    status: 'pending' | 'processing' | 'completed' | 'failed' | 'unknown';
    filename: string;
    workspace_id?: string;  // UUID string
    message: string;
    progress: number;
    result?: any;
}

const BASE_URL = '/api/v1/workspaces';

export const workspaceApi = {
    list: async (userId: string): Promise<Workspace[]> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}?user_id=${userId}`);
        return response.json();
    },

    create: async (data: WorkspaceCreate): Promise<Workspace> => {
        const response = await fetchWithErrorHandlers(BASE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        return response.json();
    },

    get: async (uuid: string, userId: string): Promise<Workspace> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/${uuid}?user_id=${userId}`);
        return response.json();
    },

    update: async (uuid: string, userId: string, data: WorkspaceUpdate): Promise<any> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/${uuid}?user_id=${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        return response.json();
    },

    delete: async (uuid: string, userId: string): Promise<any> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/${uuid}?user_id=${userId}`, {
            method: 'DELETE',
        });
        return response.json();
    },

    uploadFile: async (uuid: string, userId: string, file: File): Promise<any> => {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetchWithErrorHandlers(`${BASE_URL}/${uuid}/upload?user_id=${userId}`, {
            method: 'POST',
            body: formData,
        });
        return response.json();
    },

    getUploadStatus: async (fileId: string): Promise<UploadStatus> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/upload/status/${fileId}`);
        return response.json();
    },

    /**
     * 파일 업로드 후 완료까지 폴링
     * @param uuid 워크스페이스 UUID
     * @param userId 사용자 ID (소유권 검증)
     * @param file 업로드할 파일
     * @param onProgress 진행 상태 콜백 (optional)
     * @returns 완료된 업로드 결과
     */
    uploadFileWithPolling: async (
        uuid: string,
        userId: string,
        file: File,
        onProgress?: (status: UploadStatus) => void
    ): Promise<any> => {
        // 1. 업로드 시작 (즉시 반환)
        const startResult = await workspaceApi.uploadFile(uuid, userId, file);
        const fileId = startResult.file_id;

        if (!fileId) {
            throw new Error('No file_id returned from upload');
        }

        // 2. 상태 폴링
        const pollInterval = 2000; // 2초
        const maxAttempts = 300; // 최대 10분 (2초 * 300)

        for (let attempt = 0; attempt < maxAttempts; attempt++) {
            await new Promise(resolve => setTimeout(resolve, pollInterval));

            const status = await workspaceApi.getUploadStatus(fileId);

            if (onProgress) {
                onProgress(status);
            }

            if (status.status === 'completed') {
                return status.result || { success: true, file_id: fileId };
            }

            if (status.status === 'failed') {
                throw new Error(status.message || 'Upload failed');
            }

            if (status.status === 'unknown') {
                // 상태를 찾을 수 없음 - 이미 완료되었을 수 있음
                return { success: true, file_id: fileId };
            }
        }

        throw new Error('Upload timeout - processing took too long');
    },

    listFiles: async (uuid: string, userId: string): Promise<WorkspaceFile[]> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/${uuid}/files?user_id=${userId}`);
        return response.json();
    },

    deleteFile: async (uuid: string, userId: string, fileId: string): Promise<any> => {
        const response = await fetchWithErrorHandlers(`${BASE_URL}/${uuid}/files/${fileId}?user_id=${userId}`, {
            method: 'DELETE',
        });
        return response.json();
    },
};
