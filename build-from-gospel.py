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

# ---------------------------------------------------------------------------
# The one deliberate difference from the gospel.
#
# The owner asked on 2026-09-17 for the Balance 'Em and Build 'Em preview clips
# to appear here, knowing the gospel does not carry them. Everything else on
# this page is a copy; THIS is the divergence, and it is injected rather than
# hand-edited into index.html so a rebuild does not silently delete it.
#
# preload="none" is load-bearing, not a nicety: the two MP4s are 31MB and 39MB
# and this is a page for children who may be on a phone connection. With
# preload="none" the browser fetches the poster only, and a byte of video moves
# when a child taps play. The WebM sources are listed FIRST because they are a
# quarter of the size; Safari and iOS ignore them and take the MP4, which is
# why the MP4s ship at all.
#
# The clips carry their own captured audio, so they are NOT autoplay and NOT
# muted -- they have controls and start on a tap.
PREVIEWS_HTML = """<section class="previews panel" aria-labelledby="previews-heading">
    <h2 id="previews-heading">Watch a game</h2>
    <p class="lsub">Two short clips, with sound. Tap to play.</p>
    <div class="prow">
      <figure class="pv">
        <video controls playsinline preload="none"
               poster="/assets/previews/balance-poster.png"
               aria-label="Balance &#8217;Em gameplay clip">
          <source src="/assets/previews/balance-preview.webm" type="video/webm">
          <source src="/assets/previews/balance-preview.mp4" type="video/mp4">
        </video>
        <figcaption>Balance &#8217;Em</figcaption>
      </figure>
      <figure class="pv">
        <video controls playsinline preload="none"
               poster="/assets/previews/build-poster.png"
               aria-label="Build &#8217;Em gameplay clip">
          <source src="/assets/previews/build-preview.webm" type="video/webm">
          <source src="/assets/previews/build-preview.mp4" type="video/mp4">
        </video>
        <figcaption>Build &#8217;Em</figcaption>
      </figure>
    </div>
  </section>

  """

# Written in the page's own variables (--card, --line, --ink2) so the section
# cannot drift from the palette if the gospel restyles.
PREVIEWS_CSS = """
  .prow{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));}
  .pv{margin:0;background:var(--card);border:1px solid var(--line);
    border-radius:16px;overflow:hidden;}
  .pv video{display:block;width:100%;aspect-ratio:886/1920;background:#000;}
  .pv figcaption{padding:11px 12px 13px;font-weight:700;font-size:14px;}
  @media (max-width:560px){
    .prow{grid-template-columns:1fr;}
    .pv{border-radius:13px;}
    .pv figcaption{font-size:13px;padding:9px 10px 11px;}
  }
"""


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
    # EVERY same-origin /api/ call, not a named list of them.
    #
    # This used to rewrite the single literal '/api/live-lobbies?jr=1'. The
    # gospel then grew Friends and Ranks, whose fetches came through untouched
    # and pointed at this host, which serves no API -- so the "Top scores"
    # dialog sat on "Loading..." forever. A rewrite that has to be extended by
    # hand every time the gospel gains an endpoint is a rewrite that will be
    # wrong again, so it matches the shape instead.
    #
    # Those two send `credentials: "include"`, which a browser refuses against
    # a wildcard CORS header. The Worker answers this exact origin with
    # `access-control-allow-origin: https://www.rumyfriendjr.com` and
    # `access-control-allow-credentials: true` (verified 2026-09-17), so the
    # credentialed cross-origin call is allowed. If that ever reverts to `*`,
    # Friends and Ranks go blank here and nowhere else.
    html = re.sub(r"""(["'])/api/""", r"\1" + GOSPEL.rstrip("/") + "/api/", html)
    html = html.replace('href="/rankings"', f'href="{RANKINGS}"')

    # Between Live games and the game grid: after what is happening now, before
    # the list of everything.
    anchor = '<section class="library panel"'
    if anchor not in html:
        raise SystemExit("the library section moved; previews have nowhere to go")
    html = html.replace(anchor, PREVIEWS_HTML + anchor, 1)

    if "</style>" not in html:
        raise SystemExit("no </style> to append the preview rules to")
    html = html.replace("</style>", PREVIEWS_CSS + "</style>", 1)
    return html


def check(html: str) -> None:
    """Refuse to write a page that is broken in a way we already know about."""
    problems = []
    if "/assets/games/" in html:
        problems.append("an unflattened /assets/games/ path survived")
    # Any surviving same-origin /api/ is a dialog that will hang on "Loading…".
    stragglers = re.findall(r"""["']/api/[A-Za-z0-9/?=&_-]*""", html)
    if stragglers:
        problems.append(f"relative API calls survived: {sorted(set(stragglers))}")
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

    # The one deliberate divergence, checked as hard as the copy itself.
    for needed in (
        'id="previews-heading"',
        "/assets/previews/balance-preview.mp4",
        "/assets/previews/balance-preview.webm",
        "/assets/previews/build-preview.mp4",
        "/assets/previews/build-preview.webm",
        "/assets/previews/balance-poster.png",
        "/assets/previews/build-poster.png",
        ".pv video",
    ):
        if needed not in html:
            problems.append(f"preview section incomplete: {needed} missing")
    if 'preload="none"' not in html:
        problems.append("previews would preload; 70MB on a child's phone connection")

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
