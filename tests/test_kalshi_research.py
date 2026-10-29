import unittest
from dashboard.kalshi.research.observations import seconds, build
from dashboard.kalshi.research.backtest import run, fee
from dashboard.kalshi.research.run import score
from dashboard.kalshi.research.history import epoch, Client
from unittest.mock import Mock

class ResearchTests(unittest.TestCase):
    def row(self, **kw):
        return dict(ticker="A",time=1,close_time=900,p=.8,bid=.49,ask=.5,outcome=1,**kw)

    def test_fee_rounding(self):
        self.assertEqual(fee(.5),.02)
        self.assertEqual(fee(.5,100),1.75)

    def test_first_entry_only(self):
        row=self.row()
        trades,summary=run([row,{**row,"time":2}])
        self.assertEqual(len(trades),1)
        self.assertAlmostEqual(summary["net_profit"],.48)

    def test_no_payoff(self):
        row={**self.row(),"p":.1,"outcome":0}
        trades,_=run([row])
        self.assertEqual(trades[0]["side"],"no")
        self.assertAlmostEqual(trades[0]["pnl"],.47)

    def test_costs_remove_edge(self):
        row={**self.row(),"p":.55}
        self.assertEqual(len(run([row])[0]),1)
        self.assertEqual(len(run([row],slippage=.02)[0]),0)

    def test_no_trade_at_equal_threshold(self):
        self.assertEqual(len(run([{**self.row(),"p":.5}])[0]),0)

    def test_probability_scores(self):
        self.assertAlmostEqual(score([self.row()])["brier"],.04)

    def test_strict_second_boundary(self):
        t=1793023200000
        result=seconds([{"time":t,"value":100},{"time":t+999,"value":101},
                        {"time":t+1000,"value":999}])
        self.assertEqual(result[t//1000+1],101)

    def test_conflicting_ticks(self):
        with self.assertRaises(ValueError):
            seconds([{"time":1793023200000,"value":100},{"time":1793023200000,"value":101}])

    def test_timezone_required(self):
        with self.assertRaises(ValueError):
            epoch("2026-10-26T14:00:00")

    def test_repeated_cursor_rejected(self):
        client=object.__new__(Client)
        client.get=Mock(return_value={"markets":[],"cursor":"same"})
        with self.assertRaises(ValueError):
            list(client.pages("/markets",{}))

    def dataset(self):
        closing=epoch("2026-10-26T14:15:00Z")
        decision=closing-120
        ticks=[{"time":(s-1)*1000,"value":100+(s%3)} for s in range(decision-300,decision+1)]
        return {"markets":[{"ticker":"A","close_time":"2026-10-26T14:15:00Z",
                            "floor_strike":100,"strike_type":"greater","result":"yes","_tier":"historical"}],
                "candles":{"A":[{"end_period_ts":decision,"yes_bid":{"close":".49"},
                                "yes_ask":{"close":".50"}}]},"ticks":ticks}

    def test_future_data_does_not_change_prediction(self):
        data=self.dataset()
        first=build(data,lookback=300)[0]
        self.assertEqual(len(first),1)
        data["ticks"].append({"time":first[0]["time"]*1000,"value":99999})
        self.assertEqual(first,build(data,lookback=300)[0])

    def test_missing_second_skips(self):
        data=self.dataset()
        data["ticks"].pop(5)
        rows,skips,_=build(data,lookback=300)
        self.assertFalse(rows)
        self.assertTrue(skips)

    def test_live_cents_and_dollars(self):
        data=self.dataset()
        expected=build(data,lookback=300)[0]
        data["markets"][0]["_tier"]="live"
        for side,value in (("yes_bid",49),("yes_ask",50)):
            data["candles"]["A"][0][side]["close"]=value
        self.assertEqual(expected,build(data,lookback=300)[0])
        data["candles"]["A"][0]["yes_bid"]["close_dollars"]="0.49"
        data["candles"]["A"][0]["yes_ask"]["close_dollars"]="0.50"
        self.assertEqual(expected,build(data,lookback=300)[0])


    def full_dataset(self):
        data=self.dataset()
        closing=epoch(data["markets"][0]["close_time"])
        data["ticks"]=[{"time":s*1000,"value":100+(s%7)} for s in range(closing-1500,closing)]
        data["markets"][0]["expiration_value"]="103"
        return data

    def test_final_minute_counts_and_no_invented_fills(self):
        data=self.full_dataset()
        rows,_,_=build(data,lookback=300)
        closing=epoch(data["markets"][0]["close_time"])
        row=next(r for r in rows if r["tau"]==30)
        expected=[100+(s%7) for s in range(closing-60,closing-30)]
        self.assertAlmostEqual(row["known_avg"],sum(expected)/30)
        self.assertAlmostEqual(row["mean"],(row["known_avg"]+row["spot"])/2)
        self.assertEqual(row["source_time"],row["time"]-1)
        self.assertFalse(row["trade_eligible"])
        self.assertEqual(run([row])[0],[])
        self.assertIsNotNone(row["z"])

    def test_discrete_variance_matches_innovation_weights(self):
        from dashboard.kalshi.fairvalue import settle_moments
        for tau in (0,1,10,30,59,60,120):
            # Independent one-second increments, each affects remaining later samples.
            weights=[sum(sample>=innovation for sample in range(max(1,tau-59),tau+1))/60
                     for innovation in range(1,tau+1)]
            _,sd=settle_moments(100,tau,2,100 if tau<60 else None)
            self.assertAlmostEqual(float(sd)**2,4*sum(w*w for w in weights))

    def test_outcome_does_not_affect_prediction(self):
        data=self.full_dataset()
        before=build(data,lookback=300)[0]
        data["markets"][0].update(result="no",expiration_value="90")
        after=build(data,lookback=300)[0]
        self.assertEqual([r["p"] for r in before],[r["p"] for r in after])

    def test_ewma_resets_after_gap(self):
        from dashboard.kalshi.research.observations import volatility
        prices={t:100+t%7 for t in range(100)}
        prices.pop(50)
        sigmas=volatility(prices,30,5,600)
        self.assertNotIn(60,sigmas)
        self.assertIn(90,sigmas)

    def test_validation_adapter(self):
        from dashboard.kalshi.research.observations import validation_frame
        from dashboard.kalshi.research.validate import evaluate
        rows=build(self.full_dataset(),lookback=300)[0]
        summary=evaluate(validation_frame(rows),n_boot=3)
        self.assertFalse(summary.empty)
        self.assertTrue(summary["verdict"].str.startswith("INCONCLUSIVE").all())

if __name__=="__main__":
    unittest.main()
