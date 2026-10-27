import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import closing
from dashboard.kalshi import recorder as kr

class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parents[1] / 'data'
        self.test_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='recorder-test-', dir=self.test_root)
        self.env = patch.dict(os.environ, {'KALSHI_RESEARCH_DB_PATH':str(Path(self.temp.name)/'tape.sqlite3')})
        self.env.start()
        with closing(kr.connect()) as db, db:
            db.execute('INSERT INTO sessions VALUES (?, ?, NULL, ?, NULL)', ('session',1000,'recording'))

    def tearDown(self):
        self.env.stop()
        assert Path(self.temp.name).resolve().is_relative_to(self.test_root.resolve())
        self.temp.cleanup()

    def frame(self, timestamp, value='100'):
        return {'type':'cfbenchmarks_value','msg':{'index_id':'BRTI','data':json.dumps({'time':timestamp,'value':value})}}

    def test_window_boundaries_and_duplicates(self):
        end = 900000
        rows = [{'source_ms':end-60000+i*1000,'value':100+i} for i in range(61)]
        rows += [rows[-1]]
        result = kr.window_coverage(rows,end)
        self.assertTrue(result['complete'])
        self.assertEqual(result['observed_seconds'],60)
        self.assertEqual(result['observed_average'],130.5)
        rows.append({'source_ms':end,'value':999})
        self.assertFalse(kr.window_coverage(rows,end)['complete'])

    def test_missing_seconds_not_filled(self):
        result=kr.window_coverage([{'source_ms':899000,'value':100}],900000)
        self.assertEqual(result['missing_seconds'],59)
        self.assertFalse(result['complete'])

    def test_raw_tape_persistence_and_restart_status(self):
        kr.append_frame('session','connection', self.frame(899000),received_ms=899100)
        kr.append_frame('session','connection', self.frame(900000),received_ms=900100)
        status=kr.Recorder().status()
        self.assertFalse(status['running'])
        self.assertEqual(status['session']['state'],'interrupted')
        self.assertEqual(status['counts']['cfbenchmarks_value'],2)
        self.assertEqual(status['latest_brti']['source_ms'],900000)
        self.assertEqual(status['latest_brti']['received_ms'],900100)
        self.assertEqual(status['windows'][0]['observed_seconds'],2)
        with closing(kr.connect()) as db:
            raw=db.execute('SELECT * FROM frames ORDER BY id LIMIT 1').fetchone()
        self.assertGreater(raw['monotonic_ns'],0)
        self.assertEqual(json.loads(raw['payload']),self.frame(899000))

    def test_invalid_brti_retains_raw_but_not_average(self):
        kr.append_frame('session','connection',self.frame(899000,'NaN'))
        status=kr.Recorder().status()
        self.assertEqual(status['counts']['invalid_brti'],1)
        self.assertIsNone(status['latest_brti'])

    def test_missing_credentials_never_start_thread(self):
        with patch.dict(os.environ,{'KALSHI_API_KEY_ID':'','KALSHI_PRIVATE_KEY_PATH':''}):
            recorder=kr.Recorder()
            with self.assertRaises(ValueError): recorder.start()
            self.assertIsNone(recorder.thread)

    def test_stop_request_and_terminal_state(self):
        recorder=kr.Recorder()
        recorder.stop()
        self.assertTrue(recorder.stop_event.is_set())
        recorder.set_state('session','completed',finished=True)
        status=recorder.status()
        self.assertEqual(status['session']['state'],'completed')
        self.assertIsNotNone(status['session']['ended_ms'])

    def test_worker_subscribes_only_to_market_data(self):
        recorder=kr.Recorder()
        commands=[]
        frame=self.frame(900000)
        class Socket:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def send(self,raw): commands.append(json.loads(raw))
            def recv(self,timeout):
                recorder.stop_event.set()
                return json.dumps(frame)
        with patch('websockets.sync.client.connect',return_value=Socket()), patch('dashboard.api.kalshi.fetch_public',return_value={'markets':[{'ticker':'KXBTC15M-TEST','market_type':'binary'}]}), patch.object(kr,'headers',return_value={}):
            recorder.run('session',object(),1)
        self.assertEqual([c['params']['channels'] for c in commands], [['cfbenchmarks_value'],['orderbook_delta'],['ticker']])
        self.assertTrue(all(c['cmd']=='subscribe' for c in commands))
        status=recorder.status()
        self.assertEqual(status['session']['state'],'stopped')
        self.assertEqual(status['counts']['cfbenchmarks_value'],1)
        self.assertEqual(status['counts']['market_metadata'],1)

    def test_failed_connections_stop_after_five_attempts(self):
        recorder=kr.Recorder()
        with patch('dashboard.api.kalshi.fetch_public',side_effect=OSError('secret-bearing error')), patch.object(recorder.stop_event,'wait'):
            recorder.run('session',object(),1)
        status=recorder.status()
        self.assertEqual(status['session']['state'],'failed')
        self.assertEqual(status['counts']['connection_error'],5)
        self.assertNotIn('secret',status['session']['error'])

    def test_sequence_gap_is_recorded_and_reconnects(self):
        recorder=kr.Recorder()
        messages=iter([
            {'type':'orderbook_snapshot','sid':2,'seq':1,'msg':{'market_ticker':'KXBTC15M-TEST'}},
            {'type':'orderbook_delta','sid':2,'seq':3,'msg':{'market_ticker':'KXBTC15M-TEST'}},
        ])
        class Socket:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def send(self,raw): pass
            def recv(self,timeout):
                try: return json.dumps(next(messages))
                except StopIteration:
                    recorder.stop_event.set()
                    return json.dumps({'type':'orderbook_snapshot','sid':2,'seq':1,'msg':{}})
        with patch('websockets.sync.client.connect',return_value=Socket()) as socket, patch('dashboard.api.kalshi.fetch_public',return_value={'markets':[{'ticker':'KXBTC15M-TEST','market_type':'binary'}]}), patch.object(kr,'headers',return_value={}), patch.object(recorder.stop_event,'wait'):
            recorder.run('session',object(),1)
        self.assertEqual(socket.call_count,2)
        status=recorder.status()
        self.assertEqual(status['counts']['sequence_gap'],1)
        self.assertEqual(status['counts']['orderbook_snapshot'],2)

if __name__=='__main__': unittest.main()
