# Pitch deck (#66)

Source: `slides.md` ([Slidev](https://sli.dev)). Speaker notes are the HTML comment at the end of each slide (about 670 words, roughly 4:30 min at a normal pace).

| File | Use |
|---|---|
| `GroundIQ-pitch.pdf` | Submission and presenting. Fonts are embedded. |
| `GroundIQ-pitch.pptx` | PowerPoint copy with speaker notes. Each slide is one image. |

```sh
cd pitch
npm ci
npx playwright install chromium   # once, for the export
npm run dev                        # presenter mode at http://localhost:3030/presenter
npm run export                     # rebuilds the PDF and PPTX
```

Why the PPTX text can't be edited: Slidev 53.1 also has `--format pptx-editable`. When we tried it, PowerPoint repeated the word at every line break (e.g. "machen machen"). To change the text, edit `slides.md` and export again.

## Sources of the content

- Figures: FMI & PlanGrid, *Construction Disconnected* (2018); FMI & Autodesk, *Harnessing the Data Advantage in Construction* (2021). We checked them against the published reports. We left out the "5–12 % rework" range from PLAN §1 because the newer contractor data from Love et al. contradicts it.
- Screenshots: copies of `design/screenshots-55/` (#55). All data in them is synthetic.
- Plan of apartment 3B: `public/plan-3b.svg`. It comes straight from `cad/plans/A-103_RevC.dxf` and `A-103_RevD.dxf`. To regenerate it: `python pitch/scripts/plan_3b_svg.py > pitch/public/plan-3b.svg` (needs `ezdxf`, like the backend).
- Hero timeline and the learning case: `backend/demo/hero-scenario.json` and `docs/REPLAY.md`.
