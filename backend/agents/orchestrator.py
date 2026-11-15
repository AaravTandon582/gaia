"""Concurrent scout coordination and monthly PCMCI causal discovery.

Scouts implement ``async scan(regions, date_range) -> list[dict]``. Each
discovery identifies a ``region`` and ``variable`` and carries either a pandas
Series in ``timeseries`` or parallel ``dates`` and ``values`` arrays. A custom
series_loader may instead retrieve a Series from the discovery's metadata.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol

import numpy as np
import pandas as pd
from tigramite import data_processing as pp
from tigramite.independence_tests.parcorr import ParCorr
from tigramite.pcmci import PCMCI
from .cancellation import check_cancelled
from .preprocessing import preprocess_for_causal
from ..analysis.transfer_entropy import transfer_entropy_significance


class ScoutAgent(Protocol):
    """Structural interface for scouts; no inheritance is required."""

    async def scan(self, regions: Sequence[str], date_range: tuple) -> list[dict]: ...


StatusCallback = Callable[[dict], Awaitable[None]]


class OrchestratorAgent:
    tau_max = 6

    def __init__(
        self,
        scouts: Sequence[ScoutAgent] = (),
        *,
        status_callback: StatusCallback | None = None,
        series_loader: Callable[[Mapping[str, Any]], pd.Series] | None = None,
        pc_alpha: float = 0.2,
    ):
        if not np.isfinite(pc_alpha) or not 0 < pc_alpha < 1:
            raise ValueError("pc_alpha must be between 0 and 1")
        self.scouts = list(scouts)
        self.status_callback = status_callback
        self.series_loader = series_loader
        self.pc_alpha = pc_alpha
        self.causal_metadata = dict(n_samples=0, n_variables=0, tau_max=self.tau_max, fdr_applied=False)

    async def _status(self, agent: str, status: str, **details) -> None:
        check_cancelled()
        if self.status_callback is not None:
            await self.status_callback(
                {"type": "status", "agent": agent, "status": status, **details}
            )

    async def run_scan(self, regions, date_range) -> list[dict]:
        """Run every scout concurrently; cancel remaining work on failure."""
        check_cancelled()
        if not self.scouts:
            raise ValueError("No ScoutAgents configured")
        await self._status("orchestrator", "scan_started", scout_count=len(self.scouts))

        async def run_scout(index, scout):
            check_cancelled()
            name = f"{getattr(scout, 'name', type(scout).__name__)}:{index}"
            await self._status(name, "started")
            try:
                discoveries = await scout.scan(regions, date_range)
                if not isinstance(discoveries, list) or not all(
                    isinstance(item, Mapping) for item in discoveries
                ):
                    raise TypeError("Scout.scan must return a list of discovery mappings")
            except asyncio.CancelledError:
                raise
            except Exception as error:
                await self._status(name, "error", message=str(error))
                raise
            await self._status(name, "completed", discovery_count=len(discoveries))
            return discoveries

        tasks = [asyncio.create_task(run_scout(i, scout)) for i, scout in enumerate(self.scouts)]
        try:
            results = await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        discoveries = [item for result in results for item in result]
        await self._status("orchestrator", "scan_completed", discovery_count=len(discoveries))
        return discoveries

    def _monthly_series(self, discovery: Mapping[str, Any]) -> pd.Series:
        if "timeseries" in discovery:
            series = discovery["timeseries"]
        elif "dates" in discovery and "values" in discovery:
            dates = discovery["dates"]
            if pd.api.types.is_numeric_dtype(np.asarray(dates).dtype):
                raise ValueError("Discovery dates must be calendar dates")
            series = pd.Series(
                discovery["values"],
                index=pd.to_datetime(dates, format="mixed", utc=True),
            )
        elif self.series_loader is not None:
            series = self.series_loader(discovery)
        else:
            raise ValueError("Discovery needs timeseries, dates/values, or a series_loader")
        if not isinstance(series, pd.Series) or not isinstance(series.index, pd.DatetimeIndex):
            raise ValueError("Time series must be a pandas Series with a DatetimeIndex")
        if series.empty or series.index.hasnans or series.index.has_duplicates:
            raise ValueError("Time series must have nonempty, unique, valid timestamps")
        if np.iscomplexobj(series.to_numpy()):
            raise ValueError("Time series must contain real values")
        series = series.astype(float).copy()
        if not np.isfinite(series.to_numpy()).all():
            raise ValueError("Time series must contain finite values")
        if series.index.tz is not None:
            series.index = series.index.tz_convert("UTC").tz_localize(None)
        # All GAIA lag units are calendar months, including submonthly inputs.
        return series.sort_index().resample("MS").mean()

    def run_causal_discovery(self, discoveries) -> list[dict]:
        """Return directed lagged links; positive lag means cause(t-lag) -> effect(t).

        Variables are region-qualified (``region:variable``). Duplicate flags
        for one series are collapsed. Monthly means are aligned over the shared
        date range; missing months and constant columns are rejected. Lag-zero
        associations are omitted because PCMCI cannot orient them. This CPU
        operation is synchronous; async callers should use asyncio.to_thread.
        """
        check_cancelled()
        self.causal_metadata = dict(n_samples=0, n_variables=0, tau_max=self.tau_max, fdr_applied=False)
        columns = {}
        for discovery in discoveries:
            check_cancelled()
            if not discovery.get("flagged", True):
                continue
            region, variable = discovery.get("region"), discovery.get("variable")
            if not isinstance(region, str) or not region or not isinstance(variable, str) or not variable:
                raise ValueError("Each discovery needs nonempty region and variable strings")
            if ":" in region or ":" in variable:
                raise ValueError("Region and variable names must not contain ':'")
            name = f"{region}:{variable}"
            series = self._monthly_series(discovery)
            if name in columns and not columns[name].equals(series):
                raise ValueError(f"Conflicting time series for {name}")
            columns[name] = series
        if not columns:
            return []
        start = max(series.index.min() for series in columns.values())
        end = min(series.index.max() for series in columns.values())
        frame = pd.DataFrame(columns).reindex(pd.date_range(start, end, freq="MS"))
        if len(frame) < 2 * self.tau_max + 3:
            raise ValueError("PCMCI needs at least 15 overlapping monthly observations")
        if not np.isfinite(frame.to_numpy(dtype=float)).all():
            raise ValueError("Missing observations within the shared monthly date range")
        if (np.ptp(frame.to_numpy(dtype=float), axis=0) == 0).any():
            raise ValueError("PCMCI cannot analyze constant time series")
        names = list(frame.columns)
        processed = []
        for name in names:
            check_cancelled()
            processed.append(preprocess_for_causal(frame[name].to_numpy(), frame.index.month))
        matrix = np.column_stack(processed)
        self.causal_metadata.update(n_samples=matrix.shape[0], n_variables=matrix.shape[1])
        dataframe = pp.DataFrame(data=matrix, var_names=names)
        pcmci = PCMCI(
            dataframe=dataframe,
            cond_ind_test=ParCorr(significance="analytic"),
            verbosity=0,
        )
        check_cancelled()
        results = pcmci.run_pcmci(tau_min=1, tau_max=self.tau_max,
                                  pc_alpha=self.pc_alpha, alpha_level=0.05)
        check_cancelled()
        corrected = pcmci.get_corrected_pvalues(
            p_matrix=results["p_matrix"], fdr_method="fdr_bh",
            exclude_contemporaneous=True, tau_min=1, tau_max=self.tau_max,
        )
        self.causal_metadata["fdr_applied"] = True
        links = []
        for cause in range(len(names)):
            for effect in range(len(names)):
                # Node identity includes both region and variable.
                if names[cause] == names[effect]:
                    continue
                for lag in range(1, self.tau_max + 1):
                    corrected_p = float(corrected[cause, effect, lag])
                    if not np.isfinite(corrected_p):
                        raise ValueError("PCMCI produced nonfinite corrected p-values")
                    if corrected_p >= 0.05:
                        continue
                    strength = float(results["val_matrix"][cause, effect, lag])
                    p_value = float(results["p_matrix"][cause, effect, lag])
                    if not np.isfinite(strength) or not np.isfinite(p_value):
                        raise ValueError("PCMCI produced nonfinite link statistics")
                    te = transfer_entropy_significance(
                        matrix[:, cause], matrix[:, effect], lag=lag,
                        check_cancelled=check_cancelled,
                    )
                    links.append(dict(cause=names[cause], effect=names[effect],
                                      lag=lag, strength=strength, p_value=p_value,
                                      corrected_p=corrected_p, **te))
        return links
