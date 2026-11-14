# GAIA

**Geospatial Autonomous Intelligence for Anomaly & Trend Discovery**

Project structure for a planned Earth system analysis and causal discovery application.
This repository contains empty placeholders only. No application code, dependencies,
data, or trained models have been added. The Next.js frontend is not initialized yet.

## Project structure

```text
gaia/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── scout.py              # ScoutAgent
│   │   ├── orchestrator.py       # OrchestratorAgent
│   │   └── models.py             # Discovery, Domain, SignalType
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── trend.py              # Mann-Kendall, Sen's slope, deseasonalization
│   │   ├── changepoint.py        # BOCPD
│   │   ├── wavelet.py            # DWT/CWT decomposition
│   │   ├── causal.py             # PCMCI and planned BOCPD-gated discovery
│   │   ├── transfer_entropy.py
│   │   └── physics.py            # Energy/water balance validation
│   ├── data/
│   │   ├── __init__.py
│   │   ├── loader.py             # earthaccess and CSV fallback
│   │   └── cache/                # Future pre-downloaded CSVs
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── autoencoder.py        # LSTM autoencoder
│   │   └── saved_models/         # Future pre-trained .pt files
│   ├── main.py                   # Future FastAPI app
│   └── requirements.txt
├── frontend/                     # Reserved for a Next.js app
└── README.md
```

Empty directories contain `.gitkeep` files so Git preserves them.
