"use client";

import type { UseChatHelpers } from "@ai-sdk/react";
import { motion } from "framer-motion";
import { memo, useEffect, useState } from "react";
import type { ChatMessage } from "@/lib/types";
import { Suggestion } from "./elements/suggestion";

const ALL_SUGGESTED_ACTIONS = [
  // 웹 검색
  "오늘 대구 날씨는 어때요?",
  "이번달 엘앤에프 뉴스 정리해줘",
  "이번달 2차전지 산업 주요 동향 정리해줘",
  // IT VOC
  "최근 IT VOC에 올라온 내역 20건을 분석해줘",
  "IT VOC 중 SAP 비밀번호 초기화 요청 관련 문의 찾아줘",
  "WA에서 다른 부서 코스트센터 권한이 필요한데 어떻게 신청하나요?",
  // 회계 VOC
  "개인 유류비 전표는 어떻게 처리하나요?",
  "명의개서료 회계처리 방법",
  "월세는 어떻게 연말정산 하나요?",
  "전표 역분개 후 매핑이 안 되는데 어떻게 해야 하나요?",
  "법인카드로 결제했다가 취소한 경우 전표 처리는 어떻게 하나요?",
  "관세환급금 받았을 때 미수금 전표는 어떻게 처리하나요?",
  // YouTube / URL 분석
  "https://www.youtube.com/watch?v=7j2HMm3t4x0 요약",
  "https://blog.naver.com/shmoon305/224172937025 분석",
  "https://doi.org/10.1038/s41467-021-22635-w 이 논문 분석해줘",
  // 메일
  "인사팀에서 발송한 메일 찾아줄 수 있어?",
  "내 메일함에서 내가 안읽은 메일이 있는지 확인해줘",
  // 사내 문서
  "가장 최근 올라온 공지글 요약해줘",
  // PPT 생성
  "2차전지 시장 현황을 분석해서 PPT 3장으로 요약해줘",
  "최근 양극재 관련 뉴스를 검색해서 워드로 보고서를 생성해줘",
  "2차전지 시장 현황을 분석해서 워드로 만들어줘",
  // 엑셀 생성
  //"월별 매출 실적 비교 엑셀 표 만들어줘",
  //"프로젝트 일정 관리 엑셀 템플릿 만들어줘",
  // PDF / 차트 생성
  //"최근 3년 매출 추이를 라인 차트로 그려줘",
  //"부서별 예산 집행률 비교 막대 차트 만들어줘",
  //"회의록 양식을 PDF로 만들어줘",
  // 전자결재
  "내가 결재할 문서가 있는지 확인해줘",
  "이번 주 내가 상신한 결재 목록 보여줘",
  // 일반
  "루시드AI로 할 수 있는 기능이 어떤 것들이 있어?",
  "엘앤에프 2025년 매출액을 차트로 만들어줘"
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
