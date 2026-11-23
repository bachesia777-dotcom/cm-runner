"""Check a list of Instagram handles via the official Business Discovery API.
Usage: python robot/verify.py handles.txt -> data/research/verify-<ts>.json
One light call per handle: username, name, followers, posts, bio, 12 latest captions/likes/comments.
Also lists @mentions found in captions (to find more similar accounts). Stops on rate-limit errors."""
import json, os, re, sys, time, statistics, collections
from datetime import datetime, timezone
import requests
sys.path.insert(0, os.path.dirname(__file__))
import ig  # noqa: E402

F = "username,name,followers_count,media_count,biography,website,media.limit(12){caption,like_count,comments_count,timestamp,media_type}"

def main(path):
    hs = [h.strip().lstrip("@").lower() for h in open(path).read().replace(",", "\n").split() if h.strip()]
    cfgs = [ig._cfg(None)] + ([ig._cfg("jaffarystudios")] if os.environ.get("IG_USER_ID_2") else [])
    out, errs, ment = [], {}, collections.Counter()
    for n, h in enumerate(hs):
        token, ig_id, ver = cfgs[n % len(cfgs)]
        try:
            r = requests.get(f"{ig.GRAPH}/{ver}/{ig_id}", params={"fields": f"business_discovery.username({h}){{{F}}}", "access_token": token}, timeout=60)
            bd = ig._check(r)["business_discovery"]
        except Exception as e:
            s = str(e); errs[h] = s[:160]
            if any(k in s for k in ("(#4)", "(#17)", "(#32)", "code': 4", "code': 17", "rate limit", "too many calls")):
                errs["_stopped_at"] = h; break
            continue
        media = (bd.get("media") or {}).get("data", [])
        eng = [(m.get("like_count") or 0) + (m.get("comments_count") or 0) for m in media]
        for m in media:
            for u in re.findall(r"@([A-Za-z0-9_.]{2,30})", m.get("caption") or ""):
                ment[u.lower().rstrip(".")] += 1
        out.append({"username": bd.get("username"), "name": bd.get("name"), "followers": bd.get("followers_count"),
                    "posts": bd.get("media_count"), "bio": bd.get("biography"), "website": bd.get("website"),
                    "median_engagement": statistics.median(eng) if eng else 0,
                    "last_post": media[0].get("timestamp") if media else None})
        time.sleep(0.4)
    os.makedirs("data/research", exist_ok=True)
    fn = f"data/research/verify-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.json"
    json.dump({"accounts": out, "errors": errs, "mentions": ment.most_common(300)}, open(fn, "w"), indent=1, ensure_ascii=False)
    print(fn, len(out), "ok", len(errs), "failed")

if __name__ == "__main__":
    main(sys.argv[1])
