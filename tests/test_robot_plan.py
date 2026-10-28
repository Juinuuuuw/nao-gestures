import unittest
from unittest.mock import patch
import numpy as np
from app.robot_plan import build_plan,build_diagnostic_plan,GESTURE_NEUTRAL,PACES,bezier_bounds
from nao_gestures.kinematics import NAMES,REST,LIMITS

class RobotPlanTests(unittest.TestCase):
    def test_diagnostic_arc_limits_continuity_and_speed(self):
        plan=build_diagnostic_plan(REST)
        self.assertTrue(plan['diagnostic'])
        self.assertAlmostEqual(np.degrees(plan['control_points'][0][1][0]-plan['control_points'][0][2][0]),40.107,places=2)
        for j,points in enumerate(plan['control_points']):
            times=plan['times'][j]
            self.assertAlmostEqual(points[0][0],REST[j]);self.assertAlmostEqual(points[-1][0],REST[j])
            for point in points:
                self.assertGreaterEqual(point[0],LIMITS[j,0]);self.assertLessEqual(point[0],LIMITS[j,1])
            for k in range(len(times)-1):
                delta=abs(points[k+1][0]-points[k][0]);dt=times[k+1]-times[k]
                self.assertLessEqual(1.5*delta/dt,.7+1e-9)
                self.assertLessEqual(6*delta/dt**2,2.+1e-9)
    def fixture(self):
        t=np.arange(150)/30;q=np.tile(REST,(150,1));q[:,0]+=.3*np.sin(t)**2
        return {'joint_names':NAMES,'interpolation':'uniform_cubic_control_points','times_s':t.tolist(),'angles_rad':q.tolist()}
    def test_reduced_plan_has_only_arms_and_valid_bezier_handles(self):
        plan=build_plan(self.fixture(),REST,.35)
        self.assertEqual(plan['names'],NAMES)
        self.assertEqual(len(plan['times']),8)
        self.assertGreater(plan['audio_start_s'],.8)
        self.assertLess(plan['audio_start_s'],2.)
        self.assertTrue(np.all(np.diff(plan['times'][0])>0))
        for j,points in enumerate(plan['control_points']):
            for angle,before,after in points:
                for position in (angle,angle+before[2],angle+after[2]):
                    self.assertGreaterEqual(position,LIMITS[j,0]-.001)
                    self.assertLessEqual(position,LIMITS[j,1]+.001)
        np.testing.assert_allclose([p[-1][0] for p in plan['control_points']],REST)
    def test_wrong_schema_and_nonfinite_sensors_are_rejected(self):
        bad=self.fixture();bad['joint_names']=['HeadYaw']
        with self.assertRaises(ValueError):build_plan(bad,REST)
        bad=self.fixture();current=REST.copy();current[0]=np.nan
        with self.assertRaises(ValueError):build_plan(bad,current)
    def test_high_intensity_rejected(self):
        with self.assertRaises(ValueError):build_plan(self.fixture(),REST,1.01)
        full=build_plan(self.fixture(),REST,1.)
        reduced=build_plan(self.fixture(),REST,.6)
        self.assertGreater(full['gesture_range_deg'][0],reduced['gesture_range_deg'][0]*1.5)
    def test_gesture_center_does_not_depend_on_starting_pose(self):
        other=REST.copy();other[[0,4]]+=.25
        a=build_plan(self.fixture(),REST);b=build_plan(self.fixture(),other)
        def speech(plan):
            t=np.array(plan['times'][0]);q=np.array([[p[0] for p in j] for j in plan['control_points']]).T
            # Entry includes its endpoint; following samples are the speech curve.
            return q[(t>=plan['audio_start_s']-1e-8)&(t<=plan['audio_start_s']+149/30+1e-8)]
        np.testing.assert_allclose(speech(a),speech(b),atol=1e-10)
        np.testing.assert_allclose(speech(a).mean(axis=0),GESTURE_NEUTRAL,atol=1e-10)
        self.assertGreater(a['effective_intensity'],.59)
    def test_bezier_velocity_and_acceleration_bounds(self):
        import json
        from pathlib import Path
        source=json.loads((Path(__file__).resolve().parents[1]/'examples/edge_pt/trajectory.json').read_text())
        plan=build_plan(source,REST)
        for times,points in zip(plan['times'],plan['control_points']):
            for k in range(len(times)-1):
                dt=times[k+1]-times[k];a,b=points[k:k+2]
                controls=np.array([a[0],a[0]+a[2][2],b[0]+b[1][2],b[0]])
                self.assertLessEqual(np.abs(3*np.diff(controls)/dt).max(),PACES['natural']['velocity']+1e-4)
                self.assertLess(np.abs(6*np.diff(controls,n=2)/dt**2).max(),5.)
    def test_paces_keep_speech_clock_and_bound_final_curve(self):
        source=self.fixture();t=np.array(source['times_s'])
        raw=np.tile(REST,(len(t),1));raw[:,0]+=.5*np.sin(2*np.pi*1.2*t)
        source['source_joint_targets_rad']=raw.tolist()
        plans={pace:build_plan(source,REST,pace=pace) for pace in PACES}
        for pace,plan in plans.items():
            self.assertAlmostEqual(plan['speech_duration_s'],t[-1])
            self.assertAlmostEqual(plan['duration_s']-plan['audio_start_s']-plan['exit_duration_s'],t[-1])
            bounds=bezier_bounds(plan)
            self.assertLessEqual(bounds['velocity_bound_rad_s'],PACES[pace]['velocity']+1e-4)
            self.assertLessEqual(bounds['acceleration_bound_rad_s2'],PACES[pace]['acceleration']+1e-3)
        self.assertLess(plans['brisk']['entry_duration_s'],plans['gentle']['entry_duration_s'])
        self.assertGreater(plans['brisk']['gesture_range_deg'][0],plans['gentle']['gesture_range_deg'][0])
        self.assertGreater(plans['brisk']['velocity_bound_rad_s'],plans['natural']['velocity_bound_rad_s'])
        self.assertGreater(plans['natural']['velocity_bound_rad_s'],plans['gentle']['velocity_bound_rad_s'])
    def test_bad_pace_and_nonuniform_clock_are_rejected(self):
        with self.assertRaises(ValueError):build_plan(self.fixture(),REST,pace='fastest')
        source=self.fixture();source['times_s'][2]+=.01
        with self.assertRaises(ValueError):build_plan(source,REST)

if __name__=='__main__':unittest.main()
