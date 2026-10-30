"""Two-parameter logistic calibration, fitted on earlier settled windows only.

Usage: python -m dashboard.kalshi.research.calibration --observations PATH --output PATH
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

EPS = 1e-4
RIDGE = .001

def model_hash():
    path = Path(__file__).resolve().parents[1] / "fairvalue.py"
    return hashlib.sha256(path.read_bytes()).hexdigest()

def logits(probabilities):
    p = np.asarray(probabilities, dtype=float)
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Probabilities must be finite fractions from 0 to 1.")
    p = np.clip(p, EPS, 1-EPS)
    return np.log(p)-np.log1p(-p)

def predict(probabilities, a, b):
    if not np.isfinite([a,b]).all() or b <= 0:
        raise ValueError("Invalid calibration coefficients.")
    return expit(a+b*logits(probabilities))

def predict_time(probabilities, tau, a, b_late, b_early):
    tau = np.asarray(tau, dtype=float)
    if not np.isfinite(tau).all() or ((tau < 0) | (tau > 900)).any():
        raise ValueError("Time remaining must be finite seconds from 0 to 900.")
    if not np.isfinite([a,b_late,b_early]).all() or min(b_late,b_early) <= 0:
        raise ValueError("Invalid time-aware coefficients.")
    u = tau/900
    return expit(a + ((1-u)*b_late+u*b_early)*logits(probabilities))


def corrected_probabilities(probabilities, tau, artifact):
    if artifact["method"] == "logistic_time":
        return predict_time(probabilities,tau,artifact["a"],artifact["b_late"],artifact["b_early"])
    return predict(probabilities,artifact["a"],artifact["b"])


def fit(observations, method="logistic"):
    if method not in ("logistic", "logistic_time"):
        raise ValueError("Unknown calibration method.")
    required = {"window_id","tau","p_model","outcome","time","close_time"}
    if not required.issubset(observations.columns):
        raise ValueError("Use observations.csv, not trades.csv; required fields are missing.")
    # Trade entry is currently supported only at minute boundaries. Do not let
    # nearly certain final-minute predictions dominate the fitted correction.
    frame = observations.loc[observations["tau"] >= 60].copy()
    if frame.empty:
        raise ValueError("No minute-level observations.")
    if frame[list(required)].isna().any().any():
        raise ValueError("Missing calibration inputs or outcomes.")
    if frame.duplicated(["window_id","tau"]).any():
        raise ValueError("Duplicate window/checkpoint observations.")
    if frame.groupby("window_id").outcome.nunique().max() > 1:
        raise ValueError("Conflicting outcomes within a window.")
    y = frame.outcome.to_numpy(float)
    if not np.isin(y,[0,1]).all() or len(np.unique(y)) != 2:
        raise ValueError("Training needs both YES and NO outcomes.")
    if not (frame.time < frame.close_time).all():
        raise ValueError("Predictions must precede closing.")
    windows = frame.window_id.nunique()
    if windows < 30:
        raise ValueError("At least 30 training windows required; this is not a reliability guarantee.")
    if not np.isfinite(frame.tau.to_numpy(float)).all() or (frame.tau > 900).any():
        raise ValueError("Invalid time remaining.")
    x = logits(frame.p_model.to_numpy(float))
    u = frame.tau.to_numpy(float)/900
    X = np.column_stack([np.ones(len(x)),x]) if method == "logistic" else np.column_stack([np.ones(len(x)),(1-u)*x,u*x])
    initial = np.array([0.,1.] if method == "logistic" else [0.,1.,1.])
    bounds = [(-5,5)]+[(.05,5)]*(len(initial)-1)
    weights = 1/frame.groupby("window_id").window_id.transform("size").to_numpy(float)
    weights /= weights.sum()

    def objective(beta):
        z = X@beta
        loss = np.sum(weights*(np.logaddexp(0,z)-y*z))
        delta = beta-initial
        penalty = .5*RIDGE*np.dot(delta,delta)
        gradient = X.T@(weights*(expit(z)-y))+RIDGE*delta
        if method == "logistic_time":
            # Fixed shrinkage against unnecessary early/late differences.
            difference = beta[2]-beta[1]
            penalty += .5*RIDGE*difference*difference
            gradient += RIDGE*difference*np.array([0.,-1.,1.])
        return loss+penalty, gradient

    result = minimize(objective,initial,jac=True,method="L-BFGS-B",
                      bounds=bounds,options={"maxiter":1000,"ftol":1e-12})
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("Calibration fitting did not converge.")
    coefficients = dict(zip(("a","b") if method == "logistic" else ("a","b_late","b_early"),map(float,result.x)))
    raw = frame.p_model.to_numpy(float)
    corrected = corrected_probabilities(raw,frame.tau.to_numpy(float),{"method":method,**coefficients})
    def loss(p):
        p=np.clip(p,EPS,1-EPS)
        return float(np.sum(weights*(-y*np.log(p)-(1-y)*np.log1p(-p))))
    return {
        "version":1,"method":method,**coefficients,"clip":EPS,"ridge":RIDGE,
        "time_scale_seconds":900,"time_difference_penalty":RIDGE if method == "logistic_time" else 0,
        "weighting":"Each contract has equal total weight; tau >= 60 only.",
        "bounds":dict(zip(coefficients,bounds)),
        "at_bound":bool(any(abs(v-lo)<.0001 or abs(v-hi)<.0001 for v,(lo,hi) in zip(result.x,bounds))),
        "training_windows":int(windows),"training_rows":len(frame),
        "training_first_prediction":int(frame.time.min()),
        "training_last_close":int(frame.close_time.max()),
        "training_available_after":int(frame.close_time.max())+60,
        "training_scores":{"raw_log_loss":loss(raw),"corrected_log_loss":loss(corrected)},
        "created_at":datetime.now(timezone.utc).isoformat(),"fairvalue_sha256":model_hash(),
        "note":"Training scores are in-sample. They do not show performance on unseen data."
    }

def load(path):
    artifact = json.loads(Path(path).read_text())
    if artifact.get("version") != 1 or artifact.get("method") not in ("logistic","logistic_time") or artifact.get("clip") != EPS:
        raise ValueError("Unsupported calibration file.")
    corrected_probabilities([.5],[60],artifact)
    if artifact["fairvalue_sha256"] != model_hash():
        raise ValueError("fairvalue.py changed since training. Refit the calibration.")
    return artifact

def apply(rows, artifact, settings):
    if artifact.get("observation_settings") != settings:
        raise ValueError("EWMA settings differ from training. Use identical settings or refit.")
    if rows and min(r["time"] for r in rows) < artifact["training_available_after"]:
        raise ValueError("Test predictions overlap training or precede outcome availability. Choose later dates.")
    if artifact["method"] == "logistic_time" and any("tau" not in r for r in rows):
        raise ValueError("Time-aware calibration requires time remaining on every row.")
    corrected = corrected_probabilities([r["p"] for r in rows],
                                        [r.get("tau",60) for r in rows],artifact)
    return [{**r,"p_raw":r["p"],"p":float(p),"p_model":float(p)} for r,p in zip(rows,corrected)]

def main():
    parser=argparse.ArgumentParser(description="Fit probability correction; never optimizes trading profit.")
    parser.add_argument("--observations",required=True,nargs="+")
    parser.add_argument("--method",choices=("logistic","logistic_time"),default="logistic")
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    try:
        frames, sources, settings = [], [], None
        for name in args.observations:
            source=Path(name)
            report=json.loads(source.with_name("report.json").read_text())
            config=report["config"]
            current={k:config[k] for k in ("lookback","halflife","vol_step")}
            if settings is not None and current != settings:
                raise ValueError("Training files have different EWMA settings.")
            settings=current
            frame=pd.read_csv(source)
            # Refit from the original probabilities, never calibrate twice.
            if "p_raw" in frame:
                frame["p_model"]=frame["p_raw"]
            frames.append(frame)
            sources.append({"path":str(source),"sha256":hashlib.sha256(source.read_bytes()).hexdigest()})
        artifact=fit(pd.concat(frames,ignore_index=True),args.method)
        artifact["observation_settings"]=settings
        artifact["sources"]=sources
        output=Path(args.output)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(artifact,indent=2),encoding="utf-8")
        print(json.dumps(artifact,indent=2))
        print("Saved:",output.resolve())
        print("This fits training data only. Next evaluate on later, untouched dates.")
    except (OSError,ValueError,KeyError) as exc:
        parser.exit(1,"Calibration stopped: "+str(exc)+"\n")

if __name__=="__main__":
    main()
