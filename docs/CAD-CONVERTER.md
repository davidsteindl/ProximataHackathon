# CAD converter decision (Issue #4)

LibreDWG is selected as a standalone command-line process. ODA is not used.
The source build uses the native Debian architecture (ARM64 or amd64), without
forcing x64 emulation. Version 0.13.3 is pinned for reproducible behavior.

## Run

From the repository root in PowerShell:

```powershell
New-Item -ItemType Directory -Force cad-data
Copy-Item <path-to-input.dwg> cad-data/input.dwg
docker compose -f compose.cad.yaml --profile cad build cad-converter
docker compose -f compose.cad.yaml run --rm cad-converter -o output.dxf input.dwg
```

The result is `cad-data/output.dxf`. Use a fresh output filename: existing files
are not overwritten by default. The converter has no network access at runtime.
This optional Compose job does not start the API or database. It can also be
combined with the main stack using `-f compose.yaml -f compose.cad.yaml`.

Direct DXF input remains the fallback: pass existing DXF files straight to the
future CAD extraction pipeline (#16), skipping this converter. No ingestion or
geometry endpoint is introduced here.

## Licence and boundaries

LibreDWG is GPL-3.0-or-later. SiteMind communicates only through command-line
arguments and files; it never imports or links the library. The separate runtime
image contains no SiteMind application code. Before distributing converter
images, supply the applicable GPL notices, licence and corresponding source.
See COMPLIANCE.md.

Sources:
- https://www.gnu.org/software/libredwg/
- https://www.gnu.org/software/libredwg/manual/html_node/Programs.html

## Smoke test

Run from the repository root: `pwsh -File tools/libredwg/smoke.ps1 -DwgPath <sample.dwg>`. The script requires successful conversion and checks DXF section and EOF markers. Local test artifacts stay in ignored cad-data; source DWGs are never committed.

## Verified sample and limits

On Windows ARM64 with Docker's native aarch64 Linux engine, LibreDWG 0.13.3
converted the supplied local sample (DWG signature AC1021 / AutoCAD 2007).
The process returned zero and the output contained SECTION, ENTITIES and EOF.
LibreDWG reported `Invalid num_pages 0` and unknown/unstable AEC classes,
skipping unsupported objects. This verifies conversion, not lossless geometry
or AEC semantics. Use a trusted DXF export when these objects matter.
The amd64 build path uses the same source and Dockerfile but was not run locally.
No private sample is bundled; the smoke script accepts an external DWG path.
