"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";

const FOOD_EMOJIS = [
  "🍱", "🍙", "🍚", "🍜", "🍛", "🍲", "🥘", "🍳",
  "🥗", "🍖", "🥟", "🍕", "🌮", "🍔", "🥪", "🍿",
];

const ITEM_COUNT = 20;
const ANIMATION_DURATION_S = 5;

interface FallingItem {
  id: number;
  emoji: string;
  left: number;      // vw
  delay: number;      // seconds
  duration: number;   // seconds
  size: number;       // rem
  rotate: number;     // degrees
}

function generateItems(): FallingItem[] {
  return Array.from({ length: ITEM_COUNT }, (_, i) => ({
    id: i,
    emoji: FOOD_EMOJIS[Math.floor(Math.random() * FOOD_EMOJIS.length)],
    left: Math.random() * 100,
    delay: Math.random() * 2,
    duration: 2.5 + Math.random() * 2,
    size: 1.5 + Math.random() * 1.5,
    rotate: -30 + Math.random() * 60,
  }));
}

function shouldShow(): boolean {
  // 11:59에만 + 하루 1회
  const now = new Date();
  if (now.getHours() !== 11 || now.getMinutes() !== 59) return false;

  const todayKey = `lunchbox-rain-${now.toISOString().slice(0, 10)}`;
  if (localStorage.getItem(todayKey)) return false;
  localStorage.setItem(todayKey, "1");
  return true;
}

export function LunchboxRain() {
  const [show, setShow] = useState(false);
  const [items, setItems] = useState<FallingItem[]>([]);

  const trigger = useCallback(() => {
    setItems(generateItems());
    setShow(true);
    setTimeout(() => setShow(false), ANIMATION_DURATION_S * 1000);
  }, []);

  useEffect(() => {
    // 마운트 시 즉시 체크 (11:59에 새로고침한 경우)
    if (shouldShow()) {
      const t = setTimeout(trigger, 800);
      return () => clearTimeout(t);
    }

    // 11:59 자동 발동 타이머: 다음 11:59까지 남은 ms 계산
    const now = new Date();
    const target = new Date(now);
    target.setHours(11, 59, 0, 0);
    if (now >= target) {
      target.setDate(target.getDate() + 1);
    }
    const msUntil = target.getTime() - now.getTime();
    const timerId = setTimeout(() => {
      if (shouldShow()) {
        trigger();
      }
    }, msUntil);

    return () => clearTimeout(timerId);
  }, [trigger]);

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          className="fixed inset-0 pointer-events-none overflow-hidden"
          style={{ zIndex: 9999 }}
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.5 } }}
        >
          {/* 상단 배너 */}
          <motion.div
            className="absolute top-8 left-1/2 -translate-x-1/2 bg-amber-500/90 dark:bg-amber-600/90 text-white px-6 py-3 rounded-2xl shadow-lg pointer-events-auto select-none"
            initial={{ y: -60, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -60, opacity: 0 }}
            transition={{ type: "spring", damping: 15 }}
          >
            <span className="text-lg font-bold">🔔 점심시간이에요, 식사 맛있게 하세요!</span>
          </motion.div>

          {/* 떨어지는 음식들 */}
          {items.map((item) => (
            <motion.div
              key={item.id}
              className="absolute select-none"
              style={{
                left: `${item.left}vw`,
                fontSize: `${item.size}rem`,
                top: -60,
              }}
              initial={{ y: -60, rotate: 0, opacity: 0.9 }}
              animate={{
                y: "110vh",
                rotate: item.rotate,
                opacity: [0.9, 1, 1, 0.8, 0],
              }}
              transition={{
                duration: item.duration,
                delay: item.delay,
                ease: "easeIn",
              }}
            >
              {item.emoji}
            </motion.div>
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
