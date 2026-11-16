# Earth system LSTM autoencoder

From the repository root, run:

```bash
python -m backend.ml.train_autoencoder
python -m unittest backend.ml.test_autoencoder backend.ml.test_inference -v
```

The local training environment is `/opt/anaconda3/bin/python`. Dependencies
are listed in this directory's `requirements.txt`.

## Data preparation

Every CSV in `backend/data/cache/` is inspected. Giovanni metadata is skipped,
dated records become a pandas Series, and declared fill values become missing
values. Hourly and 3-hourly observations are averaged to calendar months.
Exports with the same dataset variable, actual data bounding box, monthly
dates, and values count as one feature; all original filenames and hashes
are recorded. Non-time-series CSVs are reported and skipped. Missing monthly
observations cause an error rather than silent interpolation.

The bundled model's provenance lists MERRA-2, GLDAS, and FLDAS series. Future training
uses the distinct series available at that time. Region labels do not imply identical bounding
boxes across variables; original boxes are retained in the training summary.
Source CSVs are never modified.

The shared monthly timeline is split chronologically 80/20 **before** forming
12-month windows with stride 1. Windows crossing the split are excluded to
avoid shared observations between training and validation. Means and population
standard deviations are fitted on training months only; validation and full
inference use that same scaler. Constant training columns use scale 1.

## Model and training

Two-layer LSTM encoder (64 hidden units), linear projection to 16 latent units,
linear projection back to 64 units, repeated latent input to a two-layer LSTM
decoder, and linear output to the original feature count. `forward(x)` returns
the reconstructed tensor. `anomaly_score(x)` returns MSE over features for each
timestep, shaped `(batch, months)`.

Training uses CPU, seed 42, batch size 32, Adam at 0.001, MSE, and 100 epochs.
The checkpoint with the lowest validation loss is saved and reloaded. Its
validation loss is verified before scoring every window in the full dataset.
For months appearing in multiple windows, scores are averaged over those
windows. Scores measure reconstruction difficulty in standardized units;
they do not by themselves establish a physical climate anomaly or causation.
The full-data ranking includes training months and is retrospective, not a
forecast or an independent test evaluation.

## Saved artifacts

- `saved_models/autoencoder.pt`: state dictionary, architecture configuration,
  feature order, sequence length, best epoch, validation loss, and (for newly
  trained checkpoints) training reconstruction-error mean and standard deviation.
- `saved_models/scaler.npy`: NumPy structured array with `feature`, `mean`,
  and `std` fields, readable with `allow_pickle=False`.
- `saved_models/monthly_data.csv`: aligned, unnormalized monthly values.
- `saved_models/normalized_data.npy`: float32 matrix in checkpoint feature order.
- `saved_models/training_history.csv`: training and validation losses per epoch.
- `saved_models/anomaly_scores.csv`: dates, scores, window counts, and split labels.
- `saved_models/training_summary.json`: provenance, preprocessing, versions,
  configuration, best epoch, and top five months.

## Inference

Run on a CSV with a `date` column and the 12 saved feature columns:

```bash
/opt/anaconda3/bin/python -m backend.ml.inference \
  --input backend/ml/saved_models/monthly_data.csv \
  --output /tmp/gaia-autoencoder-inference.csv
```

Use `--model /path/to/autoencoder.pt` for another checkpoint and `--batch-size`
to set the inference batch size. `scaler.npy` must sit beside the checkpoint.
The Python interface also accepts an explicit scaler path:

```python
import pandas as pd
from backend.ml.inference import AutoencoderInference

pipeline = AutoencoderInference('backend/ml/saved_models/autoencoder.pt')
series = pd.read_csv('backend/ml/saved_models/monthly_data.csv',
                     index_col='date', parse_dates=['date'])
result = pipeline.predict(series)
anomalies = result[result.is_anomaly]
```

DataFrames are reordered to the exact saved feature order; missing/extra/duplicate
columns are rejected. A NumPy `(timesteps, features)` matrix is also accepted in
saved feature order. Supply at least one full window of finite monthly values;
dated inputs with gaps or reversed/duplicate months are rejected. No imputation
or new scaler fitting is performed.

The pipeline loads the model on CPU with `weights_only=True`, enters evaluation
and inference mode, creates stride-1 windows of the saved sequence length, and
averages each timestep's feature MSE across all covering windows. Every input
row receives `reconstruction_error`, `window_count`, `threshold`, and
`is_anomaly`. A flag means error is **strictly greater than** the training mean
plus two training population standard deviations (`ddof=0`). Calibration uses
the same per-timestep overlap averaging, but only windows wholly inside the
training split. The threshold does not adapt to incoming data.

New training runs save these calibration statistics for the best checkpoint.
The existing older checkpoint is supported using its adjacent
`training_summary.json` and `normalized_data.npy`: only the first
`training_months` rows are rescored. The loader does not overwrite artifacts.
It deliberately does not calibrate from `anomaly_scores.csv`, whose full-series
windows cross the training/validation boundary. If saved statistics and the
legacy calibration artifacts are both missing, loading fails rather than
calibrating on inference data.

Scoring is retrospective: windows can include observations later than a scored
timestep. The bundled full series includes training data; its flags are not an
independent test evaluation. The current checkpoint requires all 12 saved
features, not a single regional variable.

The default FastAPI app now runs `AnomalyAgent` after causal discovery. It loads
all saved features from their curated regional CSVs for the requested interval,
preserves the saved feature order, and reports a combined score in the additive
`anomalies` field. Inference runs in a worker thread with cancellation checks
between batches; the model is reused and concurrent forwards are serialized.
Unavailable dependencies, artifacts, or features produce `status: unavailable`.
See [Cursor's API contract](../../docs/cursor-handoff.md) before adding chart bands.

Checkpoint loading follows the [PyTorch serialization documentation](https://docs.pytorch.org/docs/stable/notes/serialization).
