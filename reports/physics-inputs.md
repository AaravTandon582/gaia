# Water-balance input inventory

Checked 2026-11-15 against `backend/data/cache`, excluding backup copies.

| Region | Precipitation | ET | Runoff | Storage change |
|---|---|---|---|---|
| Amazon | GLDAS rainfall rate | GLDAS ET rate | New GLDAS `Qs_acc` storm surface runoff only | Missing total storage change; shallow soil moisture exists |
| Sahel | GLDAS rainfall rate | FLDAS ET rate | Missing | Missing |
| Mediterranean | GLDAS rainfall rate | GLDAS ET rate | Missing | Missing total storage change; shallow soil moisture exists |
| Arctic | Missing | Missing | Missing | Snow mass exists; total storage change missing |
| California | Missing | Missing | Missing | Shallow soil moisture exists; total storage change missing |

The new Amazon export is
`g4.areaAvgTimeSeries.GLDAS_NOAH025_M_2_1_Qs_acc.20000101-20251231.75W_15S_45W_5N.csv`.
It does not supply subsurface/baseflow runoff (`Qsb_acc`) or a complete storage
change. Do not treat the 0–10 cm soil stock as total storage change, fill missing
terms with zero, or mix kg/m²/s rates with kg/m² accumulations.

Therefore a real `P - ET - Q - dS` residual is **inputs unavailable** for every
current demo region. No numerical real-data residual is claimed. The implemented
function returns numerical residual/error when compatible complete inputs are
provided; balanced and unbalanced synthetic cases are covered by tests.

Before using the runoff export, verify its product's accumulation interval:
a monthly average of subdaily accumulated quantities is not automatically a
monthly total. Verify temporal units, region bounds, total runoff components,
and the definition/interval of storage change together.
