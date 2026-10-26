import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

ROOT = Path(__file__).parent.parent
SECRETS = ["GOOGLE_API_KEY", "E2B_API_KEY", "PINECONE_API_KEY", "HF_TOKEN"]
CODE = ["*.py", "requirements.txt", "Dockerfile", ".dockerignore", "README.md", "web/**"]
NOT_CODE = ["web/node_modules/**", "web/dist/**", "**/__pycache__/**", "deploy/**"]

if len(sys.argv) != 2:
    sys.exit("usage: python deploy/hf_push.py <your-hf-username>")
load_dotenv(ROOT / ".env")
missing = [k for k in SECRETS if not os.getenv(k)]
if missing:
    sys.exit(f"Add these to .env first: {', '.join(missing)} (HF_TOKEN = a write token from huggingface.co/settings/tokens)")

user = sys.argv[1]
space, state = f"{user}/analyst-buddy", f"{user}/analyst-buddy-state"
api = HfApi(token=os.environ["HF_TOKEN"])

api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)
for key in SECRETS:
    api.add_space_secret(space, key, os.environ[key])
api.add_space_variable(space, "STATE_REPO", state)

sys.path.insert(0, str(ROOT))
import persist

persist.REPO = state
api.create_repo(state, repo_type="dataset", private=True, exist_ok=True)
if (ROOT / "accounts.json").exists():
    persist.push()
    print(f"Copied your accounts and workspaces to the private dataset {state}")

api.upload_folder(repo_id=space, repo_type="space", folder_path=ROOT, allow_patterns=CODE, ignore_patterns=NOT_CODE,
                  commit_message="deploy Analyst Buddy")
print(f"Uploaded. It builds in a few minutes: https://huggingface.co/spaces/{space}")
