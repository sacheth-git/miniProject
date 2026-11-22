r"""Create (or update) the HireX Hugging Face Space and upload deploy/build/.

Needs HF_TOKEN (a Hugging Face access token with write permission) in the repo's .env file.
Sets a fresh random JWT_SECRET as a Space secret on first creation. API keys are never uploaded:
the Space serves the job snapshot in the bundled database and does not fetch new jobs.

Usage (repo root, after make_deploy_bundle.py):
    backend\.venv\Scripts\python.exe backend\scripts\push_space.py [--name hirex] [--private]
"""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path

from huggingface_hub import HfApi
from huggingface_hub.utils import HfHubHTTPError

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "deploy" / "build"


def token_from_env() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("HF_TOKEN="):
            tok = line.split("=", 1)[1].strip().strip('"')
            if tok:
                return tok
    raise SystemExit("Add HF_TOKEN=hf_... (a write token from huggingface.co/settings/tokens) to .env")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="hirex")
    ap.add_argument("--private", action="store_true")
    args = ap.parse_args()
    if not (BUNDLE / "Dockerfile").exists():
        raise SystemExit("Build the bundle first: backend/scripts/make_deploy_bundle.py")

    api = HfApi(token=token_from_env())
    user = api.whoami()["name"]
    repo_id = f"{user}/{args.name}"
    try:
        api.repo_info(repo_id, repo_type="space")
        created = False
    except HfHubHTTPError:
        api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=args.private)
        created = True
    if created:
        api.add_space_secret(repo_id, "JWT_SECRET", secrets.token_urlsafe(48))
    api.add_space_variable(repo_id, "ENABLE_SCHEDULER", "false")
    api.add_space_variable(repo_id, "ENVIRONMENT", "production")

    print(f"Uploading {BUNDLE} to {repo_id} (large files go through Git LFS; this can take several minutes)...")
    api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=str(BUNDLE), commit_message="Deploy HireX")
    host = f"{user}-{args.name}".lower().replace("_", "-").replace(".", "-")
    print(f"Space: https://huggingface.co/spaces/{repo_id}")
    print(f"App:   https://{host}.hf.space  (first build takes about 10-15 minutes)")


if __name__ == "__main__":
    main()
