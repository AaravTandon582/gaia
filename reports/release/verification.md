# Final local release verification

Date: 2026-11-15, America/Los_Angeles.

## Changes completed

- Preserved and committed the earlier backend, data loader, LSTM, frontend,
  demo, and documentation work.
- Fixed unfinished BOCPD date serialization and ineffective test mocks.
  Scouts now use standardized deseasonalized observations, preserve the monthly
  calendar, and check cancellation on every update. Candidate dates appear in
  the dashboard without changing the causal screening or significance rules.
- Hardened the unfinished regional water-balance helper. Complete inputs must
  use mm/month, identical spatial bounds, and identical consecutive monthly
  intervals. Missing values, gaps, duplicates, mismatched units or bounds remain
  unavailable. The dashboard explains missing total runoff and storage change.
- Added a production launcher that starts missing services and reuses healthy
  GAIA services. It refuses unrelated/unhealthy occupied ports.
- Rebuilt the pitch as 12 slides: nine main slides and three technical backups.
  HTML includes all imagery, a measured anomaly chart, speaker notes, captions,
  and the 30-second demo. PDF provides a static sharing copy.

## Verification

- Full backend suite: **195 passed, 9 subtests passed**. Two pre-existing
  dependency deprecation warnings remain.
- Frontend: **18 passed**, including live-backend integration and strengthened
  regime-date and missing-physics display assertions.
- Production build: passed, including TypeScript and static page generation.
- Demo rehearsal: five identical API result payloads each for Amazon and Sahel,
  returning 2 and 1 links. Both use the combined model's 19 flagged months.
- Final production Chrome: Amazon and Sahel scans complete. Candidate regime
  dates and missing physics inputs render. Zero page/console errors. Mobile
  document width equals its 390-pixel viewport. See `browser.json`.
- Launcher: verified starting both services from stopped state and reusing both
  on a second invocation without creating duplicate listeners.
- Deck: 12 slides, working navigation, notes, and offline embedded 30-second
  video. All slides rendered and reviewed. Exported PDF has 12 pages. Fixed a
  clipped anomaly peak by extending the chart scale to include every value.
- `git diff --check`: passed.

## Scope

This is a complete local demo release, not an independently validated climate
prediction system. All real water-balance checks remain unavailable until the
required compatible physical inputs exist. No held-out anomaly accuracy is
claimed. Public hosting remains intentionally skipped. No submission platform
or destination repository was supplied; no external submission was made.
