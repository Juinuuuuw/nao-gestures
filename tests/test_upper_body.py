import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from scipy.spatial.transform import Rotation
from app.upper_body import load_upper_body,HEAD_NAMES,head_coefficients,torso_coefficients,preview_trajectory
from app.robot_plan import build_plan,bezier_bounds
from nao_gestures.kinematics import NAMES,REST

class UpperBodyTests(unittest.TestCase):
    def fixture(self,directory):
        t=np.arange(121)/30;poses=np.zeros((len(t),55,3));rest=np.zeros((22,3))
        rest[12]=[0.,1.,0.];rest[16]=[1.,.8,0.];rest[17]=[-1.,.8,0.]
        basis=np.array([[0.,1.,0.],[0.,0.,1.],[1.,0.,0.]])
        yaw=.3*np.sin(t);pitch=.1*np.cos(t)
        head=Rotation.from_euler('ZYX',np.column_stack([yaw,pitch,np.zeros(len(t))])).as_matrix()
        poses[:,12]=Rotation.from_matrix(basis@head@basis.T).as_rotvec()
        torso=.06*np.sin(t)
        spine=Rotation.from_euler('Y',torso).as_matrix()
        poses[:,3]=Rotation.from_matrix(basis@spine@basis.T).as_rotvec()
        np.savez(directory/'emage_motion.npz',poses=poses.reshape(len(t),165),mocap_frame_rate=30.)
        np.save(directory/'rest_joints.npy',rest)
        source={'joint_names':NAMES,'times_s':t.tolist(),'angles_rad':np.tile(REST,(len(t),1)).tolist(),'interpolation':'uniform_cubic_control_points'}
        return source,yaw,pitch,torso

    def test_anatomical_axes_and_head_relative_to_spine(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);_,yaw,pitch,torso=self.fixture(d);upper=load_upper_body(d)
        np.testing.assert_allclose(upper['head_rad'],np.column_stack([yaw,pitch]),atol=1e-12)
        np.testing.assert_allclose(upper['torso_pitch_rad'],torso,atol=1e-12)

    def test_head_plan_is_bounded_returns_to_pose_and_has_no_leg_joints(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);source,*_=self.fixture(d);upper=load_upper_body(d)
        plan=build_plan(source,REST,head_targets=upper['head_rad'],current_head=[.1,.06])
        self.assertEqual(plan['names'],NAMES+HEAD_NAMES);self.assertFalse(plan['arm_only'])
        self.assertEqual(plan['scope'],'arms_head');self.assertTrue(plan['head_enabled'])
        np.testing.assert_allclose([p[-1][0] for p in plan['control_points'][-2:]],[.1,.06])
        np.testing.assert_allclose([p[0][0] for p in plan['control_points'][-2:]],[.1,.06])
        bounds=bezier_bounds({'times':plan['times'][-2:],'control_points':plan['control_points'][-2:]})
        self.assertLessEqual(bounds['velocity_bound_rad_s'],.451)
        self.assertLessEqual(bounds['acceleration_bound_rad_s2'],1.501)
        self.assertAlmostEqual(plan['speech_duration_s'],source['times_s'][-1])

    def test_torso_only_added_to_simulation_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);source,*_=self.fixture(d);upper=load_upper_body(d)
        preview=preview_trajectory(source,upper,torso=True)
        self.assertEqual(preview['joint_names'],NAMES+HEAD_NAMES)
        self.assertLessEqual(np.abs(preview['simulated_torso_pitch_rad']).max(),.025001)
        self.assertNotIn('simulated_torso_pitch_rad',source)
        self.assertEqual(source['joint_names'],NAMES)

    def test_nan_and_incompatible_clocks_are_rejected(self):
        with self.assertRaises(ValueError):head_coefficients(np.full((4,2),np.nan),30,[0,0])
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);source,*_=self.fixture(d);upper=load_upper_body(d)
        source['times_s'][1]+=.01
        with self.assertRaises(ValueError):preview_trajectory(source,upper)

if __name__=='__main__':unittest.main()
