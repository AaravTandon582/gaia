# GAIA presentation package

Open **gaia-pitch.html** in Chrome or another modern browser. It contains all
images, the measured anomaly chart, and the 30-second demo video in one file.
No server or internet connection is required for the presentation itself.

- **gaia-pitch.html**: nine-slide, three-minute pitch plus three technical backup
  slides. Arrow keys or swipe navigate. N shows speaker notes. F enters full
  screen. B blanks the screen. Q&A jumps to the backup slides. The demo button
  on slide 3 plays the embedded recording with optional captions.
- **gaia-pitch.pdf**: static 12-page copy for sharing or submission. The PDF
  excludes speaker notes and video playback. Use the browser deck to present.
- **pitch-script.md**: timed speaking script, questions, and source references.
- **gaia-demo-30s.mp4**: 30-second recording of the real local production app,
  H.264, 1440 × 1000. No voice-over. Captions: gaia-demo-30s.srt.

The editable source is `scripts/presentation/deck.html`. Run
`node scripts/presentation/build.mjs` from the repository root to rebuild the
self-contained deck and speaker script. The chart uses all monthly scores in
`reports/demo-rehearsal.json`. The PDF was exported from Chrome and visually
reviewed. This release includes HTML and PDF, not PowerPoint.

For the live demo, run `./scripts/demo.sh` from the repository root and open
http://127.0.0.1:3000/dashboard. The launcher uses the production build and starts
missing services. Map tiles need internet access. Reuse the embedded recording
if the live venue connection is unreliable.

## Image credits

Earth photograph: NASA / Apollo 17,
https://www.nasa.gov/image-article/blue-marble-view-from-apollo-17/.
Amazon image: NASA/JPL-Caltech, EMIT, June 30, 2024,
https://science.nasa.gov/photojournal/nasas-emit-scans-the-amazon-river-in-northern-brazil/.
These images provide visual context and are not the time-series inputs.
Application screenshots and the recording are from GAIA.

## Scientific scope

The LSTM combines 12 features across five regions. Full-period scores include
training observations and do not establish independent detection accuracy.
PCMCI/TE are statistical diagnostics. Complete water-balance inputs remain
absent. Public deployment remains intentionally skipped. The source repository
has a local release commit but no configured remote.
