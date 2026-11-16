"""Optional, request-cancellable inference on the model's full feature matrix."""

import logging
from pathlib import Path
from threading import Lock

import pandas as pd

from .cancellation import check_cancelled
from ..data.loader import load_series

logger = logging.getLogger(__name__)


def _region_attribution(feature_errors_frame, feature_names):
    """Aggregate per-feature errors into per-region mean error over time.

    Feature names are ``region_variable``; the region is the first underscore
    token. Returns ``{region: mean error}``.
    """
    by_region = {}
    for name in feature_names:
        region = name.split("_", 1)[0]
        by_region.setdefault(region, []).append(name)
    attribution = {}
    for region, names in by_region.items():
        frame = feature_errors_frame[names]
        attribution[region] = float(frame.values.mean())
    return attribution


class AnomalyAgent:
    """One cached CPU model; scores describe all features, not regional attribution."""

    def __init__(self, model_path=None, *, series_loader=load_series):
        self.model_path = model_path
        self.series_loader = series_loader
        self._pipeline = None
        self._lock = Lock()

    def run(self, date_range):
        check_cancelled()
        # Serialize inference to avoid competing CPU forwards and model loads.
        while not self._lock.acquire(timeout=0.1):
            check_cancelled()
        try:
            check_cancelled()
            if self._pipeline is None:
                from ..ml.inference import AutoencoderInference, DEFAULT_MODEL_PATH
                self._pipeline = AutoencoderInference(
                    Path(self.model_path) if self.model_path else DEFAULT_MODEL_PATH)
            pipeline = self._pipeline
            columns = {}
            for feature in pipeline.feature_names:
                check_cancelled()
                region, variable = feature.split("_", 1)
                columns[feature], _ = self.series_loader(region, variable, date_range)
            start, end = (pd.Timestamp(value).to_period("M").to_timestamp()
                          for value in date_range)
            frame = pd.DataFrame(columns).reindex(pd.date_range(start, end, freq="MS"))
            scores = pipeline.predict(frame, check_cancelled=check_cancelled)
            check_cancelled()
            result = dict(
                status="complete", scope="all_model_features", retrospective=True,
                feature_names=list(pipeline.feature_names),
                dates=scores.index.strftime("%Y-%m-%d").tolist(),
                reconstruction_error=scores.reconstruction_error.tolist(),
                is_anomaly=scores.is_anomaly.tolist(),
                window_count=scores.window_count.tolist(),
                threshold=pipeline.threshold,
                training_error_mean=pipeline.training_error_mean,
                training_error_std=pipeline.training_error_std,
                sequence_length=pipeline.sequence_length,
                interpretation="Combined reconstruction error across all model features; "
                               "not an attribution to the selected region or variable.",
            )
            # Region/variable attribution: per-feature reconstruction errors,
            # aggregated by region. Additive; never fails the causal scan.
            try:
                check_cancelled()
                errors_frame = pipeline.feature_errors(frame, check_cancelled=check_cancelled)
                result["feature_errors"] = {
                    name: errors_frame[name].tolist()
                    for name in pipeline.feature_names}
                result["region_attribution"] = _region_attribution(
                    errors_frame, pipeline.feature_names)
            except Exception as error:  # noqa: BLE001
                logger.warning("Anomaly attribution unavailable: %s", error)
            # This period selected the checkpoint; it is not an independent test.
            try:
                check_cancelled()
                from ..ml.inference import held_out_evaluation
                result["held_out_evaluation"] = held_out_evaluation(
                    pipeline, check_cancelled=check_cancelled)
            except Exception as error:  # noqa: BLE001
                logger.warning("Held-out evaluation unavailable: %s", error)
                result["held_out_evaluation"] = {"status": "unavailable", "reason": str(error)}
            return dict(result)
        except (ImportError, OSError, ValueError, KeyError, RuntimeError) as error:
            logger.warning("LSTM inputs unavailable: %s", error)
            return dict(status="unavailable", scope="all_model_features", reason=str(error))
        finally:
            self._lock.release()
