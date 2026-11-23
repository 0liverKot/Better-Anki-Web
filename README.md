# Better Anki Web

A self-hosted web version of Anki that you can use from any browser (at the library, on a
borrowed laptop, on your phone) without Anki desktop or AnkiConnect running anywhere.

## How it works

```
Browser ──HTTPS──> Better Anki Web (FastAPI + official `anki` package) ──sync──> AnkiWeb
                          │                                                        ▲
                   collection.anki2 + media                    Anki desktop / AnkiDroid / iOS
```

Anki desktop is a GUI on top of Anki's Rust core, which is published on PyPI as the official
[`anki`](https://pypi.org/project/anki/) package. The server uses it directly: it opens its own
copy of your collection and syncs it with AnkiWeb, acting as one more Anki client. It schedules
cards with the same engine as desktop (including FSRS and your deck options), and your phone and
desktop keep syncing with AnkiWeb as usual.

- **First connect:** your collection and media are downloaded from AnkiWeb.
- **While you study:** changes are pushed about a minute after you stop, and when you leave
  or hide the tab.
- **Changes from other devices** are pulled when you open the app, and checked for every
  10 minutes.
- **One-way syncs** (for example after a note type change) are never done silently, except the
  very first download into an empty server. The Settings page asks which copy to keep.
- **Self-hosted sync server:** you can switch from AnkiWeb at any time. On the Settings page,
  choose "Use a self-hosted sync server", or set `BAW_SYNC_ENDPOINT`.

## Features

- Deck list with new, learning and due counts, and collapsible subdecks
- Reviewer with Again/Hard/Good/Easy, next-interval labels, undo, and keyboard shortcuts
- Cards render with your note types' own HTML, CSS and JavaScript, and support MathJax,
  images, audio/video (`[sound:...]`), text-to-speech tags and type-in-the-answer
- Add cards with any note type: cloze shortcut, paste/drop images and audio, tag suggestions,
  sticky fields, and duplicate warnings
- Editor shortcuts match Anki desktop:
  - Ctrl+, / Ctrl+. for bullet / numbered lists, and Ctrl+Shift+, / . to outdent / indent.
  - Ctrl+M then M / E / C for MathJax inline `\(…\)` / block `\[…\]` / chemistry.
    As in Anki, formulas show rendered in a box while editing; click one to edit its TeX
    with a live preview. Fields are still stored in Anki's normal `\(…\)` form.
  - Ctrl+Shift+C for cloze, and Ctrl+Shift+X to edit a field's HTML.
  - (Anki's LaTeX shortcuts aren't available: browsers reserve Ctrl+T.)
- Search your cards across all decks or one deck (subdecks included):
  - Plain words match the front or back, with matches highlighted.
  - Anki's search syntax also works (`"exact phrase"`, `-word`, `front:x`, `tag:x`, `is:due`).
  - Click a result to preview its cards as they appear when reviewing.
  - Edit a note from its preview: fields, tags, and which deck its cards are in. Editing uses
    the same editor as adding cards (`NoteEditor.svelte`), so editor features work in both.
- Works well on phones, with light and dark mode
- Single-user password login

Not supported yet: image occlusion cards (adding or editing), changing a note's type,
statistics, and deck options.

## Run it locally

```bash
./dev.sh
```

Then open http://localhost:5173 and log in with the password `dev`. The script installs
dependencies on its first run, then starts the backend (port 8000) and frontend (port 5173),
and both reload when you edit code. Ctrl+C stops both.

To use your own password, put `BAW_PASSWORD=...` in `backend/.env` (gitignored). A plain
password is fine locally; the bcrypt hash is for deployments.

Data is stored in `backend/data/` (gitignored). It holds your collection, media, the AnkiWeb
sync key and the cookie-signing secret.

## Deploy (Docker + automatic HTTPS)

You need a small VPS (1 GB RAM is plenty) and a domain pointing at it.

```bash
cp .env.example .env
docker compose run --rm app python -m app.hash_password   # paste the hash into .env
nano .env                                                  # set DOMAIN too
docker compose up -d
```

Then open `https://your-domain`, log in, and connect AnkiWeb on the Settings page.

Run exactly **one** app process. An Anki collection must not be opened by two processes, so
don't scale the `app` service or add uvicorn workers.

## Configuration

All settings are environment variables (or a `.env` file):

| Variable | Default | |
|---|---|---|
| `BAW_PASSWORD_HASH` | | bcrypt hash of the app password (recommended) |
| `BAW_PASSWORD` | | plain password, for local development |
| `BAW_DATA_DIR` | `data` | collection, media, sync key, secret |
| `BAW_SECRET_KEY` | generated | signs session cookies. If unset, one is generated and stored in the data dir |
| `BAW_COOKIE_SECURE` | `false` | set `true` behind HTTPS (docker-compose does this) |
| `BAW_SESSION_DAYS` | `30` | how long a login lasts |
| `BAW_SYNC_ENDPOINT` | AnkiWeb | default sync server for new connections |
| `BAW_AUTOSYNC` | `true` | background syncing |
| `BAW_AUTOSYNC_IDLE_SECONDS` | `60` | push local changes after this much idle time |
| `BAW_AUTOSYNC_POLL_SECONDS` | `600` | check for changes from other devices this often |
| `BAW_MAX_UPLOAD_MB` | `50` | media upload limit |

## Security notes

- **AnkiWeb password:** it's used once to get a sync key and is never stored. The key is kept
  in `data/sync_auth.json` (mode 600). "Disconnect" deletes it.
- **Card scripts** run in a sandboxed iframe with no access to the app's cookies or API, so a
  shared deck's JavaScript can't act on your account.
- **Editing fields with scripts:** a field containing scripts, embedded content or event
  handlers opens as HTML source rather than in the rich editor, so its code never runs in the
  app, and saving keeps it exactly as it was.
- **Media URLs** carry a secret token, because the sandboxed card frame can't send cookies.
  Media is served with `Content-Security-Policy: sandbox`.
- **Writes and logins:** every write needs a custom header (CSRF protection), and logins are
  rate-limited.

## Development

```bash
cd backend && .venv/bin/python -m pytest      # includes real syncs against a local Anki sync server
cd frontend && npm run check                  # svelte-check / TypeScript
```

Project layout:

```
backend/app/
  main.py         app factory, error handling, serves the built frontend
  collection.py   the single open Collection and its lock
  sync.py         AnkiWeb sync, full-sync handling, background autosync
  rendering.py    card HTML for the browser (media, audio buttons, type-in-the-answer)
  auth.py         password login, session cookie, CSRF, rate limit
  routes/         decks, review, notes (add), media, sync, auth
frontend/src/
  routes/         Decks, Review, Add, Settings, Login pages
  lib/cardFrame.ts  sandboxed card iframe and its audio/keyboard bridge
```

The `anki` package version is pinned on purpose. Its Python API changes between releases, and
AnkiWeb eventually stops accepting old clients, so upgrade it deliberately and run the tests.
