"""Server orchestration tests. All SDK workers and robot reads are replaced."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from app import server
from nao_gestures.kinematics import NAMES, REST


class FakeWorker:
    def __init__(self, events, before_terminal=None):
        self.returncode=None
        self.wait_calls=0

        def output():
            for event in events:
                if before_terminal and event['event'] in ('complete','stopped','error'):
                    before_terminal()
                yield json.dumps(event)+'\n'

        self.stdout=output()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls+=1
        self.returncode=0
        return self.returncode


class RobotExecutionTests(unittest.TestCase):
    def setUp(self):
        self.patches=ExitStack()
        self.addCleanup(self.patches.close)
        temporary=self.patches.enter_context(tempfile.TemporaryDirectory())
        self.root=Path(temporary)
        self.jobs=self.root/'jobs';self.jobs.mkdir()
        self.generation=self.root/'generation';self.generation.mkdir()
        (self.root/'robot_connection.json').write_text(
            json.dumps({'host':'192.0.2.1','naoqi_port':9561}),encoding='utf-8')
        self.state={'busy':True,'operation':'robot','message':'Starting','execution':None}
        self.stop=threading.Event()
        self.active={}
        for name,value in [('ROOT',self.root),('JOBS',self.jobs),('STATE',self.state),
                           ('STOP',self.stop),('ACTIVE',self.active)]:
            self.patches.enter_context(patch.object(server,name,value))
        self.job_dir=self.patches.enter_context(patch.object(server,'job_dir',return_value=self.generation))
        self.probe=self.patches.enter_context(patch.object(server,'bridge_probe',return_value={'angles':REST.tolist()}))
        self.launch=self.patches.enter_context(patch.object(server,'launch_bridge'))
        self.run_command=self.patches.enter_context(patch.object(server,'run_command'))
        self.calls=[]
        self.workers=[]

    def fake_launch(self,args,**kwargs):
        self.calls.append(list(args))
        path=Path(args[args.index('--telemetry')+1])
        rows=[{'elapsed_s':i*.1,'commanded':[.01*i]*len(NAMES),
               'measured':[.01*i]*len(NAMES)} for i in range(6)]
        path.write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
        worker=FakeWorker([{'event':'moving'},
                           {'event':'complete','motor_tracking_rms_deg':0.}])
        self.workers.append(worker)
        return worker

    def run_comparison(self):
        server.execute_robot('demo',False,diagnostic=True,compare=True)

    def assert_released(self):
        self.assertFalse(self.state['busy'])
        self.assertIsNone(self.state['operation'])
        self.assertNotIn('robot_process',self.active)
        self.assertNotIn('stop_file',self.active)

    def test_comparison_uses_default_then_constant_without_speech_and_saves_quality(self):
        self.launch.side_effect=self.fake_launch
        self.run_comparison()

        self.assertEqual(self.launch.call_count,2)
        first,second=self.calls
        self.assertNotIn('--constant-stiffness',first)
        self.assertIn('--constant-stiffness',second)
        for args,constant in [(first,False),(second,True)]:
            self.assertNotIn('--audio-on-robot',args)
            plan=json.loads(Path(args[args.index('--plan')+1]).read_text(encoding='utf-8'))
            self.assertTrue(plan['diagnostic'])
            self.assertEqual(plan['constant_stiffness'],constant)
        self.run_command.assert_not_called()
        self.assertFalse(self.state['execution']['audio_started'])
        summaries=list(self.jobs.glob('run_*/quality_summary.json'))
        self.assertEqual(len(summaries),1)
        report=json.loads(summaries[0].read_text(encoding='utf-8'))
        self.assertTrue(report['comparison'])
        self.assertEqual(len(report['results']),2)
        self.assertEqual([r['constant_stiffness'] for r in report['results']],[False,True])
        self.assertTrue(all(r['unplanned_pause_count']==0 for r in report['results']))
        self.assertEqual(self.state['quality'],report)
        self.assertTrue(all(worker.wait_calls>=1 for worker in self.workers))
        self.assert_released()

    def test_stop_during_a_does_not_launch_b(self):
        def launch_stopping_worker(args,**kwargs):
            self.calls.append(list(args))
            return FakeWorker([{'event':'moving'},{'event':'stopped'}],before_terminal=self.stop.set)

        self.launch.side_effect=launch_stopping_worker
        self.run_comparison()

        self.assertEqual(self.launch.call_count,1)
        self.assertNotIn('--constant-stiffness',self.calls[0])
        self.assertEqual(self.state['message'],'Execução interrompida.')
        self.assertEqual(self.state['execution']['phase'],'stopped')
        self.assertEqual(list(self.jobs.glob('run_*/B_constant')),[])
        self.assertEqual(list(self.jobs.glob('run_*/quality_summary.json')),[])
        self.assert_released()

    def test_job_directory_failure_releases_busy_without_launching(self):
        self.job_dir.side_effect=ValueError('Generation missing')
        self.run_comparison()

        self.probe.assert_not_called()
        self.launch.assert_not_called()
        self.assertEqual(self.state['execution']['phase'],'error')
        self.assertIn('Generation missing',self.state['message'])
        self.assert_released()

    def test_log_failure_happens_before_worker_launch(self):
        real_open=Path.open

        def fail_log_open(path,*args,**kwargs):
            if path.name=='run.log':
                raise OSError('Cannot open run log')
            return real_open(path,*args,**kwargs)

        with patch.object(Path,'open',fail_log_open):
            self.run_comparison()

        self.probe.assert_called_once()
        self.launch.assert_not_called()
        self.assertEqual(self.state['execution']['phase'],'error')
        self.assertIn('Cannot open run log',self.state['message'])
        self.assert_released()

    def test_log_write_failure_requests_stop_and_waits_for_worker_before_release(self):
        real_open=Path.open
        worker=FakeWorker([{'event':'moving'}])
        stop_seen=[]
        original_wait=worker.wait
        def wait(timeout=None):
            stop_seen.append(next(self.jobs.glob('run_*/STOP')).is_file())
            self.assertTrue(self.state['busy'])
            return original_wait(timeout)
        worker.wait=wait
        class BrokenLog:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def write(self,*args):raise OSError('Disk full')
        def open_log(path,*args,**kwargs):
            if path.name=='run.log':return BrokenLog()
            return real_open(path,*args,**kwargs)
        self.launch.return_value=worker
        with patch.object(Path,'open',open_log):self.run_comparison()
        self.assertEqual(stop_seen,[True])
        self.assertEqual(self.launch.call_count,1)
        self.assertEqual(self.state['execution']['phase'],'error')
        self.assertIn('Disk full',self.state['message'])
        self.assert_released()


if __name__=='__main__':
    unittest.main()
