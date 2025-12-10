import { tool } from "ai";
import { z } from "zod";

export const requestSuggestions = ({
  session,
  dataStream,
}: any) =>
  tool({
    description: "Request suggestions for a document",
    inputSchema: z.object({
      documentId: z.string(),
    }),
    execute: async ({ documentId }) => {
      return {
        error: "Suggestions not implemented in UI-only mode",
      };
    },
  });
