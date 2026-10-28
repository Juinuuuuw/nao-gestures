import unittest
from unittest.mock import Mock
from app.joint_activation import JointActivation

class JointActivationTests(unittest.TestCase):
    def fixture(self):
        motion=Mock();motion.getAngles.return_value=[0.,0.,.02,.02]
        return motion,JointActivation(motion,['LWristYaw','RWristYaw','LHand','RHand'],[0.]*4,[0.,0.,.02,.02])
    def test_restores_after_success(self):
        motion,scope=self.fixture()
        with scope:pass
        self.assertEqual(motion.stiffnessInterpolation.call_args_list[0].args[1],[.6]*4)
        self.assertEqual(motion.stiffnessInterpolation.call_args_list[-1].args[1],[0.]*4)
    def test_restores_after_body_failure(self):
        motion,scope=self.fixture()
        with self.assertRaises(RuntimeError):
            with scope:raise RuntimeError('failed')
        self.assertEqual(motion.stiffnessInterpolation.call_args_list[-1].args[1],[0.]*4)
    def test_stale_pose_rejected_before_activation(self):
        motion,scope=self.fixture();motion.getAngles.return_value=[.5,0.,.02,.02]
        with self.assertRaises(RuntimeError):scope.__enter__()
        motion.stiffnessInterpolation.assert_not_called()
    def test_partial_activation_failure_attempts_restoration(self):
        motion,scope=self.fixture();motion.stiffnessInterpolation.side_effect=[RuntimeError('RPC'),None]
        with self.assertRaises(RuntimeError):scope.__enter__()
        self.assertEqual(motion.stiffnessInterpolation.call_args_list[-1].args[1],[0.]*4)

if __name__=='__main__':unittest.main()
