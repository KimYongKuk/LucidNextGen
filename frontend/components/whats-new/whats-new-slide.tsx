"use client";

import { motion } from "framer-motion";
import {
  MessageSquare,
  Upload,
  FolderOpen,
  FileSearch,
  Headphones,
  BarChart3,
  Youtube,
  Globe,
  Presentation,
  Sparkles,
  Zap,
  Shield,
  Bell,
  Settings,
  Users,
  Link,
  FileText,
  Database,
} from "lucide-react";
import type { WhatsNewStep } from "@/lib/whats-new/announcements";

const variants = {
  enter: (direction: number) => ({
    x: direction > 0 ? 300 : -300,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (direction: number) => ({
    x: direction < 0 ? 300 : -300,
    opacity: 0,
  }),
};

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  MessageSquare,
  Upload,
  FolderOpen,
  FileSearch,
  Headphones,
  BarChart3,
  Youtube,
  Globe,
  Presentation,
  Sparkles,
  Zap,
  Shield,
  Bell,
  Settings,
  Users,
  Link,
  FileText,
  Database,
};

interface WhatsNewSlideProps {
  step: WhatsNewStep;
  version: string;
  date: string;
  direction: number;
  slideKey: string;
}

export function WhatsNewSlide({
  step,
  version,
  date,
  direction,
  slideKey,
}: WhatsNewSlideProps) {
  const IconComponent = iconMap[step.icon];

  return (
    <motion.div
      key={slideKey}
      custom={direction}
      variants={variants}
      initial="enter"
      animate="center"
      exit="exit"
      transition={{
        x: { type: "spring", stiffness: 300, damping: 30 },
        opacity: { duration: 0.2 },
      }}
      className="flex flex-col items-center py-4 md:py-6"
    >
      {/* Version Badge + Date */}
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded-full bg-gradient-to-r from-blue-500 to-cyan-500 px-3 py-0.5 text-xs font-semibold text-white">
          {version}
        </span>
        <span className="text-xs text-muted-foreground">{date}</span>
      </div>

      {/* Icon */}
      {IconComponent && (
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <IconComponent className="h-6 w-6 text-primary" />
        </div>
      )}

      {/* Title */}
      <h3 className="mb-2 text-center text-xl font-bold md:text-2xl">
        {step.titleKo}
      </h3>

      {/* Description */}
      <p className="mb-4 max-w-md px-4 text-center text-sm text-muted-foreground md:mb-6 md:text-base">
        {step.descriptionKo}
      </p>

      {/* Media Container */}
      {step.mediaUrl && (
        <div className="relative aspect-video w-full max-w-lg overflow-hidden rounded-lg border bg-muted shadow-lg">
          {step.mediaType === "video" ? (
            <video
              src={step.mediaUrl}
              autoPlay
              loop
              muted
              playsInline
              className="h-full w-full object-cover"
            />
          ) : (
            <img
              src={step.mediaUrl}
              alt={step.titleKo}
              className="h-full w-full object-cover"
              loading="eager"
            />
          )}
        </div>
      )}

      {/* Feature Tags */}
      {step.features && step.features.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          {step.features.map((feature) => (
            <span
              key={feature}
              className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
            >
              {feature}
            </span>
          ))}
        </div>
      )}
    </motion.div>
  );
}
