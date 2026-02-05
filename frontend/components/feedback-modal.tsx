"use client";

import { useState, useRef, useEffect } from "react";
import { Loader2, ChevronLeft, ChevronRight, MessageSquarePlus, Sparkles } from "lucide-react";
import { motion, AnimatePresence, useMotionValue, useTransform, PanInfo } from "framer-motion";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useFeedback } from "@/hooks/use-feedback";
import { cn } from "@/lib/utils";
import type { FeedbackMessage } from "@/lib/types";

interface FeedbackModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// 카드 그라데이션 색상
const CARD_GRADIENTS = [
  "from-violet-500/90 to-purple-600/90",
  "from-blue-500/90 to-cyan-500/90",
  "from-emerald-500/90 to-teal-500/90",
  "from-orange-500/90 to-amber-500/90",
  "from-pink-500/90 to-rose-500/90",
  "from-indigo-500/90 to-blue-600/90",
];

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return "방금 전";
  if (diffMin < 60) return `${diffMin}분 전`;
  if (diffHour < 24) return `${diffHour}시간 전`;
  if (diffDay < 7) return `${diffDay}일 전`;
  return date.toLocaleDateString("ko-KR");
}

function seededRandom(seed: string): number {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    const char = seed.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash % 100) / 100;
}

function FeedbackCard({
  feedback,
  isTop,
  index,
  onSwipe,
}: {
  feedback: FeedbackMessage;
  isTop: boolean;
  index: number;
  onSwipe: () => void;
}) {
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-200, 200], [-25, 25]);
  const opacity = useTransform(x, [-200, -100, 0, 100, 200], [0.5, 1, 1, 1, 0.5]);

  const colorIndex = Math.floor(seededRandom(feedback.feedback_id) * CARD_GRADIENTS.length);
  const gradient = CARD_GRADIENTS[colorIndex];

  const handleDragEnd = (_: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
    if (Math.abs(info.offset.x) > 100) {
      onSwipe();
    }
  };

  // 뒤에 쌓인 카드들의 스타일
  const stackOffset = index * 4;
  const stackScale = 1 - index * 0.03;
  const stackRotate = index * 1.5;

  return (
    <motion.div
      className="absolute inset-0 cursor-grab active:cursor-grabbing"
      style={{
        x: isTop ? x : 0,
        rotate: isTop ? rotate : stackRotate,
        scale: stackScale,
        y: stackOffset,
        zIndex: 10 - index,
      }}
      drag={isTop ? "x" : false}
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={0.7}
      onDragEnd={isTop ? handleDragEnd : undefined}
      initial={{ scale: 0.8, opacity: 0, y: 50 }}
      animate={{
        scale: stackScale,
        opacity: index > 2 ? 0 : 1,
        y: stackOffset,
        rotate: isTop ? 0 : stackRotate,
      }}
      exit={{
        x: 300,
        opacity: 0,
        rotate: 30,
        transition: { duration: 0.3 }
      }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
    >
      <motion.div
        className={cn(
          "w-full h-full rounded-2xl p-6 flex flex-col",
          "bg-gradient-to-br backdrop-blur-sm",
          gradient,
          "shadow-2xl border border-white/20",
          isTop && "hover:shadow-3xl"
        )}
        style={{ opacity: isTop ? opacity : 1 }}
      >
        {/* 카드 상단 장식 */}
        <div className="flex items-center gap-2 mb-4">
          <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center">
            <span className="text-lg">💬</span>
          </div>
          <div className="flex-1" />
          <span className="text-white/60 text-xs">{formatRelativeTime(feedback.created_at)}</span>
        </div>

        {/* 메시지 내용 */}
        <div className="flex-1 flex items-center justify-center">
          <p className="text-white text-lg leading-relaxed text-center font-medium">
            "{feedback.message}"
          </p>
        </div>

        {/* 카드 하단 힌트 */}
        {isTop && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center text-white/50 text-xs mt-4"
          >
            ← 스와이프하여 다음 카드 →
          </motion.div>
        )}
      </motion.div>
    </motion.div>
  );
}

export function FeedbackModal({ open, onOpenChange }: FeedbackModalProps) {
  const [input, setInput] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showInput, setShowInput] = useState(false);
  const prevFeedbacksRef = useRef<FeedbackMessage[]>([]);

  const {
    feedbacks,
    isLoading,
    error,
    submitFeedback,
    loadMore,
    hasMore,
    isSubmitting,
  } = useFeedback({ pollingInterval: 3000, limit: 50, enabled: open });

  // 모달 열릴 때 최신 카드(index 0)로 리셋
  useEffect(() => {
    if (open) {
      setCurrentIndex(0);
      setShowInput(false);
    }
  }, [open]);

  // 새 피드백이 오면 맨 앞으로
  useEffect(() => {
    if (feedbacks.length > prevFeedbacksRef.current.length) {
      setCurrentIndex(0);
    }
    prevFeedbacksRef.current = feedbacks;
  }, [feedbacks]);

  const handleSwipe = () => {
    if (currentIndex < feedbacks.length - 1) {
      setCurrentIndex(prev => prev + 1);
    } else if (hasMore) {
      loadMore();
    }
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(prev => prev - 1);
    }
  };

  const handleNext = () => {
    if (currentIndex < feedbacks.length - 1) {
      setCurrentIndex(prev => prev + 1);
    } else if (hasMore) {
      loadMore();
    }
  };

  const handleSubmit = async () => {
    if (!input.trim() || isSubmitting) return;
    try {
      await submitFeedback(input);
      setInput("");
      setShowInput(false);
      setCurrentIndex(0); // 방금 제출한 피드백(최신)이 맨 앞에 보이도록
    } catch {
      // Error handled by hook
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // 현재 보여줄 카드들 (최대 3장)
  const visibleCards = feedbacks.slice(currentIndex, currentIndex + 3);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px] h-[600px] flex flex-col p-0 gap-0 overflow-hidden bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 border-slate-700">
        {/* 헤더 */}
        <DialogHeader className="px-6 py-4 border-b border-white/10">
          <DialogTitle className="text-white flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-amber-400" />
            <span>Feedback</span>
            <span className="text-sm font-normal text-white/50 ml-2">
              {feedbacks.length > 0 && `${currentIndex + 1} / ${feedbacks.length}`}
            </span>
          </DialogTitle>
        </DialogHeader>

        {/* 카드 영역 */}
        <div className="flex-1 relative overflow-hidden">
          {/* 배경 장식 */}
          <div className="absolute inset-0 overflow-hidden">
            <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-purple-500/10 rounded-full blur-3xl" />
            <div className="absolute bottom-1/4 right-1/4 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl" />
          </div>

          {/* 로딩 */}
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="w-8 h-8 animate-spin text-white/50 mx-auto" />
                <p className="text-white/50 text-sm mt-3">불러오는 중...</p>
              </div>
            </div>
          )}

          {/* 에러 */}
          {error && (
            <div className="absolute inset-0 flex items-center justify-center p-6">
              <div className="bg-red-500/20 border border-red-500/50 rounded-xl p-4 text-center">
                <p className="text-red-300 text-sm">{error}</p>
              </div>
            </div>
          )}

          {/* 빈 상태 */}
          {!isLoading && feedbacks.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center p-6">
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className="text-center"
              >
                <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
                  <MessageSquarePlus className="w-10 h-10 text-white" />
                </div>
                <p className="text-white text-lg font-medium">아직 피드백이 없어요</p>
                <p className="text-white/50 text-sm mt-1">첫 번째 피드백을 남겨보세요!</p>
              </motion.div>
            </div>
          )}

          {/* 카드 스택 */}
          {!isLoading && feedbacks.length > 0 && (
            <div className="absolute inset-0 p-6">
              <div className="relative w-full h-full" style={{ perspective: "1000px" }}>
                <AnimatePresence mode="popLayout">
                  {visibleCards.map((feedback, idx) => (
                    <FeedbackCard
                      key={feedback.feedback_id}
                      feedback={feedback}
                      isTop={idx === 0}
                      index={idx}
                      onSwipe={handleSwipe}
                    />
                  ))}
                </AnimatePresence>
              </div>
            </div>
          )}

          {/* 네비게이션 버튼 */}
          {feedbacks.length > 1 && (
            <>
              <button
                onClick={handlePrev}
                disabled={currentIndex === 0}
                className={cn(
                  "absolute left-2 top-1/2 -translate-y-1/2 z-20",
                  "w-10 h-10 rounded-full bg-white/10 backdrop-blur-sm",
                  "flex items-center justify-center",
                  "transition-all hover:bg-white/20",
                  "disabled:opacity-30 disabled:cursor-not-allowed"
                )}
              >
                <ChevronLeft className="w-5 h-5 text-white" />
              </button>
              <button
                onClick={handleNext}
                disabled={currentIndex >= feedbacks.length - 1 && !hasMore}
                className={cn(
                  "absolute right-2 top-1/2 -translate-y-1/2 z-20",
                  "w-10 h-10 rounded-full bg-white/10 backdrop-blur-sm",
                  "flex items-center justify-center",
                  "transition-all hover:bg-white/20",
                  "disabled:opacity-30 disabled:cursor-not-allowed"
                )}
              >
                <ChevronRight className="w-5 h-5 text-white" />
              </button>
            </>
          )}
        </div>

        {/* 하단 입력 영역 */}
        <div className="border-t border-white/10 p-4">
          <AnimatePresence mode="wait">
            {showInput ? (
              <motion.div
                key="input"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
                className="space-y-3"
              >
                <Textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="피드백을 입력하세요..."
                  className={cn(
                    "min-h-[80px] resize-none",
                    "bg-white/5 border-white/10 text-white",
                    "placeholder:text-white/30",
                    "focus-visible:ring-purple-500/50"
                  )}
                  disabled={isSubmitting}
                  autoFocus
                />
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowInput(false)}
                    className="flex-1 text-white/70 hover:text-white hover:bg-white/10"
                  >
                    취소
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleSubmit}
                    disabled={!input.trim() || isSubmitting}
                    className="flex-1 bg-gradient-to-r from-violet-500 to-purple-600 hover:from-violet-600 hover:to-purple-700 text-white"
                  >
                    {isSubmitting ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      "보내기"
                    )}
                  </Button>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="button"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
              >
                <Button
                  onClick={() => setShowInput(true)}
                  className="w-full bg-gradient-to-r from-violet-500 to-purple-600 hover:from-violet-600 hover:to-purple-700 text-white h-12"
                >
                  <MessageSquarePlus className="w-5 h-5 mr-2" />
                  피드백 남기기
                </Button>
                <p className="text-center text-white/40 text-xs mt-2">
                  개선 의견을 자유롭게 남겨주세요
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </DialogContent>
    </Dialog>
  );
}
