# Production browser acceptance — 2026-11-15

Ran the built Next.js app with `next start` on port 3000 and the real FastAPI
backend on port 8000, using an isolated headless Google Chrome session. The
app-provided browser host was unavailable; Playwright drove installed Chrome.
No app dependencies were added. Temporary verification/CLI tools live outside
the repository; no hosting login or deployment was performed.

## Observed checks

- **Amazon normal completion:** 2 graph links, 19 combined-model anomaly bands,
  and a closed socket after the result. Server logs show scan start and done.
- **Switch during a running scan:** Amazon socket closed with no result; Sahel
  completed with 1 link. Server logs show client disconnected, scan cancelled,
  and connection closed for the interrupted scan.
- **Refresh during a running scan:** pagehide called `WebSocket.close()` from
  OPEN (1), leaving CLOSING (2) before navigation. Backend logs confirm disconnect,
  cancellation and connection closed; the refreshed page has no stale graph.
  Chrome's Playwright socket-close callback is not reliably delivered for a
  discarded document, so this check uses the observed close call plus server logs.
- **Cancel button:** no remaining graph; a new scan can run.
- **Invalid date range and retry:** the 24-month error is displayed, then a valid
  request succeeds. Arctic's legitimate 0-link result has an explicit empty state.
- **Detail view:** edge selection shows strength, lag, raw p, corrected q, TE,
  wavelet display, and the raw chart with anomaly bands.
- **Console/network:** zero page errors, console errors, or failed requests in
  the production acceptance session. Map tiles loaded successfully.
- **Desktop:** 1440-pixel viewport, document width 1440; no page overflow.
- **Mobile:** 390-pixel viewport, document width 390; map height 380 and 19 bands.
  The summary table scrolls independently (332-pixel viewport, 560-pixel content).

The visual check found cramped summary columns in the 350-pixel detail panel.
Added cell spacing and an accessible horizontal scroll container so numeric
columns can be read without clipping or running together.

Evidence: [machine-readable checks](browser/acceptance.json),
[backend lifecycle log](browser/backend-lifecycle.log),
[desktop scan](browser/amazon-desktop.png),
[detail view](browser/amazon-detail.png),
[anomaly chart](browser/amazon-anomalies.png),
[mobile scan](browser/sahel-mobile.png).

## Release materials

Recorded a real 30-second MP4 and created an editable five-slide HTML pitch with
speaker notes and a separate rehearsal script in `deliverables/`. All five slides
were rendered and inspected; a heading/image overlap found on slide 3 was fixed.
The MP4 duration and codec were verified with ffprobe, and a recorded frame was
inspected. Public deployment was skipped at the user's request; no public URL
or cloud deployment validation is claimed.

Frontend regression suite: 18 passed. Production build: passed, including
TypeScript and static page generation. Backend verification is recorded in
`backend-completion.md`.
