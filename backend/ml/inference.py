"""Reload a trained LSTM and flag monthly reconstruction-error anomalies.

Run: python -m backend.ml.inference --input monthly.csv --output anomalies.csv
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .autoencoder import EarthSystemAutoencoder
from .train_autoencoder import aggregate_scores, make_windows, score_all, training_error_statistics


DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "saved_models" / "autoencoder.pt"
SUMMARY_PATH = Path(__file__).resolve().parent / "saved_models" / "training_summary.json"


def score_feature_errors(model, windows, batch_size=32, check_cancelled=lambda: None):
    """Per-window, per-feature squared reconstruction errors (n_windows, seq, features)."""
    model.eval()
    with torch.inference_mode():
        errors = []
        for batch in torch.from_numpy(windows).split(batch_size):
            check_cancelled()
            errors.append(model.feature_errors(batch).cpu().numpy())
        check_cancelled()
    return np.concatenate(errors)


def aggregate_feature_errors(window_errors, n_months):
    """Average a month's per-feature errors across every overlapping window."""
    n_features = window_errors.shape[2]
    totals = np.zeros((n_months, n_features), dtype=np.float64)
    counts = np.zeros(n_months, dtype=np.int64)
    for start, errors in enumerate(window_errors):
        totals[start:start + len(errors)] += errors
        counts[start:start + len(errors)] += 1
    if (counts == 0).any():
        raise ValueError("Every month must be covered by at least one window")
    return totals / counts[:, None], counts


def held_out_evaluation(pipeline, summary_path=SUMMARY_PATH):
    """Score the held-out validation period independently of training.

    The model is calibrated on training months only (mean + 2σ threshold from
    training reconstruction errors). This reports how the held-out validation
    months behave under that fixed threshold: anomaly rate, mean score, and the
    share of validation months above threshold. No threshold is re-estimated
    from validation data.
    """
    if not summary_path.is_file():
        return {"status": "unavailable", "reason": "training summary not found"}
    try:
        summary = json.loads(summary_path.read_text())
        split = summary["training_months"]
        total = summary["matrix_shape"][0]
        feature_names = summary["feature_names"]
    except (ValueError, KeyError, TypeError) as error:
        return {"status": "unavailable", "reason": str(error)}
    if not isinstance(split, int) or not split < total:
        return {"status": "unavailable", "reason": "invalid training split"}
    normalized_path = pipeline.model_path.with_name("normalized_data.npy")
    if not normalized_path.is_file():
        return {"status": "unavailable", "reason": "normalized data not found"}
    normalized = np.load(normalized_path, allow_pickle=False)
    validation = normalized[split:]
    if len(validation) < pipeline.sequence_length:
        return {"status": "unavailable", "reason": "insufficient validation months"}
    windows = make_windows(validation.astype(np.float32), pipeline.sequence_length)
    scores, counts = aggregate_feature_errors(
        score_feature_errors(pipeline.model, windows), len(validation))
    monthly = scores.mean(axis=1)
    threshold = pipeline.threshold
    flagged = monthly > threshold
    return {
        "status": "complete",
        "training_months": int(split),
        "validation_months": int(len(validation)),
        "validation_start": summary.get("validation_start"),
        "validation_mean_error": float(monthly.mean()),
        "validation_anomaly_rate": float(flagged.mean()),
        "validation_anomaly_count": int(flagged.sum()),
        "threshold": float(threshold),
        "feature_errors": {
            name: scores[:, i].tolist()
            for i, name in enumerate(feature_names)
        },
    }


class AutoencoderInference:
    """CPU inference with fixed training normalization and a mean + 2σ cutoff.

    DataFrame columns are reordered to the saved feature order; arrays must
    already have that order. Rows must represent consecutive monthly samples.
    Errors are MSE over standardized features, averaged across overlapping
    windows. This is retrospective scoring: an early timestep can be scored
    using a window that also contains later input observations.
    """

    def __init__(self, model_path=DEFAULT_MODEL_PATH, *, scaler_path=None):
        model_path = Path(model_path)
        self.model_path = model_path
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
        self.model = EarthSystemAutoencoder(**checkpoint["model_config"])
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()
        self.feature_names = list(checkpoint["feature_names"])
        self.sequence_length = checkpoint["sequence_length"]
        if (len(self.feature_names) != self.model.n_features
                or len(set(self.feature_names)) != len(self.feature_names)):
            raise ValueError("Checkpoint feature names do not match the model")
        if (isinstance(self.sequence_length, bool) or not isinstance(self.sequence_length, int)
                or self.sequence_length < 1):
            raise ValueError("Checkpoint sequence_length must be a positive integer")
        scaler = np.load(scaler_path or model_path.with_name("scaler.npy"), allow_pickle=False)
        if (scaler.ndim != 1 or not {"feature", "mean", "std"}.issubset(scaler.dtype.names or ())
                or scaler["feature"].tolist() != self.feature_names):
            raise ValueError("Scaler feature order does not match the checkpoint")
        self.mean = np.asarray(scaler["mean"], dtype=float)
        self.std = np.asarray(scaler["std"], dtype=float)
        if not np.isfinite(self.mean).all() or not np.isfinite(self.std).all() or (self.std <= 0).any():
            raise ValueError("Scaler must contain finite means and positive standard deviations")

        keys = ("training_error_mean", "training_error_std")
        if not any(key in checkpoint for key in keys):
            # Older artifacts have no calibration statistics. Never estimate the
            # threshold from incoming data or full-series scores crossing the split.
            summary = json.loads(model_path.with_name("training_summary.json").read_text())
            normalized = np.load(model_path.with_name("normalized_data.npy"), allow_pickle=False)
            split = summary["training_months"]
            if (summary["feature_names"] != self.feature_names
                    or summary["sequence_length"] != self.sequence_length
                    or normalized.ndim != 2 or normalized.shape[1] != len(self.feature_names)
                    or list(normalized.shape) != summary["matrix_shape"]
                    or isinstance(split, bool) or not isinstance(split, int)
                    or not self.sequence_length <= split <= len(normalized)):
                raise ValueError("Legacy training artifacts do not match the checkpoint")
            training = normalized[:split].astype(np.float32)
            if not np.isfinite(training).all():
                raise ValueError("Training calibration data must be finite")
            checkpoint.update(training_error_statistics(self.model, training, self.sequence_length))
        if not all(key in checkpoint for key in keys):
            raise ValueError("Checkpoint must supply both training error mean and standard deviation")
        self.training_error_mean = float(checkpoint[keys[0]])
        self.training_error_std = float(checkpoint[keys[1]])
        self.threshold = self.training_error_mean + 2 * self.training_error_std
        if (not np.isfinite([self.training_error_mean, self.training_error_std, self.threshold]).all()
                or min(self.training_error_mean, self.training_error_std) < 0):
            raise ValueError("Training error statistics must be finite and nonnegative")

    def predict(self, timeseries, *, batch_size=32, check_cancelled=lambda: None):
        """Return an error, coverage count, fixed threshold and flag for each row."""
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if isinstance(timeseries, pd.DataFrame):
            if not timeseries.columns.is_unique or set(timeseries.columns) != set(self.feature_names):
                raise ValueError("Input columns must match the saved feature names exactly")
            index = timeseries.index
            if isinstance(index, pd.DatetimeIndex):
                months = index.year.to_numpy() * 12 + index.month.to_numpy()
                if index.hasnans or not np.all(np.diff(months) == 1):
                    raise ValueError("Input dates must be ordered, unique, consecutive calendar months")
            values = timeseries.loc[:, self.feature_names].to_numpy()
        else:
            values = np.asarray(timeseries)
            index = None
        if np.iscomplexobj(values):
            raise ValueError("Input time series must be real-valued")
        values = np.asarray(values, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(self.feature_names):
            raise ValueError("Expected a (timesteps, saved feature count) matrix")
        if not np.isfinite(values).all():
            raise ValueError("Input time series must contain finite observations")
        with np.errstate(over="ignore", invalid="ignore"):
            normalized = ((values - self.mean) / self.std).astype(np.float32)
        if not np.isfinite(normalized).all():
            raise ValueError("Nonfinite normalized input")
        windows = make_windows(normalized, self.sequence_length)
        scores, counts = aggregate_scores(
            score_all(self.model, windows, batch_size, check_cancelled), len(values))
        if not np.isfinite(scores).all():
            raise ValueError("Nonfinite reconstruction errors")
        return pd.DataFrame({"reconstruction_error": scores, "window_count": counts,
                             "threshold": self.threshold, "is_anomaly": scores > self.threshold},
                            index=index)

    def feature_errors(self, timeseries, *, batch_size=32, check_cancelled=lambda: None):
        """Per-timestep, per-feature reconstruction errors as a DataFrame.

        Columns are the saved feature names; values are the mean squared
        reconstruction error for each feature at each timestep, averaged across
        overlapping windows. Used for region/variable attribution.
        """
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if isinstance(timeseries, pd.DataFrame):
            if not timeseries.columns.is_unique or set(timeseries.columns) != set(self.feature_names):
                raise ValueError("Input columns must match the saved feature names exactly")
            index = timeseries.index
            values = timeseries.loc[:, self.feature_names].to_numpy()
        else:
            values = np.asarray(timeseries)
            index = None
        if np.iscomplexobj(values):
            raise ValueError("Input time series must be real-valued")
        values = np.asarray(values, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(self.feature_names):
            raise ValueError("Expected a (timesteps, saved feature count) matrix")
        if not np.isfinite(values).all():
            raise ValueError("Input time series must contain finite observations")
        with np.errstate(over="ignore", invalid="ignore"):
            normalized = ((values - self.mean) / self.std).astype(np.float32)
        if not np.isfinite(normalized).all():
            raise ValueError("Nonfinite normalized input")
        windows = make_windows(normalized, self.sequence_length)
        errors, counts = aggregate_feature_errors(
            score_feature_errors(self.model, windows, batch_size, check_cancelled),
            len(values))
        return pd.DataFrame(errors, columns=self.feature_names, index=index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--input", type=Path, required=True, help="CSV with date column then saved feature columns")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    pipeline = AutoencoderInference(args.model)
    frame = pd.read_csv(args.input, index_col="date", parse_dates=["date"])
    if not isinstance(frame.index, pd.DatetimeIndex):
        parser.error("Input CSV dates must be valid calendar dates")
    results = pipeline.predict(frame, batch_size=args.batch_size)
    results.to_csv(args.output, index_label="date")
    print(f"Training mean={pipeline.training_error_mean:.6g}, std={pipeline.training_error_std:.6g}; "
          f"threshold={pipeline.threshold:.6g}. Flagged {int(results.is_anomaly.sum())}/{len(results)} timesteps.")


if __name__ == "__main__":
    main()
