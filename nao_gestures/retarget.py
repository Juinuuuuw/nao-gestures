"""Bounded IK and offline smoothing. Export is for review, not robot deployment."""
import numpy as np
from scipy.optimize import least_squares
from scipy.signal import savgol_filter
from .kinematics import LIMITS, REST, arm_fk, directions
from .trajectory import UniformCubic

def smooth_fixed_time(q, fps, max_velocity=1.2, max_acceleration=5., *,
                      velocity_weight=.008, acceleration_weight=.0008,joint_limits=None):
    """Convex trajectory fit with hard discrete position/velocity/acceleration limits.

    Limits apply to piecewise-linear targets, not all possible motor interpolators.
    Fixed clock: keep speech timing instead of stretching the entire performance.
    """
    import osqp
    from scipy import sparse
    if not all(np.isfinite(w) and w>=0 for w in (velocity_weight,acceleration_weight)):
        raise ValueError('Smoothing weights must be finite and nonnegative.')
    limits=LIMITS if joint_limits is None else np.asarray(joint_limits,float)
    if limits.shape!=(q.shape[1],2) or not np.isfinite(limits).all() or np.any(limits[:,0]>=limits[:,1]):
        raise ValueError('Invalid smoothing joint limits.')
    n=len(q)
    identity=sparse.eye(n,format='csc')
    d1=sparse.diags([-np.ones(n-1),np.ones(n-1)],[0,1],shape=(n-1,n),format='csc')*fps
    d2=sparse.diags([np.ones(n-2),-2*np.ones(n-2),np.ones(n-2)],[0,1,2],shape=(n-2,n),format='csc')*fps**2
    # Penalize accelerations softly as well as constraining their maxima.
    p=sparse.triu(2*(identity+velocity_weight*d1.T@d1+acceleration_weight*d2.T@d2),format='csc')
    a=sparse.vstack([identity,d1,d2],format='csc')
    result=np.empty_like(q)
    for j in range(q.shape[1]):
        lower=np.r_[np.full(n,limits[j,0]+.003),np.full(n-1,-max_velocity*.995),np.full(n-2,-max_acceleration*.995)]
        upper=np.r_[np.full(n,limits[j,1]-.003),np.full(n-1,max_velocity*.995),np.full(n-2,max_acceleration*.995)]
        # Repeated endpoint coefficients give stationary cubic boundaries.
        lower[n]=upper[n]=lower[n+n-2]=upper[n+n-2]=0.
        solver=osqp.OSQP()
        solver.setup(P=p,q=-2*q[:,j],A=a,l=lower,u=upper,verbose=False,eps_abs=1e-6,eps_rel=1e-6,max_iter=40000,polishing=True)
        solution=solver.solve()
        if solution.info.status_val!=1:
            raise ValueError('Trajectory optimization failed: '+solution.info.status)
        result[:,j]=solution.x
    return result

def fit(arms, fps, timing='preserve', include_raw=False):
    if len(arms) < 3 or not np.isfinite(fps) or not 1 <= fps <= 240:
        raise ValueError('Need >=3 finite frames and fps in [1,240]')
    targets = directions(arms)
    q = np.zeros((len(arms),8))
    previous = REST.copy()
    for t in range(len(arms)):
        for s,side in enumerate(('L','R')):
            sl = slice(4*s,4*s+4)
            def residual(a):
                error = (directions(arm_fk(a,side))-targets[t,s]).ravel()
                return np.r_[error, .025*(a-previous[sl])]
            result = least_squares(residual, previous[sl], bounds=(LIMITS[sl,0]+.002,LIMITS[sl,1]-.002),max_nfev=80)
            if not result.success:
                raise ValueError('IK failed at frame %d (%s): %s' % (t,side,result.message))
            q[t,sl] = result.x
        previous = q[t].copy()
    raw_q=q.copy()
    if timing=='preserve':
        q=smooth_fixed_time(q,fps)
    elif timing=='stretch' and len(q) >= 7:
        q = savgol_filter(q,7,2,axis=0,mode='interp')
    elif timing!='stretch':
        raise ValueError('timing must be preserve or stretch')
    q = np.clip(q,LIMITS[:,0]+.002,LIMITS[:,1]-.002)
    # Slow the entire clip uniformly to preserve shape/continuity, rather than
    # clipping successive samples and distorting gesture timing unpredictably.
    velocity = np.max(np.abs(np.diff(q,axis=0))*fps)
    acceleration = np.max(np.abs(np.diff(q,n=2,axis=0))*fps*fps)
    stretch = max(1.,velocity/1.2,np.sqrt(acceleration/5.)) if timing=='stretch' else 1.
    times = np.arange(len(q))/fps*stretch
    sampled=UniformCubic(q,fps)(np.arange(len(q))/fps) if timing=='preserve' else q
    predicted = np.stack([np.stack([arm_fk(row[:4],'L'),arm_fk(row[4:],'R')]) for row in sampled])
    predicted_dirs = directions(predicted)
    dot = np.sum(predicted_dirs*targets,axis=-1)
    angle_errors = np.degrees(np.arccos(np.clip(dot,-1,1)))
    report = {
        'frames':len(q),'source_fps':fps,'source_duration_s':(len(q)-1)/fps,
        'timing_mode':timing,
        'raw_max_velocity_rad_s':float(np.max(np.abs(np.diff(raw_q,axis=0)))*fps),
        'raw_max_acceleration_rad_s2':float(np.max(np.abs(np.diff(raw_q,n=2,axis=0)))*fps**2),
        'trajectory_adjustment_rms_deg':float(np.degrees(np.sqrt(np.mean((q-raw_q)**2)))),
        'output_duration_s':float(times[-1]),'time_stretch':float(stretch),
        'max_sampled_velocity_rad_s':float(velocity/stretch),
        'max_sampled_acceleration_rad_s2':float(acceleration/stretch**2),
        'mean_limb_direction_error_deg':float(angle_errors.mean()),
        'max_limb_direction_error_deg':float(angle_errors.max()),
        'within_static_joint_limits':bool(np.all((q>=LIMITS[:,0])&(q<=LIMITS[:,1]))),
        'hardware_validated':False,'collision_checked':False,'balance_checked':False,
        'audio_sync_valid':bool(stretch <= 1.000001),
        'note':'Fixed-time optimization trades pose fidelity for smoothness. Clock alignment is not a measurement of physical audio latency. Discrete limits do not certify hardware motion.' if timing=='preserve' else 'Time stretch changes audio alignment. Replan or retime audio before synchronized playback. Sample bounds do not certify interpolated motor motion.'
    }
    result=(q,times,predicted,report)
    return result+(raw_q,) if include_raw else result
