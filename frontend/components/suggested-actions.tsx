"use client";

import type { UseChatHelpers } from "@ai-sdk/react";
import { motion } from "framer-motion";
import { memo, useEffect, useState } from "react";
import type { ChatMessage } from "@/lib/types";
import { Suggestion } from "./elements/suggestion";

const ALL_SUGGESTED_ACTIONS = [
  "오늘 대구 날씨는 어때요?",
  "이번달 엘앤에프 뉴스 정리해줘",
  "이번달 2차전지 산업 주요 동향 정리해줘",
  "최근 IT VOC에 올라온 내역 20건을 분석해줘",
  "개인 유류비 전표는 어떻게 처리하나요?",
  "https://www.youtube.com/watch?v=7j2HMm3t4x0 요약",
  "https://blog.naver.com/shmoon305/224172937025 분석",
  "명의개서료 회계처리 방법",
  "월세는 어떻게 연말정산 하나요?",
  "내가 업로드한 csv 파일로 라인차트 만들어줘",
  "가장 최근 올라온 공지글 요약해줘",
  "내 읽지 않은 메일 요약해줘",
  "IT VOC 중 SAP 비밀번호 초기화 요청 관련 문의 찾아줘",
  "WA에서 다른 부서 코스트센터 권한이 필요한데 어떻게 신청하나요?",
  "전표 역분개 후 매핑이 안 되는데 어떻게 해야 하나요?",
  "법인카드로 결제했다가 취소한 경우 전표 처리는 어떻게 하나요?",
  "관세환급금 받았을 때 미수금 전표는 어떻게 처리하나요?",
  "인사팀에서 발송한 메일 찾아줄 수 있어?",
  "https://doi.org/10.1038/s41467-021-22635-w 이 논문 분석해줘"
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
  const [suggestedActions, setSuggestedActions] = useState<string[]>([]);

  useEffect(() => {
    setSuggestedActions(getRandomItems(ALL_SUGGESTED_ACTIONS, 4));
  }, [chatId]);

  if (suggestedActions.length === 0) return null;

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
