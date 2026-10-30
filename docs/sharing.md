# 4.4 Sharing a Link

`qdbd serve`'s address (`http://127.0.0.1:8765`) only works on your own machine. The safest way to show someone else the diagram is the page itself: `qdbd build` writes one self-contained HTML file ([2.4](getting-started.md#build-and-share)), which you send through your organisation's own channels, so the schema goes nowhere new.

A **link** puts the diagram on a third-party service, outside your organisation's control. Read the [disclaimer](#disclaimer) first: a client's schema may not be allowed there. There are three ways:

| | Option | Updates | Who can open it | Your machine needs to stay on |
|---|---|---|---|---|
| 1 | [`qdbd share`](#qdbd-share): a snapshot on a GitHub gist (off by default) | each time you run it again | anyone with the link | no |
| 2 | [`qdbd serve --read-only`](#live-read-only-link) + a tunnel | live, as you edit | anyone with the address, unless the tunnel has a login | yes |
| 3 | [GitHub Pages](github-action.md#publishing-to-github-pages) from CI | on every push | everyone, unless the site has [access control](github-action.md#publishing-to-github-pages) | no |

## `qdbd share` { #qdbd-share }

!!! warning "Off by default"
    `qdbd share` uploads the whole diagram, every table and column name, to GitHub, outside your organisation's control. Anyone with the link can open it. If the schema belongs to a client, their data agreements may not allow that. Sharing stays off until you turn it on, and turning it on means you accept the [disclaimer](#disclaimer):

    ```bash
    export QDBD_ALLOW_SHARE=1     # e.g. in ~/.zshrc; without it, qdbd share refuses
    ```

    In VS Code, the switch is the user setting **QuickDBD: Allow Sharing** (`quickdbd.allowSharing`). Until it's on, **Share as a Gist Link** is hidden.

```bash
qdbd share schema.txt
```

```text
Before you share: this uploads the diagram (every table and column name, type, key, relationship
…
Share 12 tables as a secret gist? [y/N] y
Shared 12 tables (secret gist https://gist.github.com/you/1a2b3c…)
Link: https://gistpreview.github.io/?1a2b3c…
  (if that doesn't load: https://gist.githack.com/you/1a2b3c…/raw/schema.html)
```

Send the **Link**. It opens the full interactive page: search, filter, details, path finder and tag legend.

- **Asks every time:** each share shows a short disclaimer and asks you to confirm. In a script, where there's no terminal to ask in, add `--yes` to accept it. In VS Code, a dialog asks instead.
- **Same link every time:** running `qdbd share` again for the same files updates the same gist, so the link keeps working with the new version. It can take a few minutes for viewers to see the update. `--new` makes a separate gist.
- **Secret by default:** the gist is unlisted. Anyone with the link can open it, but it isn't listed on your profile or in search. `--public` lists it.
- **A view, not just the page:** on the shared page, press **Link** to copy a URL that also opens your filter, selected table and zoom.
- **Needs the GitHub CLI:** install it (`brew install gh`) and run `gh auth login` once. The upload uses your GitHub account.
- **Also takes:** the same options as `build`: `-s/--exclude`, `--by-group`, `--diff-base`, `--layout`.

To stop sharing, delete the gist on GitHub.

## Live, read-only link { #live-read-only-link }

To let someone watch the diagram change as you edit, serve it read-only and put a tunnel in front of it.

!!! warning "Check your data policy first"
    A tunnel publishes the diagram on the internet. A quick tunnel's address has no login: anyone who has it can open the diagram while the tunnel runs. For a schema that isn't yours to publish, use a tunnel with a login in front, such as a named Cloudflare Tunnel behind [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/), or don't tunnel it. Using a tunnel means you accept the [disclaimer](#disclaimer).

For example, with [Cloudflare's quick tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/), which need no account:

```bash
brew install cloudflared
qdbd serve schema.txt --read-only                    # terminal 1
cloudflared tunnel --url http://127.0.0.1:8765       # terminal 2 (use the port qdbd printed): prints https://<random>.trycloudflare.com
```

With `--read-only`:

- the page has **no editor pane**, and viewers can't change anything: the server refuses every write;
- nothing is written to disk, not even the layout file;
- the page still **reloads live** when you save the schema in your editor.

!!! warning "Don't tunnel a normal `qdbd serve`"
    Without `--read-only`, anyone with the URL can edit your schema files through the editor pane. Always add `--read-only` before exposing it, and stop the tunnel when you're done.

## Disclaimer { #disclaimer }

qdbd and its VS Code extension are provided "as is", without warranties or conditions of any kind, under the [Apache License 2.0](https://github.com/MarkPhamm/quickdbd-cli/blob/main/LICENSE) (see its sections 7 and 8).

`qdbd share`, the extension's **Share as a Gist Link**, a tunnel to `qdbd serve` and a GitHub Pages site each send your schema to a third-party service (GitHub, or the tunnel's provider) that qdbd's authors don't operate or control. A diagram reveals how a system is designed even without any of its data: table and column names, types, keys, relationships, comments and notes can all be confidential.

By turning sharing on, or by publishing a diagram any other way, you confirm that:

- you have the right to publish the schema, and your organisation's policies and every agreement that covers it (for example, a client's confidentiality or data-processing terms) allow you to;
- you are responsible for who can open it: anyone who has a secret gist's link or a tunnel's address can open it, a public Pages site is open to everyone, and copies can outlive the gist, the tunnel or the site;
- to the extent the law allows, the authors and contributors of qdbd are not liable for any disclosure, loss, damage or claim that comes from using these features.

If you aren't sure the schema may leave your organisation, keep sharing off and send the HTML file through your own channels.
