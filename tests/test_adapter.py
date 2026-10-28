import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from nao_gestures.kinematics import LIMITS, arm_fk, directions
from nao_gestures.inputs import load_json, load_npz
from nao_gestures.retarget import fit

class AdapterTests(unittest.TestCase):
    def test_documented_zero_pose_offsets(self):
        np.testing.assert_allclose(arm_fk([0,0,0,0],'L'),[[0,.098,.1],[.105,.113,.1],[.16095,.113,.1]])
        np.testing.assert_allclose(arm_fk([0,0,0,0],'R'),[[0,-.098,.1],[.105,-.113,.1],[.16095,-.113,.1]])

    def test_elbow_signs_bend_toward_body(self):
        for side,bend in [('L',-.8),('R',.8)]:
            p=arm_fk([0,0,0,bend],side)
            self.assertLess(p[2,1]-p[1,1],0) if side=='L' else self.assertGreater(p[2,1]-p[1,1],0)

    def test_known_feasible_target_and_time_limits(self):
        q=np.array([.7,.4,-.8,-.9,.7,-.4,.8,.9])
        frame=np.stack([arm_fk(q[:4],'L'),arm_fk(q[4:],'R')])
        arms=np.repeat(frame[None],15,axis=0)
        out,t,robot,report=fit(arms,30)
        self.assertLess(report['mean_limb_direction_error_deg'],1.)
        self.assertTrue(np.all((out>=LIMITS[:,0])&(out<=LIMITS[:,1])))
        self.assertTrue(np.all(np.diff(t)>0))

    def test_abrupt_input_is_retimed_and_flagged(self):
        frames=[]
        for i in range(30):
            pitch=-.7 if i>=15 else 1.5
            frames.append([arm_fk([pitch,.2,-1.,-.6],'L'),arm_fk([pitch,-.2,1.,.6],'R')])
        _,_,_,report=fit(np.array(frames),30,timing='stretch')
        self.assertGreater(report['time_stretch'],1.)
        self.assertFalse(report['audio_sync_valid'])
        self.assertLessEqual(report['max_sampled_velocity_rad_s'],1.200001)
        self.assertLessEqual(report['max_sampled_acceleration_rad_s2'],5.000001)

    def test_fixed_time_optimizer_preserves_duration_under_abrupt_input(self):
        frames=[]
        for i in range(60):
            pitch=.3 if i>=30 else 1.4
            frames.append([arm_fk([pitch,.2,-1.,-.6],'L'),arm_fk([pitch,-.2,1.,.6],'R')])
        _,t,_,report=fit(np.array(frames),30)
        self.assertAlmostEqual(t[-1],59/30)
        self.assertTrue(report['audio_sync_valid'])
        self.assertLessEqual(report['max_sampled_velocity_rad_s'],1.20001)
        self.assertLessEqual(report['max_sampled_acceleration_rad_s2'],5.00001)

    def test_cubic_interpolator_respects_dense_derivative_bounds(self):
        from nao_gestures.retarget import smooth_fixed_time
        from nao_gestures.trajectory import UniformCubic
        rng=np.random.default_rng(17)
        q=rng.uniform(LIMITS[:,0],LIMITS[:,1],size=(120,8))
        c=smooth_fixed_time(q,30)
        curve=UniformCubic(c,30)
        t=np.linspace(0,119/30,11901);sample=curve(t);dt=t[1]-t[0]
        self.assertLessEqual(np.abs(np.diff(sample,axis=0)).max()/dt,1.201)
        self.assertLessEqual(np.abs(np.diff(sample,n=2,axis=0)).max()/dt**2,5.01)
        self.assertTrue(np.all((sample>=LIMITS[:,0])&(sample<=LIMITS[:,1])))
        np.testing.assert_allclose(curve(0),c[0],atol=1e-6)
        np.testing.assert_allclose(curve(119/30),c[-1],atol=1e-6)

    def test_missing_rest_skeleton_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'poses.npz';np.savez(path,poses=np.zeros((3,165)))
            with self.assertRaisesRegex(ValueError,'rest-joints'):load_npz(path)

    def test_nan_and_zero_limb_rejected(self):
        bad=np.zeros((3,2,3,3))
        with self.assertRaises(ValueError):fit(bad,30)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.json';bad[0,0,0,0]=float('nan')
            path.write_text(json.dumps({'arms':bad.tolist(),'fps':30,'coordinate_system':'nao_torso_x_forward_y_left_z_up'}))
            with self.assertRaisesRegex(ValueError,'NaN'):load_json(path)

    def test_smplx_import_removes_global_rotation(self):
        from scipy.spatial.transform import Rotation
        joints=np.zeros((3,22,3))
        # An anatomical T pose in human coordinates: x left, y up, z front.
        joints[:,12]=[0,.5,0]
        joints[:,16]=[.2,.4,0];joints[:,17]=[-.2,.4,0]
        joints[:,18]=[.45,.4,0];joints[:,19]=[-.45,.4,0]
        joints[:,20]=[.65,.4,.1];joints[:,21]=[-.65,.4,.1]
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a.npz';b=Path(folder)/'b.npz'
            np.savez(a,joints=joints,mocap_frame_rate=30)
            rotation=Rotation.from_euler('xyz',[.3,.8,-.4]).as_matrix()
            np.savez(b,joints=joints@rotation.T+np.array([3,4,5]),mocap_frame_rate=30)
            first,_,_=load_npz(a);second,_,_=load_npz(b)
            np.testing.assert_allclose(first,second,atol=1e-12)
            self.assertGreater(first[0,0,1,1],first[0,0,0,1])
            self.assertGreater(first[0,0,2,0],first[0,0,1,0])

if __name__=='__main__':unittest.main()
