"""Build a reduced-amplitude arm-only plan for the physical executor."""
import numpy as np
from nao_gestures.kinematics import NAMES,LIMITS
from nao_gestures.trajectory import UniformCubic

GESTURE_NEUTRAL=np.array([.95,.24,-1.1,-.75,.95,-.24,1.1,.75])

def build_diagnostic_plan(current):
    current=np.asarray(current,float)
    if current.shape!=(8,) or not np.isfinite(current).all() or np.any(current<LIMITS[:,0]-.02) or np.any(current>LIMITS[:,1]+.02):
        raise ValueError('Postura inicial invÃ¡lida.')
    a=np.array([1.35,.3,-1.1,-.6,1.35,-.3,1.1,.6])
    b=np.array([.65,.45,-1.1,-1.,.65,-.45,1.1,1.])
    poses=np.vstack([current,a,b,a,current]);times=[.04]
    for first,last in zip(poses[:-1],poses[1:]):
        delta=float(np.abs(last-first).max())
        times.append(times[-1]+max(2. if np.array_equal(first,current) or np.array_equal(last,current) else 2.4,1.5*delta/.7,np.sqrt(6*delta/2.)))
    times=np.array(times)
    controls=[]
    for j in range(8):
        controls.append([[float(q[j]),[3,-float((times[k]-times[k-1])/3 if k else .04/3),0.],
                          [3,float((times[k+1]-times[k])/3 if k<4 else .01),0.]] for k,q in enumerate(poses)])
    return {'names':NAMES,'times':[times.tolist() for _ in NAMES],'control_points':controls,
            'initial_angles':current.tolist(),'audio_start_s':float(times[1]),'duration_s':float(times[-1]),'arm_only':True,
            'planner_version':3,'diagnostic':True,'description':'Arcos simÃ©tricos de ombros de 40 graus, sem fala.'}

PACES={
    'gentle':{'velocity':.8,'acceleration':3.5,'velocity_weight':.008,'acceleration_weight':.0008,'transition_min':2.,'transition_velocity':.65,'transition_acceleration':1.7},
    'natural':{'velocity':1.05,'acceleration':4.5,'velocity_weight':.002,'acceleration_weight':.0001,'transition_min':1.,'transition_velocity':.9,'transition_acceleration':2.8},
    'brisk':{'velocity':1.2,'acceleration':5.,'velocity_weight':.001,'acceleration_weight':.00002,'transition_min':.8,'transition_velocity':1.,'transition_acceleration':3.2},
}

def bezier_bounds(plan):
    velocity=acceleration=hand_velocity=hand_acceleration=0.
    for j,(times,points) in enumerate(zip(plan['times'],plan['control_points'])):
        for k in range(len(times)-1):
            a,b=points[k:k+2];dt=times[k+1]-times[k]
            controls=np.array([a[0],a[0]+a[2][2],b[0]+b[1][2],b[0]])
            v=float(np.abs(3*np.diff(controls)/dt).max());a2=float(np.abs(6*np.diff(controls,n=2)/dt**2).max())
            if plan.get('joint_units',['radians']*len(plan['times']))[j]=='open_fraction':
                hand_velocity=max(hand_velocity,v);hand_acceleration=max(hand_acceleration,a2)
            else:velocity=max(velocity,v);acceleration=max(acceleration,a2)
    return {'velocity_bound_rad_s':velocity,'acceleration_bound_rad_s2':acceleration,
            'hand_velocity_bound_fraction_s':hand_velocity,'hand_acceleration_bound_fraction_s2':hand_acceleration}

def build_plan(trajectory,current,intensity=1.,pace='natural',head_targets=None,current_head=None,direction=None,current_manual=None,emotion='neutral',emotion_cues=None):
    from app.emotion import profile,apply_emotion,BODY_STYLES
    expression=profile(emotion)
    from nao_gestures.retarget import smooth_fixed_time
    if pace not in PACES:raise ValueError('Ritmo desconhecido.')
    cfg=PACES[pace]
    if trajectory.get('joint_names')!=NAMES or trajectory.get('interpolation')!='uniform_cubic_control_points':
        raise ValueError('Trajetória incompatível com o executor físico.')
    if not .1<=float(intensity)<=1.:raise ValueError('Intensidade deve estar entre 10 e 100%.')
    t=np.asarray(trajectory['times_s'],float);current=np.asarray(current,float)
    q=np.asarray(trajectory.get('source_joint_targets_rad',trajectory['angles_rad']),float)
    if current.shape!=(8,) or q.shape!=(len(t),8) or len(t)<3 or not np.isfinite(t).all() or not np.all(np.diff(t)>0) or not np.isfinite(q).all() or not np.isfinite(current).all():
        raise ValueError('Trajetória inválida.')
    if abs(t[0])>1e-8 or not np.allclose(np.diff(t),np.diff(t).mean(),rtol=1e-4,atol=1e-8):
        raise ValueError('A trajetória deve ter relógio uniforme e iniciar em zero.')
    if t[-1]>60:raise ValueError('Nesta versão, use falas de até 60 segundos.')
    if np.any(current<LIMITS[:,0]-.02) or np.any(current>LIMITS[:,1]+.02):raise ValueError('Sensores fora dos limites esperados.')
    fps=1/np.diff(t).mean()
    source=q if 'source_joint_targets_rad' in trajectory else UniformCubic(q,fps)(t)
    deviation=source-source.mean(axis=0);gain=float(intensity)
    for j in range(8):
        low,high=deviation[:,j].min(),deviation[:,j].max()
        if low<0:gain=min(gain,(GESTURE_NEUTRAL[j]-LIMITS[j,0]-.02)/-low)
        if high>0:gain=min(gain,(LIMITS[j,1]-.02-GESTURE_NEUTRAL[j])/high)
    targets=GESTURE_NEUTRAL+deviation*gain
    manual=None
    if direction is not None:
        from app.direction import direct_motion
        targets,head_targets,manual=direct_motion(targets,head_targets,t,direction)
    cue_times=[cue['at_s'] for cue in (emotion_cues or [])]
    targets,head_targets,manual=apply_emotion(targets,head_targets,manual,t,emotion,cue_times=cue_times)
    # Enforce physical limits AFTER amplitude adaptation; do not attenuate the
    # source velocity limit by the amplitude again. Keep the speech clock fixed.
    coefficients=smooth_fixed_time(targets,fps,max_velocity=cfg['velocity'],max_acceleration=cfg['acceleration'],
                                   velocity_weight=cfg['velocity_weight'],acceleration_weight=cfg['acceleration_weight'])
    names=list(NAMES);limits=LIMITS
    transition_velocity=np.full(8,cfg['transition_velocity']);transition_acceleration=np.full(8,cfg['transition_acceleration'])
    if head_targets is not None:
        from app.upper_body import HEAD_NAMES,HEAD_LIMITS,head_coefficients
        current_head=np.asarray(current_head,float)
        if current_head.shape!=(2,) or not np.isfinite(current_head).all() or np.any(current_head<HEAD_LIMITS[:,0]) or np.any(current_head>HEAD_LIMITS[:,1]):
            raise ValueError('Posição inicial da cabeça inválida.')
        if np.shape(head_targets)!=(len(t),2):raise ValueError('Relógio da cabeça incompatível.')
        heads=head_coefficients(head_targets,fps,current_head,pitch_bias=expression['pitch_bias'],yaw_bias=BODY_STYLES[emotion]['yaw_bias'])
        coefficients=np.column_stack([coefficients,heads]);current=np.r_[current,current_head]
        names+=HEAD_NAMES;limits=np.vstack([LIMITS,HEAD_LIMITS])
        transition_velocity=np.r_[transition_velocity,[.35,.35]]
        transition_acceleration=np.r_[transition_acceleration,[1.,1.]]
    if manual is not None:
        from app.direction import MANUAL_NAMES,MANUAL_LIMITS,MANUAL_GESTURE_LIMITS
        current_manual=np.asarray(current_manual,float)
        if current_manual.shape!=(4,) or not np.isfinite(current_manual).all() or np.any(current_manual<MANUAL_LIMITS[:,0]-.002) or np.any(current_manual>MANUAL_LIMITS[:,1]+.002):
            raise ValueError('Leitura de punhos e mãos inválida.')
        wrists=smooth_fixed_time(manual[:,:2],fps,max_velocity=.65,max_acceleration=2.,velocity_weight=.003,acceleration_weight=.0002,joint_limits=MANUAL_GESTURE_LIMITS[:2])
        hands=smooth_fixed_time(manual[:,2:],fps,max_velocity=1.,max_acceleration=3.,velocity_weight=.002,acceleration_weight=.0001,joint_limits=MANUAL_GESTURE_LIMITS[2:])
        coefficients=np.column_stack([coefficients,wrists,hands]);current=np.r_[current,current_manual]
        names+=MANUAL_NAMES;limits=np.vstack([limits,MANUAL_LIMITS])
        transition_velocity=np.r_[transition_velocity,[.5,.5,.8,.8]]
        transition_acceleration=np.r_[transition_acceleration,[1.5,1.5,2.,2.]]
    curve=UniformCubic(coefficients,fps)
    first,last=curve(np.array([0.,t[-1]]))
    def duration(a,b):
        delta=np.abs(b-a)
        return max(cfg['transition_min'],float(np.max(1.875*delta/transition_velocity)),float(np.sqrt(5.774*delta/transition_acceleration).max()))*1.02
    entry,exit_time=duration(current,first),duration(last,current)
    def transition(a,b,start,length):
        at=np.linspace(0,length,int(np.ceil(length*50))+1);u=at/length
        values=a+(b-a)*(u**3*(10-15*u+6*u*u))[:,None]
        slopes=(b-a)*(30*u*u*(1-u)**2/length)[:,None]
        return at+start,values,slopes
    ti,pi,vi=transition(current,first,.04,entry)
    te,pe,ve=transition(last,current,.04+entry+t[-1],exit_time)
    n=len(coefficients);indices=np.arange(n)
    previous=coefficients[np.maximum(indices-1,0)];following=coefficients[np.minimum(indices+1,n-1)]
    speech_values=curve(t)
    speech_slopes=(following-previous)*fps/2.
    # Use the original spline knots and its exact derivative. Each Hermite
    # segment is then exactly the same cubic, without 25 Hz resampling error.
    times=np.r_[ti,t[1:]+.04+entry,te[1:]]
    angles=np.vstack([pi,speech_values[1:],pe[1:]])
    velocities=np.vstack([vi,speech_slopes[1:],ve[1:]])
    controls=[]
    for j in range(len(names)):
        points=[]
        for k,(at,angle) in enumerate(zip(times,angles[:,j])):
            before=(at-times[k-1])/3 if k else at/3
            after=(times[k+1]-at)/3 if k+1<len(times) else .01
            points.append([float(angle),[3,-float(before),float(-velocities[k,j]*before)],
                           [3,float(after),float(velocities[k,j]*after)]])
        controls.append(points)
    plan={'names':names,'times':[times.tolist() for _ in names],'control_points':controls,
          'audio_start_s':float(.04+entry),'speech_duration_s':float(t[-1]),'entry_duration_s':entry,'exit_duration_s':exit_time,
          'duration_s':float(times[-1]),'intensity':float(intensity),'effective_intensity':gain,'pace':pace,
          'raw_targets_available':'source_joint_targets_rad' in trajectory,'planner_version':9,
          'body_style':BODY_STYLES[emotion]['label'],'emotion_cues':emotion_cues or [],
          'emotion':emotion,'emotion_label':expression['label'],'eye_color':expression['color'],
          'manual_method':'arm posture and motion energy + intent accents' if manual is not None else None,
          'joint_units':['open_fraction' if name in ('LHand','RHand') else 'radians' for name in names],
          'gesture_range_deg':[None if name in ('LHand','RHand') else float(np.degrees(np.ptp(speech_values[:,j]))) for j,name in enumerate(names)],
          'hand_range_fraction':{name:float(np.ptp(speech_values[:,j])) for j,name in enumerate(names) if name in ('LHand','RHand')},
          'arm_only':head_targets is None and manual is None,'hand_enabled':manual is not None,
          'head_enabled':head_targets is not None,'scope':('arms_head' if head_targets is not None else 'arms')+('_hands' if manual is not None else ''),
          'intent_events':direction['events'] if direction is not None else [],'intent_method':direction['method'] if direction is not None else None}
    bounds=bezier_bounds(plan);plan.update(bounds)
    if bounds['velocity_bound_rad_s']>cfg['velocity']+1e-4 or bounds['acceleration_bound_rad_s2']>cfg['acceleration']+1e-3:
        raise ValueError('A curva física ultrapassou os limites do perfil de ritmo.')
    for j,points in enumerate(controls):
        if names[j] in ('HeadYaw','HeadPitch'):
            hb=bezier_bounds({'times':[plan['times'][j]],'control_points':[points]})
            if hb['velocity_bound_rad_s']>.4501 or hb['acceleration_bound_rad_s2']>1.501:raise ValueError('Velocidade da cabeça fora do limite.')
        if names[j] in ('LWristYaw','RWristYaw','LHand','RHand'):
            mb=bezier_bounds({'times':[plan['times'][j]],'control_points':[points]})
            mv,ma=(1.,3.) if names[j] in ('LHand','RHand') else (.65,2.)
            if mb['velocity_bound_rad_s']>mv+.001 or mb['acceleration_bound_rad_s2']>ma+.001:raise ValueError('Velocidade de mão/punho fora do limite.')
        for angle,before,after in points:
            if any(not limits[j,0]-.001<=position<=limits[j,1]+.001 for position in (angle,angle+before[2],angle+after[2])):
                raise ValueError('A interpolação física ultrapassou os limites de articulação.')
    return plan
