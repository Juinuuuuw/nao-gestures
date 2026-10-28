import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch,Mock
from nao_gestures.kinematics import REST,LIMITS

class ProbeTests(unittest.TestCase):
    def test_leg_trajectory_is_rejected_before_any_write(self):
        module,calls=self.load()
        plan={'names':['LHipPitch'],'arm_only':True,'initial_angles':[0.],'times':[[1.]],'control_points':[[[0.]]]}
        with patch.object(sys,'argv',['worker','--host','fake','--port','9561','--execute','--plan','fixture']),patch.object(module,'io',types.SimpleNamespace(open=lambda *a,**k:io.StringIO(__import__('json').dumps(plan)))),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'somente bracos e cabeca'):module.main()
        self.assertFalse(any(method.startswith(('set','kill','angleInterpolation','stiffnessInterpolation')) for _,method in calls))

    def test_head_pitch_range_depends_on_yaw(self):
        module,_=self.load()
        center=module.head_limits(0.)
        side=module.head_limits(1.52)
        self.assertGreater(side[0],center[0]);self.assertLess(side[1],center[1])
        self.assertLess(side[1],.25)
    def test_audio_clock_waits_for_new_robot_task_not_future_creation(self):
        module,_=self.load();motion=Mock();future=Mock();future.isFinished.return_value=False
        motion.getTaskList.side_effect=[[['angleInterpolationBezier',1]], [['angleInterpolationBezier',1],['angleInterpolationBezier',2]]]
        with patch.object(module.time,'sleep') as sleep:
            start=module.wait_for_motion_start(motion,future,{1},lambda:False)
        self.assertIsInstance(start,float);self.assertEqual(motion.getTaskList.call_count,2);sleep.assert_called_once()
    def test_motion_acknowledgement_can_be_cancelled(self):
        module,_=self.load();motion=Mock()
        self.assertIsNone(module.wait_for_motion_start(motion,Mock(),set(),lambda:True))
        motion.getTaskList.assert_not_called()
    def test_telemetry_evaluates_bezier_without_motor_calls(self):
        module,calls=self.load()
        plan={'times':[[1.,2.]],'initial_angles':[0.], 'control_points':[[[0.,[3,-.3,0.],[3,1./3,1./3]],[1.,[3,-1./3,-1./3],[3,.1,0.]]]]}
        self.assertAlmostEqual(module.planned_angles(plan,1.25)[0],.25)
        self.assertEqual(module.planned_angles(plan,0.),[0.])
        self.assertEqual(module.planned_angles(plan,3.),[1.])
        self.assertEqual(calls,[])
    def load(self,posture='Stand',stiffness=1):
        calls=[]
        class Service:
            def __init__(self,name):self.name=name
            def __getattr__(self,method):
                def read(*args):
                    calls.append((self.name,method))
                    values={'systemVersion':'2.8.7.7','getPosture':posture,'getBatteryCharge':40,'getAngles':REST.tolist(),'getStiffnesses':[stiffness]*8,'getState':'disabled','getSmartStiffnessEnabled':True}
                    if method=='getListData':return [0.]*len(args[0])
                    if method=='getLimits':return [list(x)+[8.,2.] for x in (LIMITS[:4] if args[0]=='LArm' else LIMITS[4:])]
                    if method not in values:raise AssertionError('Unexpected mutation: '+method)
                    return values[method]
                return read
        class Session:
            def connect(self,*args):pass
            def service(self,name):return Service(name)
        spec=importlib.util.spec_from_file_location('test_worker',Path(__file__).resolve().parents[1]/'app/robot_runner.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'qi':types.SimpleNamespace(Session=Session)}):spec.loader.exec_module(module)
        return module,calls
    def test_probe_never_writes_to_hardware(self):
        module,calls=self.load()
        with patch.object(sys,'argv',['worker','--host','127.0.0.1','--port','9561','--probe']),contextlib.redirect_stdout(io.StringIO()):module.main()
        self.assertGreater(len(calls),5)
        self.assertFalse(any(method.startswith(('set','kill','angleInterpolation')) for _,method in calls))
    def test_crouched_robot_rejected_before_motion(self):
        module,calls=self.load(posture='Crouch')
        with patch.object(sys,'argv',['worker','--host','127.0.0.1','--port','9561','--execute']),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'Stand'):module.main()
        self.assertFalse(any(method.startswith(('set','kill','angleInterpolation')) for _,method in calls))
    def test_unpowered_arms_rejected_before_motion(self):
        module,calls=self.load(stiffness=0)
        with patch.object(sys,'argv',['worker','--host','127.0.0.1','--port','9561','--execute']),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'rigidez'):module.main()
        self.assertFalse(any(method.startswith(('set','kill','angleInterpolation')) for _,method in calls))

if __name__=='__main__':unittest.main()
