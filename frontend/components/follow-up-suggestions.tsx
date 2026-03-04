"use client";

import { motion, AnimatePresence } from "framer-motion";
import { memo } from "react";
import { Suggestion } from "./elements/suggestion";

type FollowUpSuggestionsProps = {
  suggestions: string[] | null;
  onSuggestionClick: (suggestion: string) => void;
};

function PureFollowUpSuggestions({
  suggestions,
  onSuggestionClick,
}: FollowUpSuggestionsProps) {
  return (
    <AnimatePresence>
      {suggestions && suggestions.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ duration: 0.2 }}
          className="flex flex-wrap gap-2 px-1"
        >
          {suggestions.map((suggestion, index) => (
            <motion.div
              key={suggestion}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.05 * index }}
            >
              <Suggestion
                className="h-auto whitespace-nowrap px-3 py-1.5 text-xs max-w-[250px] truncate bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100 dark:bg-blue-950/60 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-900/60"
                onClick={onSuggestionClick}
                suggestion={suggestion}
              >
                {suggestion}
              </Suggestion>
            </motion.div>
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export const FollowUpSuggestions = memo(
  PureFollowUpSuggestions,
  (prevProps, nextProps) => {
    if (prevProps.suggestions !== nextProps.suggestions) return false;
    return true;
  }
);
