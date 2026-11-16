# A Page, while it is being made

The README gallery preserves the existing ivory/sage three-phone showcase and adds
three moments from one synthetic Page. These are real browser captures of the
existing [canvas](../../packages/renderer/canvas.tsx) and
[work renderer](../../server/page_work.py), not native iOS or Messages screenshots.
The decorative phone frames are presentation only. Aster is a synthetic agent name.

1. **Work begins:** the sticky status names the agent, shows its note, and lists
   finished/pending work. Existing Page content stays readable.
2. **New details arrive:** a real saved revision changes “A shared table” to
   “Eight places, one shared table” and adds the finishing paragraph. Polling loads
   and hydrates that revision without navigation. The renderer highlights changed
   words/blocks and places Aster's caret at the end of the last changed text.
3. **Ready to enjoy:** setting `done` changes the status and hides the caret. The
   capture waits for transient highlights to finish fading; the content remains.

## Reproduce

From the repository root, use the same Node/Python/Chrome prerequisites as the main
README. No private data, transport, service, account, environment file or recipient
is needed. All runtime files stay in ignored `apps/web/build/working/`.

```sh
npm ci --ignore-scripts
npm run capture:working
python3 examples/working/verify.py
```

This builds the two real TSX revisions, serves them on a randomly assigned loopback
port, applies explicit fixture saves, waits for the renderer's actual polling and
DOM changes, and captures mobile (390 × 844 at 3×) and desktop (1440 × 1000 at 1×)
views. It also tests reduced motion, completion reload, no horizontal overflow,
status accessibility, cursor placement, browser errors, and external requests.
`CHROME_PATH` selects Chrome; CI uses `/usr/bin/google-chrome`.

The three mobile captures are composed at equal scale into
[`docs/images/working-states.png`](../../docs/images/working-states.png), 2700 × 2020,
under 1.5 MB, stripped to essential PNG chunks. Individual captures, extracted
visible text, and 390px/880px composition review copies stay in the ignored build
folder. Font/Chrome versions and real status timestamps can change pixels.

To watch the actual transitions yourself, run:

```sh
node examples/working/build.mjs
python3 examples/working/fixture.py start
python3 -m http.server 19480 --bind 127.0.0.1 --directory apps/web/build/working/build
```

Open `http://127.0.0.1:19480/studio.html`. In another terminal, from the repo root:

```sh
python3 examples/working/fixture.py reveal
python3 examples/working/fixture.py done
```

Allow each state to arrive before advancing. Working Pages poll every three seconds;
finished Pages poll every sixty seconds. Reload after `start` to restart a finished
demo immediately. The fixture is a single-writer demonstration, not an agent service.

## Supported API and boundaries

The existing `server/page_work.py` provides these Python functions:

- `new_record(previous, state, note=None, by=None, sections=None, lease_minutes=None)`
  creates status; `save(root, slug, record)` writes it to `src/<slug>/work.json`.
  Accepted states are `working`, `needs_input`, `done`, `failed`; `stalled` is derived
  after a working lease expires (15 minutes by default). A working heartbeat
  preserves `since`; a state change clears an omitted note.
- `block(slug, revision, record)` emits the status shell, CSS and live updater.
  Place it outside and before `#root` in the HTML. `record_edit(root, slug, old_html,
  new_html, by)` retains the previous HTML and identifies the revision's author.
- After saving the new HTML to `build/<slug>.html`, `sync(root, slug, record)` patches
  its status and writes `build/live/<slug>.json`. See the complete ordering in
  [`fixture.py`](fixture.py). The fixture uses fixed revision keys for its two
  versions; real integrations must change their revision key when content changes.

The live script supports the static files above, or the private library routes
`/v1/pages/<slug>/content`, `/live`, and `/previous` implemented by
[`server.py`](../../server/server.py). Those routes read generated files; they are
**not status-write endpoints**. The default `npm run build` builds only the form
and does not add the status shell. This gallery supplies that missing example wiring;
it does not replace the renderer, add a general authoring CLI, or change the API.

The cursor follows a saved content diff, not keystrokes or a remote mouse. Its name
flag folds after 3.2 seconds; visible highlights fade after a short delay. Reduced
motion removes animation. Local storage remembers what this browser has seen.
Content hydration runs trusted JavaScript; don't feed it untrusted Page sources.
No native app or iMessage behavior is established by these web tests.

See [verification and full-size QA captures](VERIFICATION.md).
