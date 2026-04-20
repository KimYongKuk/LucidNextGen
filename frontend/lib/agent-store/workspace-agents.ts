import type { Agent } from "./types";
import { MOCK_AGENTS } from "./mock-data";

const STORAGE_PREFIX = "ws_agents_";

function storageKey(workspaceUuid: string): string {
  return `${STORAGE_PREFIX}${workspaceUuid}`;
}

function readIds(workspaceUuid: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(storageKey(workspaceUuid));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function writeIds(workspaceUuid: string, ids: string[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(workspaceUuid), JSON.stringify(ids));
  } catch {
    // ignore quota / disabled storage
  }
}

export function getWorkspaceAgents(workspaceUuid: string): Agent[] {
  const ids = new Set(readIds(workspaceUuid));
  return MOCK_AGENTS.filter((a) => ids.has(a.id));
}

export function getWorkspaceAgentIds(workspaceUuid: string): string[] {
  return readIds(workspaceUuid);
}

export function setWorkspaceAgents(workspaceUuid: string, ids: string[]): void {
  const unique = Array.from(new Set(ids));
  writeIds(workspaceUuid, unique);
}

export function addAgentToWorkspace(workspaceUuid: string, agentId: string): void {
  const current = new Set(readIds(workspaceUuid));
  current.add(agentId);
  writeIds(workspaceUuid, Array.from(current));
}

export function removeAgentFromWorkspace(workspaceUuid: string, agentId: string): void {
  const current = readIds(workspaceUuid).filter((id) => id !== agentId);
  writeIds(workspaceUuid, current);
}

export function getInstalledAgents(): Agent[] {
  return MOCK_AGENTS.filter((a) => a.isInstalled);
}
