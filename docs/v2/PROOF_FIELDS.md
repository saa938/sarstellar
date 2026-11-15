# `web/public/proof.json` fields (science track output)

Every number is measured by the pipeline. Intervals are 95% site-bootstrap intervals. `null` means
"not measured"; show it as not measured, never as zero.

```json
{
  "fixture": false,
  "generated_at": "2026-11-15T20:00:00Z",
  "headline": {
    "reference_sites": 224,          // US sites with independent reference labels
    "train_sites": 164, "test_sites": 60, "test_states": 12,
    "hectares_scored": 2173521,      // blocks in the reference table
    "passes_read": 2650,             // NISAR granule reads behind the site
    "stages": 15, "countries": 9
  },
  "moves": [                          // held-out states, model trained on training states only
    { "id": "fall", "name": "The Fall", "reference": "OPERA DIST-ALERT-HLS",
      "auprc": 0.41, "auprc_ci": [0.30, 0.52], "base_rate": 0.02,
      "precision": 0.5, "recall": 0.6, "f1": 0.55, "f1_ci": [0.4, 0.6], "n_test_blocks": 1234 }
  ],
  "macro_f1": { "value": 0.5, "ci": [0.4, 0.6] },
  "confusion": { "classes": ["still","fall","scorch","vanish","waltz"], "rows_true_cols_pred": [[0]] },
  "polarization": {                   // the measured answer to "which polarizations highlight these changes"
    "classes": ["fall", "scorch", "vanish", "waltz"],
    "variants": [
      { "name": "HH only", "auprc": { "fall": 0.2 }, "auprc_ci": { "fall": [0.1, 0.3] } },
      { "name": "HV only", "auprc": { "fall": 0.35 }, "auprc_ci": { "fall": [0.25, 0.45] } },
      { "name": "HH + HV", "auprc": { "fall": 0.41 }, "auprc_ci": { "fall": [0.30, 0.52] } }
    ]
  },
  "sentinel1": {                      // NISAR L-band vs Sentinel-1 C-band, forest loss, same blocks
    "n_sites": 37, "recall": 0.5,
    "precision_nisar": 0.311, "precision_s1": 0.040, "ratio": 7.8,
    "auprc_nisar": 0.283, "auprc_nisar_ci": [0.185, 0.408],
    "auprc_s1": 0.033, "auprc_s1_ci": [0.023, 0.056]
  },
  "cross_continent": [                // trained on US sites only, scored abroad
    { "stage": "rondonia", "move": "fall", "reference": "OPERA DIST-ALERT-HLS",
      "auprc": 0.3, "base_rate": 0.01, "n_blocks": 100000 }
  ],
  "limits": [ "Plain-language limitation.", "..." ]
}
```

Base rate matters: an AUPRC is only meaningful next to the share of positives (a random guess
scores the base rate). Show both.
