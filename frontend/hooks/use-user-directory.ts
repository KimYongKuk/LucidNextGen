"use client";

import { useEffect, useState } from "react";
import { fetchWithErrorHandlers } from "@/lib/utils";

export interface UserInfo {
  user_id: string;
  name: string;
  team: string;
  position: string;
  display: string; // "DA파트 김용국" 형식 (디렉토리 미스 시 사번)
  found: boolean;  // 디렉토리 hit 여부
}

// in-memory 캐시 (탭 세션 동안 재요청 방지)
const _cache = new Map<string, UserInfo>();
const _pending = new Map<string, Promise<UserInfo | null>>();

async function fetchSingle(userId: string): Promise<UserInfo | null> {
  if (_cache.has(userId)) return _cache.get(userId)!;
  if (_pending.has(userId)) return _pending.get(userId)!;

  const p = (async () => {
    try {
      const res = await fetchWithErrorHandlers(`/api/v1/users/${encodeURIComponent(userId)}`);
      const data: UserInfo = await res.json();
      _cache.set(userId, data);
      return data;
    } catch {
      return null;
    } finally {
      _pending.delete(userId);
    }
  })();
  _pending.set(userId, p);
  return p;
}

async function fetchBatch(userIds: string[]): Promise<Record<string, UserInfo>> {
  const missing = userIds.filter((u) => u && !_cache.has(u));
  if (missing.length > 0) {
    try {
      const res = await fetchWithErrorHandlers("/api/v1/users/lookup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_ids: missing }),
      });
      const data: Record<string, UserInfo> = await res.json();
      Object.entries(data).forEach(([k, v]) => _cache.set(k, v));
    } catch {
      // 캐시 미스 — fallback은 호출자가 처리
    }
  }
  const result: Record<string, UserInfo> = {};
  userIds.forEach((u) => {
    if (_cache.has(u)) result[u] = _cache.get(u)!;
  });
  return result;
}

/**
 * 사번 1개 → UserInfo lookup. 캐시 활용.
 */
export function useUserInfo(userId: string | null | undefined): UserInfo | null {
  const [info, setInfo] = useState<UserInfo | null>(
    userId ? _cache.get(userId) ?? null : null,
  );
  useEffect(() => {
    if (!userId) {
      setInfo(null);
      return;
    }
    if (_cache.has(userId)) {
      setInfo(_cache.get(userId)!);
      return;
    }
    let cancelled = false;
    fetchSingle(userId).then((data) => {
      if (!cancelled && data) setInfo(data);
    });
    return () => {
      cancelled = true;
    };
  }, [userId]);
  return info;
}

/**
 * 사번 N개 → { user_id: UserInfo } 매핑. 한 번에 lookup.
 */
export function useUserDirectory(userIds: (string | null | undefined)[]): Record<string, UserInfo> {
  const valid = Array.from(new Set(userIds.filter((u): u is string => !!u)));
  const [dir, setDir] = useState<Record<string, UserInfo>>(() => {
    const initial: Record<string, UserInfo> = {};
    valid.forEach((u) => {
      if (_cache.has(u)) initial[u] = _cache.get(u)!;
    });
    return initial;
  });
  useEffect(() => {
    if (valid.length === 0) return;
    let cancelled = false;
    fetchBatch(valid).then((data) => {
      if (!cancelled) setDir((prev) => ({ ...prev, ...data }));
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valid.join(",")]);
  return dir;
}

/**
 * 사번 → 표시 형식 ("부서 이름" 또는 사번 fallback). 캐시 직접 lookup (동기).
 */
export function formatUserDisplay(userId: string | null | undefined, info?: UserInfo | null): string {
  if (!userId) return "";
  const i = info ?? _cache.get(userId);
  if (!i || !i.found || !i.name) return userId;
  return i.team ? `${i.team} ${i.name}` : i.name;
}
