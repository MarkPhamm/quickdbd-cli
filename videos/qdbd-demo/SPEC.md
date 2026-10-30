# qdbd demo: spec

GOAL:    a data engineer watching muted on qdbd.dev or the README gets "my schema as a text file in git becomes a
         diagram I can actually use", sees it work locally first, then in VS Code, and leaves with `pipx install quickdbd-cli`.
OUTPUT:  HyperFrames, 1920 x 1080, 30 fps, H.264, <= 8 MB.
TIME:    60 s x 30 = 1800 frames. Music bed TBD (HeyGen catalog, or silent: see BRIEF.md).
LOOK:    the qdbd.dev blueprint sheet, the brand's own material.
         ground paper #f2f2ee with a 96 px major grid at rgba(21,24,30,.07) and a 24 px minor grid at .035;
         ink #15181e; secondary ink #4a505b; one accent #2f5bea, on one word per shot at most, the wordmark and the CTA;
         titles Geist 600, 64 px (5.9% of the height), tracking -0.03em, left-aligned at x = 96, baseline zone y 64-150;
         code and terminal Geist Mono 400, 23-34 px; the product's own UI keeps its own fonts (Inter).
         windows: sheet #fafaf7 chrome bar 44 px, radius 14 px, shadow 0 18px 40px -18px rgba(21,24,30,.28);
         terminal and editor windows ink #15181e with paper text. VS Code world: ground #181818 (VS Code Dark Modern).
         no grain, no vignette, no glow.
OBJECTS: the real viewer (recorded at 2880 x 1800), the real VS Code, real terminal output, the qdbd mark (two blue
         blocks joined by a line) and wordmark from docs/assets/img.
MOTION:  arrive expo.out 0.5-0.7 s; camera power2.inOut 0.55 s; exits power3.in 0.25 s; words blur 6 px -> 0 in
         0.13 s, 0.067 s apart, no translate; titles dead still once landed; punch-ins 1.6-2.2x so UI text >= 26 px.
SHOTS:
  01 hook     0.0-7.0   real zoom from one readable table out to all 200 (product performing), then the plate
                        settles under the title; "Database diagrams that live in git" (3.3-5.2),
                        "Readable at 200+ tables" (5.3-6.9, 200+ in accent)
  02 write    7.0-12.5  dark editor: shop.txt arrives line by line; tab flips to shop.dbml (same schema, real
                        `qdbd convert` output); "Write the schema as text", then "QuickDBD or DBML"
  03 build   12.5-17.5  the editor morphs into a terminal: `qdbd build shop.dbml -o shop.html`, real output, then
                        `open shop.html`; "One command, one HTML file"
  04 open    17.5-21.5  zoom through `shop.html`: the browser window grows out of it; hover lights each
                        relationship; "Opens in any browser"
  05 explore 21.5-33.5  AdventureWorks DW (28 tables): search, select (neighbours stay lit), hover a line,
                        the details panel; punch-ins on each; four short lines
  06 serve   33.5-42.0  `qdbd serve`: type a Review table, autosave redraws it next to Product, drag it;
                        "qdbd serve: edit it live", "It saves and redraws itself"
  07 vscode  42.0-50.5  colour flood into VS Code: the diagram follows the cursor; a typo gets QuickDBD's own
                        error in the hover; fixed; "In VS Code and Cursor", "Errors as you type"
  08 more    50.5-55.0  export buttons clicked (PNG, SVG, draw.io), then the diff build (NEW green, CHANGED amber);
                        "Export PNG, SVG, draw.io", "Every PR shows what changed"
  09 end     55.0-60.0  the mark performed (blocks land, the line draws), wordmark wipes in, `pipx install
                        quickdbd-cli` and qdbd.dev · VS Code Marketplace · Open VSX; hold 3 s
BANNED:  the defaults in the skill's spec.md; plus anything about sharing (`qdbd share`, Share menus, the viewer's Link
         button, tunnels); emoji or icon glyphs in our own text; a title over a dimmed screenshot; three cards in a row;
         invented UI.
QA:      2.0 (zoom mid-flight, readable table earlier), 4.5, 6.2, 9.5, 11.5, 15.0, 19.0, 23.5, 27.0, 30.5, 33.0,
         36.5, 40.5, 44.5, 48.5, 51.5, 53.8, 58.5: titles >= 64 px and readable at 360 px wide, UI text >= 26 px
         in punch-ins, no Link button, no sharing UI.
