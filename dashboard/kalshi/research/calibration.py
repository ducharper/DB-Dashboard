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

def fit(observations):
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
    x = logits(frame.p_model.to_numpy(float))
    weights = 1/frame.groupby("window_id").window_id.transform("size").to_numpy(float)
    weights /= weights.sum()

    def objective(beta):
        a,b = beta
        z = a+b*x
        loss = np.sum(weights*(np.logaddexp(0,z)-y*z))
        penalty = .5*RIDGE*(a*a+(b-1)**2)
        residual = weights*(expit(z)-y)
        gradient = np.array([residual.sum()+RIDGE*a,
                             (residual*x).sum()+RIDGE*(b-1)])
        return loss+penalty, gradient

    result = minimize(objective,[0.,1.],jac=True,method="L-BFGS-B",
                      bounds=[(-5,5),(.05,5)],options={"maxiter":1000,"ftol":1e-12})
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("Calibration fitting did not converge.")
    a,b = map(float,result.x)
    raw = frame.p_model.to_numpy(float)
    corrected = predict(raw,a,b)
    def loss(p):
        p=np.clip(p,EPS,1-EPS)
        return float(np.sum(weights*(-y*np.log(p)-(1-y)*np.log1p(-p))))
    return {
        "version":1,"method":"logistic","a":a,"b":b,"clip":EPS,"ridge":RIDGE,
        "weighting":"Each contract has equal total weight; tau >= 60 only.",
        "bounds":{"a":[-5,5],"b":[.05,5]},
        "at_bound":bool(abs(a)>=4.999 or b<=.0501 or b>=4.999),
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
    if artifact.get("version") != 1 or artifact.get("method") != "logistic" or artifact.get("clip") != EPS:
        raise ValueError("Unsupported calibration file.")
    predict([.5],artifact["a"],artifact["b"])
    if artifact["fairvalue_sha256"] != model_hash():
        raise ValueError("fairvalue.py changed since training. Refit the calibration.")
    return artifact

def apply(rows, artifact, settings):
    if artifact.get("observation_settings") != settings:
        raise ValueError("EWMA settings differ from training. Use identical settings or refit.")
    if rows and min(r["time"] for r in rows) < artifact["training_available_after"]:
        raise ValueError("Test predictions overlap training or precede outcome availability. Choose later dates.")
    corrected = predict([r["p"] for r in rows],artifact["a"],artifact["b"])
    return [{**r,"p_raw":r["p"],"p":float(p),"p_model":float(p)} for r,p in zip(rows,corrected)]

def main():
    parser=argparse.ArgumentParser(description="Fit probability correction; never optimizes trading profit.")
    parser.add_argument("--observations",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    try:
        source=Path(args.observations)
        report=json.loads(source.with_name("report.json").read_text())
        config=report["config"]
        artifact=fit(pd.read_csv(source))
        artifact["observation_settings"]={k:config[k] for k in ("lookback","halflife","vol_step")}
        artifact["source_sha256"]=hashlib.sha256(source.read_bytes()).hexdigest()
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
