"use client";

import type { UseChatHelpers } from "@ai-sdk/react";
import { motion } from "framer-motion";
import { memo, useMemo } from "react";
import type { ChatMessage } from "@/lib/types";
import { Suggestion } from "./elements/suggestion";

const ALL_SUGGESTED_ACTIONS = [
  "오늘 대구 날씨는 어때요?",
  "최근 IT VOC에 올라온 내역 20건을 분석해줘",
  "개인 유류비 전표는 어떻게 처리하나요?",
  "https://www.youtube.com/watch?v=7j2HMm3t4x0 요약",
  "https://blog.naver.com/shmoon305/224172937025 분석",
  "명의개서료 회계처리 방법",
  "월세는 어떻게 연말정산 하나요?",
  "급여계좌를 다른 계좌로 변경할 수 있나요?",
  "관세환급금 전표 처리 방법",
  "내가 업로드한 csv 파일로 라인차트 만들어줘",
  "IT VOC 중 SAP 비밀번호 초기화 요청 관련 문의 찾아줘",
  "근골격계 부담작업은 어떤게 있나요?"
];

function getRandomItems<T>(array: T[], count: number): T[] {
  const shuffled = [...array].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, count);
}

type SuggestedActionsProps = {
  chatId: string;
  sendMessage: UseChatHelpers<ChatMessage>["sendMessage"];
};

function PureSuggestedActions({ chatId, sendMessage }: SuggestedActionsProps) {
  const suggestedActions = useMemo(
    () => getRandomItems(ALL_SUGGESTED_ACTIONS, 4),
    [chatId]
  );

  return (
    <div
      className="grid w-full gap-2 sm:grid-cols-2"
      data-testid="suggested-actions"
    >
      {suggestedActions.map((suggestedAction, index) => (
        <motion.div
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          initial={{ opacity: 0, y: 20 }}
          key={suggestedAction}
          transition={{ delay: 0.05 * index }}
        >
          <Suggestion
            className="h-auto w-full whitespace-normal p-3 text-left"
            onClick={(suggestion) => {
              window.history.pushState({}, "", `/chat/${chatId}`);
              sendMessage({
                role: "user",
                parts: [{ type: "text", text: suggestion }],
              });
            }}
            suggestion={suggestedAction}
          >
            {suggestedAction}
          </Suggestion>
        </motion.div>
      ))}
    </div>
  );
}

export const SuggestedActions = memo(
  PureSuggestedActions,
  (prevProps, nextProps) => {
    if (prevProps.chatId !== nextProps.chatId) {
      return false;
    }

    return true;
  }
);
