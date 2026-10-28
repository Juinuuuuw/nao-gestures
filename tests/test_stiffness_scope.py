import unittest
from unittest.mock import Mock, call

from app.stiffness_scope import ConstantStiffness


class ConstantStiffnessTests(unittest.TestCase):
    def motion(self, previous=True):
        motion = Mock()
        motion.getSmartStiffnessEnabled.return_value = previous
        return motion

    def test_normal_scope_disables_and_restores(self):
        motion = self.motion()
        with ConstantStiffness(motion) as scope:
            self.assertTrue(scope.entered)
            self.assertEqual(motion.mock_calls, [
                call.getSmartStiffnessEnabled(),
                call.setSmartStiffnessEnabled(False),
            ])
        self.assertEqual(motion.mock_calls[-1], call.setSmartStiffnessEnabled(True))
        self.assertFalse(scope.entered)

    def test_body_exception_is_propagated_after_restoration(self):
        motion = self.motion()
        failure = RuntimeError('body failed')
        with self.assertRaises(RuntimeError) as result:
            with ConstantStiffness(motion):
                raise failure
        self.assertIs(result.exception, failure)
        self.assertEqual(motion.mock_calls[-1], call.setSmartStiffnessEnabled(True))

    def test_previously_disabled_is_restored_to_false(self):
        motion = self.motion(False)
        with ConstantStiffness(motion):
            self.assertEqual(motion.mock_calls, [call.getSmartStiffnessEnabled()])
        self.assertEqual(motion.mock_calls, [
            call.getSmartStiffnessEnabled(),
            call.setSmartStiffnessEnabled(False),
        ])

    def test_disabled_scope_makes_no_calls_even_on_exception(self):
        motion = self.motion()
        with ConstantStiffness(motion, enabled=False):
            pass
        with self.assertRaises(ValueError):
            with ConstantStiffness(motion, enabled=False):
                raise ValueError('body')
        motion.assert_not_called()
        self.assertEqual(motion.mock_calls, [])

    def test_failed_disable_attempts_restore_then_propagates(self):
        motion = self.motion()
        failure = RuntimeError('disable failed')
        motion.setSmartStiffnessEnabled.side_effect = [failure, None]
        with self.assertRaises(RuntimeError) as result:
            with ConstantStiffness(motion):
                self.fail('body must not run')
        self.assertIs(result.exception, failure)
        self.assertEqual(motion.mock_calls, [
            call.getSmartStiffnessEnabled(),
            call.setSmartStiffnessEnabled(False),
            call.setSmartStiffnessEnabled(True),
        ])

    def test_restore_failure_is_not_hidden_by_body_exception(self):
        motion = self.motion()
        restore_failure = RuntimeError('restore failed')
        motion.setSmartStiffnessEnabled.side_effect = [None, restore_failure]
        with self.assertRaises(RuntimeError) as result:
            with ConstantStiffness(motion):
                raise ValueError('body failed')
        self.assertIs(result.exception, restore_failure)

    def test_restore_failure_during_enter_is_not_hidden(self):
        motion = self.motion()
        restore_failure = RuntimeError('restore failed')
        motion.setSmartStiffnessEnabled.side_effect = [ValueError('disable failed'), restore_failure]
        with self.assertRaises(RuntimeError) as result:
            with ConstantStiffness(motion):
                self.fail('body must not run')
        self.assertIs(result.exception, restore_failure)


if __name__ == '__main__':
    unittest.main()
