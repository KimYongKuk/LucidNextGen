"use client";

import { useCallback, useMemo } from "react";
import useSWR from "swr";

export type DocumentType = "pdf" | "docx";

export interface DocumentViewerState {
  isOpen: boolean;
  filename: string | null;
  documentType: DocumentType | null;
  isLoading: boolean;
}

const initialState: DocumentViewerState = {
  isOpen: false,
  filename: null,
  documentType: null,
  isLoading: false,
};

type Selector<T> = (state: DocumentViewerState) => T;

export function useDocumentViewerSelector<Selected>(
  selector: Selector<Selected>
) {
  const { data: state } = useSWR<DocumentViewerState>(
    "document-viewer",
    null,
    { fallbackData: initialState }
  );

  const selectedValue = useMemo(() => {
    if (!state) return selector(initialState);
    return selector(state);
  }, [state, selector]);

  return selectedValue;
}

export function useDocumentViewer() {
  const { data: state, mutate: setState } = useSWR<DocumentViewerState>(
    "document-viewer",
    null,
    { fallbackData: initialState }
  );

  const currentState = useMemo(() => state || initialState, [state]);

  const openFile = useCallback(
    (filename: string, documentType: DocumentType) => {
      setState({
        isOpen: true,
        filename,
        documentType,
        isLoading: true,
      });
    },
    [setState]
  );

  const closeViewer = useCallback(() => {
    setState({
      ...initialState,
    });
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
