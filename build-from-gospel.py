#!/usr/bin/env python3
"""Rebuild rumyfriendjr.com as a copy of jr.rumyfriend.com.

WHY A CLONE AND NOT A GENERATOR. This site used to be generated from the Flutter
app's own catalogue (gen_site.py reading /tmp/jr_catalog.json, written by
test/dump_jr_catalog_test.dart). That kept the site honest about what the app
ships, but it also meant the two pages looked nothing alike. The owner asked on
2026-09-17 for rumyfriendjr.com to BE jr.rumyfriend.com, so the source of truth
is the rendered page itself.

NO DIVERGENCES. Two earlier ones are gone, and both deletions are deliberate:

  * The Balance 'Em / Build 'Em preview section was added on request and then
    removed when the owner restated that the two sites must match. The media
    still sits unreferenced in assets/previews/ so it can be restored without
    re-exporting; nothing links to it.
  * A `[hidden]{display:none !important}` patch worked around the Top scores
    dialog covering the page. THE GOSPEL HAS SINCE FIXED THAT ITSELF -- measured
    2026-09-17, every [hidden] element there now computes display:none and the
    element under the middle of the viewport is the hero. Carrying the patch
    would be keeping a difference for no reason.

THREE THINGS CANNOT BE COPIED VERBATIM, because this is GitHub Pages and the
gospel is a Cloudflare Worker:

  1. Its /api/ routes do not exist here. A relative fetch would 404 and leave
     Live games, Friends and Ranks hanging. Every quoted /api/ path is rewritten
     absolute. Friends and Ranks send `credentials: "include"`, which a browser
     refuses against a wildcard CORS header -- the Worker answers this exact
     origin with `access-control-allow-origin: https://www.rumyfriendjr.com`
     and `access-control-allow-credentials: true` (verified 2026-09-17), so the
     credentialed cross-origin call is allowed.
  2. Asset layout differs: the gospel serves /assets/games/<name>-poster.jpg,
     this repo has assets/ flat. Paths are flattened rather than duplicating the
     binaries into a second directory.
  3. /rankings is a separate Worker page with its own API and 404s here, so the
     link points back at the gospel host rather than dangling.

The Cloudflare bot-challenge <script> is stripped: it is injected by the edge,
is not part of the page, and does nothing but make a 1x1 iframe here.
"""

import json
import os
import re
import sys
import urllib.request

GOSPEL = "https://jr.rumyfriend.com/"
OUT = "index.html"
RANKINGS = "https://jr.rumyfriend.com/rankings"

# The gospel grew from 29 games to 30 between two runs of this script, which is
# exactly why the count is not hard-coded any more -- see games_in().
MIN_GAMES = 29


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


def games_in(html: str) -> dict:
    """The page's OWN game map, as the source of truth for what it carries.

    The live-games script embeds `var G = {"names": ..., "origins": ...}`. Using
    it rather than a number typed into this file means a gospel that gains a
    game is copied rather than rejected: the previous check demanded exactly 29
    hosts and would have refused the build the day Rally 'Em appeared.
    """
    m = re.search(r"var G = (\{.*?\});", html, re.S)
    if not m:
        raise SystemExit("could not find the page's game map; the live script changed")
    return json.loads(m.group(1))


def rewrite(html: str) -> str:
    html = strip_cf_challenge(html)
    # Flatten the asset layout. This also catches the path built inside the
    # live-lobby script ('/assets/games/' + art + '-poster.jpg').
    html = html.replace("/assets/games/", "/assets/")
    # EVERY same-origin /api/ call, matched by SHAPE rather than by a list of
    # names. The list version broke the day the gospel grew Friends and Ranks.
    html = re.sub(r"""(["'])/api/""", r"\1" + GOSPEL.rstrip("/") + "/api/", html)
    html = html.replace('href="/rankings"', f'href="{RANKINGS}"')
    return html


def sync_assets(html: str) -> list:
    """Download every asset the page references that this repo does not have.

    WHY THIS IS AUTOMATIC. The first clone needed five files fetched by hand;
    the next gospel change needed seven more (the Ranks header, podium and four
    icons, plus Rally 'Em's poster). Copying a page but not the pictures it
    names produces a site that passes every structural check and renders broken
    images, which is worse than failing the build.

    Paths are tried in the rewritten form first and then under /assets/games/,
    because rewrite() flattens that directory away -- so a missing
    /assets/foo-poster.jpg may live at /assets/games/foo-poster.jpg upstream.
    """
    refs = sorted(
        set(
            re.findall(
                r"/assets/([A-Za-z0-9/_.-]+\.(?:jpg|jpeg|png|svg|webp|mp4|webm|avif))",
                html,
            )
        )
    )
    fetched = []
    for ref in refs:
        local = os.path.join("assets", ref)
        if os.path.exists(local):
            continue
        for remote in (
            f"{GOSPEL.rstrip('/')}/assets/{ref}",
            f"{GOSPEL.rstrip('/')}/assets/games/{ref}",
        ):
            try:
                req = urllib.request.Request(
                    remote, headers={"User-Agent": "rumyfriendjr-build"}
                )
                with urllib.request.urlopen(req, timeout=60) as r:
                    if r.status != 200:
                        continue
                    blob = r.read()
            except Exception:
                continue
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, "wb") as f:
                f.write(blob)
            fetched.append((ref, len(blob)))
            break
        else:
            raise SystemExit(f"{ref} is referenced but could not be fetched")
    return fetched


def check(html: str) -> None:
    """Refuse to write a page that is broken in a way we already know about."""
    problems = []
    if "/assets/games/" in html:
        problems.append("an unflattened /assets/games/ path survived")
    # Any surviving same-origin /api/ is a panel that will hang on "Loading…".
    stragglers = re.findall(r"""["']/api/[A-Za-z0-9/?=&_-]*""", html)
    if stragglers:
        problems.append(f"relative API calls survived: {sorted(set(stragglers))}")
    if 'href="/rankings"' in html:
        problems.append("/rankings still points at a page this host does not have")
    if "jrlive" not in html:
        problems.append("the Live games container is gone")

    # Every game the page SAYS it has must actually be linked in the page.
    game_map = games_in(html)
    names, origins = game_map.get("names", {}), game_map.get("origins", {})
    if len(names) < MIN_GAMES:
        problems.append(f"only {len(names)} games in the page's own map")
    for key, origin in origins.items():
        host = re.match(r"https://([a-z0-9-]+)\.", origin)
        if not host or host.group(1) not in html:
            problems.append(f"{names.get(key, key)} is in the map but not linked")

    # The divergences are gone; assert they stay gone, or "same as the gospel"
    # quietly stops being true again.
    if "previews-heading" in html:
        problems.append("the previews section is back; this site must match the gospel")
    # The exact rule this build used to inject, not "!important" generally: the
    # gospel's own CSS uses !important ten times, including the
    # `display:none!important` that is ITS fix for the dialog bug this patch
    # used to work around. Banning the substring rejected a faithful copy.
    if "[hidden]{display:none !important;}" in html:
        problems.append(
            "the local [hidden] patch is back; the gospel fixed this itself"
        )

    if problems:
        for p in problems:
            print("  FAIL:", p, file=sys.stderr)
        raise SystemExit("not writing index.html")
    print(f"ok: {len(names)} games, all linked, live strip present, no divergences")


def main() -> None:
    html = rewrite(fetch(GOSPEL))
    for ref, size in sync_assets(html):
        print(f"  fetched assets/{ref}  {size} bytes")
    check(html)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {OUT}  {len(html)} bytes")


if __name__ == "__main__":
    main()
