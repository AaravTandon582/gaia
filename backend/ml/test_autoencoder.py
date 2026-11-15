"""Focused checks for Giovanni parsing, reconstruction, and score aggregation."""

from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from .autoencoder import EarthSystemAutoencoder
from .train_autoencoder import aggregate_scores, make_windows, read_giovanni


class AutoencoderTests(unittest.TestCase):
    def test_metadata_fill_values_and_monthly_mean(self):
        content = (
            'Title:,Example\n'
            'Data Bounding Box:,"-5,30,40,45"\n'
            'URL to Reproduce Results:,https://example.test/?data=OTHER_VARIABLE\n'
            'Fill Value (M2_T2M):,-9999\n\n'
            'time, mean_M2_T2M\n'
            '2000-01-01 00:00:00,2\n'
            '2000-01-01 01:00:00,4\n'
            '2000-01-02 00:00:00,-9999\n'
            '2000-02,6\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.csv'
            path.write_text(content)
            series, metadata = read_giovanni(path)
        np.testing.assert_allclose(series.to_numpy(), [3, 6])
        self.assertEqual(metadata['dataset_variable'], 'M2_T2M')
        self.assertEqual(metadata['missing_raw_values'], 1)

    def test_overlapping_scores_are_averaged_at_edges(self):
        scores, counts = aggregate_scores(np.array([[1., 2.], [3., 4.]]), 3)
        np.testing.assert_allclose(scores, [1, 2.5, 4])
        np.testing.assert_array_equal(counts, [1, 2, 1])

    def test_windows_preserve_time_and_features(self):
        matrix = np.arange(30, dtype=np.float32).reshape(15, 2)
        windows = make_windows(matrix, 12)
        self.assertEqual(windows.shape, (4, 12, 2))
        np.testing.assert_array_equal(windows[-1], matrix[-12:])

    def test_reconstruction_score_and_backward(self):
        torch.manual_seed(1)
        model = EarthSystemAutoencoder(3, hidden_dim=8, latent_dim=4)
        x = torch.randn(2, 12, 3)
        reconstruction = model(x)
        self.assertEqual(reconstruction.shape, x.shape)
        expected = ((reconstruction - x) ** 2).mean(dim=-1)
        torch.testing.assert_close(model.anomaly_score(x), expected)
        expected.mean().backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all()
                            for p in model.parameters()))


if __name__ == '__main__':
    unittest.main()
