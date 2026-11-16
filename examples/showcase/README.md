# Mobile web showcase

Synthetic workshop examples, authored with the real `grok/canvas` components in
this repository. No private service, account, library, transport or user data is
used. The form runs locally in the browser and does not save an RSVP remotely.

From the repository root, with Node 22+ and Chrome installed:

```sh
npm ci --ignore-scripts
node examples/showcase/render.mjs
```

Set `CHROME_PATH` for another Chrome installation. The script bundles and hydrates
the three TSX sources with esbuild and the unchanged canvas stylesheet, captures
390 × 844 CSS-pixel viewports at 3×, tests both form choices, and composes the
screens at equal scale in decorative phone frames. No browser chrome or native
app UI is simulated. Screenshot intermediates and 880px / 390px review copies
are in ignored `apps/web/build/showcase/`; the published PNG is
`docs/images/showcase.png` (2700 × 2020). PNG metadata is removed and raster data
is losslessly compressed. Output is rejected above 1.5 MB. Chrome and system
font versions can affect pixels across machines.

The composition is legible as a visual overview at phone width; enlarge it to
read body text. The source examples remain the accessible text equivalents.
See [the pre-implementation visual brief](DESIGN.md) and [approval](APPROVAL.md).
