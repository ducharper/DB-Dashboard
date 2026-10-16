// NinjaTrader 8 strategy. Use ONE-MINUTE bars and platform time zone Eastern.
// Research proxy, not a Nasdaq auction-imbalance strategy.
using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;

namespace NinjaTrader.NinjaScript.Strategies
{
    public class LateDayPressureResearch : Strategy
    {
        private Queue<double> priorWindowVolumes;
        private DateTime currentDate;
        private DateTime previousRegularBar;
        private int regularBars;
        private bool continuousSession;
        private bool evaluated;
        private double cumulativePV;
        private double cumulativeVolume;
        private const string EntrySignal = "LateDayLong";

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "LateDayPressureResearch";
                Description = "Tests late-day price/volume pressure versus a same-time long baseline. Eastern time, one-minute bars only.";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds = 30;
                BarsRequiredToTrade = 1;
                IsInstantiatedOnEachOptimizationIteration = true;
                LookbackSessions = 20;
                RelativeVolumeThreshold = 1.5;
                TradeQuantity = 1;
                UsePressureFilter = true;
            }
            else if (State == State.DataLoaded)
            {
                if (BarsPeriod.BarsPeriodType != BarsPeriodType.Minute || BarsPeriod.Value != 1)
                    throw new InvalidOperationException("LateDayPressureResearch requires 1-minute bars.");
                priorWindowVolumes = new Queue<double>();
                currentDate = DateTime.MinValue;
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;

            // NinjaTrader minute bars have END timestamps. Platform must use Eastern.
            DateTime stamp = Time[0];
            int clock = ToTime(stamp);
            if (stamp.Date != currentDate)
            {
                currentDate = stamp.Date;
                previousRegularBar = DateTime.MinValue;
                regularBars = 0;
                continuousSession = true;
                evaluated = false;
                cumulativePV = 0;
                cumulativeVolume = 0;
                // Recovery if an earlier exit could not fill before the data ended.
                if (Position.MarketPosition == MarketPosition.Long)
                    ExitLong("DateBoundaryExit", EntrySignal);
            }

            // Scheduled market exit; historical processing normally fills next bar.
            if (clock >= 155900)
            {
                if (Position.MarketPosition == MarketPosition.Long)
                    ExitLong("TimedExit", EntrySignal);
                return;
            }

            // 09:31 is the bar covering 09:30-09:31. Ignore overnight data.
            if (clock < 93100 || clock > 155500)
                return;
            if (regularBars == 0)
                continuousSession = clock == 93100;
            else if (stamp - previousRegularBar != TimeSpan.FromMinutes(1))
                continuousSession = false;
            previousRegularBar = stamp;
            regularBars++;

            double volume = Convert.ToDouble(Volume[0]);
            // Typical-price bar approximation; does not require Order Flow VWAP.
            cumulativePV += ((High[0] + Low[0] + Close[0]) / 3.0) * volume;
            cumulativeVolume += volume;

            if (clock != 155500 || evaluated || CurrentBar < 5)
                return;
            evaluated = true;
            // Skip incomplete sessions and early closes, without inventing bars.
            if (!continuousSession || regularBars != 385 || cumulativeVolume <= 0)
                return;

            double windowVolume = 0;
            for (int i = 0; i < 5; i++)
                windowVolume += Convert.ToDouble(Volume[i]);

            // Compare 15:50-15:55 with the SAME window on prior eligible sessions.
            // Today's observation enters the queue only AFTER its decision.
            if (priorWindowVolumes.Count == LookbackSessions)
            {
                double meanVolume = 0;
                foreach (double value in priorWindowVolumes)
                    meanVolume += value;
                meanVolume /= LookbackSessions;
                double vwap = cumulativePV / cumulativeVolume;
                bool pressure = meanVolume > 0
                    && windowVolume >= RelativeVolumeThreshold * meanVolume
                    && Close[0] > vwap
                    && Close[0] > Close[5];
                if (Position.MarketPosition == MarketPosition.Flat
                    && (!UsePressureFilter || pressure))
                    EnterLong(TradeQuantity, EntrySignal);
            }
            priorWindowVolumes.Enqueue(windowVolume);
            while (priorWindowVolumes.Count > LookbackSessions)
                priorWindowVolumes.Dequeue();
        }

        [NinjaScriptProperty]
        [Range(2, 100)]
        [Display(Name = "Lookback sessions", Order = 1, GroupName = "Research")]
        public int LookbackSessions { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 10.0)]
        [Display(Name = "Relative volume threshold", Order = 2, GroupName = "Research")]
        public double RelativeVolumeThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Quantity", Order = 3, GroupName = "Research")]
        public int TradeQuantity { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Use pressure filter", Order = 4, GroupName = "Research")]
        public bool UsePressureFilter { get; set; }
    }
}
