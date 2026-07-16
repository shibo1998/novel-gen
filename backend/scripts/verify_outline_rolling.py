import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import create_access_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id")
    parser.add_argument("user_id")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=700)
    args = parser.parse_args()

    token = create_access_token({"sub": args.user_id})
    client = httpx.Client(
        base_url=args.base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
        trust_env=False,
    )
    response = client.post(
        f"/api/projects/{args.project_id}/outline",
        json={"regenerate": True},
    )
    response.raise_for_status()
    task_id = response.json()["task_id"]
    print(json.dumps({"task_id": task_id, "status": "started"}, ensure_ascii=False), flush=True)

    deadline = time.time() + args.timeout
    last_snapshot = None
    while time.time() < deadline:
        status = client.get(f"/api/tasks/{task_id}").json()
        meta = status.get("meta") or {}
        snapshot = (status.get("status"), meta.get("phase"), meta.get("message"))
        if snapshot != last_snapshot:
            print(json.dumps(status, ensure_ascii=False), flush=True)
            last_snapshot = snapshot
        if status.get("status") in ("completed", "failed", "orphaned"):
            break
        time.sleep(2)
    else:
        raise TimeoutError(f"Outline verification exceeded {args.timeout} seconds")

    if status.get("status") != "completed":
        raise RuntimeError(status.get("error") or status.get("status"))

    outline = client.get(f"/api/projects/{args.project_id}/outline").json()
    summary = {
        "volumes": [
            {
                "number": volume["number"],
                "range": [volume["chapter_start"], volume["chapter_end"]],
                "planned": volume["planned_chapter_count"],
                "target": volume["target_chapter_count"],
                "status": volume["status"],
            }
            for volume in outline["volumes"]
        ],
        "chapters": [chapter["number"] for chapter in outline["chapters"]],
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
