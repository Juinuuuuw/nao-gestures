"""NAO arm FK in torso coordinates: x forward, y left, z up, metres/radians.

Reference: Aldebaran Links/Joints documentation; NAO V6 datasheet.
This reduced arm model omits hands, shell geometry and dynamics.
"""
import numpy as np
from scipy.spatial.transform import Rotation

NAMES = [s + j for s in ('L', 'R') for j in
         ('ShoulderPitch', 'ShoulderRoll', 'ElbowYaw', 'ElbowRoll')]
LIMITS = np.array([[-2.0857, 2.0857], [-.3142, 1.3265],
                   [-2.0857, 2.0857], [-1.5446, -.0349],
                   [-2.0857, 2.0857], [-1.3265, .3142],
                   [-2.0857, 2.0857], [.0349, 1.5446]])
REST = np.array([1.25, .20, -1.1, -.50, 1.25, -.20, 1.1, .50])

def rot(axis, angle):
    return Rotation.from_rotvec(np.eye(3)[axis] * angle).as_matrix()

def arm_fk(q, side):
    """Shoulder, elbow and wrist-yaw origin; includes lateral elbow offset."""
    if side not in ('L', 'R'):
        raise ValueError('side must be L or R')
    sign = 1 if side == 'L' else -1
    pitch, roll, yaw, bend = q
    shoulder = np.array([0., sign * .098, .100])
    base = rot(1, pitch) @ rot(2, roll)
    elbow = shoulder + base @ np.array([.105, sign * .015, 0.])
    wrist = elbow + base @ rot(0, yaw) @ rot(2, bend) @ np.array([.05595, 0., 0.])
    return np.stack([shoulder, elbow, wrist])

def unit(v):
    length = np.linalg.norm(v, axis=-1, keepdims=True)
    if np.any(length < 1e-8):
        raise ValueError('Zero-length limb in input')
    return v / length

def directions(points):
    return unit(np.diff(points, axis=-2))
