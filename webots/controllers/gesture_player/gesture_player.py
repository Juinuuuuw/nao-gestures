"""Webots-only playback and telemetry. Never connects to a physical robot.

12 ms simulation clock, C1-continuous joint interpolation, staged entry and exit.
No Supervisor pose resets or root pinning: falls remain visible and logged.
"""
import argparse
import csv
from datetime import datetime,timezone
import json
import math
import os
import time
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from controller import Supervisor,Speaker
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from nao_gestures.kinematics import LIMITS,NAMES
from nao_gestures.trajectory import UniformCubic
from app.upper_body import HEAD_NAMES,HEAD_LIMITS
from app.direction import MANUAL_NAMES,MANUAL_LIMITS
from virtual_hand import VirtualHand
def main():
    p=argparse.ArgumentParser();p.add_argument('--trajectory',default='examples/edge_pt/trajectory.json');p.add_argument('--audio',default='examples/edge_pt/speech.wav');p.add_argument('--out',default='webots/results/edge_pt');p.add_argument('--quit',action='store_true',default=os.environ.get('NAO_LAB_QUIT')=='1');p.add_argument('--mute',action='store_true',default=os.environ.get('NAO_LAB_MUTE')=='1');p.add_argument('--capture',action='store_true',default=os.environ.get('NAO_LAB_CAPTURE')=='1');args=p.parse_args()
    if os.environ.get('NAO_LAB_OUT'):args.out=os.environ['NAO_LAB_OUT']
    robot=Supervisor();step=int(robot.getBasicTimeStep());node=robot.getSelf()
    data=json.loads((ROOT/args.trajectory).read_text(encoding='utf-8'))
    names=data['joint_names'];times=np.array(data['times_s']);q=np.array(data['angles_rad'])
    if times.ndim!=1 or q.shape!=(len(times),len(names)) or not np.isfinite(q).all() or not np.isfinite(times).all() or not np.all(np.diff(times)>0):raise ValueError('Invalid trajectory')
    interpolate=UniformCubic(q,1/float(np.diff(times).mean())) if data.get('interpolation')=='uniform_cubic_control_points' else PchipInterpolator(times,q,axis=0,extrapolate=False)
    first=interpolate(times[0]);last=interpolate(times[-1])
    has_head=all(name in names for name in HEAD_NAMES)
    has_hands=all(name in names for name in ('LHand','RHand'))
    angular_indices=[j for j,name in enumerate(names) if name not in ('LHand','RHand')]
    head_indices=[names.index(name) for name in HEAD_NAMES] if has_head else []
    hand_indices=[names.index(name) for name in ('LHand','RHand')] if has_hands else []
    torso=np.array(data.get('simulated_torso_pitch_rad',np.zeros(len(times))),float)
    if torso.shape!=(len(times),) or not np.isfinite(torso).all() or np.abs(torso).max()>.026:raise ValueError('Invalid simulated torso lean')
    torso_curve=UniformCubic(torso[:,None],1/float(np.diff(times).mean()))
    torso_first=float(torso_curve(times[0])[0]);torso_last=float(torso_curve(times[-1])[0])
    limit_map=dict(zip(NAMES,LIMITS));limit_map.update(dict(zip(HEAD_NAMES,HEAD_LIMITS)))
    limit_map.update(dict(zip(MANUAL_NAMES,MANUAL_LIMITS)))
    out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True)
    motors=[VirtualHand(robot,name[0]) if name in ('LHand','RHand') else robot.getDevice(name) for name in names];sensors=[];limits={}
    for name,m in zip(names,motors):
        j=names.index(name)
        if name not in limit_map:raise ValueError('Unknown trajectory joint: '+name)
        lo=max(m.getMinPosition(),limit_map[name][0]);hi=min(m.getMaxPosition(),limit_map[name][1]);limits[name]=[lo,hi,m.getMaxVelocity()]
        if np.any(q[:,j]<lo-1e-5) or np.any(q[:,j]>hi+1e-5):raise ValueError('Motor limit exceeded: '+name)
        m.setVelocity(min(.6 if name in HEAD_NAMES else 1.5,m.getMaxVelocity()))
        sensor=m.getPositionSensor();sensor.enable(step);sensors.append(sensor)
    # Symmetric modest knee bend. Motors remain physical, without fixing the base.
    for name,target in {'HeadYaw':0.,'HeadPitch':0.,'LHipYawPitch':0.,'RHipYawPitch':0.,'LHipRoll':0.,'RHipRoll':0.,'LHipPitch':-.15,'RHipPitch':-.15,'LKneePitch':.3,'RKneePitch':.3,'LAnklePitch':-.15,'RAnklePitch':-.15,'LAnkleRoll':0.,'RAnkleRoll':0.,'LWristYaw':0.,'RWristYaw':0.}.items():
        m=robot.getDevice(name)
        if m:m.setVelocity(min(.8,m.getMaxVelocity()));m.setPosition(target)
    for i in range(robot.getNumberOfDevices()):
        d=robot.getDeviceByIndex(i)
        if 'Phalanx' in d.getName() and hasattr(d,'setPosition'):d.setPosition(.25)
    speaker=robot.getDevice('speech')
    robot.step(step)
    initial=np.array([s.getValue() for s in sensors])
    rest_map=dict(zip(NAMES,[1.25,.2,-1.1,-.5,1.25,-.2,1.1,.5]));rest_map.update({'HeadYaw':0.,'HeadPitch':0.,'LWristYaw':0.,'RWristYaw':0.,'LHand':.42,'RHand':.42})
    rest=np.array([rest_map[name] for name in names])
    def transition_duration(a,b,minimum):
        delta=float(np.max(np.abs(b-a)))
        return max(minimum,1.875*delta/1.2,math.sqrt(5.774*delta/5.))
    prepare=transition_duration(initial,rest,3.)
    entry=transition_duration(rest,first,2.)
    exit_duration=transition_duration(last,rest,2.)
    start=prepare+entry
    end=start+times[-1];finish=end+exit_duration+1.
    rows=[];played=False;audio_start=None;capture_count=0;capture_dir=out/'frames';movie_started=False;movie_stopped=False;active_wall_start=None;drifts=[]
    if args.capture:capture_dir.mkdir(exist_ok=True)
    eyes=[];eye_original=[];eye_active=False
    if data.get('eye_color') is not None:
        eyes=[robot.getDevice('Face/Led/Left'),robot.getDevice('Face/Led/Right')]
        eye_original=[eye.get() for eye in eyes]
    clock0=robot.getTime();wall0=time.perf_counter()
    def blend(a,b,f):
        f=min(1.,max(0.,f));s=f*f*f*(10-15*f+6*f*f);return a*(1-s)+b*s
    while robot.step(step)!=-1:
        t=robot.getTime()-clock0
        should_express=start<=t<end
        if eyes and should_express!=eye_active:
            for eye,original in zip(eyes,eye_original):eye.set(int(data['eye_color']) if should_express else original)
            eye_active=should_express
        lean=0.
        if t<prepare:phase='Preparando postura';target=blend(initial,rest,t/prepare)
        elif t<start:
            phase='Preparando gesto';target=blend(rest,first,(t-prepare)/entry)
            lean=blend(0.,torso_first,(t-prepare)/entry)
        elif t<=end:
            phase='Fala + gestos';target=interpolate(np.clip(t-start,times[0],times[-1]))
            lean=float(torso_curve(np.clip(t-start,times[0],times[-1]))[0])
            if not played:
                if not args.mute:Speaker.playSound(speaker,speaker,str((ROOT/args.audio).resolve()),.7,1.,0.,False)
                if args.capture:
                    robot.movieStartRecording(str((out/'webots_motion.mp4').resolve()),960,720,0,25,1,False)
                    movie_started=True
                audio_start=t;played=True
                active_wall_start=time.perf_counter()
            drifts.append((time.perf_counter()-active_wall_start)-(t-audio_start))
        elif t<end+exit_duration:
            phase='Retorno ao repouso';target=blend(last,rest,(t-end)/exit_duration)
            lean=blend(torso_last,0.,(t-end)/exit_duration)
        else:phase='Concluido';target=rest
        actual=np.array([s.getValue() for s in sensors]);position=node.getPosition();orientation=node.getOrientation()
        tilt=math.acos(max(-1.,min(1.,orientation[8])))
        if not np.isfinite(actual).all():raise ValueError('Invalid motor sensors')
        for m,value in zip(motors,target):m.setPosition(float(value))
        # Simulation-only experiment: small symmetric hip pitch offset.
        # No root pose override, ankle reset or physical-robot command is used.
        for name in ('LHipPitch','RHipPitch'):robot.getDevice(name).setPosition(-.15+float(lean))
        contacts=node.getContactPoints(True)
        rows.append([t,phase,*target,*actual,*position,tilt,len(contacts)])
        if len(rows)%8==0:
            robot.setLabel(0,'NAO V6 | EMAGE + Edge TTS',.025,.025,.075,0x83E4CE,0,'Arial')
            robot.setLabel(1,phase+' | %.2f s'%min(times[-1],max(0.,t-start)),.025,.105,.055,0xFFFFFF,0,'Arial')
            robot.setLabel(2,'Fisica ativa | inclinacao %.1f graus'%math.degrees(tilt),.025,.17,.045,0xFFCF80,0,'Arial')
        if movie_started and not movie_stopped and t>end:
            robot.movieStopRecording();movie_stopped=True
        if (not args.capture) and any(abs(t-(start+x))<step/1000 for x in [1.,6.,12.]):
            robot.exportImage(str((out/('snapshot_%02d.png'%int(t-start))).resolve()),90)
        if t>=finish:break
    columns=['time_s','phase']+['target_'+n for n in names]+['actual_'+n for n in names]+['base_x','base_y','base_z','tilt_rad','contact_count']
    with (out/'telemetry.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(columns);w.writerows(rows)
    active=[r for r in rows if r[1]=='Fala + gestos']
    count=len(names);base=2+2*count
    targets=np.array([r[2:2+count] for r in active]);actuals=np.array([r[2+count:base] for r in active]);errors=actuals-targets
    heights=np.array([r[base+2] for r in active]);tilts=np.array([r[base+3] for r in active])
    velocities=np.diff(targets[:,angular_indices],axis=0)/(step/1000);accelerations=np.diff(targets[:,angular_indices],n=2,axis=0)/(step/1000)**2
    summary={'simulator':'Webots R2025a','model':'Installed NaoV6.proto (copied); physical elbow limits enforced by controller','physics_enabled':True,'self_collision_enabled':True,'root_pinned':False,'timestep_ms':step,'gesture_duration_s':float(times[-1]),'samples':len(rows),'audio_requested':not args.mute,'audio_simulation_start_s':audio_start,'audio_start_quantization_bound_ms':step,'max_wall_sim_clock_drift_s':max(map(abs,drifts)) if drifts else None,'audio_output_latency_measured':False,'arm_tracking_rms_deg':float(np.degrees(np.sqrt(np.mean(errors[:,:8]**2)))),'arm_tracking_max_deg':float(np.degrees(np.abs(errors[:,:8]).max())),'base_min_height_m':float(heights.min()),'base_max_tilt_deg':float(np.degrees(tilts.max())),'fall_detected':bool(np.any(heights<.20)|np.any(tilts>.7)),'interpolated_target_max_velocity_rad_s':float(np.abs(velocities).max()),'interpolated_target_max_acceleration_rad_s2':float(np.abs(accelerations).max()),'motor_limits':limits,'movie_recording_requested':args.capture,'wall_time_s':time.perf_counter()-wall0,'trajectory':args.trajectory,'hardware_validated':False,'note':'Tracking and fall checks concern this simulated model and clip only. Contact count is not proof of collision-free motion.'}
    summary['completed']=bool(t>=finish)
    summary['head_enabled']=has_head
    summary['head_tracking_rms_deg']=float(np.degrees(np.sqrt(np.mean(errors[:,head_indices]**2)))) if has_head else None
    summary['head_tracking_max_deg']=float(np.degrees(np.abs(errors[:,head_indices]).max())) if has_head else None
    summary['head_target_range_deg']=np.degrees(np.ptp(targets[:,head_indices],axis=0)).tolist() if has_head else []
    summary['hand_enabled']=has_hands
    summary['hand_mapping']='Approximate coupled phalanges, normalized openness' if has_hands else None
    summary['hand_target_range_fraction']=np.ptp(targets[:,hand_indices],axis=0).tolist() if has_hands else []
    summary['hand_measured_range_fraction']=np.ptp(actuals[:,hand_indices],axis=0).tolist() if has_hands else []
    summary['hand_tracking_rms_fraction']=float(np.sqrt(np.mean(errors[:,hand_indices]**2))) if has_hands else None
    summary['intent_events']=data.get('intent_events',[])
    summary['emotion']=data.get('emotion','neutral');summary['eye_color']=data.get('eye_color')
    summary['torso_simulated']=bool('simulated_torso_pitch_rad' in data)
    summary['torso_hip_offset_max_deg']=float(np.degrees(np.abs(torso).max()))
    summary['created_at_utc']=datetime.now(timezone.utc).isoformat()
    summary['checks_passed']=bool(summary['completed'] and not summary['fall_detected'] and summary['arm_tracking_rms_deg']<5. and summary['arm_tracking_max_deg']<10. and summary['interpolated_target_max_velocity_rad_s']<=1.201 and summary['interpolated_target_max_acceleration_rad_s2']<=5.01)
    if has_head:summary['checks_passed']=bool(summary['checks_passed'] and summary['head_tracking_rms_deg']<3. and summary['head_tracking_max_deg']<8.)
    if has_hands:summary['checks_passed']=bool(summary['checks_passed'] and summary['hand_tracking_rms_fraction']<.15)
    if summary['torso_simulated']:summary['checks_passed']=bool(summary['checks_passed'] and summary['base_max_tilt_deg']<5.)
    (out/'simulation_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('GESTURE_TEST_COMPLETE '+json.dumps(summary),flush=True)
    robot.exportImage(str((out/'final.png').resolve()),95)
    if movie_started:
        wait_start=time.perf_counter()
        while not robot.movieIsReady() and not robot.movieFailed() and time.perf_counter()-wait_start<45:
            if robot.step(step)==-1:break
        print('MOVIE_READY '+str(robot.movieIsReady()),flush=True)
    if args.quit:robot.simulationQuit(0)
    else:
        robot.simulationSetMode(Supervisor.SIMULATION_MODE_PAUSE)
        while robot.step(step)!=-1:pass

if __name__=='__main__':main()
