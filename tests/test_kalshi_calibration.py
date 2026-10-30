import copy
import unittest
import numpy as np
import pandas as pd
from dashboard.kalshi.research.calibration import fit,predict,apply

class CalibrationTests(unittest.TestCase):
    def sample(self):
        rows=[]
        for i,p in enumerate((.1,.3,.5,.7,.9)*40):
            # Outcomes generated from a weaker probability signal.
            rng=np.random.default_rng(i)
            y=int(rng.random()<float(predict(p,0,.5)))
            rows.append(dict(window_id=str(i),tau=600,p_model=p,outcome=y,
                             time=10000+i*900,close_time=10800+i*900))
        return pd.DataFrame(rows)

    def test_identity_and_confidence(self):
        p=np.array([.2,.5,.8])
        np.testing.assert_allclose(predict(p,0,1),p)
        q=predict(p,0,.7)
        self.assertTrue(q[0]>.2 and q[2]<.8)
        self.assertTrue(np.isfinite(predict([0,1],0,1)).all())

    def test_fit_improves_training_loss(self):
        model=fit(self.sample())
        self.assertLess(model["b"],1)
        scores=model["training_scores"]
        self.assertLess(scores["corrected_log_loss"],scores["raw_log_loss"])

    def test_each_window_has_equal_weight(self):
        frame=self.sample()
        a=fit(frame)
        extra=frame.iloc[:1].copy()
        extra["tau"]=300
        b=fit(pd.concat([frame,extra],ignore_index=True))
        self.assertAlmostEqual(a["a"],b["a"],places=6)
        self.assertAlmostEqual(a["b"],b["b"],places=6)

    def test_duplicate_or_invalid_data_rejected(self):
        frame=self.sample()
        with self.assertRaises(ValueError): fit(pd.concat([frame,frame.iloc[:1]]))
        frame.loc[0,"p_model"]=70
        with self.assertRaises(ValueError): fit(frame)

    def test_overlap_rejected_and_labels_do_not_affect_apply(self):
        model=fit(self.sample())
        settings={"lookback":7200,"halflife":600,"vol_step":5}
        model["observation_settings"]=settings
        row={"time":model["training_available_after"],"p":.8,"p_model":.8,"outcome":1}
        before=copy.deepcopy(row)
        first=apply([row],model,settings)
        second=apply([{**row,"outcome":0,"settle":0}],model,settings)
        self.assertEqual(first[0]["p"],second[0]["p"])
        self.assertEqual(first[0]["p"],first[0]["p_model"])
        self.assertEqual(first[0]["p_raw"],.8)
        self.assertEqual(row,before)
        with self.assertRaises(ValueError):
            apply([{**row,"time":model["training_last_close"]}],model,settings)
        with self.assertRaises(ValueError):
            apply([row],model,{**settings,"halflife":10})

    def test_final_minute_excluded_from_fitting(self):
        frame=self.sample()
        final=frame.copy()
        final["tau"]=10
        final["p_model"]=1-final["p_model"]
        a=fit(frame); b=fit(pd.concat([frame,final],ignore_index=True))
        self.assertAlmostEqual(a["b"],b["b"])

    def test_runner_writes_separate_comparison(self):
        import json,tempfile,sys
        from pathlib import Path
        from unittest.mock import patch
        from dashboard.kalshi.research.run import main
        from dashboard.kalshi.research.history import epoch
        start=epoch("2026-10-27T00:00:00Z")
        settings={"lookback":7200,"halflife":600,"vol_step":5}
        artifact={**fit(self.sample()),"observation_settings":settings}
        row=dict(ticker="X",window_id="X",group="X",time=start+60,close_time=start+900,
                 tau=840,p=.8,p_model=.8,bid=.49,ask=.5,outcome=1,trade_eligible=True)
        with tempfile.TemporaryDirectory(dir="data/kalshi_research") as directory:
            model=Path(directory)/"model.json"
            model.write_text(json.dumps(artifact))
            args=["run","--start","2026-10-27T00:00:00Z","--end","2026-10-28T00:00:00Z",
                  "--output",directory,"--calibration",str(model)]
            with patch.object(sys,"argv",args), \
                 patch("dashboard.kalshi.research.run.download",return_value={"markets":[{}]}), \
                 patch("dashboard.kalshi.research.run.build",return_value=([row],[],[])), \
                 patch("dashboard.kalshi.research.run.evaluate",return_value=pd.DataFrame()):
                main()
            reports=list(Path(directory).glob("*/calibrated_*/report.json"))
            self.assertEqual(len(reports),1)
            report=json.loads(reports[0].read_text())
            self.assertIn("original",report["comparison"])
            self.assertIn("calibrated",report["comparison"])
            self.assertTrue((reports[0].parent/"original_trades.csv").exists())


    def test_time_interpolation_and_constant_equivalence(self):
        from dashboard.kalshi.research.calibration import predict_time
        self.assertAlmostEqual(float(predict_time(.8,0,0,.7,1.1)),float(predict(.8,0,.7)))
        self.assertAlmostEqual(float(predict_time(.8,900,0,.7,1.1)),float(predict(.8,0,1.1)))
        np.testing.assert_allclose(predict_time([.2,.8],[60,840],.1,.8,.8),predict([.2,.8],.1,.8))
        with self.assertRaises(ValueError): predict_time(.8,901,0,.7,1.1)

    def test_time_fit_learns_changing_confidence(self):
        from scipy.special import expit,logit
        rng=np.random.default_rng(123)
        rows=[]
        for i in range(1500):
            q=rng.uniform(.05,.95)
            y=int(rng.random()<q)
            for tau in (60,450,840):
                b=.6+(1.4-.6)*tau/900
                rows.append(dict(window_id=str(i),tau=tau,p_model=float(expit(logit(q)/b)),
                                 outcome=y,time=100000+i*900+900-tau,close_time=100900+i*900))
        model=fit(pd.DataFrame(rows),method="logistic_time")
        self.assertLess(model["b_late"],model["b_early"])
        self.assertGreater(model["b_late"],0)
        self.assertLess(model["training_scores"]["corrected_log_loss"],
                        model["training_scores"]["raw_log_loss"])


    def test_time_artifact_roundtrip_and_application(self):
        import json,tempfile
        from pathlib import Path
        from dashboard.kalshi.research.calibration import load,predict_time
        model=fit(self.sample(),method="logistic_time")
        settings={"lookback":7200,"halflife":600,"vol_step":5}
        model["observation_settings"]=settings
        with tempfile.TemporaryDirectory(dir="data/kalshi_research") as directory:
            path=Path(directory)/"model.json"
            path.write_text(json.dumps(model))
            artifact=load(path)
        rows=[{"time":model["training_available_after"],"tau":tau,"p":.8} for tau in (60,840)]
        corrected=apply(rows,artifact,settings)
        with self.assertRaises(ValueError):
            apply([{k:v for k,v in rows[0].items() if k != "tau"}],artifact,settings)
        expected=predict_time([.8,.8],[60,840],model["a"],model["b_late"],model["b_early"])
        np.testing.assert_allclose([r["p"] for r in corrected],expected)
        with self.assertRaises(ValueError):
            apply([{**rows[0],"time":0}],artifact,settings)

