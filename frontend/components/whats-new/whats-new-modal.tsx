"use client";

import { useState, useCallback, useMemo } from "react";
import { AnimatePresence } from "framer-motion";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Megaphone } from "lucide-react";
import { OnboardingProgress } from "@/components/onboarding/onboarding-progress";
import { WhatsNewSlide } from "./whats-new-slide";
import { useWhatsNew } from "./whats-new-provider";
import type { WhatsNewAnnouncement, WhatsNewStep } from "@/lib/whats-new/announcements";

interface FlatSlide {
  step: WhatsNewStep;
  version: string;
  date: string;
  announcementId: string;
}

function flattenAnnouncements(announcements: WhatsNewAnnouncement[]): FlatSlide[] {
  const slides: FlatSlide[] = [];
  for (const announcement of announcements) {
    for (const step of announcement.steps) {
      slides.push({
        step,
        version: announcement.version,
        date: announcement.date,
        announcementId: announcement.id,
      });
    }
  }
  return slides;
}

export function WhatsNewModal() {
  const { isOpen, closeWhatsNew, displayAnnouncements } = useWhatsNew();

  const [currentStep, setCurrentStep] = useState(0);
  const [direction, setDirection] = useState(0);

  const slides = useMemo(
    () => flattenAnnouncements(displayAnnouncements),
    [displayAnnouncements]
  );

  const totalSteps = slides.length;
  const slide = slides[currentStep];
  const isFirstStep = currentStep === 0;
  const isLastStep = currentStep === totalSteps - 1;

  const goToNext = useCallback(() => {
    if (!isLastStep) {
      setDirection(1);
      setCurrentStep((prev) => prev + 1);
    }
  }, [isLastStep]);

  const goToPrev = useCallback(() => {
    if (!isFirstStep) {
      setDirection(-1);
      setCurrentStep((prev) => prev - 1);
    }
  }, [isFirstStep]);

  const handleComplete = useCallback(() => {
    closeWhatsNew();
    setCurrentStep(0);
    setDirection(0);
  }, [closeWhatsNew]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "Enter") {
        if (isLastStep) {
          handleComplete();
        } else {
          goToNext();
        }
      } else if (e.key === "ArrowLeft") {
        goToPrev();
      }
    },
    [goToNext, goToPrev, handleComplete, isLastStep]
  );

  const goToStep = useCallback(
    (index: number) => {
      setDirection(index > currentStep ? 1 : -1);
      setCurrentStep(index);
    },
    [currentStep]
  );

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      closeWhatsNew();
      setCurrentStep(0);
      setDirection(0);
    }
  };

  if (totalSteps === 0) return null;

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent
        className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl md:max-w-3xl"
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <DialogHeader className="flex-shrink-0 p-4 pb-0 md:p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Megaphone className="h-5 w-5 text-blue-500" />
              <DialogTitle className="text-lg font-semibold md:text-xl">
                공지사항
              </DialogTitle>
            </div>
          </div>
          <DialogDescription className="mt-1 text-sm text-muted-foreground">
            {currentStep + 1} / {totalSteps}
          </DialogDescription>
        </DialogHeader>

        {/* Progress Bar */}
        <OnboardingProgress currentStep={currentStep} totalSteps={totalSteps} />

        {/* Content Area with Animation */}
        <div className="relative flex-1 overflow-hidden px-4 md:px-6">
          <AnimatePresence mode="wait" initial={false} custom={direction}>
            {slide && (
              <WhatsNewSlide
                key={`${slide.announcementId}-${currentStep}`}
                slideKey={`${slide.announcementId}-${currentStep}`}
                step={slide.step}
                version={slide.version}
                date={slide.date}
                direction={direction}
              />
            )}
          </AnimatePresence>
        </div>

        {/* Navigation Footer */}
        <div className="flex flex-shrink-0 items-center justify-between border-t bg-muted/30 p-4 pt-4 md:p-6">
          <Button
            variant="outline"
            onClick={goToPrev}
            disabled={isFirstStep}
            className="gap-1"
          >
            <ChevronLeft className="h-4 w-4" />
            <span className="hidden sm:inline">이전</span>
          </Button>

          {/* Step Dots */}
          <div className="flex items-center gap-1.5">
            {slides.map((_, index) => (
              <button
                key={index}
                type="button"
                onClick={() => goToStep(index)}
                className={`h-2 rounded-full transition-all duration-200 ${
                  index === currentStep
                    ? "w-4 bg-primary"
                    : "w-2 bg-muted-foreground/30 hover:bg-muted-foreground/50"
                }`}
                aria-label={`Step ${index + 1}`}
              />
            ))}
          </div>

          {isLastStep ? (
            <Button onClick={handleComplete} className="gap-1">
              확인
            </Button>
          ) : (
            <Button onClick={goToNext} className="gap-1">
              <span className="hidden sm:inline">다음</span>
              <ChevronRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
