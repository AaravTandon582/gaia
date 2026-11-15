# Earth system LSTM autoencoder

From the repository root, run:

```bash
python -m backend.ml.train_autoencoder
python -m unittest backend.ml.test_autoencoder -v
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

The cache includes MERRA-2, GLDAS, and FLDAS, so this model uses the distinct
series from all three sources. Region labels do not imply identical bounding
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
  feature order, sequence length, best epoch, and validation loss.
- `saved_models/scaler.npy`: NumPy structured array with `feature`, `mean`,
  and `std` fields, readable with `allow_pickle=False`.
- `saved_models/monthly_data.csv`: aligned, unnormalized monthly values.
- `saved_models/normalized_data.npy`: float32 matrix in checkpoint feature order.
- `saved_models/training_history.csv`: training and validation losses per epoch.
- `saved_models/anomaly_scores.csv`: dates, scores, window counts, and split labels.
- `saved_models/training_summary.json`: provenance, preprocessing, versions,
  configuration, best epoch, and top five months.

Load for inference:

```python
import numpy as np
import torch
from backend.ml.autoencoder import EarthSystemAutoencoder

checkpoint = torch.load('backend/ml/saved_models/autoencoder.pt',
                        map_location='cpu', weights_only=True)
model = EarthSystemAutoencoder(**checkpoint['model_config'])
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()
scaler = np.load('backend/ml/saved_models/scaler.npy', allow_pickle=False)
# Align monthly inputs to scaler['feature'], then apply (x - mean) / std.
# In torch.inference_mode(), pass float32 windows shaped (batch, 12, features).
```

Checkpoint loading follows the [PyTorch serialization documentation](https://docs.pytorch.org/docs/stable/notes/serialization).
