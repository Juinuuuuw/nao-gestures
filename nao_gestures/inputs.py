"""Explicit skeleton input adapters. Untrusted NPZ data never enables pickle."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from .kinematics import unit

# SMPL-X first 22 body joints (pelvis through wrists).
PARENTS = [-1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19]

def finite_array(value, label):
    a = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(a)):
        raise ValueError(label + ' contains NaN or infinity')
    return a

def load_json(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('coordinate_system') != 'nao_torso_x_forward_y_left_z_up':
        raise ValueError('JSON must declare NAO torso coordinates; see demo input')
    arms = finite_array(data['arms'], 'arms')
    # T x [left,right] x [shoulder,elbow,wrist] x xyz.
    if arms.ndim != 4 or arms.shape[1:] != (2, 3, 3):
        raise ValueError('arms must have shape [T,2,3,3]')
    return arms, float(data['fps']), data.get('source', 'landmark JSON')

def load_npz(path, rest_joints=None):
    """SMPL-X poses require actual rest joints, never a guessed human skeleton.

    A rest-joint NPY must contain J in the SAME shape/betas as the source.
    Axis-angle rotations are local; root/global motion is removed for torso gestures.
    """
    with np.load(path, allow_pickle=False) as data:
        fps = float(np.asarray(data['mocap_frame_rate']).item()) if 'mocap_frame_rate' in data else 30.
        if 'joints' in data:
            joints = finite_array(data['joints'], 'joints')
            if joints.ndim != 3 or joints.shape[1] < 22 or joints.shape[2] != 3:
                raise ValueError('joints must be [T,J>=22,3] in SMPL-X order')
        elif 'poses' in data:
            if rest_joints is None:
                raise ValueError('SMPL-X poses need --rest-joints rest_joints.npy; see README')
            poses = finite_array(data['poses'], 'poses')
            if poses.ndim != 2 or poses.shape[1] != 165:
                raise ValueError('Expected EMAGE poses [T,165] in axis-angle radians')
            rest = finite_array(np.load(rest_joints, allow_pickle=False), 'rest joints')
            if rest.ndim != 2 or rest.shape[0] < 22 or rest.shape[1] != 3:
                raise ValueError('rest joints must be [J>=22,3]')
            local = Rotation.from_rotvec(poses.reshape(-1,55,3)[:,:22].reshape(-1,3)).as_matrix().reshape(-1,22,3,3)
            world = np.zeros_like(local)
            joints = np.zeros((len(poses),22,3))
            world[:,0] = np.eye(3)  # Remove whole-body heading and translation.
            for j in range(1,22):
                p = PARENTS[j]
                joints[:,j] = joints[:,p] + np.einsum('tij,j->ti',world[:,p],rest[j]-rest[p])
                world[:,j] = world[:,p] @ local[:,j]
        else:
            raise ValueError('NPZ needs SMPL-X poses or joints')
    # Anatomical axes make import independent of global heading and conventions.
    # left x up = front in a right-handed frame. Also remove torso lean/twist:
    # the first prototype keeps the robot torso fixed.
    left = unit(joints[:,16] - joints[:,17])
    up = joints[:,12] - joints[:,0]
    up = unit(up - np.sum(up * left, axis=1, keepdims=True) * left)
    front = unit(np.cross(left, up))
    basis = np.stack([front, left, up], axis=-1)
    joints = np.einsum('tji,tik->tjk', joints-joints[:,0:1], basis)
    arms = np.stack([joints[:,[16,18,20]],joints[:,[17,19,21]]], axis=1)
    return finite_array(arms, 'converted arms'), fps, 'SMPL-X: ' + Path(path).name
