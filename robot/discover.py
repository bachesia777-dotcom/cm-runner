"""Competitor research via the official Business Discovery API (public business/creator accounts only).
Usage: python robot/discover.py handle1,handle2,...  -> data/research/<date>.json
No scraping: one API call per account, reading what the account already shows publicly."""
import json, os, sys, statistics
from datetime import datetime, timezone
import requests
sys.path.insert(0, os.path.dirname(__file__))
import ig  # noqa: E402

MEDIA = "id,caption,like_count,comments_count,media_type,media_product_type,permalink,timestamp"

def fetch(token, ig_id, ver, handle, with_views):
    fields = MEDIA + (",view_count" if with_views else "")
    q = f"business_discovery.username({handle}){{username,name,followers_count,media_count,biography,media.limit(30){{{fields}}}}}"
    r = requests.get(f"{ig.GRAPH}/{ver}/{ig_id}", params={"fields": q, "access_token": token}, timeout=60)
    return ig._check(r)["business_discovery"]

def main(handles):
    cfgs = [ig._cfg(None)] + ([ig._cfg("jaffarystudios")] if os.environ.get("IG_USER_ID_2") else [])
    out, errs = [], {}
    for h in handles:
        h = h.strip().lstrip("@")
        if not h: continue
        try:
            bd, last = None, None
            for token, ig_id, ver in cfgs:
                for views in (True, False):
                    try: bd = fetch(token, ig_id, ver, h, views); break
                    except ig.IGError as e: last = e
                if bd: break
            if not bd: raise last
            media = (bd.get("media") or {}).get("data", [])
            reels = [m for m in media if m.get("media_product_type") == "REELS" or m.get("media_type") == "VIDEO"]
            eng = [(m.get("like_count") or 0) + (m.get("comments_count") or 0) for m in reels]
            med = statistics.median(eng) if eng else 0
            for m in reels:
                e = (m.get("like_count") or 0) + (m.get("comments_count") or 0)
                m["engagement"] = e; m["multiple"] = round(e / med, 2) if med else None
            out.append({"username": bd.get("username"), "name": bd.get("name"), "followers": bd.get("followers_count"),
                        "posts": bd.get("media_count"), "bio": bd.get("biography"), "median_engagement": med, "reels": reels})
        except Exception as e:
            errs[h] = str(e)[:200]
    os.makedirs("data/research", exist_ok=True)
    fn = f"data/research/{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    json.dump({"accounts": out, "errors": errs}, open(fn, "w"), indent=1, ensure_ascii=False)
    print(fn, len(out), "ok,", len(errs), "failed:", list(errs))

if __name__ == "__main__":
    main(sys.argv[1].split(","))
