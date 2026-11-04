# Review: qdbd demo, 60 s

## Calls made

- Silent: HeyGen wasn't signed in, and the agreed fallback was no music. The site plays the video muted anyway.
  To add a bed: `npx hyperframes auth login`, then `/media-use` bgm ("calm minimal tech pulse, 100-110 bpm"), as an `<audio>` on the root with a 0.4 s fade-in and a 1.5 s fade-out.
- The hook is a real zoom from one readable table out to all 200 tables. The plan's title over a dimmed still was a banned default.
- "And more" is the real export button clicks, then the diff build. There are no three cards in a row and no PR-comment card.
- The write and terminal shots typeset real text: `shop.txt`, `qdbd convert` and `qdbd build` output, saved verbatim by `videos/capture/record.py`.
- Footage is recorded at 2880 x 1800: CDP screencast with `--force-device-scale-factor=2`, because the screencast ignores emulated DPR.

## Measured vs looked at

- Measured: `hyperframes check` passes; the render is 60.0 s, 1920 x 1080, 30 fps; the web copy is about 6.6 MB (CRF 25).
- Looked at: a 26-moment contact sheet, the board stills, the phone sheet (titles readable at 360 px), and the seam strips.
- Not checked by a person: motion feel at full speed. No sound to check.

## Weakest shot and what more time would buy

- The VS Code establishing shot (42-44.5 s) is small on a phone. A punch-in on the diagram as it follows the cursor would help.
- The hook plate is sparse once settled. A recording that stops zooming out earlier would fill it.

## Warnings kept on purpose

- `line_unread` on the editor and terminal lines: code is texture there; the titles carry the read.
- `nested_media_start_basis_ambiguous` on the VS Code trims: their `data-start` is local, as intended.
- `film_silent`: see above.

## Second pass

- The first hook zoom was a wheel recording. Each wheel tick jumped the zoom 6%, and Chrome stalled repainting 200
  tables at 4K, so half the zoom played at about 15 fps. The hook is now captured frame by frame through the viewer's own
  `#z=&c=` hash: an eased zoom with every frame unique at 30 fps. The plate settles after the zoom lands, with no
  counter-zoom.
- Moves are faster: camera 0.42 s on power3.inOut, whips 0.26 s in and 0.16 s out, windows land in 0.3 s. The build
  scene loses its dead second before the zoom-through.
- The film is now 58.2 s: the hook is 6.2 s and the build 4.0 s. Scenes from build on start earlier than the times in
  SPEC.md and STORYBOARD.md (0.8 s for build, 1.8 s for every scene after it).
