# Frontend Routes Documentation

This document lists all the routes available in the frontend application, including UI pages and API endpoints.

## Page Routes (UI)

These are the pages accessible via the browser.

| Route | File Path | Description |
| :--- | :--- | :--- |
| `/` | `app/(chat)/page.tsx` | The main home page of the chatbot application. |
| `/chat/[id]` | `app/(chat)/chat/[id]/page.tsx` | The dynamic chat page for a specific conversation session (identified by `id`). |

## API Routes (Endpoints)

These are the backend API endpoints hosted by the Next.js frontend (Route Handlers).

| Route | File Path | Description |
| :--- | :--- | :--- |
| `/api/chat` | `app/(chat)/api/chat/route.ts` | Handles chat interactions (sending messages, getting responses). |
| `/api/chat/[id]/stream` | `app/(chat)/api/chat/[id]/stream/route.ts` | Handles streaming responses for a specific chat session. |
| `/api/document` | `app/(chat)/api/document/route.ts` | Handles document-related operations (e.g., retrieval, processing). |
| `/api/files/upload` | `app/(chat)/api/files/upload/route.ts` | Handles file uploads. |
| `/api/history` | `app/(chat)/api/history/route.ts` | Retrieves or manages chat history. |
| `/api/suggestions` | `app/(chat)/api/suggestions/route.ts` | Provides suggestions for chat inputs or actions. |
| `/api/vote` | `app/(chat)/api/vote/route.ts` | Handles voting (thumbs up/down) on messages. |

## Directory Structure Overview

The project uses the **Next.js App Router**.

- **`(auth)`**: Contains authentication-related utilities (`auth.ts`), but no visible routes in this folder.
- **`(chat)`**: The main route group for the chat application.
  - **`api`**: Contains all the API route handlers.
  - **`chat`**: Contains the dynamic chat page.
