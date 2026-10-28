"""Opt-in, temporary Smart Stiffness override for an operator A/B test.

Compatible with the robot SDK's Python 2.7 and the local Python 3 runtime.
This scope changes only the Smart Stiffness flag, never joint stiffness values
or any collision, fall or diagnosis setting.
"""
from __future__ import absolute_import


class ConstantStiffness(object):
    def __init__(self, motion, enabled=True):
        self.motion = motion
        self.enabled = bool(enabled)
        self.previous = None
        self.entered = False

    def __enter__(self):
        if not self.enabled:
            return self
        self.previous = self.motion.getSmartStiffnessEnabled()
        if self.previous:
            try:
                self.motion.setSmartStiffnessEnabled(False)
            except BaseException:
                # A transport failure need not mean the robot rejected the write.
                # Restore even if disabling did not return an acknowledgement.
                self.motion.setSmartStiffnessEnabled(self.previous)
                raise
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.enabled and self.entered:
            self.entered = False
            # Do not hide restoration failures, including when the body failed.
            self.motion.setSmartStiffnessEnabled(self.previous)
        return False
