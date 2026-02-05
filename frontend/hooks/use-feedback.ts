"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { FeedbackMessage } from "@/lib/types";
import { getUserId } from "@/lib/utils";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface UseFeedbackOptions {
  pollingInterval?: number; // Default 5000ms
  limit?: number; // Default 20
  enabled?: boolean; // Default true - set to false to disable polling
}

interface UseFeedbackReturn {
  feedbacks: FeedbackMessage[];
  isLoading: boolean;
  error: string | null;
  submitFeedback: (message: string) => Promise<void>;
  loadMore: () => Promise<void>;
  hasMore: boolean;
  isSubmitting: boolean;
}

export function useFeedback(options: UseFeedbackOptions = {}): UseFeedbackReturn {
  const { pollingInterval = 5000, limit = 20, enabled = true } = options;

  const [feedbacks, setFeedbacks] = useState<FeedbackMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);

  // Track latest timestamp for polling
  const latestTimestampRef = useRef<string | null>(null);
  const isPollingRef = useRef(false);

  // Initial fetch
  const fetchFeedbacks = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const url = new URL(`${BACKEND_URL}/api/v1/feedback`);
      url.searchParams.set("limit", limit.toString());

      const response = await fetch(url.toString());
      if (!response.ok) {
        throw new Error("Failed to fetch feedbacks");
      }

      const data = await response.json();

      // Keep newest first (card stack style)
      setFeedbacks(data.feedbacks);
      setHasMore(data.has_more);
      setCursor(data.next_cursor);

      // Update latest timestamp for polling
      if (data.feedbacks.length > 0) {
        latestTimestampRef.current = data.feedbacks[0].created_at;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, [limit]);

  // Poll for new feedbacks
  const pollNewFeedbacks = useCallback(async () => {
    if (!latestTimestampRef.current || isPollingRef.current) return;

    try {
      isPollingRef.current = true;
      const url = `${BACKEND_URL}/api/v1/feedback/since/${encodeURIComponent(latestTimestampRef.current)}`;

      const response = await fetch(url);
      if (!response.ok) return;

      const data = await response.json();

      if (data.feedbacks.length > 0) {
        setFeedbacks((prev) => {
          // Deduplicate by feedback_id
          const existingIds = new Set(prev.map((f) => f.feedback_id));
          const newFeedbacks = data.feedbacks.filter(
            (f: FeedbackMessage) => !existingIds.has(f.feedback_id)
          );
          // Add new feedbacks to the beginning (newest first)
          return [...newFeedbacks, ...prev];
        });

        if (data.latest_timestamp) {
          latestTimestampRef.current = data.latest_timestamp;
        }
      }
    } catch {
      // Silent fail for polling
    } finally {
      isPollingRef.current = false;
    }
  }, []);

  // Load more (older) feedbacks
  const loadMore = useCallback(async () => {
    if (!hasMore || !cursor) return;

    try {
      const url = new URL(`${BACKEND_URL}/api/v1/feedback`);
      url.searchParams.set("limit", limit.toString());
      url.searchParams.set("cursor", cursor);

      const response = await fetch(url.toString());
      if (!response.ok) {
        throw new Error("Failed to load more feedbacks");
      }

      const data = await response.json();

      // Append older feedbacks to the end (newest first order)
      setFeedbacks((prev) => [...prev, ...data.feedbacks]);
      setHasMore(data.has_more);
      setCursor(data.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }, [hasMore, cursor, limit]);

  // Submit new feedback
  const submitFeedback = useCallback(async (message: string) => {
    if (!message.trim()) return;

    try {
      setIsSubmitting(true);
      setError(null);

      const response = await fetch(`${BACKEND_URL}/api/v1/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: message.trim(),
          user_id: getUserId() ?? undefined
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to submit feedback");
      }

      const newFeedback = await response.json();

      // Optimistic update - add to beginning (newest first)
      setFeedbacks((prev) => [newFeedback, ...prev]);

      // Update latest timestamp
      if (newFeedback.created_at) {
        latestTimestampRef.current = newFeedback.created_at;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      throw err;
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  // Initial fetch on mount (only when enabled)
  useEffect(() => {
    if (enabled) {
      fetchFeedbacks();
    }
  }, [fetchFeedbacks, enabled]);

  // Polling interval (only when enabled)
  useEffect(() => {
    if (!enabled) return;

    const handleVisibilityChange = () => {
      // Don't poll when tab is hidden
      if (document.hidden) return;
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    const intervalId = setInterval(() => {
      if (!document.hidden) {
        pollNewFeedbacks();
      }
    }, pollingInterval);

    return () => {
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [pollingInterval, pollNewFeedbacks, enabled]);

  return {
    feedbacks,
    isLoading,
    error,
    submitFeedback,
    loadMore,
    hasMore,
    isSubmitting,
  };
}