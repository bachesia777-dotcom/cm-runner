"""Post every approved, due Instagram item in the queue. Run by GitHub Actions.

Usage: python robot/post_due.py --queue-dir queue_branch [--ledger data/posted.csv] [--limit 3] [--dry-run]
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
import postqueue as q  # noqa: E402
import ig  # noqa: E402

LEDGER_FIELDS = ["id", "account", "group", "variant", "platform", "trial", "media_id", "posted_at", "caption"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue-dir", required=True)
    ap.add_argument("--ledger", default="data/posted.csv")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    qpath = os.path.join(a.queue_dir, "queue.json")
    if not os.path.exists(qpath):
        print("No queue.json yet - nothing to post.")
        return 0
    items = q.load(qpath)
    # at most one reel per account per run, so accounts never get bursts
    # skip Asia prime time (04:00-10:00 UTC = 08:00-14:00 Dubai); post in US/EU hours
    if 4 <= datetime.now(timezone.utc).hour < 10:
        print("Outside US/EU window - nothing posted.")
        return 0
    todo, seen = [], set()
    for it in q.due(items, limit=1000):
        acct = it.get("account") or "default"
        if acct in seen:
            continue
        seen.add(acct)
        todo.append(it)
        if len(todo) >= a.limit:
            break
    paused = set()
    print(f"{len(todo)} item(s) due.")
    posted, failed = 0, 0
    for it in todo:
        if (it.get("account") or "default") in paused:
            continue
        path = os.path.join(a.queue_dir, it["file"])
        if not os.path.exists(path):
            it.update(status="error", error="video file missing")
            failed += 1
            continue
        if a.dry_run:
            print(f"[dry-run] would post {it['id']} ({it.get('trial') or 'normal'})")
            continue
        try:
            mid = ig.publish_reel(path, it.get("caption", ""), it.get("trial"), repo_path=it["file"], account=it.get("account"))
            it.update(status="posted", media_id=mid, error=None,
                      posted_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            # only delete the file when no other queued item still needs it (same video on 2 accounts)
            if not any(o is not it and o.get("file") == it["file"] and o.get("status") in ("pending", "error") for o in items):
                os.remove(path)  # keep the queue branch small; the ledger keeps the record
            _append_ledger(a.ledger, it)
            posted += 1
            print(f"Posted {it['id']} -> {mid}")
        except ig.IGError as e:
            if "too many actions" in str(e).lower() or "2207078" in str(e) or '"code": 9' in str(e):
                # Instagram spam limit: push this account's whole queue back 24h instead of hammering it
                acct = it.get("account")
                paused.add(acct or "default")
                for o in items:
                    if o.get("account") == acct and o.get("status") == "pending":
                        t = datetime.strptime(o["scheduled_at"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                        o["scheduled_at"] = (max(t, datetime.now(timezone.utc)) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
                it["error"] = "rate limited - account paused 24h: " + str(e)[:120]
                failed += 1
                print(f"Rate limited on {acct}: paused 24h")
                continue
            it["attempts"] = it.get("attempts", 0) + 1
            it["error"] = str(e)
            if it["attempts"] >= 3:
                it["status"] = "error"
            failed += 1
            print(f"Failed {it['id']}: {e}")
    q.save(qpath, items)
    print(f"Done: {posted} posted, {failed} failed.")
    return 1 if failed and not posted else 0


def _append_ledger(path, it):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: it.get(k) for k in LEDGER_FIELDS})


if __name__ == "__main__":
    sys.exit(main())
