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
} from "lucide-react";
import type { OnboardingStep as StepType } from "@/lib/onboarding/steps";

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
};

interface OnboardingStepProps {
  step: StepType;
  direction: number;
}

export function OnboardingStep({ step, direction }: OnboardingStepProps) {
  const IconComponent = iconMap[step.icon];

  return (
    <motion.div
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

      {/* Example Queries */}
      {step.examples && step.examples.length > 0 && (
        <div className="mt-3 flex flex-col items-center gap-1">
          <span className="text-xs text-muted-foreground">예시:</span>
          <div className="flex flex-wrap items-center justify-center gap-2">
            {step.examples.map((example) => (
              <span
                key={example}
                className="text-xs italic text-muted-foreground"
              >
                "{example}"
              </span>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}
