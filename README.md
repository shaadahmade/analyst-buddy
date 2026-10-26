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

## Deploy to a Hugging Face Space

```
pip install huggingface_hub
python deploy/hf_push.py <your-hf-username>
```

Reads `HF_TOKEN` (a write token) and the API keys from `.env`, creates the Space and a private dataset that keeps
accounts and workspaces across restarts, and uploads the code.
