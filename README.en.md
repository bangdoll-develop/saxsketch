# SaxSketch

A local web app for parametrically designing wind-instrument mouthpieces and
accessories, simulating their acoustics while you design, and exporting
print-ready data (STL / STEP / 3MF), a bill of materials and a specification
sheet in one pass.

**The project language is Japanese.** This page is the English entry point;
the UI, the generated documents and the engineering notes under `docs/` and
`cad/` are in Japanese. See [README.md](README.md) for the full documentation.

> ## ⚠ This tool designs a part that goes in your mouth
>
> Use a food-contact-compliant material. Post-cure and wash resin prints
> thoroughly — **uncured resin is a skin sensitiser**. PLA deforms at about
> 55 °C, so no boiling water. **Inspect every print for cracks, chips and
> sharp edges before putting it in your mouth. Printed parts break.**
> Dimensions and acoustic figures are estimates; nothing here guarantees that
> what you print is safe, durable or fit for purpose.
> → **[SAFETY.md](SAFETY.md)** (including product-liability notes if you sell).

## What it does today

**Works — the mouthpiece / ligature / reed "set".** Three sizes (soprano,
alto, tenor). Parametric design with a live 3D view and a drag-to-edit cross
section, design-time acoustic simulation, a workflow for measuring a printed
part and feeding the numbers back into the design, and export to STL / STEP /
3MF plus a spec sheet, a BOM and a submission ZIP. The mouthpiece's 33
parameters have measured limits behind them.

**Does not work — the neck and body are shapes, not instruments.**

| | |
|---|---|
| Printing the body / neck | **Not possible.** Arc length is 502–1378 mm; splitting for the build volume is not implemented |
| Body acoustics | **Not connected.** The bell flare is unmeasured in all three sizes; connecting it would move the lowest resonance by +38…+106 cents |
| Tone-hole positions | A zeroth-order placeholder rule — neither measured nor solved. Finger reach allows only 4 / 3 / 2 holes (soprano / alto / tenor) |
| Octave key | No mechanism |
| Reed & ligature limits | 30 parameters still unclassified; only the mouthpiece's 33 are done |

## Requirements and platforms

| Platform | Status |
|---|---|
| **WSL2 (Ubuntu)** | **The configuration this is actually developed and run on** |
| Linux | Should work; CI runs on Ubuntu |
| **Windows (native)** | **Broken when Smart App Control / WDAC is on** — see below |
| macOS | Untested |

Windows 11's Smart App Control blocks the OCCT DLL that `build123d` loads.
`pip install` succeeds but importing fails with
`ImportError: DLL load failed while importing OCP`, and because that import is
on the server's startup path, **the whole app fails to start**. This is an OS
policy, not a packaging problem. Turn SAC off, or use WSL2.

Needs Python ≥ 3.11 and Node ≥ 20.

## Install and run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
saxsketch          # or: python -m saxsketch.server.app
```

Then open <http://127.0.0.1:8712>.

On WSL2, `scripts/wsl_sync.sh --deps` does all of the above against a working
copy under `~/mp_design`, and `scripts/wsl_run.sh` starts the server.

> **Local only.** There is no authentication. The API reads and writes
> arbitrary absolute paths and launches external tools — that is the design,
> because the only entry point is the OS file dialog and the user picks the
> path. So it refuses to bind anywhere but loopback: setting `SAX_HOST` to a
> non-loopback address **aborts startup** unless you also set
> `SAX_ALLOW_REMOTE=1`. `Host` and `Sec-Fetch-Site` are checked so that other
> web pages cannot drive it.

Optional: `pip install -e ".[acoustics]"` adds OpenWind (GPL-3, **not
bundled**) for physical-model sound synthesis. Without it the built-in
transfer-matrix solver is used and impedance still works.

## License and provenance

- Code is **Apache-2.0** — see [LICENSE](LICENSE).
- **The mouthpiece's base geometry was measured from someone else's model**,
  published under CC BY-NC-SA. Attribution, the exact provenance, and what the
  non-commercial clause means for this project are in [NOTICE](NOTICE) and
  [cad/windycity/ATTRIBUTION.md](cad/windycity/ATTRIBUTION.md). The model files
  themselves are not in this repository; five plotted figures derived from the
  mesh are marked CC BY-NC-SA rather than Apache-2.0.
- Third-party software is listed in [THIRD-PARTY.md](THIRD-PARTY.md).
- Product and brand names are trademarks of their respective owners, used only
  to identify the specimens that were measured. No affiliation or endorsement.
