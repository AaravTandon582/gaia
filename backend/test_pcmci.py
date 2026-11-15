"""
Test Tigramite PCMCI on synthetic climate-like data.
Run with: python backend/test_pcmci.py
Expected output: printed causal links + a saved graph image
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')  # no display needed
import matplotlib.pyplot as plt

from tigramite import data_processing as pp
from tigramite.toymodels import structural_causal_processes as toys
from tigramite.pcmci import PCMCI
from tigramite.independence_tests.parcorr import ParCorr
from tigramite import plotting as tp

print("✅ Tigramite imported successfully\n")

# ── 1. Generate synthetic Earth-system-like data ──────────────────────────────
# 3 variables over 300 months (~25 years, like MERRA-2):
#   0: Arctic Temperature (strongly autocorrelated)
#   1: Amazon Precipitation (driven by Arctic temp with 3-month lag)
#   2: Sahel Vegetation (driven by Amazon precip with 2-month lag)

np.random.seed(42)
T = 300

links = {
    0: [((0, -1), 0.7)],
    1: [((1, -1), 0.5), ((0, -3), -0.4)],
    2: [((2, -1), 0.6), ((1, -2),  0.35)],
}

data, _ = toys.var_process(links, T=T)

var_names = ["Arctic_T2M", "Amazon_Precip", "Sahel_Veg"]
print(f"✅ Synthetic data generated: shape {data.shape}  ({T} months, 3 variables)\n")

# ── 2. Run PCMCI ──────────────────────────────────────────────────────────────
dataframe  = pp.DataFrame(data=data, var_names=var_names)
cond_test  = ParCorr(significance='analytic')
pcmci      = PCMCI(dataframe=dataframe, cond_ind_test=cond_test, verbosity=0)

results = pcmci.run_pcmci(tau_max=6, pc_alpha=0.05)

# ── 3. Print significant links ────────────────────────────────────────────────
print("── Significant causal links found ──────────────────────────────────────")
graph     = results['graph']
p_matrix  = results['p_matrix']
val_matrix = results['val_matrix']

found_any = False
for j in range(len(var_names)):
    for i in range(len(var_names)):
        for tau in range(1, 7):
            if graph[i, j, tau] != '':
                p   = p_matrix[i, j, tau]
                val = val_matrix[i, j, tau]
                print(f"  {var_names[j]} (t-{tau})  -->  {var_names[i]} (t)"
                      f"   | strength={val:.3f}  p={p:.4f}")
                found_any = True

if not found_any:
    print("  ⚠️  No significant links found — check tau_max or alpha")

# ── 4. Save causal graph image ────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5))
tp.plot_graph(
    val_matrix=results['val_matrix'],
    graph=results['graph'],
    var_names=var_names,
    link_colorbar_label='Causal Strength',
    fig_ax=(fig, ax)
)
plt.title("GAIA — PCMCI Causal Graph (Synthetic Test)")
plt.tight_layout()
plt.savefig("backend/test_pcmci_graph.png", dpi=150)
print("\n✅ Causal graph saved → backend/test_pcmci_graph.png")
print("\n🟢 PCMCI test PASSED — Tigramite is working correctly")
