"""Minimal Instagram Graph API client (Facebook Login for Business, Page access token).

Publishes Reels (optionally as trial reels) via resumable upload of a local file,
and reads Reel insights. Secrets come from environment variables only and are never printed.
"""
import json
import os
import time

import requests

GRAPH = "https://graph.facebook.com"
RUPLOAD = "https://rupload.facebook.com/ig-api-upload"
TIMEOUT = 60


class IGError(RuntimeError):
    pass


ACCOUNTS = {"jaffarym": "IG_USER_ID", "jaffarystudios": "IG_USER_ID_2"}
TOKENS = {"jaffarym": "META_PAGE_TOKEN", "jaffarystudios": "META_PAGE_TOKEN_2"}


def _cfg(account=None):
    acct = account or "jaffarym"
    token = (os.environ.get(TOKENS.get(acct, "META_PAGE_TOKEN"), "") or os.environ.get("META_PAGE_TOKEN", "")).strip()
    ig_id = os.environ.get(ACCOUNTS.get(account or "jaffarym", "IG_USER_ID"), "").strip()
    ver = os.environ.get("GRAPH_VERSION", "").strip() or "v26.0"
    if not token or not ig_id:
        raise IGError(f"Missing META_PAGE_TOKEN or {ACCOUNTS.get(account or 'jaffarym', 'IG_USER_ID')} secret")
    return _page_token(token, ig_id, ver), ig_id, ver


_PT = {}


def _page_token(token, ig_id, ver):
    """If the secret is a user token, swap it for the Page token of the Page linked to IG_USER_ID."""
    if token in _PT:
        return _PT[token]
    out = token
    try:
        r = requests.get(f"{GRAPH}/{ver}/me/accounts",
                         params={"fields": "access_token,instagram_business_account", "limit": 100,
                                 "access_token": token}, timeout=TIMEOUT)
        for page in (r.json() or {}).get("data", []):
            if (page.get("instagram_business_account") or {}).get("id") == ig_id and page.get("access_token"):
                out = page["access_token"]
                break
    except (requests.RequestException, ValueError):
        pass
    _PT[token] = out
    return out


def _check(resp):
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text[:300]}
    if resp.status_code >= 400 or (isinstance(data, dict) and "error" in data):
        err = data.get("error", data) if isinstance(data, dict) else data
        # Never echo the token: only message/code/type from Meta.
        if isinstance(err, dict):
            err = {k: err.get(k) for k in ("message", "type", "code", "error_subcode") if k in err}
        raise IGError(f"HTTP {resp.status_code}: {json.dumps(err)[:400]}")
    return data


def temp_link(video_path, repo_path=None, branch="queue"):
    """Short-lived download URL for the file, from the GitHub contents API (private repo, token in URL)."""
    gh, repo = os.environ.get("SRC_TOKEN") or os.environ.get("GITHUB_TOKEN"), os.environ.get("SRC_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if gh and repo and repo_path:
        r = requests.get(f"https://api.github.com/repos/{repo}/contents/{repo_path}", params={"ref": branch},
                         headers={"Authorization": f"Bearer {gh}", "Accept": "application/vnd.github+json"}, timeout=60)
        url = (r.json() or {}).get("download_url") if r.status_code == 200 else None
        if url:
            return url
        raise IGError(f"[temp link] GitHub contents API HTTP {r.status_code}")
    raise IGError("[temp link] no GITHUB_TOKEN/GITHUB_REPOSITORY or repo path")


def _stage(name, call):
    try:
        return _check(call())
    except IGError as e:
        raise IGError(f"[{name}] {e}") from None
    except requests.RequestException as e:
        raise IGError(f"[{name}] network error: {type(e).__name__}") from None


def publish_reel(video_path, caption, trial_strategy=None, repo_path=None, share_to_feed=True, poll_seconds=15, max_wait=900, account=None):
    """Upload a local MP4 and publish it as a Reel. Returns the published media id.

    trial_strategy: None (normal reel), "MANUAL" or "SS_PERFORMANCE" (trial reel).
    """
    token, ig_id, ver = _cfg(account)
    params = {"media_type": "REELS", "upload_type": "resumable", "caption": caption, "access_token": token}
    if trial_strategy:
        params["trial_params"] = json.dumps({"graduation_strategy": trial_strategy})
    else:
        params["share_to_feed"] = "true" if share_to_feed else "false"
    container = _stage("create container", lambda: requests.post(
        f"{GRAPH}/{ver}/{ig_id}/media", data=params, timeout=TIMEOUT))["id"]

    with open(video_path, "rb") as fh:
        body = fh.read()  # send with Content-Length (no chunked upload)
    upload_error = None
    try:
        _stage("upload video", lambda: requests.post(
            f"{RUPLOAD}/{ver}/{container}",
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(body)),
                     "Content-Type": "application/octet-stream"},
            data=body, timeout=600))
    except IGError as e:
        upload_error = str(e)
    if upload_error:
        # Fallback: Instagram fetches the video from a temporary link (auto-deletes after 24 h).
        url = temp_link(video_path, repo_path)
        p2 = {k: v for k, v in params.items() if k != "upload_type"}
        p2["video_url"] = url
        container = _stage("create container (video_url)", lambda: requests.post(
            f"{GRAPH}/{ver}/{ig_id}/media", data=p2, timeout=TIMEOUT))["id"]

    waited = 0
    while True:
        st = _check(requests.get(f"{GRAPH}/{ver}/{container}",
                                 params={"fields": "status_code,status", "access_token": token}, timeout=TIMEOUT))
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise IGError(f"[processing] Container {code}: {st.get('status', '')}"
                          + (f" | upload: {upload_error}" if upload_error else ""))
        if waited >= max_wait:
            raise IGError(f"[processing] Timed out (last status {code}: {st.get('status', '')})"
                          + (f" | upload: {upload_error}" if upload_error else ""))
        time.sleep(poll_seconds)
        waited += poll_seconds

    pub = _stage("publish", lambda: requests.post(f"{GRAPH}/{ver}/{ig_id}/media_publish",
                                                  data={"creation_id": container, "access_token": token}, timeout=TIMEOUT))
    return pub["id"]


REEL_METRICS = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
                "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]


def reel_insights(media_id, account=None):
    """Return {metric: value} for a published reel. Unsupported metrics are skipped."""
    token, _, ver = _cfg(account)
    out = {}
    for m in REEL_METRICS:
        r = requests.get(f"{GRAPH}/{ver}/{media_id}/insights",
                         params={"metric": m, "access_token": token}, timeout=TIMEOUT)
        try:
            data = _check(r)
        except IGError:
            continue
        for item in data.get("data", []):
            vals = item.get("values") or []
            if vals:
                out[item.get("name", m)] = vals[0].get("value")
    meta = _check(requests.get(f"{GRAPH}/{ver}/{media_id}",
                               params={"fields": "permalink,timestamp", "access_token": token}, timeout=TIMEOUT))
    out["permalink"] = meta.get("permalink", "")
    return out
