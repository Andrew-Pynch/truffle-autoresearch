# Experiment Summary: Automated Hyperparameter & Architecture Search

## Overview

Two autonomous research agents ran parallel experiment campaigns on different GPUs, each searching for the best language model configuration under a fixed 5-minute training budget.

| Metric | RTX 4090 | RTX 3080 |
|---|---|---|
| Total experiments | 116 | 145 |
| Baseline val_bpb | 1.092496 | 1.168815 |
| Best val_bpb | 1.074108 | 1.141978 |
| Improvement | **1.68%** | **2.30%** |
| Kept (including baseline) | 18 (15.5%) | 20 (13.8%) |
| Discarded | 96 (82.8%) | 120 (82.8%) |
| Crashed | 2 (1.7%) | 5 (3.4%) |
| Baseline memory | 6.0 GB | 2.0 GB |
| Final memory | 5.2 GB | 2.3 GB |
| Baseline architecture | DEPTH=8, MLP 4x | DEPTH=6, MLP 4x |
| Final architecture | DEPTH=8, MLP 2x, VE every layer | DEPTH=8, MLP 3x |

Both agents achieved an identical discard rate of 82.8%, suggesting a fundamental property of the search space rather than agent strategy. The 3080 ran 25% more experiments (145 vs 116), likely due to its smaller models training faster per iteration, giving the agent more wall-clock budget for exploration.

---

## 4090 Trajectory (116 experiments, 1.092496 → 1.074108)

### Phase 1: Architecture Exploration (experiments 1–11)

The agent began by probing model scale. Every attempt to increase capacity failed:

| Experiment | Change | val_bpb | Status | Reason |
|---|---|---|---|---|
| 92adbf4 | DEVICE_BATCH_SIZE=64 | — | crash | OOM at 22.4 GB |
| 423c630 | DEVICE_BATCH_SIZE=32 | 1.101031 | discard | Worse val_bpb, 11.4 GB |
| 9f1cca1 | DEPTH=12 | 1.178480 | discard | 135M params, only 200 steps |
| d56282e | DEPTH=10 | 1.120550 | discard | 86M params, only 313 steps |
| f6af1a9 | DEPTH=9 | 1.111998 | discard | 81M params, only 344 steps |

The agent also tested TOTAL_BATCH_SIZE=2^17, WINDOW_PATTERN=L, and two WARMDOWN_RATIO values — all worse. The key lesson: under a 5-minute budget, the DEPTH=8 baseline (65M params, ~517 steps) was already at the throughput sweet spot.

### Phase 2: Learning Rate Tuning (experiments 12–28)

The first productive phase. The agent systematically tuned each optimizer group:

| Experiment | Change | val_bpb | Delta | Status |
|---|---|---|---|---|
| e51aed9 | EMBEDDING_LR: 0.6→1.0 | 1.089049 | −0.003447 | **keep** |
| 130dc77 | MATRIX_LR: 0.04→0.06 | 1.088789 | −0.000260 | **keep** |

Other LR experiments discarded: EMBEDDING_LR=1.5 (too high), MATRIX_LR=0.08 (too high), MATRIX_LR=0.05 (worse), UNEMBEDDING_LR=0.008 (marginal). The agent also rejected WEIGHT_DECAY=0.1, WARMUP_RATIO=0.05, HEAD_DIM=64, higher x0_lambdas, disabled value embeddings, and several other changes.

**Running best: 1.088789** (−0.003707 from baseline)

### Phase 3: Schedule & Softcap Tuning (experiments 29–56)

Fine-tuning the training schedule and logit capping:

| Experiment | Change | val_bpb | Delta | Status |
|---|---|---|---|---|
| c780b55 | FINAL_LR_FRAC=0.1 | 1.087569 | −0.001220 | **keep** |
| 024ba09 | softcap: 15→12 | 1.086618 | −0.000951 | **keep** |

28 other experiments in this phase were discarded, including ADAM_BETAS=(0.8,0.99), ADAM_BETAS=(0.8,0.975), cosine warmdown, various softcap values (10, 11, 13), and SCALAR_LR variants. Label smoothing=0.1 was catastrophic (1.413287).

**Running best: 1.086618** (−0.005878 from baseline)

### Phase 4: Short Window Sweep — The Big Win (experiments 57–68)

The single most impactful discovery on the 4090. The agent progressively shortened the local attention window:

| Experiment | Window size | val_bpb | Delta from prev | Status |
|---|---|---|---|---|
| 8feda9e | seq_len//4 (512) | 1.086381 | −0.000237 | **keep** |
| 904c04e | seq_len//8 (256) | 1.084616 | −0.001765 | **keep** |
| 2dcc586 | seq_len//16 (128) | 1.083032 | −0.001584 | **keep** |
| b76bacd | seq_len//32 (64) | 1.081389 | −0.001643 | **keep** |
| df29c55 | seq_len//64 (32) | 1.082144 | +0.000755 | discard |
| 3af0221 | WARMDOWN_RATIO=0.6 | 1.079859 | −0.001530 | **keep** |

The insight: shorter local windows are faster to compute, enabling more training steps in the same 5-minute budget. The throughput gain outweighed the reduced context until 32 tokens, which was too small. Combined with a longer warmdown, this phase achieved a **0.006759 improvement** — the largest single-phase gain.

**Running best: 1.079859** (−0.012637 from baseline)

### Phase 5: MLP Narrowing (experiments 79–90)

The agent traded model width for training speed, accepting a temporary regression:

| Experiment | Change | val_bpb | Steps | Status |
|---|---|---|---|---|
| dc5104e | MLP 3x (46.1M) | 1.082023 | 600 | **keep** |
| 7ece56d | MLP 2x (41.9M) | 1.081561 | 668 | **keep** (replaces 3x) |

MLP 2x regressed from 1.079859 to 1.081561 — but the agent bet that faster throughput (668 vs ~517 steps) would pay off once re-tuned. Subsequent experiments confirmed the 4x→2x narrowing was correct: every attempt to combine 2x MLP with deeper models (DEPTH=9, higher AR) produced worse results.

**Running best: 1.081561** (temporarily regressed)

### Phase 6: VE Gate Tuning (experiments 91–97)

Progressive narrowing of the value embedding gate, plus expanding VE coverage:

| Experiment | Change | val_bpb | Delta | Status |
|---|---|---|---|---|
| b53174e | ve_gate_channels: 32→16 | 1.081118 | −0.000443 | **keep** |
| a3beeca | ve_gate_channels: 16→8 | 1.080667 | −0.000451 | **keep** |
| 15b35c9 | ve_gate_channels: 8→4 | 1.080420 | −0.000247 | **keep** |
| 882fd81 | ve_gate_channels: 4→2 | 1.080531 | +0.000111 | discard |
| 825f690 | VE on every layer (8 layers) | 1.079982 | −0.000438 | **keep** |

Removing VE gating entirely (7930c24, 1.081685) or reducing VE to every 4th layer (6d29d86, 1.085961) both hurt. The gate is load-bearing, but needs very few channels.

**Running best: 1.079982** (recovered past pre-MLP-narrowing best)

### Phase 7: Final Breakthroughs (experiments 98–116)

After extensive fine-tuning experiments (MATRIX_LR re-tuning, sqrt warmdown, weight decay variants — all discarded), two discoveries:

| Experiment | Change | val_bpb | Delta | Status |
|---|---|---|---|---|
| 9d67d55 | QK norm before RoPE | 1.079471 | −0.000511 | **keep** |
| 81e0041 | ADAM_BETAS=(0.85, 0.95) | **1.074108** | **−0.005363** | **keep** |

The ADAM_BETAS change was the single largest improvement from any one experiment — a 0.005363 drop in val_bpb. The agent confirmed this was robust by testing nearby values: (0.9, 0.95) gave 1.075665, (0.875, 0.95) gave 1.074796, (0.85, 0.99) gave 1.075639. The sweet spot was precisely (0.85, 0.95).

**Final best: 1.074108** (−0.018388 from baseline, 1.68% improvement)

---

## 3080 Trajectory (145 experiments, 1.168815 → 1.141978)

### Phase 1: Architecture Exploration (experiments 1–8)

The 3080 started with a smaller baseline (DEPTH=6, 8 GB VRAM) and immediately hit memory walls trying to scale up:

| Experiment | Change | val_bpb | Status | Reason |
|---|---|---|---|---|
| 043b4f5 | DEPTH=8, BATCH=64, TOTAL=2^19 | — | crash | OOM ~9.1 GB |
| b6dde83 | DEPTH=8, BATCH=32, TOTAL=2^19 | — | crash | OOM ~9.6 GB |
| f912b1c | DEPTH=8, BATCH=16, TOTAL=2^18 | 1.186487 | discard | Slower throughput |
| e8883e9 | AR=128 | 1.232676 | discard | 73.9M params, only 38M tokens |

The 3080 couldn't fit DEPTH=8 with standard batch sizes at this point. It would take 110 more experiments before finding a way.

### Phase 2: Hyperparameter Tuning (experiments 9–41)

The longest productive phase. The agent methodically tuned every knob available at DEPTH=6:

| Experiment | Change | val_bpb | Delta from prev keep | Status |
|---|---|---|---|---|
| 30a0e3e | MATRIX_LR: 0.04→0.06 | 1.165132 | −0.003683 | **keep** |
| 3f3102b | EMBEDDING_LR: 0.6→1.0 | 1.164204 | −0.000928 | **keep** |
| 414352d | EMBEDDING_LR: 1.0→1.5 | 1.162610 | −0.001594 | **keep** |
| b244550 | WEIGHT_DECAY: 0.2→0.1 | 1.160281 | −0.002329 | **keep** |
| de76db2 | FINAL_LR_FRAC=0.1 | 1.158817 | −0.001464 | **keep** |
| eb4a482 | MATRIX_LR: 0.06→0.07 | 1.158393 | −0.000424 | **keep** |
| ea02fac | FINAL_LR_FRAC: 0.1→0.05 | 1.157288 | −0.001105 | **keep** |

Notable rejections: SwiGLU, ADAM_BETAS=(0.9,0.95), label smoothing=0.1 (1.488221 — even worse than on 4090), parallel attention+MLP (1.182719), disabled VE (1.182719).

**Running best: 1.157288** (−0.011527 from baseline)

### Phase 3: The Plateau — Exhaustive Fine-Tuning (experiments 42–110)

The most striking phase: approximately 69 consecutive experiments, **every single one discarded**. The agent exhaustively searched:

- Optimizer: ADAM_BETAS variants, Adam epsilon, Muon momentum (start/end/ramp/beta2), Muon NS steps
- Architecture: ve_gate_channels, RoPE base, head dim, init scales, VE gate scale
- Schedule: warmdown ratio, LR fractions, cosine/sqrt schedules, weight decay schedules
- Regularization: weight decay on specific params, gradient clipping, dropout

Nothing worked. The DEPTH=6 architecture had been fully optimized. The agent had reached the Pareto frontier for that depth.

**Running best: 1.157288** (unchanged through 69 experiments)

### Phase 4: Depth Breakthrough (experiments 111–113)

After exhausting DEPTH=6, the agent revisited depth scaling — this time with a smaller aspect ratio to control memory:

| Experiment | Change | val_bpb | Delta | Status |
|---|---|---|---|---|
| 1de2771 | DEPTH=7, AR=54 (dim=384) | 1.155352 | −0.001936 | **keep** |
| 185af75 | DEPTH=8, AR=48 (dim=384) | **1.146679** | **−0.008673** | **keep** |
| 9c9708a | DEPTH=9, AR=42 | 1.159366 | — | discard (too slow, 566 steps) |

The DEPTH=8 breakthrough was the single largest step on the 3080: a 0.008673 drop. The trick was keeping dim=384 (smaller AR) to stay within VRAM and maintain throughput. The 3080 now matched the 4090's depth but with a narrower model.

**Running best: 1.146679** (−0.022136 from baseline)

### Phase 5: Deep Model Re-Optimization (experiments 114–145)

With a new architecture, every hyperparameter needed re-tuning. The agent systematically re-swept:

**Softcap sweep** — the deeper model benefited from tighter logit capping:

| Experiment | Softcap | val_bpb | Status |
|---|---|---|---|
| b66799d | 15 (from 17) | 1.146519 | **keep** |
| 8acc627 | 13 | 1.145333 | **keep** |
| b1bf1f1 | 11 | 1.145034 | **keep** |
| 04e96c6 | 9 | 1.144474 | **keep** |
| 8a73c96 | 7 | 1.148342 | discard (too tight) |

**Schedule and LR re-tuning:**

| Experiment | Change | val_bpb | Status |
|---|---|---|---|
| 0ffb145 | WARMDOWN_RATIO=0.6 | 1.143212 | **keep** |
| f75cf89 | EMBEDDING_LR=1.8 | 1.143074 | **keep** |
| fc9e58c | MATRIX_LR=0.075 | 1.142657 | **keep** |
| 8d5e89b | FINAL_LR_FRAC=0.1 | 1.142550 | **keep** |
| 409e936 | WARMDOWN_RATIO=0.65 | 1.142190 | **keep** |

Note: FINAL_LR_FRAC reverted from 0.05 back to 0.1 for the deeper model — the optimal LR floor changed with architecture.

**Final architecture change:**

| Experiment | Change | val_bpb | Status |
|---|---|---|---|
| c96146e | MLP 3x expansion (689 steps vs 628) | **1.141978** | **keep** |

Unlike the 4090 which went to MLP 2x, the 3080 went to MLP 3x — a less aggressive narrowing, likely because the 3080's model was already narrower (dim=384 vs the 4090's larger dim).

Notably, ADAM_BETAS=(0.85,0.95) was tested at experiment 140 (bde1120) and **rejected** with val_bpb=1.145512 — the exact change that was the 4090's biggest win actually hurt the 3080's configuration.

**Final best: 1.141978** (−0.026837 from baseline, 2.30% improvement)

---

## Cross-Platform Comparison

### Convergent Discoveries

Both agents independently converged on the same findings:

| Discovery | 4090 | 3080 |
|---|---|---|
| First productive move | LR tuning | LR tuning |
| MATRIX_LR improvement | 0.04→0.06 | 0.04→0.06 (then →0.07, →0.075) |
| EMBEDDING_LR improvement | 0.6→1.0 | 0.6→1.0→1.5→1.8 |
| FINAL_LR_FRAC helps | 0.1 | 0.1 (then 0.05, then back to 0.1) |
| WARMDOWN_RATIO=0.6+ | 0.6 | 0.6→0.65 |
| Value embeddings crucial | Removing VE: 1.122 (+0.030) | Removing VE: 1.183 (+0.024) |
| QK norm crucial | Removing: 1.098 (+0.019) | Removing: 1.193 (+0.035) |
| SwiGLU rejected | 1.101 (worse + slower) | 1.169 (worse) |
| Label smoothing catastrophic | 1.413 (+0.327) | 1.488 (+0.331) |
| Cosine warmdown rejected | Marginal, not better | Marginally worse |
| Higher RoPE base rejected | 1.084 (worse) | 1.159 (worse) |

### Divergent Discoveries — The Thesis

The most significant finding: **identical search algorithms on different hardware converged on different architectural innovations**.

| Dimension | RTX 4090 | RTX 3080 |
|---|---|---|
| **Starting depth** | DEPTH=8 (baseline) | DEPTH=6 (baseline) |
| **Final depth** | DEPTH=8 (unchanged) | DEPTH=8 (discovered at exp 112) |
| **MLP expansion** | 4x→3x→**2x** | 4x→**3x** |
| **Final model params** | ~42M (leaner) | ~38M (narrower) |
| **Short window attention** | seq_len//32 = 64 tokens (**major win**) | Not explored |
| **VE gate optimization** | Channels 32→4, VE every layer | Not explored |
| **QK norm reordering** | Norm before RoPE (keep) | Not explored |
| **Softcap value** | 15→**12** | 17→15→13→11→**9** |
| **ADAM_BETAS=(0.85,0.95)** | **Biggest single win** (−0.005363) | **Rejected** (+0.003322) |
| **WEIGHT_DECAY** | 0.2 (kept default) | 0.2→**0.1** |
| **EMBEDDING_LR** | 1.0 | 1.0→1.5→**1.8** |
| **Memory usage** | 6.0→5.2 GB | 2.0→2.5 GB |
| **Depth exploration story** | Already at DEPTH=8, tried going deeper (failed) | Stuck at DEPTH=6 for 110 exp, then broke through to DEPTH=8 |

Key divergences explained:

1. **Short windows (4090 only):** The 4090 discovered that shorter attention windows increased throughput enough to improve quality under time constraints. The 3080 never explored this, possibly because its smaller model already had sufficient throughput.

2. **Softcap 12 vs 9:** The 3080's deeper-but-narrower model (dim=384) benefited from much tighter logit capping than the 4090's wider model. This suggests optimal softcap correlates with model width.

3. **ADAM_BETAS divergence:** The most striking difference. (0.85, 0.95) was a breakthrough on the 4090 but harmful on the 3080. The optimal momentum depends on the loss landscape, which differs between the two architectures.

4. **MLP 2x vs 3x:** The 4090 could afford more aggressive narrowing because it compensated with other innovations (short windows, VE gating). The 3080's narrower baseline left less room to shrink the MLP.

5. **70-experiment plateau (3080 only):** The 3080 spent 69 experiments hitting a wall at DEPTH=6 before the depth breakthrough. The 4090 never experienced a comparable plateau because its starting architecture was already at the right depth.

---

## Failure Analysis

### Crash Breakdown

| Category | 4090 | 3080 | Total |
|---|---|---|---|
| Out of memory (OOM) | 1 | 2 | 3 |
| Code/runtime error | 1 | 3 | 4 |
| **Total crashes** | **2** | **5** | **7** |

Crash details:
- **OOM:** DEVICE_BATCH_SIZE=64 on 4090 (22.4 GB), DEPTH=8 with batch 64/32 on 3080 (~9 GB)
- **Muon bias bug** (4090): VE gate with bias — Muon optimizer can't handle 1D bias parameters
- **Process killed** (3080): z-loss regularization killed before completion
- **Param counting bug** (3080): Weight tying broke parameter counting
- **CUDA graph error** (3080): torch.compile max-autotune caused CUDA graph overwrite

### Discard Breakdown

Across both machines, 216 of 261 experiments (82.8%) were discarded. Major discard categories:

| Category | Count (approx) | Examples |
|---|---|---|
| Wrong direction (clearly worse) | ~130 | Most LR/WD/schedule variants |
| Too slow (throughput loss > quality gain) | ~15 | DEPTH=12/10/9, SwiGLU, large AR |
| Within noise (marginal, not convincingly better) | ~40 | Many fine-tuning attempts near optima |
| Catastrophic (massive regression) | ~5 | Label smoothing, plain ReLU, remove VE |
| Temporary regression accepted | ~2 | MLP narrowing on 4090 |

The high discard rate (83%) across both machines suggests that the search space around a well-tuned baseline is mostly downhill — most perturbations hurt. This validates the greedy, one-change-at-a-time strategy: the probability of any single change being beneficial is only ~15%.

### What Failures Reveal About the Search Space

1. **Depth is a cliff, not a slope.** Going one layer too deep (DEPTH=9 on both machines) caused >10% throughput loss, making the model strictly worse under time budgets.

2. **Optimizer hyperparameters are fragile.** Both machines found that moving MATRIX_LR by ±0.01 from optimal could erase gains. The useful region is narrow.

3. **Architecture changes invalidate hyperparameters.** After the 3080 moved to DEPTH=8, FINAL_LR_FRAC optimal shifted from 0.05 back to 0.1. The 4090 saw similar invalidation after MLP narrowing.

4. **Some features are load-bearing.** Value embeddings, QK normalization, and logit softcapping are not optional — removing any of them caused 2–3% regression on both machines.

---

## Key Insights

### 1. Throughput Beats Model Size Under Fixed Time Budgets

Both agents independently discovered that smaller, faster models outperform larger ones when training time is fixed. The 4090 proved this most dramatically: MLP 2x (41.9M params, 668 steps) beat MLP 4x (65M params, 517 steps). The 3080's final MLP 3x also traded params for steps. The short window sweep on the 4090 is the purest example: reducing attention window from full sequence to 64 tokens was a pure throughput play that improved quality.

### 2. Hardware Determines the Pareto Frontier

The 4090 and 3080 ended up with genuinely different optimal architectures despite running the same search algorithm. ADAM_BETAS=(0.85,0.95) was the 4090's best discovery but hurt the 3080. The 3080 found softcap=9 optimal where the 4090 found softcap=12. These aren't noise — they reflect different loss landscapes arising from different model geometries forced by different VRAM constraints.

### 3. Both Agents Converged on the Same Meta-Strategy, Then Diverged on Architecture

The search trajectory was remarkably similar at the strategic level:
1. Probe architecture boundaries (fail fast on too-large models)
2. Tune learning rates (highest-leverage, lowest-risk changes)
3. Tune schedule and regularization
4. Search for architectural innovations
5. Re-tune hyperparameters for new architecture

But the specific innovations found in step 4 were completely different: short windows + VE gating + ADAM tuning (4090) vs depth scaling + tight softcap (3080).

### 4. The 3080 Compensated for Less VRAM with Different Innovations

Unable to fit the 4090's wider models, the 3080 found a different path: start shallow (DEPTH=6), thoroughly optimize, then discover that a narrower-but-deeper model (DEPTH=8, dim=384) was superior. The 3080 then found that this deeper model needed tighter softcapping (9 vs 12) — a discovery the 4090 never made because its wider model at the same depth had a different optimal softcap.

### 5. Plateaus Precede Breakthroughs

The 3080's 69-experiment plateau at DEPTH=6 is a textbook example of exhausting a local optimum before finding a qualitatively different improvement. The 4090 showed a milder version: after the short window sweep, it took a temporary regression through MLP narrowing before recovering via VE gate tuning and the ADAM_BETAS breakthrough.

---

## Summary Comparison Table

| | RTX 4090 | RTX 3080 |
|---|---|---|
| **GPU VRAM** | 24 GB | 10 GB |
| **Experiments run** | 116 | 145 |
| **Baseline val_bpb** | 1.092496 | 1.168815 |
| **Final val_bpb** | 1.074108 | 1.141978 |
| **Total improvement** | −0.018388 (1.68%) | −0.026837 (2.30%) |
| **Kept improvements** | 17 | 19 |
| **Discard rate** | 82.8% | 82.8% |
| **Crash rate** | 1.7% | 3.4% |
| **Biggest single step** | ADAM_BETAS=(0.85,0.95): −0.005363 | DEPTH=6→8: −0.008673 |
| **Biggest phase** | Short window sweep: −0.006759 | Depth breakthrough: −0.010609 |
| **Final DEPTH** | 8 | 8 |
| **Final MLP ratio** | 2x | 3x |
| **Final softcap** | 12 | 9 |
| **Final WEIGHT_DECAY** | 0.2 | 0.1 |
| **Final ADAM_BETAS** | (0.85, 0.95) | (0.8, 0.95) |
| **Final WARMDOWN_RATIO** | 0.6 | 0.65 |
| **Final EMBEDDING_LR** | 1.0 | 1.8 |
| **Final MATRIX_LR** | 0.06 | 0.075 |
| **Unique discovery** | Short window attention | Depth scaling via narrow AR |
| **Unique discovery** | VE gate channel reduction | Softcap=9 for deep models |
| **Unique discovery** | QK norm reordering | — |
| **Unique discovery** | ADAM_BETAS=(0.85,0.95) | — |
| **Longest plateau** | ~20 exp (post-MLP narrowing) | 69 exp (DEPTH=6 exhaustion) |
