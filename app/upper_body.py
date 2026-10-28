"""EMAGE local neck/head and spine rotations in NAO anatomical axes."""
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from nao_gestures.inputs import unit
from nao_gestures.retarget import smooth_fixed_time

HEAD_NAMES=['HeadYaw','HeadPitch']
HEAD_LIMITS=np.array([[-2.0857,2.0857],[-.672,.5149]])
HEAD_GESTURE_LIMITS=np.array([[-.40,.40],[-.20,.20]])

def load_upper_body(directory):
    directory=Path(directory)
    with np.load(directory/'emage_motion.npz',allow_pickle=False) as data:
        poses=np.asarray(data['poses'],float)
        fps=float(np.asarray(data.get('mocap_frame_rate',30.)).item())
    rest=np.asarray(np.load(directory/'rest_joints.npy',allow_pickle=False),float)
    if poses.ndim!=2 or poses.shape[1]!=165 or len(poses)<3 or not np.isfinite(poses).all() or rest.ndim!=2 or rest.shape[0]<22 or rest.shape[1]!=3 or not np.isfinite(rest).all() or not 1<=fps<=240:
        raise ValueError('Dados EMAGE incompatíveis com cabeça/tronco.')
    left=unit(rest[16]-rest[17]);up=rest[12]-rest[0];up=unit(up-np.dot(up,left)*left)
    basis=np.stack([unit(np.cross(left,up)),left,up],axis=1)
    local=Rotation.from_rotvec(poses.reshape(-1,55,3).reshape(-1,3)).as_matrix().reshape(-1,55,3,3)
    def anatomical(rotations):return np.einsum('ij,tjk,kl->til',basis.T,rotations,basis)
    # Head relative to upper spine; root/spine lean is intentionally separate.
    head=anatomical(local[:,12]@local[:,15])
    yaw=np.unwrap(np.arctan2(head[:,1,0],head[:,0,0]))
    pitch=np.arctan2(-head[:,2,0],np.hypot(head[:,0,0],head[:,1,0]))
    spine=anatomical(local[:,3]@local[:,6]@local[:,9])
    torso=np.arctan2(-spine[:,2,0],np.hypot(spine[:,0,0],spine[:,1,0]))
    return {'fps':fps,'head_rad':np.column_stack([yaw,pitch]),'torso_pitch_rad':torso,
            'source':'EMAGE neck+head relative to upper spine; spine pitch for simulation only'}

def head_coefficients(head,fps,current):
    head=np.asarray(head,float);current=np.asarray(current,float)
    if head.ndim!=2 or head.shape[1]!=2 or len(head)<3 or current.shape!=(2,) or not np.isfinite(head).all() or not np.isfinite(current).all():
        raise ValueError('Trajetória da cabeça inválida.')
    center=np.clip(current,[-.18,-.08],[.18,.08])
    targets=np.clip(center+(head-head.mean(axis=0))*.7,HEAD_GESTURE_LIMITS[:,0]+.01,HEAD_GESTURE_LIMITS[:,1]-.01)
    return smooth_fixed_time(targets,fps,max_velocity=.45,max_acceleration=1.5,
                             velocity_weight=.004,acceleration_weight=.0003,joint_limits=HEAD_GESTURE_LIMITS)

def torso_coefficients(pitch,fps):
    pitch=np.asarray(pitch,float)
    if pitch.ndim!=1 or len(pitch)<3 or not np.isfinite(pitch).all():raise ValueError('Tronco inválido.')
    target=np.clip((pitch-pitch.mean())*.35,-.025,.025)[:,None]
    return smooth_fixed_time(target,fps,max_velocity=.04,max_acceleration=.12,
                             velocity_weight=.03,acceleration_weight=.003,joint_limits=[[-.028,.028]])[:,0]

def preview_trajectory(trajectory,upper,torso=False):
    data=dict(trajectory);q=np.asarray(data['angles_rad'],float)
    if len(q)!=len(upper['head_rad']) or not np.allclose(np.diff(data['times_s']),1/upper['fps'],atol=1e-7):raise ValueError('Relógios dos movimentos incompatíveis.')
    heads=head_coefficients(upper['head_rad'],upper['fps'],[0.,0.])
    data['joint_names']=list(data['joint_names'])+HEAD_NAMES
    data['angles_rad']=np.column_stack([q,heads]).tolist()
    data['upper_body_source']=upper['source']
    if torso:data['simulated_torso_pitch_rad']=torso_coefficients(upper['torso_pitch_rad'],upper['fps']).tolist()
    return data
