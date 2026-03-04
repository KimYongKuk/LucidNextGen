"use client";

import { useCallback, useMemo } from "react";
import useSWR from "swr";

export interface XlsxViewerState {
  isOpen: boolean;
  filename: string | null;
  isLoading: boolean;
  refreshCounter: number;
}

const initialState: XlsxViewerState = {
  isOpen: false,
  filename: null,
  isLoading: false,
  refreshCounter: 0,
};

type Selector<T> = (state: XlsxViewerState) => T;

export function useXlsxViewerSelector<Selected>(selector: Selector<Selected>) {
  const { data: state } = useSWR<XlsxViewerState>("xlsx-viewer", null, {
    fallbackData: initialState,
  });

  const selectedValue = useMemo(() => {
    if (!state) return selector(initialState);
    return selector(state);
  }, [state, selector]);

  return selectedValue;
}

export function useXlsxViewer() {
  const { data: state, mutate: setState } = useSWR<XlsxViewerState>(
    "xlsx-viewer",
    null,
    { fallbackData: initialState }
  );

  const currentState = useMemo(() => state || initialState, [state]);

  const openFile = useCallback(
    (filename: string) => {
      setState((prev) => {
        const current = prev || initialState;
        return {
          ...current,
          isOpen: true,
          filename,
          isLoading: true,
          refreshCounter: current.refreshCounter + 1,
        };
      });
    },
    [setState]
  );

  const closeViewer = useCallback(() => {
    setState((prev) => ({
      ...(prev || initialState),
      isOpen: false,
      filename: null,
      isLoading: false,
    }));
  }, [setState]);

  const setLoading = useCallback(
    (isLoading: boolean) => {
      setState((prev) => ({
        ...(prev || initialState),
        isLoading,
      }));
    },
    [setState]
  );

  return useMemo(
    () => ({ state: currentState, openFile, closeViewer, setLoading }),
    [currentState, openFile, closeViewer, setLoading]
  );
}
