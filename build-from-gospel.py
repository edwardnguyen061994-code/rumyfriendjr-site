#!/usr/bin/env python3
"""Rebuild rumyfriendjr.com as a copy of jr.rumyfriend.com.

WHY A CLONE AND NOT A GENERATOR. This site used to be generated from the Flutter
app's own catalogue (tool-side gen_site.py reading /tmp/jr_catalog.json, written
by test/dump_jr_catalog_test.dart). That kept the site honest about what the app
ships, but it also meant the two pages looked nothing alike: a 58KB marketing
page here, a 20KB list page there. The owner asked on 2026-09-17 for
rumyfriendjr.com to BE jr.rumyfriend.com, so the source of truth is now the
rendered page itself.

WHAT THAT CHANGES, SAID PLAINLY. The gospel carries Contain 'Em and the app does
not -- `contain` is in kJuniorHiddenSlugs because its landing screen is an
account form (EMAIL / PASSWORD / AGE GROUP 18+ 13-17) with no under-13 option.
The owner chose to carry it on the SITE anyway. The app is deliberately NOT
changed to match: it is in review as a Kids Category app and that link is a
rejection risk there. So the site is a superset of the app by exactly one game,
on purpose, and this comment is the record of why.

THREE THINGS CANNOT BE COPIED VERBATIM, because this is GitHub Pages and the
gospel is a Cloudflare Worker:

  1. /api/live-lobbies?jr=1 is served by that Worker. There is no such route
     here, and a relative fetch would 404 into the catch and show "No live games
     right now" forever. It is rewritten to the absolute URL; the endpoint
     answers `access-control-allow-origin: *`, verified 2026-09-17, so the strip
     works cross-origin.
  2. Asset layout differs: the gospel serves /assets/games/<name>-poster.jpg,
     this repo has assets/ flat. Paths are flattened rather than duplicating
     33 binaries into a second directory.
  3. /rankings is a separate Worker page with its own API and 404s here, so the
     link points back at the gospel host rather than dangling.

The Cloudflare bot-challenge <script> is stripped: it is injected by the edge,
is not part of the page, and does nothing but make a 1x1 iframe here.
"""

import re
import sys
import urllib.request

GOSPEL = "https://jr.rumyfriend.com/"
OUT = "index.html"
LIVE_API = "https://jr.rumyfriend.com/api/live-lobbies?jr=1"
RANKINGS = "https://jr.rumyfriend.com/rankings"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "rumyfriendjr-build"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status != 200:
            raise SystemExit(f"{url} returned {r.status}")
        return r.read().decode("utf-8")


def strip_cf_challenge(html: str) -> str:
    """Drop the edge-injected bot-challenge script, and only that one."""
    out = re.sub(
        r"<script[^>]*>(?:(?!</script>).)*__CF\$cv\$params(?:(?!</script>).)*</script>",
        "",
        html,
        flags=re.S,
    )
    if "__CF$cv$params" in out:
        raise SystemExit("the Cloudflare script was not removed")
    return out


def rewrite(html: str) -> str:
    html = strip_cf_challenge(html)
    # Flatten the asset layout. This also catches the path built inside the
    # live-lobby script ('/assets/games/' + art + '-poster.jpg').
    html = html.replace("/assets/games/", "/assets/")
    html = html.replace("'/api/live-lobbies?jr=1'", f"'{LIVE_API}'")
    html = html.replace('href="/rankings"', f'href="{RANKINGS}"')
    return html


def check(html: str) -> None:
    """Refuse to write a page that is broken in a way we already know about."""
    problems = []
    if "/assets/games/" in html:
        problems.append("an unflattened /assets/games/ path survived")
    if "'/api/live-lobbies" in html:
        problems.append("the live-lobby fetch is still relative and will 404")
    if 'href="/rankings"' in html:
        problems.append("/rankings still points at a page this host does not have")

    hosts = set(re.findall(r"https://([a-z0-9-]+)\.rumyfriend\.com", html))
    hosts -= {"jr", "www", "api"}
    if len(hosts) < 29:
        problems.append(f"only {len(hosts)} game hosts found, expected 29")
    if "containem" not in hosts:
        problems.append("Contain 'Em is missing; the owner asked for the full gospel")
    if "jrlive" not in html:
        problems.append("the Live games container is gone")

    if problems:
        for p in problems:
            print("  FAIL:", p, file=sys.stderr)
        raise SystemExit("not writing index.html")
    print(f"ok: {len(hosts)} game hosts, live strip present")


def main() -> None:
    html = rewrite(fetch(GOSPEL))
    check(html)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {OUT}  {len(html)} bytes")


if __name__ == "__main__":
    main()
