"""Checkpoint round trips and training-only anomaly threshold regression tests."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch

from .autoencoder import EarthSystemAutoencoder
from .inference import AutoencoderInference
from .train_autoencoder import run


class InferenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "autoencoder.pt"
        config = dict(n_features=2, hidden_dim=4, latent_dim=2, n_layers=1)
        model = EarthSystemAutoencoder(**config)
        for parameter in model.parameters():
            torch.nn.init.zeros_(parameter)
        self.checkpoint = dict(model_state_dict=model.state_dict(), model_config=config,
                               feature_names=["a", "b"], sequence_length=3,
                               training_error_mean=1., training_error_std=0.5)
        torch.save(self.checkpoint, self.path)
        scaler = np.array([("a", 10., 2.), ("b", 20., 4.)],
                          dtype=[("feature", "U1"), ("mean", "f8"), ("std", "f8")])
        np.save(self.root / "scaler.npy", scaler, allow_pickle=False)
        self.normalized = np.array([[0., 0.], [1., 1.], [2., 0.], [2., 2.], [0., 4.]])
        self.frame = pd.DataFrame(self.normalized * [2., 4.] + [10., 20.], columns=["a", "b"],
                                  index=pd.date_range("2025", periods=5, freq="MS"))

    def test_saved_model_scaler_feature_order_and_strict_threshold(self):
        pipeline = AutoencoderInference(self.path)
        original = self.frame.copy()
        results = pipeline.predict(self.frame[["b", "a"]], batch_size=2)
        np.testing.assert_allclose(results.reconstruction_error, [0., 1., 2., 4., 8.])
        np.testing.assert_array_equal(results.window_count, [1, 2, 3, 2, 1])
        np.testing.assert_array_equal(results.is_anomaly, [False, False, False, True, True])
        self.assertTrue((results.threshold == 2.).all())
        pd.testing.assert_index_equal(results.index, self.frame.index)
        pd.testing.assert_frame_equal(self.frame, original)
        self.assertFalse(pipeline.model.training)
        self.assertTrue(all(parameter.grad is None for parameter in pipeline.model.parameters()))
        pd.testing.assert_frame_equal(results, pipeline.predict(self.frame, batch_size=1))

    def test_overlapping_reconstructions_are_averaged_per_timestep(self):
        pipeline = AutoencoderInference(self.path)

        def reconstruct(x):
            self.assertFalse(torch.is_grad_enabled())
            self.assertFalse(pipeline.model.training)
            return torch.arange(3, dtype=x.dtype)[None, :, None].expand_as(x)

        with patch.object(pipeline.model, "forward", side_effect=reconstruct):
            result = pipeline.predict(np.tile([10., 20.], (5, 1)))
        np.testing.assert_allclose(result.reconstruction_error, [0., 0.5, 5 / 3, 2.5, 4.])

    def test_legacy_calibration_excludes_validation_and_incoming_values(self):
        del self.checkpoint["training_error_mean"], self.checkpoint["training_error_std"]
        torch.save(self.checkpoint, self.path)
        original_checkpoint = self.path.read_bytes()
        np.save(self.root / "normalized_data.npy", self.normalized.astype(np.float32))
        summary = dict(feature_names=["a", "b"], sequence_length=3, training_months=4,
                       matrix_shape=[5, 2])
        (self.root / "training_summary.json").write_text(json.dumps(summary))
        pipeline = AutoencoderInference(self.path)
        training_scores = np.array([0., 1., 2., 4.])
        self.assertEqual(pipeline.training_error_mean, training_scores.mean())
        self.assertEqual(pipeline.training_error_std, training_scores.std(ddof=0))
        expected = training_scores.mean() + 2 * training_scores.std(ddof=0)
        self.assertEqual(pipeline.threshold, expected)
        # Changing validation data must not leak into calibration windows.
        changed = self.normalized.astype(np.float32)
        changed[4] = 1e6
        np.save(self.root / "normalized_data.npy", changed)
        self.assertEqual(AutoencoderInference(self.path).threshold, expected)
        pipeline.predict(self.frame * 100)
        self.assertEqual(pipeline.threshold, expected)
        self.assertEqual(self.path.read_bytes(), original_checkpoint)

    def test_invalid_inputs_are_rejected(self):
        pipeline = AutoencoderInference(self.path)
        missing_month = self.frame.copy()
        missing_month.index = missing_month.index + pd.to_timedelta([0, 0, 31, 31, 31], unit="D")
        cases = [self.frame.iloc[:2], self.frame.drop(columns="a"),
                 self.frame.assign(c=1), self.frame.assign(a=np.nan),
                 self.frame.iloc[::-1], missing_month, np.zeros((5, 3)), np.zeros(5),
                 self.frame.assign(a=1j)]
        for values in cases:
            with self.subTest(values=type(values).__name__), self.assertRaises(ValueError):
                pipeline.predict(values)
        with self.assertRaises(ValueError):
            pipeline.predict(self.frame, batch_size=0)

    def test_mismatched_scaler_is_rejected(self):
        scaler = np.load(self.root / "scaler.npy", allow_pickle=False)
        np.save(self.root / "scaler.npy", scaler[::-1])
        with self.assertRaisesRegex(ValueError, "feature order"):
            AutoencoderInference(self.path)

    def test_missing_training_calibration_never_uses_input_data(self):
        del self.checkpoint["training_error_mean"], self.checkpoint["training_error_std"]
        torch.save(self.checkpoint, self.path)
        with self.assertRaises(FileNotFoundError):
            AutoencoderInference(self.path)

    def test_training_saves_calibration_for_best_checkpoint(self):
        frame = pd.DataFrame(np.random.default_rng(0).normal(size=(60, 2)),
                             index=pd.date_range("2000", periods=60, freq="MS"), columns=["a", "b"])
        with patch("backend.ml.train_autoencoder.load_monthly_data", return_value=(frame, {}, [])):
            report = run(self.root, self.root, epochs=1)
        checkpoint = torch.load(self.path, map_location="cpu", weights_only=True)
        pipeline = AutoencoderInference(self.path)
        scores = pipeline.predict(frame.iloc[:48]).reconstruction_error.to_numpy()
        self.assertAlmostEqual(checkpoint["training_error_mean"], scores.mean(), places=7)
        self.assertAlmostEqual(checkpoint["training_error_std"], scores.std(ddof=0), places=7)
        self.assertEqual(report["anomaly_threshold"], pipeline.threshold)


if __name__ == "__main__":
    unittest.main()
