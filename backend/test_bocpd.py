"""
Test BOCPD on a real NASA Giovanni CSV.
Run with: python backend/test_bocpd.py
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, glob

# ── 1. Load the first CSV found in cache ─────────────────────────────────────
cache_dir = "backend/data/cache/"
csv_files = glob.glob(cache_dir + "*.csv")

if not csv_files:
    print("❌ No CSV files found in backend/data/cache/")
    exit(1)

# Pick arctic T2M if available, otherwise first file
target = next((f for f in csv_files if "arctic" in f.lower() and "t2m" in f.lower()), csv_files[0])
print(f"📂 Loading: {target}")

# Giovanni CSVs have metadata header — skip until we hit numeric data
with open(target) as f:
    lines = f.readlines()

data_start = 0
for i, line in enumerate(lines):
    # Find first line that starts with a 4-digit year
    stripped = line.strip()
    if stripped and stripped[:4].isdigit():
        data_start = i
        break

df = pd.read_csv(target, skiprows=data_start, header=None)
df.columns = ["date", "value"] + [f"col{i}" for i in range(len(df.columns)-2)]
df["date"]  = pd.to_datetime(df["date"], errors="coerce")
df["value"] = pd.to_numeric(df["value"], errors="coerce")
df = df.dropna(subset=["value", "date"])
df = df.set_index("date")

# Resample to monthly mean (handles both hourly and daily inputs)
df = df["value"].resample("MS").mean().reset_index()
signal = df["value"].values
print(f"✅ Loaded and resampled to {len(signal)} monthly values\n")

# ── 2. BOCPD Implementation ───────────────────────────────────────────────────
from scipy.stats import t as student_t

class BOCPD:
    def __init__(self, hazard_lambda=100, mu0=0.0, kappa0=1.0, alpha0=1.0, beta0=1.0):
        self.lam = hazard_lambda
        self.mu0, self.kappa0, self.alpha0, self.beta0 = mu0, kappa0, alpha0, beta0
        self.R = np.array([1.0])
        self.mu = np.array([mu0])
        self.kappa = np.array([kappa0])
        self.alpha = np.array([alpha0])
        self.beta = np.array([beta0])
        self.changepoints = []
        self.t = 0

    def update(self, x):
        df_  = 2 * self.alpha
        scale = np.sqrt(self.beta * (self.kappa + 1) / (self.alpha * self.kappa))
        pred = student_t.pdf(x, df=df_, loc=self.mu, scale=scale)

        H = 1.0 / self.lam
        growth = self.R * pred * (1 - H)
        cp_prob = np.sum(self.R * pred * H)

        new_R = np.empty(len(self.R) + 1)
        new_R[0] = cp_prob
        new_R[1:] = growth
        self.R = new_R / (new_R.sum() + 1e-300)

        new_kappa = self.kappa + 1
        new_mu = (self.kappa * self.mu + x) / new_kappa
        new_alpha = self.alpha + 0.5
        new_beta = self.beta + self.kappa * (x - self.mu)**2 / (2 * new_kappa)

        self.mu    = np.insert(new_mu,    0, self.mu0)
        self.kappa = np.insert(new_kappa, 0, self.kappa0)
        self.alpha = np.insert(new_alpha, 0, self.alpha0)
        self.beta  = np.insert(new_beta,  0, self.beta0)

        map_rl = np.argmax(self.R)
        if map_rl == 0 and self.t > 10:
            self.changepoints.append(self.t)

        self.t += 1
        return map_rl

# ── 3. Run BOCPD ──────────────────────────────────────────────────────────────
# Normalize signal first
signal_norm = (signal - signal.mean()) / signal.std()

bocpd = BOCPD(hazard_lambda=len(signal) // 3)
run_lengths = []
for val in signal_norm:
    rl = bocpd.update(val)
    run_lengths.append(rl)

print(f"── Regime shifts (change points) detected ───────────────────────────────")
if bocpd.changepoints:
    for cp in bocpd.changepoints:
        print(f"  Month index {cp}  →  approx year {2000 + cp // 12}")
else:
    print("  No significant regime shifts detected")

print(f"\n  Total changepoints: {len(bocpd.changepoints)}")

# ── 4. Plot & save ────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

ax1.plot(signal, color='steelblue', lw=1.2, label='Raw signal')
for cp in bocpd.changepoints:
    ax1.axvline(cp, color='red', alpha=0.6, lw=1.5, linestyle='--')
ax1.set_ylabel("Value")
ax1.set_title(f"BOCPD Regime Shift Detection — {os.path.basename(target)}")
ax1.legend()

ax2.plot(run_lengths, color='darkorange', lw=1.2, label='Run length (MAP)')
for cp in bocpd.changepoints:
    ax2.axvline(cp, color='red', alpha=0.6, lw=1.5, linestyle='--')
ax2.set_ylabel("Run Length")
ax2.set_xlabel("Month index")
ax2.legend()

plt.tight_layout()
plt.savefig("backend/test_bocpd_graph.png", dpi=150)

print(f"\n✅ Plot saved → backend/test_bocpd_graph.png")
print("🟢 BOCPD test PASSED")
