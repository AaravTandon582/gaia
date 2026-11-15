"""Load Giovanni CSVs, train for 100 epochs, reload, and score every month.

Run from the repository root: python -m backend.ml.train_autoencoder
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from .autoencoder import EarthSystemAutoencoder


ML_DIR = Path(__file__).resolve().parent
DATE_ROW = re.compile(r"^\d{4}-\d{2}(?:-\d{2})?(?:[ T]|$)")


def read_giovanni(path):
    """Read dated records; metadata URLs are not evidence of data columns."""
    dates, values, fill_values = [], [], []
    metadata = {"file": path.name}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            key = row[0].strip()
            if DATE_ROW.match(key):
                if len(row) != 2:
                    raise ValueError(f"{path.name}: expected one variable per CSV")
                dates.append(key)
                values.append(float(row[1]) if row[1].strip() else np.nan)
            elif key.lower().startswith("fill value"):
                fill_values.append(float(row[1]))
            elif key.lower() == "time":
                if len(row) != 2:
                    raise ValueError(f"{path.name}: ambiguous data header")
                metadata["dataset_variable"] = row[1].strip().removeprefix("mean_")
            elif key in ("Title:", "User Bounding Box:", "Data Bounding Box:"):
                metadata[key.rstrip(":")] = row[1].strip()
    if not dates:
        return None, {**metadata, "skipped": "No dated data rows"}
    if "dataset_variable" not in metadata or "Data Bounding Box" not in metadata:
        raise ValueError(f"{path.name}: missing Giovanni column/bounding box metadata")
    index = pd.to_datetime(dates, format="mixed", utc=True).tz_convert(None)
    series = pd.Series(values, index=index, dtype="float64")
    series = series.mask(series.isin(fill_values) | ~np.isfinite(series))
    metadata["raw_rows"] = len(series)
    metadata["missing_raw_values"] = int(series.isna().sum())
    # Repeated timestamps do not get extra weight in the monthly mean.
    monthly = series.groupby(level=0).mean().sort_index().resample("MS").mean()
    metadata["monthly_missing_values"] = int(monthly.isna().sum())
    metadata["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return monthly, metadata


def load_monthly_data(cache_dir):
    """Read every CSV, deduplicate equivalent exports, and align shared months."""
    paths = sorted(cache_dir.glob("*"), key=lambda p: (p.name.startswith("g4."), p.name))
    columns, provenance, skipped = {}, {}, []
    seen = {}
    for path in paths:
        if not path.is_file() or path.suffix.lower() != ".csv":
            continue
        series, metadata = read_giovanni(path)
        if series is None:
            skipped.append(metadata)
            print(f"Skipping {path.name}: no dated records", flush=True)
            continue
        bbox = tuple(float(v) for v in metadata["Data Bounding Box"].split(","))
        fingerprint = (
            metadata["dataset_variable"], bbox,
            hashlib.sha256(pd.util.hash_pandas_object(series).values.tobytes()).hexdigest(),
        )
        if fingerprint in seen:
            provenance[seen[fingerprint]].append(metadata)
            continue
        name = path.stem
        seen[fingerprint] = name
        columns[name] = series
        provenance[name] = [metadata]
    if not columns:
        raise ValueError("No usable Giovanni time series found")
    start = max(s.index.min() for s in columns.values())
    end = min(s.index.max() for s in columns.values())
    frame = pd.DataFrame(columns).reindex(pd.date_range(start, end, freq="MS"))
    frame.index.name = "date"
    if len(frame) < 60:
        raise ValueError("Need at least 60 shared months for a 12-month validation window")
    if not np.isfinite(frame.to_numpy()).all():
        missing = frame.isna().sum()
        raise ValueError(f"Missing monthly observations; no imputation performed: {missing[missing > 0].to_dict()}")
    return frame, provenance, skipped


def make_windows(matrix, length=12):
    if len(matrix) < length:
        raise ValueError("Insufficient months for a window")
    return np.stack([matrix[i:i + length] for i in range(len(matrix) - length + 1)])


def aggregate_scores(window_scores, n_months):
    """Average a month's errors across every overlapping window containing it."""
    totals = np.zeros(n_months, dtype=np.float64)
    counts = np.zeros(n_months, dtype=np.int64)
    for start, errors in enumerate(window_scores):
        totals[start:start + len(errors)] += errors
        counts[start:start + len(errors)] += 1
    if (counts == 0).any():
        raise ValueError("Every month must be covered by at least one window")
    return totals / counts, counts


def score_all(model, windows, batch_size=32):
    model.eval()
    with torch.inference_mode():
        scores = [model.anomaly_score(batch).cpu().numpy()
                  for batch in torch.from_numpy(windows).split(batch_size)]
    return np.concatenate(scores)


def run(cache_dir, output_dir, epochs=100):
    torch.manual_seed(42)
    np.random.seed(42)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame, provenance, skipped = load_monthly_data(cache_dir)
    features = list(frame.columns)
    split = int(len(frame) * 0.8)
    # Split the timeline first: train/validation windows share no observations.
    train_values = frame.iloc[:split].to_numpy()
    mean, std = train_values.mean(axis=0), train_values.std(axis=0, ddof=0)
    constant = std == 0
    std[constant] = 1.0
    normalized = ((frame.to_numpy() - mean) / std).astype(np.float32)
    if not np.isfinite(normalized).all():
        raise ValueError("Nonfinite normalized values")
    scaler = np.empty(len(features), dtype=[
        ("feature", f"U{max(map(len, features))}"), ("mean", "f8"), ("std", "f8")])
    scaler["feature"], scaler["mean"], scaler["std"] = features, mean, std
    np.save(output_dir / "scaler.npy", scaler, allow_pickle=False)
    np.save(output_dir / "normalized_data.npy", normalized, allow_pickle=False)
    frame.to_csv(output_dir / "monthly_data.csv")
    train_windows = make_windows(normalized[:split])
    val_windows = make_windows(normalized[split:])
    all_windows = make_windows(normalized)
    generator = torch.Generator().manual_seed(42)
    loader = DataLoader(TensorDataset(torch.from_numpy(train_windows)), batch_size=32,
                        shuffle=True, generator=generator)
    val_tensor = torch.from_numpy(val_windows)
    config = dict(n_features=len(features), hidden_dim=64, latent_dim=16, n_layers=2)
    model = EarthSystemAutoencoder(**config)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_function = nn.MSELoss()
    best_loss, best_epoch, history = float("inf"), 0, []
    print(f"Aligned matrix: {frame.shape}; {frame.index[0]:%Y-%m} to {frame.index[-1]:%Y-%m}", flush=True)
    print(f"Read {sum(map(len, provenance.values()))} usable CSVs -> {len(features)} distinct features", flush=True)
    print(f"Chronological 80/20 split: {split}/{len(frame)-split} months; "
          f"{len(train_windows)}/{len(val_windows)} windows; CPU", flush=True)
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for (batch,) in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = loss_function(model(batch), batch)
            if not torch.isfinite(loss):
                raise RuntimeError(f"Nonfinite training loss at epoch {epoch}")
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(batch)
        train_loss = total_loss / len(train_windows)
        model.eval()
        with torch.inference_mode():
            val_loss = loss_function(model(val_tensor), val_tensor).item()
        if not np.isfinite(val_loss):
            raise RuntimeError(f"Nonfinite validation loss at epoch {epoch}")
        history.append(dict(epoch=epoch, train_loss=train_loss, val_loss=val_loss))
        if val_loss < best_loss:
            best_loss, best_epoch = val_loss, epoch
            checkpoint = dict(model_state_dict=model.state_dict(), model_config=config,
                              feature_names=features, sequence_length=12,
                              epoch=epoch, validation_loss=val_loss)
            temporary = output_dir / "autoencoder.tmp"
            torch.save(checkpoint, temporary)
            temporary.replace(output_dir / "autoencoder.pt")
        if epoch % 10 == 0:
            print(f"Epoch {epoch:3d}/{epochs}: train_loss={train_loss:.6f}, val_loss={val_loss:.6f}", flush=True)
    pd.DataFrame(history).to_csv(output_dir / "training_history.csv", index=False)

    checkpoint = torch.load(output_dir / "autoencoder.pt", map_location="cpu", weights_only=True)
    restored = EarthSystemAutoencoder(**checkpoint["model_config"])
    restored.load_state_dict(checkpoint["model_state_dict"])
    restored.eval()
    saved_scaler = np.load(output_dir / "scaler.npy", allow_pickle=False)
    assert saved_scaler["feature"].tolist() == checkpoint["feature_names"]
    reloaded_values = ((frame.to_numpy() - saved_scaler["mean"]) / saved_scaler["std"]).astype(np.float32)
    np.testing.assert_array_equal(reloaded_values, normalized)
    reloaded_windows = make_windows(reloaded_values)
    with torch.inference_mode():
        reload_val_loss = loss_function(restored(val_tensor), val_tensor).item()
    if not np.isclose(reload_val_loss, best_loss, rtol=1e-6, atol=1e-8):
        raise RuntimeError("Reloaded checkpoint does not reproduce best validation loss")
    window_scores = score_all(restored, reloaded_windows)
    scores, counts = aggregate_scores(window_scores, len(frame))
    if not np.isfinite(scores).all():
        raise RuntimeError("Nonfinite anomaly scores")
    score_frame = pd.DataFrame({"date": frame.index, "anomaly_score": scores,
                               "window_count": counts,
                               "split": ["train"] * split + ["validation"] * (len(frame)-split)})
    score_frame.to_csv(output_dir / "anomaly_scores.csv", index=False)
    top = score_frame.nlargest(5, "anomaly_score")
    report = dict(
        matrix_shape=list(frame.shape), feature_names=features,
        start_month=frame.index[0].strftime("%Y-%m"), end_month=frame.index[-1].strftime("%Y-%m"),
        training_months=split, validation_months=len(frame)-split,
        validation_start=frame.index[split].strftime("%Y-%m"),
        train_windows=len(train_windows), validation_windows=len(val_windows),
        full_windows=len(all_windows), sequence_length=12, stride=1,
        scaler_fit="training months only", scaler_format="structured array: feature, mean, std",
        constant_features=[features[i] for i in np.flatnonzero(constant)],
        epochs=epochs, optimizer="Adam", learning_rate=0.001, seed=42,
        best_epoch=best_epoch, best_validation_loss=best_loss,
        reloaded_validation_loss=reload_val_loss, device="cpu", torch_version=str(torch.__version__),
        pandas_version=pd.__version__, numpy_version=np.__version__,
        model_config=config, sources=provenance, skipped_csvs=skipped,
        score_definition="Mean squared error across standardized features, averaged across overlapping windows",
        top_anomaly_months=[dict(date=row.date.strftime("%Y-%m"), score=row.anomaly_score)
                            for row in top.itertuples()],
    )
    (output_dir / "training_summary.json").write_text(json.dumps(report, indent=2) + "\n")
    # Ensure source exports were not modified by preprocessing/training.
    for sources in provenance.values():
        for source in sources:
            assert hashlib.sha256((cache_dir / source["file"]).read_bytes()).hexdigest() == source["sha256"]
    print(f"Best checkpoint: epoch {best_epoch}, validation loss {best_loss:.6f}", flush=True)
    print("Top 5 highest anomaly months (normalized reconstruction MSE):", flush=True)
    for row in top.itertuples():
        print(f"  {row.date:%Y-%m}: {row.anomaly_score:.6f}", flush=True)
    print("✅ LSTM autoencoder trained and saved", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=ML_DIR.parent / "data" / "cache")
    parser.add_argument("--output-dir", type=Path, default=ML_DIR / "saved_models")
    parser.add_argument("--epochs", type=int, default=100)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("--epochs must be positive")
    run(args.cache_dir, args.output_dir, args.epochs)
