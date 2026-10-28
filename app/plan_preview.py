"""Sample the physical Bezier plan for Webots speech playback (no SDK)."""
import numpy as np
from nao_gestures.trajectory import UniformCubic

def sample_plan(plan,at):
    at=np.asarray(at,float);values=[]
    for j,(ts,ps) in enumerate(zip(plan['times'],plan['control_points'])):
        ts=np.asarray(ts);q=np.array([p[0] for p in ps]);left=np.array([p[1][2] for p in ps]);right=np.array([p[2][2] for p in ps])
        k=np.clip(np.searchsorted(ts,at,side='right')-1,0,len(ts)-2);dt=ts[k+1]-ts[k];u=np.clip((at-ts[k])/dt,0.,1.)
        a=q[k];b=a+right[k];d=q[k+1];c=d+left[k+1]
        result=(1-u)**3*a+3*(1-u)**2*u*b+3*(1-u)*u*u*c+u**3*d
        result[at<ts[0]]=plan['initial_angles'][j];result[at>=ts[-1]]=q[-1]
        values.append(result)
    return np.stack(values,axis=-1)

def speech_preview(plan,torso=None,torso_fps=30.):
    duration=plan['speech_duration_s'];times=np.linspace(0,duration,int(np.ceil(duration*120))+1)
    data={'joint_names':plan['names'],'joint_units':plan['joint_units'],'times_s':times.tolist(),
          'angles_rad':sample_plan(plan,times+plan['audio_start_s']).tolist(),
          'interpolation':'uniform_cubic_control_points','intent_events':plan.get('intent_events',[]),
          'source':'Sampled physical speech plan; Webots cubic playback adds slight smoothing',
          'pace':plan['pace'],'hand_enabled':plan.get('hand_enabled',False)}
    if torso is not None:
        data['simulated_torso_pitch_rad']=UniformCubic(np.asarray(torso)[:,None],torso_fps)(times)[:,0].tolist()
    return data
