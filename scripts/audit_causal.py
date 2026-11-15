"""Reproduce regional results and the 20-seed null on the actual Amazon matrix.

Run from the repository root: .venv/bin/python -m scripts.audit_causal
Outputs JSON to stdout; no files or application state are changed.
"""

import asyncio
import json
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.agents import orchestrator as module
from backend.agents.scout import default_scouts


async def audit():
    captured = {}

    class CapturePCMCI(module.PCMCI):
        def __init__(self, dataframe, **kwargs):
            captured["matrix"] = dataframe.values[0].copy()
            captured["names"] = list(dataframe.var_names)
            super().__init__(dataframe=dataframe, **kwargs)

    report = {}
    for region in ("amazon", "sahel"):
        agent = module.OrchestratorAgent(default_scouts())
        discoveries = await agent.run_scan([region], ("2000-01-01", "2025-12-31"))
        with patch.object(module, "PCMCI", CapturePCMCI):
            links = await asyncio.to_thread(agent.run_causal_discovery, discoveries)
        report[region] = {**agent.causal_metadata, "links": links}
        if region == "amazon":
            matrix, names = captured["matrix"], captured["names"]

    dates = pd.date_range("2000", periods=len(matrix), freq="MS")
    trials = []
    for seed in range(20):
        offsets = np.random.default_rng(seed).integers(50, 351, size=len(names))
        discoveries = [dict(region=name.split(":")[0], variable=name.split(":")[1],
                            timeseries=pd.Series(np.roll(matrix[:, i], offsets[i]), index=dates))
                       for i, name in enumerate(names)]
        # The captured matrix is already preprocessed. Roll it without fitting
        # a second climatology; use the production PCMCI/FDR/link-selection path.
        with patch.object(module, "preprocess_for_causal", side_effect=lambda x, months: x):
            links = module.OrchestratorAgent().run_causal_discovery(discoveries)
        trials.append(dict(seed=seed, offsets=offsets.tolist(), cross_links=len(links)))
    counts = [trial["cross_links"] for trial in trials]
    report["amazon_shift_null"] = dict(
        seeds="0..19", offset_range_inclusive=[50, 350], variables=names,
        mean=float(np.mean(counts)), max=max(counts), trials=trials,
    )
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(audit()), indent=2))
