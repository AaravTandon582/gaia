# GAIA presentation script

Nine-slide, three-minute pitch followed by three technical backup slides.
Use N for notes, F for full screen, arrow keys to advance, and Q&A for backup slides.
The embedded 30-second demo is optional and adds time if played.

## 1. GAIA

0:00–0:15. A changing climate leaves signals across rainfall, soil moisture, and evaporation. GAIA gives us a place to investigate those signals together. It brings real NASA observations into a map-based workflow, with the evidence visible at every step. Image: NASA / Apollo 17, https://www.nasa.gov/image-article/blue-marble-view-from-apollo-17/. Product scope: docs/project-summary.md.

## 2. The investigation problem

0:15–0:35. A pair of curves can look related simply because both rise and fall with the seasons. Regional measurements also come from different products. The challenge is deciding which relationships deserve investigation after accounting for those patterns. GAIA combines screening with conditional lag tests and a separate information-transfer diagnostic. Evidence: reports/causal-audit.md. Image: NASA/JPL-Caltech, EMIT, June 30, 2024, https://science.nasa.gov/photojournal/nasas-emit-scans-the-amazon-river-in-northern-brazil/. This image provides context and is not an input to the GAIA demo.

## 3. The working application

0:35–0:55. Here is the application running. I select the Amazon Basin and a date range. Domain scouts inspect the available measurements, and the pipeline returns a graph of lagged statistical associations. I can inspect each link and return to the underlying observations. The short recording is embedded and works offline. Use it instead of this spoken walkthrough if the judging format allows extra time. Sources: backend/main.py, backend/agents/orchestrator.py, reports/release/browser.json. Screenshot: reports/release/dashboard.png. Recording: deliverables/gaia-demo-30s.mp4.

## 4. The Amazon result

0:55–1:15. Across 312 months, the strongest retained Amazon link connects precipitation to evapotranspiration one month later. Its partial correlation is about 0.388 and its corrected q-value is about one times ten to the minus ten. A separate transfer-entropy diagnostic also supports this link at the chosen cutoff. This is a candidate explanation conditional on the measured variables, and it does not establish physical causation. Source: reports/demo-rehearsal.json, scenarios.amazon.links. Effective regression samples are fewer than 312 because of lag trimming.

## 5. Agreement and uncertainty

1:15–1:40. Three links survive PCMCI’s false-discovery correction across our two demo regions. Transfer entropy supports only the Amazon one-month link at 0.05. The methods condition on different information, so disagreement matters. We display both results rather than deleting an inconvenient result or turning a statistical association into a causal claim. All values come from reports/demo-rehearsal.json. TE is an additional diagnostic and does not select the retained PCMCI graph.

## 6. The anomaly model

1:40–2:00. The LSTM adds another view: months that it reconstructs poorly. It flags 19 out of 312 months using a fixed cutoff derived from training data. These scores combine 12 features across five regions. They are retrospective, include training observations, and cannot be attributed to the selected region. They are prompts for investigation. Source: reports/demo-rehearsal.json, scenarios.amazon.anomalies. Cutoff: 0.2560639903. The chart shows every month, not a smoothed estimate.

## 7. Evidence checks

2:00–2:20. We tested a synthetic system with known relationships and recovered both designed links. In a separate artifact case, unrelated noise series shared a seasonal pattern and a trend. Removing those components reduced the detected links from six to zero. We also report the nonzero results in shifted real-data checks. This is evidence about specific failure modes, not a guarantee for every climate dataset. Source: reports/causal-audit.md, known-answer tests and null checks.

## 8. Current scope and next evidence

2:20–2:45. The local prototype now includes the complete scan workflow, anomaly display, and exploratory regime dates. The next scientific milestone is independent evaluation on unseen observations. Water-balance closure needs compatible total runoff and storage change, which are not available in the curated demos. Keeping those limits explicit makes the next experiment clear. Sources: reports/physics-inputs.md, backend/agents/scout.py, docs/project-summary.md.

## 9. Closing

2:45–3:00. GAIA makes Earth-system relationships easier to investigate. A region opens into measurements, candidate links, and explicit uncertainty. The next step is to test these candidates against independent evidence. Thank you. Image background: NASA / Apollo 17, https://www.nasa.gov/image-article/blue-marble-view-from-apollo-17/. The main pitch ends here. The remaining slides support questions.

## 10. Backup: analysis methods

Sources: backend/analysis/README.md, backend/agents/README.md, backend/ml/README.md. The BOCPD implementation uses a Normal–Inverse–Gamma model and Student-t prediction, hazard lambda 200, minimum run length 5, and heuristic shorter-run posterior threshold 0.5. Default scouts now expose candidate dates. They do not use those dates to change variable screening or PCMCI selection. The wavelet view has edge artifacts and does not provide a calibrated power spectral density.

## 11. Backup: data and scope

Sources: README.md NASA datasets section, backend/data/loader.py, reports/physics-inputs.md. Exports were prepared through NASA Giovanni: https://giovanni.gsfc.nasa.gov/giovanni/. GLDAS_NOAH025_M v2.1 precipitation and shallow soil moisture, GLDAS_NOAH025_3H v2.1 evapotranspiration averaged monthly, FLDAS_NOAH01_C_GL_M v001 Sahel evapotranspiration, MERRA-2 temperature and snow products. All image assets are contextual, not data inputs. NASA imagery does not imply NASA endorsement. Data availability varies by region and domain. No biosphere time series is curated.

## 12. Backup: questions

Sources: reports/browser-acceptance.md, reports/release/browser.json, backend/agents/cancellation.py, reports/physics-inputs.md, docs/project-summary.md. Native PCMCI or model forward calls already running may finish before the next cancellation checkpoint. The prior production browser checks covered refresh, region changes, errors, cancellation, and mobile layout. The release rerun validates the new regime display against the running backend. No held-out detection accuracy or public hosting result is claimed.
