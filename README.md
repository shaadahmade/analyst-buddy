---
title: Analyst Buddy
emoji: 📊
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# Analyst Buddy

An AI data analyst on a whiteboard. Upload your data, ask in plain words, and watch the agent write and run the
Python behind every answer. Notion-style workspaces with roles (owner, admin, analyst, viewer) and per-member data
access.

Stack: React + Vite, FastAPI, LangGraph ReAct agent on Gemini, E2B code sandbox, Pinecone memory.

## Saved state (Supabase)

Accounts, workspaces, members, data files and encrypted connections live on disk and are mirrored to a Supabase
Postgres table (`app_files`) when `STATE_DATABASE_URL` is set: restored at startup, changes saved every 30 seconds.
This keeps everything across redeploys on hosts with a temporary disk. Copy local state up once with
`python persist.py push`.
