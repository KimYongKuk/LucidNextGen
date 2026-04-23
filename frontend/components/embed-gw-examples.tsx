"use client";

import { memo, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Suggestion } from "./elements/suggestion";

const GW_EXAMPLE_POOL: string[] = [
  // IT 문제 해결/매뉴얼
  "VPN 접속이 안 되는데 해결 방법 알려줘",
  "Wi-Fi 연결이 자꾸 끊겨",
  "프린터 드라이버 설치 방법 알려줘",
  "SAP 로그인 오류 해결 사례 찾아줘",
  "WA 다른 부서 코스트센터 권한 신청 방법",
  "사내 NAS 접속 방법 알려줘",
  // 담당자/조직도
  "VPN 담당자 누구야?",
  "IT 보안 담당자 알려줘",
  "DLP 문의는 어디로 해야 해?",
  "인사팀 채용 담당자 알려줘",
  "급여/4대보험 담당자 알려줘",
  "법인카드 발급 담당자 누구야?",
  "출장비/경비 정산 담당자 알려줘",
  "구매 요청은 어느 부서에 해?",
  "안전/EHS 담당자 누구야?",
  "품질 이슈는 어느 부서에 접수해?",
  // 메일
  "안 읽은 메일 확인해줘",
  "인사팀에서 발송한 메일 찾아줘",
  "최근 받은 메일 5건 요약해줘",
  // 전자결재
  "내가 결재할 문서 있는지 확인해줘",
  "이번 주 상신한 결재 목록 보여줘",
  "최근 반려된 결재 문서 확인해줘",
  // 사내 공지/지원 VOC
  "가장 최근 올라온 공지글 요약해줘",
  "개인 유류비 전표 처리 방법",
  "법인카드 취소 전표 처리 방법",
  // 일정 관리
  "오늘 내 일정 확인해줘",
  "이번 주 내 일정 보여줘",
  "내일 오후 2시 팀 미팅 일정 등록해줘",
  "다음주 월요일 오전에 회의 잡아줘",
  "최경락 수석 이번 주 공개 일정 확인해줘",
  "이번 달 금요일마다 주간보고 일정 반복 등록",
  // 회의실/자산 예약
  "내일 오후 2~3시에 본사 빈 회의실 찾아줘",
  "다음주 월요일 오전 대구공장 회의실 예약 가능한지 확인",
  "본사 회의실 목록 알려줘",
  "내가 예약한 회의실 목록 보여줘",
  "오늘 본사 회의실 예약 현황 보여줘",
  "내일 14~16시 8인 회의실 예약해줘",
  // 일정 + 예약 하이브리드
  "내일 오후 2시 팀 미팅 일정 등록하고 본사 빈 회의실도 예약해줘",
  "다음주 월요일 10시 회의 잡아주고 대구공장 회의실 같이 예약",
  "이번 주 금요일 14~16시 주간회의 일정 등록하고 회의실도 같이 예약해줘",
];

function pickRandom<T>(arr: T[], count: number): T[] {
  const shuffled = [...arr].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, count);
}

type Props = {
  chatId: string;
  onSelect: (example: string) => void;
};

function PureEmbedGwExamples({ chatId, onSelect }: Props) {
  const [examples, setExamples] = useState<string[]>([]);

  useEffect(() => {
    setExamples(pickRandom(GW_EXAMPLE_POOL, 4));
  }, [chatId]);

  if (examples.length === 0) return null;

  return (
    <div className="grid w-full gap-2 sm:grid-cols-2" data-testid="embed-gw-examples">
      {examples.map((example, index) => (
        <motion.div
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 10 }}
          initial={{ opacity: 0, y: 10 }}
          key={example}
          transition={{ delay: 0.04 * index }}
        >
          <Suggestion
            className="h-auto w-full whitespace-normal rounded-lg p-3 text-left text-sm"
            onClick={onSelect}
            suggestion={example}
          >
            {example}
          </Suggestion>
        </motion.div>
      ))}
    </div>
  );
}

export const EmbedGwExamples = memo(PureEmbedGwExamples, (prev, next) => {
  return prev.chatId === next.chatId;
});
