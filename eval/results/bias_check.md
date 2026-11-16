# Bias check: masked vs unmasked resumes

40 resumes x 200 jobs, our scorer with default weights.

| Measure | Mean | Min |
|---|---:|---:|
| Kendall tau, full ranking | 0.942 | 0.907 |
| Top-10 overlap | 0.93 | 0.80 |
| Mean absolute score change | 0.0074 | - |
| Kendall tau, SBERT whole-doc baseline (for comparison) | 0.763 | 0.656 |

Masking replaces name, email, phone, profile links, gendered words and college name before embedding. A tau near 1 says those details barely influence the ranking; whatever influence remains comes from the whole-resume embedding, which is why bias-aware mode is on by default.
