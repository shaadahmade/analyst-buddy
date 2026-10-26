# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Non-technical business owners: founders, managers and owners of small and mid-size companies who have business data in spreadsheets (sales, customers, support tickets, stock, website visits, finance: anything in CSV, Excel, JSON or Parquet) but no data analyst and cannot write code. They want to know how the business is doing against its goals, what changed, why, and what to do next, without learning a BI tool.

## Product Purpose

Analyst Buddy is an AI data analyst for a company. The owner uploads data and states goals; the agent answers questions in plain language by writing and running real Python on that data, and remembers the company's goals, definitions and corrections so answers get sharper over time. Success: an owner gets a trustworthy, actionable answer to a business question in minutes instead of waiting on an analyst or guessing from a spreadsheet.

## Positioning

General chat assistants start every conversation from zero and only analyze what is pasted in. Analyst Buddy is bound to one company: it keeps that company's goals, KPIs, definitions and past learnings, works on that company's own data in an isolated sandbox, and every number it reports comes from code it actually ran.

## Operating Context

- Workspaces like Notion: one account (email + password) can belong to many workspaces and switch between them in the sidebar. Anyone can create a workspace instantly and becomes its owner, with no waiting list or approval. Owners and admins add members directly. Each workspace is isolated: its own data, memory, sandbox, reports and audit log.
- Agent team (team.py): a supervisor plans each question; simple ones go to one analyst, harder ones are split across up to 3 analysts running in parallel in separate kernels of the member's sandbox, guided by a data agent; a verifier recomputes the key numbers with its own code and a writer answers using only checked numbers. A live agent rail (web/src/TeamBoard.jsx) runs down beside the monitor as a vertical flow of capsules, Plan → Data → Analysts → Check → Answer, showing who is working and on what; each capsule opens to show the plan, the analysts' tasks or the verifier's ✓/✗ checks; the monitor labels every step; an Agent team switch turns the team off for quick questions.
- Data sources: saved connections for Google Sheets and Google Analytics 4 (Google sign-in, auto-refreshed tokens), Shopify (client ID + secret; the 24-hour token is renewed before every sync; the daily copy holds 12 months of orders, their line items and only the products that appear in them; unscoped members also get a shopify_live tool that runs read-only Admin GraphQL against the store at question time for right-now questions, refusing mutations and subscriptions, with results saved as JSON in the sandbox), and any MCP server (Analyst Buddy acts as an MCP client: pick read-only tools, write-like tools are locked, results become tables; https only, private network addresses and redirects refused; servers that need sign-in, like Notion, Linear, Sentry and Apify, are signed in through a popup by mcp_auth.py, an OAuth client with PKCE that registers itself or uses a hosted client document, and the keys are stored encrypted and renewed on each sync; tools the server marks read-only are allowed even when their name sounds like a write; Shopify's hosted MCP refuses clients it has not approved, so Shopify stays on the custom app), each with fixed, tested import code in sources.py, a connection test before saving, keys encrypted at rest (AES-256-GCM with a per-tenant key derived by HKDF from the master key, each secret bound to its tenant and connection so it cannot be copied to another; CONNECTIONS_KEY may list several keys, newest first, for rotation, and old secrets are re-encrypted under the newest key at startup), a Refresh button and a daily sync. File upload, file links, databases and anything described in plain words go through the data agent. A separate data agent (connector.py) pulls each one in its own sandbox, saves clean tables and leaves a handoff note the analyst reads; keys reach only that sandbox as environment variables and are never stored or shown to the AI.
- MCP server (mcp_server.py) at /mcp: Claude, Cursor and other MCP clients use Analyst Buddy with personal tokens (Connect AI tab). Each token belongs to one member and workspace, is read-only or full-role, never exceeds the member's current role, and is checked on every request; tool lists are filtered by role and every call is re-checked, rate limited and logged as via MCP. claude.ai and Claude Desktop connect by URL alone through OAuth 2.1 (mcp_oauth.py): discovery metadata, dynamic client registration, a sign-in and Approve screen (pick workspace and read/full), PKCE S256 codes, 1-hour access tokens and rotating 30-day refresh tokens, all revocable in Connect AI.
- Goals and data in the sidebar: owners, admins and analysts add, edit and delete goals inline, and anyone who can upload can delete a data file (removed from storage, live sandboxes and the data notes). When a user states a target in chat, the analyst (suggest_goal tool) or the supervisor proposes a goal change; it is saved only when the user clicks Add to goals on the card under the answer.
- Roles (RBAC): owner, admin, analyst, viewer. Permissions are checked on the server; analysts and viewers can be limited to chosen files, rows and columns, filtered before the data reaches the sandbox. Every sign-in, question, upload, denial and member change is in the audit log.
- Flow: sign in, upload data files (CSV, Excel, JSON, Parquet), ask questions in a chat, receive answers with numbers, charts and recommended actions.
- Answers can take tens of seconds while the agent writes and runs code; each question is capped at 10 LLM calls.
- Goals and definitions live in a per-company knowledge file; learned facts go to long-term memory.

## Capabilities and Constraints

- Agent: LangGraph loop, Gemini model, E2B code sandbox (Python with pandas, numpy, matplotlib), Pinecone memory per company namespace.
- Backend: FastAPI (`server.py`) with endpoints login, me, ask, upload, logout. Frontend: React with Vite in `web/`.
- Charts come back as PNG images from matplotlib.
- Undecided: pricing, plans, signup flow, scheduled weekly reports, data connectors beyond file upload.
- UI text must contain no emoji and no em dashes.
- Icons: Icons8 `fluent-systems-regular` only, served as PNG masks from `web/public/icons` and locked in `web/icons8.json`; the free-tier "Icons by Icons8" credit link must stay visible.

## Brand Commitments

- Name: Analyst Buddy.
- Voice: confident expert. Sharp, direct, numbers first, like a senior analyst. Plain words a non-technical owner understands; no jargon, no hype.

## Evidence on Hand

- No real customers, testimonials, logos, metrics or press exist. Do not invent any.
- Sample tenants `acme` and `globex` with generated order data exist for demos; any example insight shown on marketing surfaces must be labeled as an example.

## Product Principles

1. Every number is earned: answers come from code that ran on the company's data, and the product shows that.
2. Plain answers first: lead with what it means for the business, then the numbers, then the action.
3. It knows your company: goals and definitions visibly shape the answers.
4. Private by default: one company's data, memory and sandbox never touch another's.
- PII redaction (pii.py): every LLM call goes through a guard that swaps emails, phone, card (Luhn-checked), Aadhaar and PAN numbers for per-session placeholders like EMAIL_3f9a2c1b before anything reaches the model, and swaps them back in the model's code and answers, so analysis in the sandbox and what the user sees use the real values while the AI provider never receives them. Names and addresses are not detected.
- LangSmith tracing (tracing.py), on when LANGSMITH_API_KEY is set: one "question" trace per ask with every LLM and tool call nested under it (team analysts too), PII scrubbed from all trace inputs and outputs, tagged with tenant, hashed user, role and mode. Online evals on every live answer, sent as LangSmith feedback: answered, steps, tool_errors, recovered, numbers_grounded (share of numbers in the answer found in tool output) and placeholder_leak, plus user_score from the thumbs buttons (only the asker can rate their trace). LLM-as-judge evaluators can be added on the project in the LangSmith UI.
