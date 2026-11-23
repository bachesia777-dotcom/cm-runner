"""List an account's recent posts (permalink + comment count) via the official Business Discovery API.
Usage: python robot/posts.py handle [max] -> data/research/posts-<handle>.json"""
import json, os, sys
import requests
sys.path.insert(0, os.path.dirname(__file__))
import ig  # noqa: E402

def main(h, mx=200):
    token, ig_id, ver = ig._cfg(None)
    out, after = [], None
    while len(out) < mx:
        page = f".after({after})" if after else ""
        f = f"business_discovery.username({h}){{media.limit(50){page}{{permalink,comments_count,like_count,timestamp,media_type}}}}"
        r = ig._check(requests.get(f"{ig.GRAPH}/{ver}/{ig_id}", params={"fields": f, "access_token": token}, timeout=60))
        m = r["business_discovery"]["media"]
        out += m.get("data", [])
        after = (m.get("paging") or {}).get("cursors", {}).get("after")
        if not after: break
    os.makedirs("data/research", exist_ok=True)
    json.dump(out[:mx], open(f"data/research/posts-{h}.json", "w"), indent=1)
    print(h, len(out), "posts", sum(p.get("comments_count") or 0 for p in out), "comments")

if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 200)
