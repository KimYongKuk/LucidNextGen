# AI Chatbot UI

This is a standalone UI extraction from `vercel/ai-chatbot`.
Backend dependencies (Drizzle, Postgres, Auth) have been removed.
The chat history is now client-side only (or transient).

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```

2. Configure environment variables:
   Copy `.env.example` to `.env.local` and set your AI provider keys (e.g. OPENAI_API_KEY).
   Check `lib/ai/providers.ts` to configure your model provider.

3. Run development server:
   ```bash
   npm run dev
   ```

## Changes

- Removed `lib/db` and database queries.
- Removed `app/(auth)` and authentication checks.
- Refactored `app/api/chat/route.ts` to accept `messages` from the client and skip DB persistence.
- Stubbed `app/(chat)/actions.ts` to avoid DB calls.
