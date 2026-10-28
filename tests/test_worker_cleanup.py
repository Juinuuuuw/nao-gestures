"""Exercise the worker's complete cleanup path with an in-memory SDK.

No SDK connection or physical command is issued by these tests. The real
ConstantStiffness context is used so worker event ordering is checked against
the actual flag restoration, not a mocked context manager.
"""
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

from app.robot_plan import build_diagnostic_plan,build_plan
from app.upper_body import HEAD_LIMITS
import numpy as np
from app.stiffness_scope import ConstantStiffness  # Load before patching io.open.
from nao_gestures.kinematics import LIMITS, REST,NAMES
from app.direction import MANUAL_NAMES,MANUAL_LIMITS


class FakeFuture:
    def __init__(self, events, complete=True):
        self.events = events
        self.complete = complete
        self.polls = 0
        self.cancelled = False

    def isFinished(self):
        self.polls += 1
        return self.cancelled or (self.complete and self.polls > 1)

    def value(self):
        self.events.append(('future_value',))


class FakeTelemetry:
    def __init__(self, events, close_error=False, write_error=False):
        self.events = events
        self.close_error = close_error
        self.write_error = write_error

    def write(self, data):
        self.events.append(('telemetry_write',))
        if self.write_error:
            raise OSError('telemetry write failed')

    def flush(self):
        self.events.append(('telemetry_flush',))

    def close(self):
        self.events.append(('telemetry_close',))
        if self.close_error:
            raise OSError('telemetry close failed')


class WorkerCleanupTests(unittest.TestCase):
    def fixture(self, close_error=False, write_error=False, restore_error=False,
                stop_during_motion=False,with_head=False,with_manual=False):
        events = []
        future = FakeFuture(events, complete=not (write_error or stop_during_motion))
        telemetry = FakeTelemetry(events, close_error, write_error)
        motion = Mock()
        pose=dict(zip(NAMES,REST));pose.update({'HeadYaw':0.,'HeadPitch':0.,'LWristYaw':0.,'RWristYaw':0.,'LHand':.02,'RHand':.02})
        motion.getAngles.side_effect=lambda names,sensors:[float(pose[name]) for name in names]
        motion.getStiffnesses.side_effect=lambda names:[1. if name in NAMES else 0. for name in names]
        def get_limits(side):
            values=HEAD_LIMITS if side=='Head' else LIMITS[:4] if side=='LArm' else LIMITS[4:]
            result=[list(x)+[8.,2.] for x in values]
            if with_manual and side!='Head':result += [list(MANUAL_LIMITS[0])+[8.,2.],[0.,1.,8.,2.]]
            return result
        motion.getLimits.side_effect=get_limits
        motion.getSmartStiffnessEnabled.return_value = True
        motion.areResourcesAvailable.return_value = True
        motion.getTaskList.side_effect = [[], [['angleInterpolationBezier', 123]]]
        motion.angleInterpolationBezier.return_value = future

        def set_smart(value):
            events.append(('smart', value))
            if value and restore_error:
                raise RuntimeError('smart restore failed')

        motion.setSmartStiffnessEnabled.side_effect = set_smart
        motion.getBreathEnabled.return_value=True;motion.getIdlePostureEnabled.return_value=True
        motion.stiffnessInterpolation.side_effect=lambda names,values,duration:events.append(('manual_stiffness' if names==MANUAL_NAMES else 'head_stiffness',tuple(values)))

        def kill(names):
            events.append(('kill',))
            future.cancelled = True

        motion.killTasksUsingResources.side_effect = kill
        abilities = {'BackgroundMovement': True, 'SpeakingMovement': False,
                     'ListeningMovement': True}
        if with_head:abilities['BasicAwareness']=True
        life = Mock()
        life.getState.return_value = 'solitary'
        life.getAutonomousAbilityEnabled.side_effect = lambda name: abilities[name]
        life.setAutonomousAbilityEnabled.side_effect = lambda name, value: events.append(('ability', name, value))
        memory = Mock()
        memory.getListData.side_effect=lambda keys:[float(pose[key.split('/')[2]]) if '/Position/' in key else 30. if '/Temperature/Sensor/Value' in key else 1. if '/Hardness/' in key else 0. for key in keys]
        services = {'ALMotion': motion, 'ALMemory': memory, 'ALAutonomousLife': life,
                    'ALSystem': types.SimpleNamespace(systemVersion=lambda: '2.8.7.7'),
                    'ALRobotPosture': types.SimpleNamespace(getPosture=lambda: 'Stand'),
                    'ALBattery': types.SimpleNamespace(getBatteryCharge=lambda: 60)}

        class Session:
            def connect(self, address):
                events.append(('fake_connect', address))

            def service(self, name):
                return services[name]

        spec = importlib.util.spec_from_file_location(
            'cleanup_worker', Path(__file__).resolve().parents[1] / 'app/robot_runner.py')
        worker = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'qi': types.SimpleNamespace(Session=Session)}):
            spec.loader.exec_module(worker)
        plan = build_diagnostic_plan(REST)
        if with_head or with_manual:
            t=np.arange(91)/30;targets=np.column_stack([.2*np.sin(t),.1*np.sin(2*t)])
            source={'joint_names':plan['names'],'times_s':t.tolist(),'angles_rad':np.tile(REST,(len(t),1)).tolist(),'interpolation':'uniform_cubic_control_points'}
            direction={'method':'fixture','events':[{'kind':'greeting','side':'L','at_s':.8}]} if with_manual else None
            plan=build_plan(source,REST,head_targets=targets if with_head else None,current_head=[0.,0.] if with_head else None,direction=direction,current_manual=[0.,0.,.02,.02] if with_manual else None)
            plan['initial_angles']=REST.tolist()+([0.,0.] if with_head else [])+([0.,0.,.02,.02] if with_manual else [])

        def open_file(path, *args, **kwargs):
            if path == 'fixture-plan.json':
                return io.StringIO(json.dumps(plan))
            if path == 'fixture-telemetry.jsonl':
                return telemetry
            raise AssertionError('Unexpected file access: ' + str(path))

        stop_checks = [0]

        def stop_file_exists(path):
            self.assertEqual(path, 'fixture-STOP')
            stop_checks[0] += 1
            # Before submission, during acknowledgement, then inside the loop.
            return stop_during_motion and stop_checks[0] >= 3

        def emit(event, **values):
            events.append(('event', event))

        def run():
            argv = ['worker', '--host', 'fake-robot', '--port', '9561', '--execute',
                    '--plan', 'fixture-plan.json', '--telemetry', 'fixture-telemetry.jsonl',
                    '--stop-file', 'fixture-STOP', '--constant-stiffness']
            with patch.object(sys, 'argv', argv), patch.object(worker, 'io', types.SimpleNamespace(open=open_file)), \
                    patch.object(worker.time, 'sleep'), patch.object(worker, 'os', types.SimpleNamespace(path=types.SimpleNamespace(exists=stop_file_exists))), \
                    patch.object(worker, 'emit', emit):
                worker.main()

        return run, events, motion, abilities

    def assert_restored(self, events, abilities):
        self.assertIn(('smart', False), events)
        self.assertIn(('smart', True), events)
        for name, original in abilities.items():
            writes = [event[2] for event in events if event[:2] == ('ability', name)]
            self.assertEqual(writes, [False, original])

    def assert_no_complete(self, events):
        self.assertNotIn(('event', 'complete'), events)

    def test_manual_activation_and_restore_after_complete(self):
        run,events,motion,abilities=self.fixture(with_head=True,with_manual=True)
        run()
        self.assertIn(('manual_stiffness',(.6,)*4),events)
        self.assertLess(events.index(('manual_stiffness',(0.,)*4)),events.index(('event','complete')))
        motion.setAngles.assert_any_call(MANUAL_NAMES,[0.,0.,.02,.02],.02)
        self.assert_restored(events,abilities)

    def test_manual_stop_restores_before_stopped(self):
        run,events,motion,abilities=self.fixture(with_head=True,with_manual=True,stop_during_motion=True)
        run()
        self.assertLess(events.index(('manual_stiffness',(0.,)*4)),events.index(('event','stopped')))
        self.assert_restored(events,abilities)

    def test_manual_restore_failure_does_not_hide_head_cleanup_or_emit_success(self):
        run,events,motion,abilities=self.fixture(with_head=True,with_manual=True)
        original=motion.stiffnessInterpolation.side_effect
        def fail_manual_restore(names,values,duration):
            original(names,values,duration)
            if names==MANUAL_NAMES and values==[0.]*4:raise RuntimeError('manual restore failed')
        motion.stiffnessInterpolation.side_effect=fail_manual_restore
        with self.assertRaisesRegex(RuntimeError,'manual restore failed'):run()
        self.assertIn(('head_stiffness',(0.,0.)),events)
        self.assert_no_complete(events)

    def test_head_activation_and_restore_are_scoped(self):
        run,events,motion,abilities=self.fixture(with_head=True)
        run()
        self.assertIn(('head_stiffness',(.7,.7)),events)
        self.assertIn(('head_stiffness',(0.,0.)),events)
        self.assertLess(events.index(('head_stiffness',(.7,.7))),events.index(('head_stiffness',(0.,0.))))
        self.assertLess(events.index(('head_stiffness',(0.,0.))),events.index(('event','complete')))
        motion.setAngles.assert_called_once_with(['HeadYaw','HeadPitch'],[0.,0.],.04)
        motion.setBreathEnabled.assert_any_call('Head',True)
        motion.setIdlePostureEnabled.assert_any_call('Head',True)
        self.assert_restored(events,abilities)

    def test_head_stop_restores_rigidity_before_stopped(self):
        run,events,motion,abilities=self.fixture(with_head=True,stop_during_motion=True)
        run()
        self.assertLess(events.index(('head_stiffness',(0.,0.))),events.index(('event','stopped')))
        self.assert_restored(events,abilities)

    def test_head_failure_still_restores_rigidity(self):
        run,events,motion,abilities=self.fixture(with_head=True,close_error=True)
        with self.assertRaisesRegex(OSError,'telemetry close failed'):run()
        self.assertIn(('head_stiffness',(0.,0.)),events)
        self.assert_no_complete(events)
        self.assert_restored(events,abilities)

    def test_success_is_emitted_only_after_flag_and_abilities_restored(self):
        run, events, motion, abilities = self.fixture()
        run()
        self.assert_restored(events, abilities)
        complete = events.index(('event', 'complete'))
        self.assertGreater(complete, events.index(('smart', True)))
        self.assertGreater(complete, events.index(('telemetry_close',)))
        for name, original in abilities.items():
            self.assertGreater(complete, max(k for k, event in enumerate(events)
                                            if event == ('ability', name, original)))
        motion.killTasksUsingResources.assert_not_called()

    def test_telemetry_close_failure_restores_and_never_announces_complete(self):
        run, events, motion, abilities = self.fixture(close_error=True)
        with self.assertRaisesRegex(OSError, 'telemetry close failed'):
            run()
        self.assert_restored(events, abilities)
        self.assert_no_complete(events)

    def test_write_and_close_failure_still_cancel_live_motion_and_restore(self):
        run, events, motion, abilities = self.fixture(close_error=True, write_error=True)
        with self.assertRaisesRegex(OSError, 'telemetry close failed'):
            run()
        motion.killTasksUsingResources.assert_called_once()
        self.assertGreater(events.index(('kill',)), events.index(('telemetry_close',)))
        self.assert_restored(events, abilities)
        self.assert_no_complete(events)

    def test_restore_failure_propagates_without_complete_and_restores_abilities(self):
        run, events, motion, abilities = self.fixture(restore_error=True)
        with self.assertRaisesRegex(RuntimeError, 'smart restore failed'):
            run()
        self.assert_restored(events, abilities)
        self.assert_no_complete(events)

    def test_stop_cancels_and_restores_before_stopped_event(self):
        run, events, motion, abilities = self.fixture(stop_during_motion=True)
        run()
        motion.killTasksUsingResources.assert_called_once()
        self.assert_restored(events, abilities)
        self.assert_no_complete(events)
        stopped = events.index(('event', 'stopped'))
        self.assertGreater(stopped, events.index(('smart', True)))
        for name, original in abilities.items():
            self.assertGreater(stopped, max(k for k, event in enumerate(events)
                                           if event == ('ability', name, original)))


if __name__ == '__main__':
    unittest.main()
