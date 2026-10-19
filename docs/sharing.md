# 4.4 Sharing a Link

`qdbd serve`'s address (`http://127.0.0.1:8765`) only works on your own machine. To send someone a link instead of a file, you have three options:

| | Option | Updates | Your machine needs to stay on |
|---|---|---|---|
| 1 | [`qdbd share`](#qdbd-share): a snapshot on a GitHub gist | each time you run it again | no |
| 2 | [`qdbd serve --read-only`](#live-read-only-link) + a tunnel | live, as you edit | yes |
| 3 | [GitHub Pages](github-action.md#publishing-to-github-pages) from CI | on every push | no |

## `qdbd share` { #qdbd-share }

```bash
qdbd share schema.txt
```

```text
Shared 12 tables (secret gist https://gist.github.com/you/1a2b3c…)
Link: https://gistpreview.github.io/?1a2b3c…
  (if that doesn't load: https://gist.githack.com/you/1a2b3c…/raw/schema.html)
```

Send the **Link**. It opens the full interactive page: search, filter, details, path finder and tag legend.

- **Same link every time:** running `qdbd share` again for the same files updates the same gist, so the link keeps working with the new version. It can take a few minutes for viewers to see the update. `--new` makes a separate gist.
- **Secret by default:** the gist is unlisted. Anyone with the link can open it, but it isn't listed on your profile or in search. `--public` lists it.
- **A view, not just the page:** on the shared page, press **Link** to copy a URL that also opens your filter, selected table and zoom.
- **Needs the GitHub CLI:** install it (`brew install gh`) and run `gh auth login` once. The upload uses your GitHub account.
- **Also takes:** the same options as `build`: `-s/--exclude`, `--by-group`, `--diff-base`, `--layout`.

To stop sharing, delete the gist on GitHub.

## Live, read-only link { #live-read-only-link }

To let someone watch the diagram change as you edit, serve it read-only and put a tunnel in front of it. For example, with [Cloudflare's quick tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/), which need no account:

```bash
brew install cloudflared
qdbd serve schema.txt --read-only                    # terminal 1
cloudflared tunnel --url http://127.0.0.1:8765       # terminal 2: prints https://<random>.trycloudflare.com
```

With `--read-only`:

- the page has **no editor pane**, and viewers can't change anything: the server refuses every write;
- nothing is written to disk, not even the layout file;
- the page still **reloads live** when you save the schema in your editor.

!!! warning "Don't tunnel a normal `qdbd serve`"
    Without `--read-only`, anyone with the URL can edit your schema files through the editor pane. Always add `--read-only` before exposing it, and stop the tunnel when you're done.
