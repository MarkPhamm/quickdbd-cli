# Review: qdbd demo, 75 s (0.6.0 redo)

## Calls made

- One film, the same slot on qdbd.dev. Storyline 1 of STORYLINES.md: after the unchanged 200-table hook, one real dbt
  project (github.com/MarkPhamm/qdbd-dbt-demo, pinned commits) goes from text to PR. Not built: "result first" and
  "dbt as the hook".
- Less terminal, more UI: write + build + open (13 s) became one 5 s text scene. The serve-only "type a Review
  table" scene and the QuickDBD/DBML tab flip are gone; VS Code carries live editing now.
- The dbt yml feature gets 25 s: the `# @dbt: ..` line, dim_customer's tooltip (yml description, then the file's
  comment), its details panel, tag:pii, then drift in VS Code (`has_shower` typed only in the ERD, fixed in the yml,
  the preview picks up its type and description), then the qa branch's dim_cabin in the PR diff.
- Silent, as before: the site plays it muted.
- Second pass, after the first cut felt fast: the film went from 60.2 s to 75 s. Footage plays at its real speed
  (only the 10 s of yml typing runs at 1.6x), titles hold longer, camera moves take 0.6 s instead of 0.42 s. The
  home page, the README, the extension README and the poster badge now say 75 seconds.
- The diff is now a clip of the real "Show changes" click, not a still. Its bar says "since main" because prep()
  points a local `main` at the pinned commit.
- The poster (docs/assets/img/demo-poster.jpg) is the hook frame at 3.8 s with the badge "Watch the 75-second demo",
  rebuilt in the old poster's style.
- The README GIF (docs/assets/img/demo.gif) is new: raw explore + dbt footage, 760 x 475, 10 fps, 13.5 s, 974 KB.

## Measured vs looked at

- Measured: `hyperframes check` ok; the render is 75.0 s, 1920 x 1080, 30 fps; the web copy is 7.6 MB (CRF 26).
- Measured in Chrome: the home page plays the new file (duration 75 s); the Skytrax demo, the docs iframe and the
  gallery card load.
- Looked at: the beat sheet, all six seams, the phone sheet (titles readable at 360 px) and 15 full-size frames at
  the QA times in SPEC.md.
- Not checked by a person: motion feel at full speed.

## Weakest shot and what more time would buy

- The first 0.85 s of the VS Code scene shows the whole window at 1x, small on a phone, before the punch-in.
- The cursor in the VS Code clip stops at the editor's edge while the preview scrolls: the injected cursor does not
  see mouse events inside the preview iframe.
- "The diagram follows" opens on the whole window for 2.9 s before the punch on has_shower; a tighter cut would land
  sooner.

## Warnings kept on purpose

- `line_unread` on the editor and terminal lines: code is texture there; the titles carry the read.
- `nested_media_start_basis_ambiguous` on the cut clips (dbt, vscode, more): their `data-start` is local, as intended.
- `film_silent`: see above.
