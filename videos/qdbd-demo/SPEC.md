# qdbd demo: spec

GOAL:    a data engineer watching muted on qdbd.dev gets "my schema is a text file in git, it becomes a diagram I can
         use, and it already knows my dbt docs", sees one real dbt project go from text to PR, and leaves with
         `pipx install quickdbd-cli`.
OUTPUT:  HyperFrames, 1920 x 1080, 30 fps, H.264, <= 8 MB for the web copy.
TIME:    75 s x 30 = 2250 frames. Silent: the site plays it muted.
LOOK:    the qdbd.dev blueprint sheet, the brand's own material.
         ground paper #f2f2ee with a 96 px major grid at rgba(21,24,30,.07) and a 24 px minor grid at .035;
         ink #15181e; secondary ink #4a505b; one accent #2f5bea, on one word per shot at most, the wordmark and the CTA;
         titles Geist 600, 64 px, tracking -0.03em, left-aligned at x = 96, baseline zone y 64-150;
         code and terminal Geist Mono 400, 29-36 px; the product's own UI keeps its own fonts (Inter).
         browser windows: sheet #fafaf7, chrome bar 44 px, 1728 px wide (90% of the frame), radius 16 px;
         editor and terminal windows ink #15181e with paper text. VS Code world: ground #181818 (Dark Modern).
         no grain, no vignette, no glow.
OBJECTS: the real viewer and the real VS Code on github.com/MarkPhamm/qdbd-dbt-demo (recorded at 2880 x 1800 by
         videos/capture/record.py from pinned commits), real terminal output, the real erd/conformed.txt, the qdbd
         mark and wordmark.
MOTION:  arrive expo.out 0.26-0.32 s; camera power3.inOut 0.6-0.7 s; footage at its real speed (the yml typing
         at 1.6x); exits power3.in 0.16 s; words blur 6 px -> 0
         in 0.13 s, 0.067 s apart, no translate; titles dead still once landed; punch-ins 1.7-2.3x so UI text >= 26 px.
SHOTS:
  01 hook     0.0-6.2   unchanged: a real zoom from one readable table out to all 200; "Database diagrams that live
                        in git", "Readable at 200+ tables" (200+ in accent)
  02 text     6.2-13.7  erd/conformed.txt arrives line by line; the editor becomes a terminal: `qdbd build erd -o
                        erd.html`, its real output; zoom through erd.html; "Text in, one HTML page out"
  03 explore 13.7-28.5  the browser lands out of the zoom; search dim_customer, select it (the facts stay lit), click
                        a line (the card's sentence and JOIN), type `group:lounge_reviews`; "Find any table",
                        "Click: its neighbours stay lit", "Click a line, get the JOIN", "Filter like dbt: ..."
  04 dbt     28.5-40.7  the editor again, line 5 `# @dbt: ..` lit; whip to the browser: dim_customer's header
                        tooltip (yml description, then the file's comment), its details panel, the pii chip filtering
                        to tag:pii; "Already documented in dbt?", "Your yml docs, on the diagram", "Tags come along too"
  05 vscode  40.7-61.3  colour flood into VS Code: the preview follows the cursor; `has_shower` typed only in the ERD
                        gets the dbt drift warning (hover); added to the yml; back in the .txt the warning is gone and
                        the preview shows has_shower as boolean with its description; "In VS Code and Cursor",
                        "Drift shows up as a warning", "Fix it in the yml", "The diagram follows"
  06 more    61.3-69.0  the qa branch's diff ("1 new · 2 changed", Show changes: dim_cabin NEW), then the export
                        buttons clicked; "Every PR shows what changed", "Export PNG, SVG, draw.io"
  07 end     69.0-75.0  the mark performed, the wordmark, `pipx install quickdbd-cli`, qdbd.dev · VS Code
                        Marketplace · Open VSX, "Example dbt project: github.com/MarkPhamm/qdbd-dbt-demo"
BANNED:  the skill's defaults; anything about sharing (`qdbd share`, Share menus, the viewer's Link button, tunnels);
         emoji or icon glyphs in our own text; a title over a dimmed screenshot; three cards in a row; invented UI;
         a window's chrome bar cut in half by a punch-in.
QA:      the beat sheet, every seam and the phone sheet from `snapshot --review`: titles
         >= 64 px and readable at 360 px wide, UI text >= 26 px in punch-ins, no Link button, no sharing UI.
