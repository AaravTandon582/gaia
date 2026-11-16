"""LSTM reconstruction model for monthly, multivariate Earth system windows."""

import torch
from torch import nn


class EarthSystemAutoencoder(nn.Module):
    """Reconstruct (batch, months, features) through a fixed-size latent vector."""

    def __init__(self, n_features, hidden_dim=64, latent_dim=16, n_layers=2):
        super().__init__()
        if min(n_features, hidden_dim, latent_dim, n_layers) < 1:
            raise ValueError("Model dimensions must be positive.")
        self.n_features = n_features
        self.encoder = nn.LSTM(
            n_features, hidden_dim, n_layers, batch_first=True
        )
        self.enc_to_latent = nn.Linear(hidden_dim, latent_dim)
        self.latent_to_dec = nn.Linear(latent_dim, hidden_dim)
        self.decoder = nn.LSTM(
            hidden_dim, hidden_dim, n_layers, batch_first=True
        )
        self.output_layer = nn.Linear(hidden_dim, n_features)

    def forward(self, x):
        """Return reconstruction with the same shape as x."""
        if x.ndim != 3 or x.shape[-1] != self.n_features or x.shape[1] == 0:
            raise ValueError("Expected (batch, nonempty sequence, n_features).")
        _, (hidden, _) = self.encoder(x)
        latent = self.enc_to_latent(hidden[-1])
        decoder_input = self.latent_to_dec(latent).unsqueeze(1)
        decoder_input = decoder_input.repeat(1, x.shape[1], 1)
        decoded, _ = self.decoder(decoder_input)
        return self.output_layer(decoded)

    def anomaly_score(self, x):
        """Per-timestep mean squared error over normalized features (batch, months)."""
        return torch.mean((self(x) - x) ** 2, dim=-1)

    def feature_errors(self, x):
        """Per-timestep, per-feature squared reconstruction error (batch, months, features).

        Used for region/variable attribution: the combined MSE is averaged over
        all 12 features, but this returns each feature's own contribution so the
        user can see which regions or variables drive a given anomaly.
        """
        return (self(x) - x) ** 2
