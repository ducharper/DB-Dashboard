from __future__ import annotations
 
import warnings
 
import numpy as np
import pandas as pd
from scipy.special import expit, ndtri
 
EPS = 1e-4
REQUIRED = ["window_id", "group", "tau", "p_model", "outcome"]
 

def check_observations(obs: pd.DataFrame) -> None:
    """Fail loudly on the mistakes that would otherwise produce plausible-looking nonsense."""

    missing = [c for c in REQUIRED if c not in obs.columns]
    if missing:
        raise ValueError(f"observations are missing columns: {missing}")
    if obs.empty:
        raise ValueError("observations are empty")
    for col in ("p_model", "p_market"):
        if col in obs.columns:
            v = obs[col].dropna()
            if ((v < 0) | (v > 1)).any():
                raise ValueError(f"{col} has values outside [0, 1]. If these are Kalshi "
                                 f"prices in cents, divide by 100 first.")
    o = obs["outcome"].dropna()
    if not o.isin([0, 1]).all():
        raise ValueError("outcome must be 1 (Yes), 0 (No) or NaN (not settled yet)")
    dup = obs.duplicated(subset=["window_id", "tau"], keep=False)
    if dup.any():
        raise ValueError(f"{int(dup.sum())} rows share a (window_id, tau); duplicates would "
                         f"double-count windows. Drop them first.")
 

def _clip(p):
    return np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
 
 
def _logit(p):
    p = _clip(p)
    return np.log(p / (1 - p))
 
 
def brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))
 
 
def _ll_rows(p, y):
    p, y = _clip(p), np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))
 
 
def log_loss(p, y):
    return float(np.mean(_ll_rows(p, y)))
 

def reliability_table(p, y, bins=10):
    """Predicted vs realised frequency by probability bucket.
 
    `gap_z` is the gap in binomial standard errors assuming independent rows (optimistic;
    use the bootstrap numbers in `evaluate` for formal judgements).
    """

    p, y = np.asarray(p, float), np.asarray(y, float)
    edges = np.linspace(0, 1, bins + 1)
    b = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows = []
    for k in range(bins):
        m = b == k
        n = int(m.sum())
        if n == 0:
            continue
        mp, f = p[m].mean(), y[m].mean()
        se = np.sqrt(max(mp * (1 - mp), 1e-12) / n)
        rows.append(dict(bucket=f"{edges[k]:.1f}-{edges[k + 1]:.1f}", n=n,
                         mean_p=mp, freq=f, gap=f - mp, gap_z=(f - mp) / se))
    return pd.DataFrame(rows)
 
 
def reliability_by_tau(obs, bins=10) -> pd.DataFrame:
    """reliability_table for every checkpoint, stacked, using settled rows only."""

    o = obs.dropna(subset=["p_model", "outcome"])
    parts = []
    for tau, g in o.groupby("tau"):
        t = reliability_table(g["p_model"], g["outcome"], bins)
        t.insert(0, "tau", int(tau))
        parts.append(t)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
 
 
def logit_fit(X, y, iters=60, ridge=1e-6):
    """Plain logistic regression by Newton's method. Returns [intercept, *coefs]."""

    X = np.asarray(X, float)
    if X.ndim == 1:
        X = X[:, None]
    y = np.asarray(y, float)
    X1 = np.column_stack([np.ones(len(X)), X])
    beta = np.zeros(X1.shape[1])
    for _ in range(iters):
        p = expit(X1 @ beta)
        w = p * (1 - p)
        grad = X1.T @ (y - p) - ridge * beta
        H = (X1 * w[:, None]).T @ X1 + ridge * np.eye(len(beta))
        step = np.clip(np.linalg.solve(H, grad), -3, 3)
        beta += step
        if np.max(np.abs(step)) < 1e-9:
            break
    return beta
 
 
def calibration_fit(p, y):
    """(intercept a, slope b) of y ~ a + b*logit(p). Perfect calibration: (0, 1)."""

    a, b = logit_fit(_logit(p), y)[:2]
    return float(a), float(b)
 

def cluster_bootstrap(groups, fn, arrays, n_boot=400, seed=0):
    """Resample whole clusters with replacement; returns array (n_boot, k) of fn outputs."""

    groups = np.asarray(groups)
    _, inv = np.unique(groups, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    counts = np.bincount(inv)
    members = np.split(order, np.cumsum(counts)[:-1])
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(members), len(members))
        idx = np.concatenate([members[i] for i in pick])
        out.append(np.atleast_1d(fn(*[a[idx] for a in arrays])))
    return np.array(out, dtype=float)
 
 
def _interval(est, draws, alpha):
    """Normal interval around the estimate using the bootstrap standard error."""

    zc = ndtri(1 - alpha / 2)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        se = np.nanstd(draws, axis=0, ddof=1)
    return est - zc * se, est + zc * se
 

def evaluate(obs: pd.DataFrame, n_boot=400, min_windows=300, min_clusters=30,
             alpha=0.01, seed=0):
    """Per-checkpoint scorecard. Returns a DataFrame; see `format_report`."""

    check_observations(obs)
    has_z = "z" in obs and obs["z"].notna().any()
    has_m = "p_market" in obs and obs["p_market"].notna().any()
    rows = []
 
    for tau, g in obs.dropna(subset=["p_model", "outcome"]).groupby("tau"):
        p, y = g["p_model"].to_numpy(float), g["outcome"].to_numpy(float)
        z = g["z"].to_numpy(float) if has_z else np.full(len(g), np.nan)
        pm = g["p_market"].to_numpy(float) if has_m else np.full(len(g), np.nan)
        has_q = np.isfinite(pm)
        n_win, n_clu = g["window_id"].nunique(), g["group"].nunique()
        n_win_m = g.loc[has_q, "window_id"].nunique()
 
        def stats(p_, y_, z_, pm_):
            a, b = calibration_fit(p_, y_)
            zf = z_[np.isfinite(z_)]
            zm = zf.mean() if len(zf) else np.nan
            zr = np.sqrt(np.mean(zf ** 2)) if len(zf) else np.nan
            q = np.isfinite(pm_)
            if q.sum() >= 30:
                d = log_loss(p_[q], y_[q]) - log_loss(pm_[q], y_[q])
                coef = logit_fit(np.column_stack([_logit(p_[q]), _logit(pm_[q])]), y_[q])
                b_mod, b_mkt = coef[1], coef[2]
            else:
                d = b_mod = b_mkt = np.nan
            return np.array([a, b, zm, zr, d, b_mod, b_mkt])
 
        est = stats(p, y, z, pm)
        draws = cluster_bootstrap(g["group"].to_numpy(), stats, [p, y, z, pm],
                                  n_boot=n_boot, seed=seed)
        lo, hi = _interval(est, draws, alpha)
        a, b, zm, zr, d, b_mod, b_mkt = est
 
        enough = n_win >= min_windows and n_clu >= min_clusters
        flags = []
        if n_win < min_windows:
            verdict = f"INCONCLUSIVE (<{min_windows} windows)"
        elif n_clu < min_clusters:
            verdict = f"INCONCLUSIVE (<{min_clusters} clusters; use a finer `group`)"
        else:
            if not lo[0] <= 0 <= hi[0]:
                flags.append("leans Yes" if a > 0 else "leans No")
            if hi[1] < 1:
                flags.append("overconfident")
            elif lo[1] > 1:
                flags.append("underconfident")
            if has_z and np.isfinite(zr):
                if lo[3] > 1:
                    flags.append("sigma too LOW")
                elif hi[3] < 1:
                    flags.append("sigma too HIGH")
                if not lo[2] <= 0 <= hi[2]:
                    flags.append("mean bias")
            verdict = "PASS" if not flags else "FLAG: " + ", ".join(flags)
 
        if not has_m:
            vs = "n/a"
        elif not (n_win_m >= min_windows and n_clu >= min_clusters and np.isfinite(d)):
            vs = "n/a (too few quotes)"
        else:
            vs = "model better" if hi[4] < 0 else ("market better" if lo[4] > 0 else "no difference")
 
        zf = z[np.isfinite(z)]
        rows.append(dict(
            tau=int(tau), windows=n_win, clusters=n_clu, brier=brier(p, y),
            logloss=log_loss(p, y),
            cal_a=a, cal_a_lo=lo[0], cal_a_hi=hi[0],
            cal_b=b, cal_b_lo=lo[1], cal_b_hi=hi[1],
            z_mean=zm, z_rms=zr, z_rms_lo=lo[3], z_rms_hi=hi[3],
            tail_gt2=float(np.mean(np.abs(zf) > 2)) if len(zf) else np.nan,
            quotes=n_win_m,
            mkt_brier=brier(pm[has_q], y[has_q]) if has_q.any() else np.nan,
            mkt_logloss=log_loss(pm[has_q], y[has_q]) if has_q.any() else np.nan,
            dbrier=(brier(p[has_q], y[has_q]) - brier(pm[has_q], y[has_q])) if has_q.any() else np.nan,
            dlogloss=d, dlogloss_lo=lo[4], dlogloss_hi=hi[4],
            enc_model=b_mod, enc_market=b_mkt, vs_market=vs, verdict=verdict))
    return pd.DataFrame(rows)
 
 
def format_report(summary: pd.DataFrame, title="Fair-value model validation") -> str:
    s = summary
    cols = ["tau", "windows", "clusters", "brier", "logloss", "cal_a", "cal_b",
            "z_mean", "z_rms", "tail_gt2"]
    if s["mkt_logloss"].notna().any():
        cols += ["quotes", "mkt_brier", "dbrier", "mkt_logloss", "dlogloss",
                 "enc_model", "enc_market", "vs_market"]
    lines = [title, "=" * len(title),
             s[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"), ""]
    for _, r in s.iterrows():
        lines.append(f"  tau={r.tau:>4}s  {r.verdict}")
    lines += ["",
              "Reading guide:",
              "  cal_b < 1 overconfident | > 1 underconfident | cal_a != 0 leans one way",
              "  z_rms: multiply sigma by this to fix scale (expect 1.00); tail_gt2 expect 0.046",
              "  dbrier / dlogloss = model - market on rows with a quote (negative = model better);",
              "         only dlogloss has a confidence interval and drives `vs_market`",
              "  enc_*: weights in logit(P) ~ model + market. Unstable when model ~ market;",
              "         only read them when the two disagree materially"]
    return "\n".join(lines)
 
 
def report(obs, buckets=False, **kw) -> pd.DataFrame:
    """Print the scorecard. buckets=True also prints the reliability table per checkpoint."""

    summary = evaluate(obs, **kw)
    print(format_report(summary))
    if buckets:
        print("\nReliability by checkpoint (mean_p vs freq should match):")
        print(reliability_by_tau(obs).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    return summary