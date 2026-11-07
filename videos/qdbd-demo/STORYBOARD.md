---
format: 1920x1080
duration: 60.2s
message: "Your schema as a text file in git becomes a diagram you can use, and it already knows your dbt docs"
arc: Hook → Text → Explore → dbt docs → VS Code drift → PR diff → End card
audience: data and analytics engineers, on qdbd.dev (muted autoplay)
---

## Frame 1: Hook (0-6.2s)
- src: compositions/hook.html
- scene: Real zoom from one readable table out to all 200 (examples/synthetic).
- reads: "Database diagrams that live in git"; "Readable at 200+ tables"

## Frame 2: Text (6.2-11.2s)
- src: compositions/text.html
- scene: erd/conformed.txt from qdbd-dbt-demo arrives line by line; the editor becomes a terminal; `qdbd build erd -o erd.html` and its real output; zoom through erd.html.
- reads: "Text in, one HTML page out"

## Frame 3: Explore (11.2-24.7s)
- src: compositions/explore.html (footage explore.mp4)
- scene: Search dim_customer and select it: the four facts that join it stay lit. Click a line: the card's sentence and JOIN. Type the filter group:lounge_reviews.
- reads: "Find any table"; "Click: its neighbours stay lit"; "Click a line, get the JOIN"; "Filter like dbt: group:lounge_reviews"

## Frame 4: dbt docs (24.7-34.2s)
- src: compositions/dbt.html (footage dbt.mp4)
- scene: The editor again, line 5 `# @dbt: ..` lit. Whip to the browser: dim_customer's header tooltip (the yml description, then the file's own comment), the details panel with column docs and pii chips, then the pii legend chip filtering to tag:pii.
- reads: "Already documented in dbt?"; "Your yml docs, on the diagram"; "Tags come along too"

## Frame 5: VS Code drift (34.2-49.7s)
- src: compositions/vscode.html (footage vscode.mp4, five cuts of one take)
- scene: The preview follows the cursor to fct_lounge_review. `has_shower` typed under staff_service gets a squiggle; the hover reads "dbt: column 'has_shower' is not in the yml for 'fct_lounge_review'". It is added to _lounge_reviews__models.yml and saved; back in the .txt the warning is gone and the preview's details show has_shower as boolean with its description.
- reads: "In VS Code and Cursor"; "Drift shows up as a warning"; "Fix it in the yml"; "The diagram follows"

## Frame 6: PR diff and exports (49.7-55.2s)
- src: compositions/more.html (footage diff.mp4, exports.mp4)
- scene: The qa branch built with --diff-base main: "Changes since main: 1 new · 2 changed"; Show changes narrows to dim_cabin (NEW) and the facts. Then the SVG, PNG and draw.io buttons clicked.
- reads: "Every PR shows what changed"; "Export PNG, SVG, draw.io"

## Frame 7: End card (55.2-60.2s)
- src: compositions/end.html
- scene: The mark performed, the wordmark wipes in, the command, the links, the example repo.
- reads: "pipx install quickdbd-cli"; "qdbd.dev · VS Code Marketplace · Open VSX"; "Example dbt project: github.com/MarkPhamm/qdbd-dbt-demo"
