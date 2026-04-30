import argparse
import json
from datetime import datetime, timezone
from urllib import error, request

from config import (
    ACCOUNT_DSL_CALLBACK_BATCH_SIZE,
    ACCOUNT_DSL_CALLBACK_SECRET,
    ACCOUNT_DSL_CALLBACK_URL,
)
from scheduler import _load_payload


def utc_now_text():
    return datetime.now(timezone.utc).isoformat()


def post_batch(url, secret, items, timeout):
    body = json.dumps({"data": items}, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Api-Secret": secret,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return {
            "ok": True,
            "status_code": resp.status,
            "response_text": resp.read().decode("utf-8", errors="replace"),
        }


def main():
    parser = argparse.ArgumentParser(description="Manual account DSL callback runner")
    parser.add_argument("--url", default=ACCOUNT_DSL_CALLBACK_URL, help="Callback URL")
    parser.add_argument("--secret", default=ACCOUNT_DSL_CALLBACK_SECRET, help="X-Api-Secret value")
    parser.add_argument("--batch-size", type=int, default=ACCOUNT_DSL_CALLBACK_BATCH_SIZE, help="Batch size per request")
    parser.add_argument("--limit", type=int, default=0, help="Only send the first N accounts, 0 means all")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Do not send requests, only print batches")
    parser.add_argument("--save", default="", help="Optional path to save full run result JSON")
    args = parser.parse_args()

    payload = _load_payload()
    if args.limit and args.limit > 0:
        payload = payload[:args.limit]

    batch_size = max(int(args.batch_size or 1), 1)
    run_result = {
        "started_at": utc_now_text(),
        "url": args.url,
        "batch_size": batch_size,
        "total_count": len(payload),
        "dry_run": bool(args.dry_run),
        "batches": [],
    }

    print(json.dumps({
        "stage": "manual_callback_start",
        "started_at": run_result["started_at"],
        "url": args.url,
        "batch_size": batch_size,
        "total_count": len(payload),
        "preview": payload[:5],
        "dry_run": bool(args.dry_run),
    }, ensure_ascii=False), flush=True)

    if not payload:
        print(json.dumps({"stage": "manual_callback_empty"}, ensure_ascii=False), flush=True)
        return

    for index, start in enumerate(range(0, len(payload), batch_size), start=1):
        batch = payload[start:start + batch_size]
        batch_result = {
            "batch_index": index,
            "started_at": utc_now_text(),
            "count": len(batch),
            "items": batch,
        }

        if args.dry_run:
            batch_result.update({
                "ok": True,
                "status_code": None,
                "response_text": "",
                "dry_run": True,
            })
            print(json.dumps({
                "stage": "manual_callback_batch_dry_run",
                "batch_index": index,
                "count": len(batch),
                "preview": batch[:5],
            }, ensure_ascii=False), flush=True)
        else:
            try:
                result = post_batch(args.url, args.secret, batch, args.timeout)
                batch_result.update(result)
                print(json.dumps({
                    "stage": "manual_callback_batch_success",
                    "batch_index": index,
                    "count": len(batch),
                    "status_code": result["status_code"],
                    "response_text": result["response_text"],
                    "preview": batch[:5],
                }, ensure_ascii=False), flush=True)
            except error.HTTPError as exc:
                response_text = exc.read().decode("utf-8", errors="replace")
                batch_result.update({
                    "ok": False,
                    "status_code": exc.code,
                    "response_text": response_text,
                    "error": f"HTTPError: {exc}",
                })
                print(json.dumps({
                    "stage": "manual_callback_batch_http_error",
                    "batch_index": index,
                    "count": len(batch),
                    "status_code": exc.code,
                    "response_text": response_text,
                    "preview": batch[:5],
                }, ensure_ascii=False), flush=True)
            except Exception as exc:
                batch_result.update({
                    "ok": False,
                    "status_code": None,
                    "response_text": "",
                    "error": str(exc),
                })
                print(json.dumps({
                    "stage": "manual_callback_batch_exception",
                    "batch_index": index,
                    "count": len(batch),
                    "error": str(exc),
                    "preview": batch[:5],
                }, ensure_ascii=False), flush=True)

        run_result["batches"].append(batch_result)

    run_result["finished_at"] = utc_now_text()
    run_result["success_batches"] = sum(1 for batch in run_result["batches"] if batch.get("ok"))
    run_result["failed_batches"] = sum(1 for batch in run_result["batches"] if not batch.get("ok"))

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(run_result, f, ensure_ascii=False, indent=2, default=str)
        print(json.dumps({
            "stage": "manual_callback_saved",
            "path": args.save,
        }, ensure_ascii=False), flush=True)

    print(json.dumps({
        "stage": "manual_callback_done",
        "finished_at": run_result["finished_at"],
        "total_count": run_result["total_count"],
        "batch_count": len(run_result["batches"]),
        "success_batches": run_result["success_batches"],
        "failed_batches": run_result["failed_batches"],
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
