"""Raw IK targets remain available for physical planning on the speech clock."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from nao_gestures.__main__ import export
from nao_gestures.kinematics import LIMITS, REST, arm_fk
from nao_gestures.retarget import fit, smooth_fixed_time


class RawTargetsTests(unittest.TestCase):
    def fixture(self):
        times=np.arange(61)/30
        targets=np.tile(REST,(len(times),1))
        targets[:,0]+=.22*np.sin(2*np.pi*2*times)
        arms=np.stack([np.stack([arm_fk(q[:4],'L'),arm_fk(q[4:],'R')]) for q in targets])
        return targets,arms

    def test_raw_targets_preserve_ik_before_smoothing_and_default_tuple(self):
        targets,arms=self.fixture()
        self.assertEqual(len(fit(arms,30)),4)
        smoothed,times,_,_,raw=fit(arms,30,include_raw=True)
        self.assertEqual(raw.shape,smoothed.shape)
        np.testing.assert_allclose(raw,targets,atol=.004)
        self.assertGreater(np.abs(np.diff(raw[:,0])*30).max(),1.2)
        self.assertLessEqual(np.abs(np.diff(smoothed,axis=0)*30).max(),1.2+1e-5)
        self.assertGreater(np.abs(smoothed-raw).max(),.01)
        self.assertAlmostEqual(times[-1],2.)

    def test_export_labels_raw_targets_separately_from_spline_coefficients(self):
        targets,arms=self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source.json';output=root/'result'
            source.write_text(json.dumps({'fps':30,'coordinate_system':'nao_torso_x_forward_y_left_z_up','arms':arms.tolist()}),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):export(source,output)
            data=json.loads((output/'trajectory.json').read_text(encoding='utf-8'))
            self.assertEqual(data['interpolation'],'uniform_cubic_control_points')
            self.assertIn('not spline control coefficients',data['source_joint_targets_representation'])
            np.testing.assert_allclose(data['source_joint_targets_rad'],targets,atol=.004)
            self.assertGreater(np.abs(np.array(data['angles_rad'])-data['source_joint_targets_rad']).max(),.01)

    def test_weaker_penalty_preserves_more_motion_with_same_hard_limits(self):
        targets,_=self.fixture()
        original=smooth_fixed_time(targets,30)
        responsive=smooth_fixed_time(targets,30,velocity_weight=.002,acceleration_weight=.0001)
        self.assertLess(np.mean((responsive-targets)**2),np.mean((original-targets)**2))
        self.assertLessEqual(np.abs(np.diff(responsive,axis=0)*30).max(),1.2+1e-5)
        self.assertLessEqual(np.abs(np.diff(responsive,n=2,axis=0)*900).max(),5.+1e-5)
        self.assertTrue(np.all(responsive>=LIMITS[:,0]))
        self.assertTrue(np.all(responsive<=LIMITS[:,1]))
        self.assertEqual(responsive.shape,targets.shape)

    def test_invalid_weights_are_rejected(self):
        targets,_=self.fixture()
        for weight in (-.1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):smooth_fixed_time(targets,30,velocity_weight=weight)
            with self.assertRaises(ValueError):smooth_fixed_time(targets,30,acceleration_weight=weight)


if __name__=='__main__':unittest.main()
