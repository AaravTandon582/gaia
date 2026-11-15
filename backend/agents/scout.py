"""Domain scouts for cached NASA data, with real trend/anomaly screening."""

import asyncio

import numpy as np
import pandas as pd
from scipy.signal import detrend

from ..analysis.trend import analyze_trend
from ..data.loader import REGIONS, VARIABLES, available_series, load_series
from .cancellation import check_cancelled


class ScoutAgent:
    def __init__(self, domain):
        self.domain = domain
        self.name = domain

    async def scan(self, regions, date_range):
        return await asyncio.to_thread(self._scan, regions, date_range)

    def _scan(self, regions, date_range):
        check_cancelled()
        discoveries = []
        for region in dict.fromkeys(regions):
            check_cancelled()
            location = next((item for item in REGIONS if item["id"] == region), None)
            if location is None:
                raise ValueError(f"Unsupported region: {region}")
            for variable in available_series(region, self.domain):
                check_cancelled()
                series, metadata = load_series(region, variable, date_range)
                check_cancelled()
                trend = analyze_trend(series.to_numpy(), series.index)
                check_cancelled()
                adjusted = trend["deseasonalized"]
                residual = detrend(adjusted)
                std = float(residual.std())
                peak_z = float(np.max(np.abs(residual / std))) if std > 0 else 0.0
                flagged = bool(trend["is_significant"] or peak_z >= 2.5)
                label, domain, unit = VARIABLES[variable]
                discoveries.append(dict(
                    region=region, variable=variable, label=label, domain=domain,
                    lat=location["lat"], lon=location["lon"], unit=unit,
                    region_name=location["name"], flagged=flagged,
                    trend_p=float(trend["mk_p"]), peak_anomaly_z=peak_z,
                    reason="Significant trend" if trend["is_significant"] else
                           "Monthly anomaly" if flagged else "No signal flagged",
                    dates=series.index.strftime("%Y-%m-%d").tolist(),
                    values=series.to_list(),
                    # PCMCI sees deseasonalized, detrended data; charts show raw observations.
                    timeseries=pd.Series(residual, index=series.index),
                    **metadata,
                ))
        check_cancelled()
        return discoveries


def default_scouts():
    return [ScoutAgent(domain) for domain in ("atmosphere", "hydro", "cryo", "bio")]
