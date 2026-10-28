# -*- coding: utf-8 -*-
"""Python 2.7 SDK worker. Probe is read-only; execute requires an explicit flag.

Only arms and optional head trajectories are accepted. No leg/posture commands.
"""
from __future__ import print_function
import argparse
import io
import json
import os
import sys
import threading
import time
import wave
import qi
import bisect
import math
import numbers

DEVICE_FIELDS=('Position/Sensor/Value','Position/Actuator/Value','Hardness/Actuator/Value',
               'ElectricCurrent/Sensor/Value','Temperature/Sensor/Value','Temperature/Sensor/Status')

def read_arm_devices(memory,names):
    keys=['Device/SubDeviceList/'+name+'/'+field for name in names for field in DEVICE_FIELDS]
    values=memory.getListData(keys)
    if len(values)!=len(keys) or any(not isinstance(v,numbers.Real) or math.isnan(v) or math.isinf(v) for v in values):
        raise RuntimeError('Leitura de sensores fisicos incompleta.')
    return {name:[float(values[j*len(DEVICE_FIELDS)+k]) for j in range(len(names))]
            for k,name in enumerate(('measured','commanded','hardness','current_a','temperature_c','temperature_status'))}

class PositionSampler(object):
    """Read positions from ALMotion; cache auxiliary device data separately.

    ALMemory position mirrors were observed updating at about 3 Hz on this NAO.
    They must never replace the positions used for tracking or pause detection.
    The legacy device snapshot is retained for preflight compatibility, but only
    its four auxiliary fields are copied into telemetry records.
    """
    METADATA=('hardness','current_a','temperature_c','temperature_status')

    def __init__(self,motion,memory,names,devices=None,strict_devices=False):
        self.motion=motion;self.memory=memory;self.names=names
        self.has_devices=devices is not None;self.strict_devices=strict_devices
        self.metadata={k:devices[k] for k in self.METADATA} if devices is not None else {}
        self.next_device_sample_s=0.;self.device_sample_s=None;self.device_error=None

    def read(self,elapsed):
        measured=self.motion.getAngles(self.names,True)
        commanded=self.motion.getAngles(self.names,False)
        for values in (measured,commanded):
            if len(values)!=len(self.names) or any(not isinstance(v,numbers.Real) or math.isnan(v) or math.isinf(v) for v in values):
                raise RuntimeError('Leitura de posicao ALMotion incompleta.')
        if self.has_devices and elapsed>=self.next_device_sample_s:
            self.next_device_sample_s=elapsed+.4
            try:
                devices=read_arm_devices(self.memory,self.names)
                self.metadata={k:devices[k] for k in self.METADATA}
                self.device_sample_s=elapsed;self.device_error=None
            except Exception as error:
                self.device_error=str(error)
                if self.strict_devices:raise
        if any(x!=0 for x in self.metadata.get('temperature_status',[])):
            raise RuntimeError('Alerta termico durante o movimento.')
        record=dict(self.metadata)
        record.update(measured=measured,commanded=commanded,
                      position_source='ALMotion.getAngles',device_source='ALMemory.getListData',
                      device_sample_elapsed_s=self.device_sample_s)
        if self.device_error is not None:record['device_read_error']=self.device_error
        return record

def planned_angles(plan,elapsed):
    result=[]
    for times,points in zip(plan['times'],plan['control_points']):
        k=bisect.bisect_right(times,elapsed)-1
        if k<0:result.append(plan['initial_angles'][len(result)]);continue
        if k>=len(times)-1:result.append(points[-1][0]);continue
        u=(elapsed-times[k])/(times[k+1]-times[k]);a,b=points[k:k+2]
        result.append((1-u)**3*a[0]+3*(1-u)**2*u*(a[0]+a[2][2])+3*(1-u)*u*u*(b[0]+b[1][2])+u**3*b[0])
    return result

def emit(event,**values):
    values['event']=event
    print(json.dumps(values,ensure_ascii=True));sys.stdout.flush()

def wait_for_motion_start(motion,task,previous_tasks,stopped,timeout=10.):
    submitted=time.time()
    while time.time()-submitted<timeout:
        if stopped():return None
        tasks=motion.getTaskList()
        if any(row[1] not in previous_tasks and 'angleinterpolationbezier' in str(row[0]).lower() for row in tasks):
            return time.time()
        if task.isFinished():
            task.value()
            raise RuntimeError('O movimento terminou antes de confirmar seu inicio.')
        time.sleep(.02)
    raise RuntimeError('O NAO nao confirmou o inicio do movimento em 10 segundos.')

def head_limits(yaw):
    # Coupled shell clearance envelope from the manufacturer joint table.
    table=[(0.,-38.5,29.51),(27.85,-38.5,24.18),(43.32,-31.4,21.2),
           (51.74,-27.5,18.91),(62.45,-24.64,17.19),(87.49,-18.91,11.46),(119.52,-25.73,18.91)]
    y=abs(math.degrees(yaw))
    if y>119.53:raise RuntimeError('HeadYaw fora do limite.')
    for a,b in zip(table[:-1],table[1:]):
        if y<=b[0]:
            u=(y-a[0])/(b[0]-a[0]);return [math.radians(a[k]+u*(b[k]-a[k])) for k in (1,2)]
    return [math.radians(x) for x in table[-1][1:]]

def main():
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--probe',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--execute',action='store_true');p.add_argument('--plan');p.add_argument('--audio');p.add_argument('--stop-file');p.add_argument('--audio-on-robot',action='store_true');p.add_argument('--telemetry');p.add_argument('--constant-stiffness',action='store_true');a=p.parse_args()
    session=qi.Session();session.connect('tcp://%s:%d'%(a.host,a.port))
    system=session.service('ALSystem');motion=session.service('ALMotion');posture=session.service('ALRobotPosture');battery=session.service('ALBattery');life=session.service('ALAutonomousLife')
    names=['LShoulderPitch','LShoulderRoll','LElbowYaw','LElbowRoll','RShoulderPitch','RShoulderRoll','RElbowYaw','RElbowRoll']
    left_limits=motion.getLimits('LArm');right_limits=motion.getLimits('RArm')
    status={'version':system.systemVersion(),'posture':posture.getPosture(),'battery':battery.getBatteryCharge(),'angles':motion.getAngles(names,True),'limits':left_limits[:4]+right_limits[:4],'stiffness':motion.getStiffnesses(names),'autonomous_life':life.getState()}
    memory=session.service('ALMemory')
    status['smart_stiffness']=motion.getSmartStiffnessEnabled()
    try:status['devices']=read_arm_devices(memory,names)
    except Exception as error:status['device_read_error']=str(error)
    head_names=['HeadYaw','HeadPitch']
    try:
        angles=motion.getAngles(head_names,True);stiff=motion.getStiffnesses(head_names);limits=motion.getLimits('Head')
        if len(angles)!=2 or len(stiff)!=2 or len(limits)!=2:raise RuntimeError('Formato da cabeca invalido.')
        status['head']={'available':True,'angles':angles,'stiffness':stiff,'limits':limits}
    except Exception as error:status['head']={'available':False,'error':str(error)}
    manual_names=['LWristYaw','RWristYaw','LHand','RHand']
    try:
        if len(left_limits)<6 or len(right_limits)<6:raise RuntimeError('Modelo sem punhos/maos completos.')
        angles=motion.getAngles(manual_names,True);stiff=motion.getStiffnesses(manual_names)
        if len(angles)!=4 or len(stiff)!=4:raise RuntimeError('Formato de punhos/maos invalido.')
        status['manual']={'available':True,'angles':angles,'stiffness':stiff,
                          'limits':[left_limits[4],right_limits[4],left_limits[5],right_limits[5]]}
    except Exception as error:status['manual']={'available':False,'error':str(error)}
    emit('status',status=status)
    if a.probe:return
    if not (a.execute or a.check):raise RuntimeError('Execucao fisica nao solicitada.')
    if status['posture'] not in ('Stand','StandInit'):raise RuntimeError('Coloque o NAO em Stand ou StandInit no Choregraphe antes de executar.')
    if status['battery']<20:raise RuntimeError('Bateria abaixo de 20%. Recarregue antes de executar.')
    if min(status['stiffness'])<.5:raise RuntimeError('Ative a rigidez/postura do robo no Choregraphe antes de executar.')
    if a.constant_stiffness and ('devices' not in status or any(x!=0 for x in status['devices']['temperature_status'])):
        raise RuntimeError('Teste de rigidez constante requer sensores termicos disponiveis e sem alerta.')
    with io.open(a.plan,encoding='utf-8') as f:plan=json.load(f)
    includes_head=bool(plan.get('head_enabled'));includes_manual=bool(plan.get('hand_enabled'))
    expected_names=names+(head_names if includes_head else [])+(manual_names if includes_manual else [])
    expected_scope=('arms_head' if includes_head else 'arms')+('_hands' if includes_manual else '')
    if plan.get('names')!=expected_names or (includes_head or includes_manual) and plan.get('scope')!=expected_scope or not (includes_head or includes_manual or plan.get('arm_only')):
        raise RuntimeError('Plano de movimento invalido: somente bracos e cabeca, com punhos/maos opcionais.')
    if includes_head:
        if not status['head']['available']:raise RuntimeError('Leitura da cabeca indisponivel.')
        if any(not 0.<=x<=1. for x in status['head']['stiffness']):raise RuntimeError('Rigidez da cabeca invalida.')
        names=names+head_names
        status['angles']=status['angles']+status['head']['angles'];status['limits']=status['limits']+status['head']['limits']
    if includes_manual:
        if not status['manual']['available']:raise RuntimeError('Punhos/maos indisponiveis. Desative os gestos com intencao.')
        if any(not 0.<=x<=1. for x in status['manual']['stiffness']):raise RuntimeError('Rigidez de punhos/maos invalida.')
        names=names+manual_names
        status['angles']=status['angles']+status['manual']['angles'];status['limits']=status['limits']+status['manual']['limits']
    if includes_head or includes_manual:
        try:status['devices']=read_arm_devices(memory,names)
        except Exception:
            if a.constant_stiffness:raise
            status.pop('devices',None)
        if 'devices' in status and any(x!=0 for x in status['devices']['temperature_status']):raise RuntimeError('Alerta termico na parte superior do corpo.')
    if len(plan.get('initial_angles',[]))!=len(names) or len(plan.get('control_points',[]))!=len(names) or len(plan.get('times',[]))!=len(names):raise RuntimeError('Dimensoes do plano invalidas.')
    # The plan was made for the last sensor pose; do not jump after a stale preflight.
    for index,(actual,expected) in enumerate(zip(status['angles'],plan['initial_angles'])):
        if abs(actual-expected)>(.08 if index>=8 else .15):raise RuntimeError('A postura mudou. Atualize a conexao e tente novamente.')
    for j,points in enumerate(plan['control_points']):
        lo,hi=status['limits'][j][:2]
        for point in points:
            if not lo-.001<=point[0]<=hi+.001:raise RuntimeError('Limite de articulacao excedido.')
    if includes_head:
        at=0.;head_index=names.index('HeadYaw')
        while at<=plan['duration_s']:
            yaw,pitch=planned_angles(plan,at)[head_index:head_index+2];lo,hi=head_limits(yaw)
            if not lo-.003<=pitch<=hi+.003:raise RuntimeError('Limite acoplado de cabeca excedido.')
            at+=.01
    stop=threading.Event();audio_error=[];abilities={};task=None;audio_device=None;telemetry=None;tracking=[];motor_tracking=[];hand_tracking=[];telemetry_failed=False
    if a.audio_on_robot:
        audio_device=session.service('ALAudioDevice')
        if audio_device.getParameter('outputSampleRate')!=48000:raise RuntimeError('Saida de audio do robo nao esta em 48 kHz. Nenhuma configuracao global foi alterada.')
        if audio_device.isAudioOutMuted():raise RuntimeError('A saida de audio do NAO esta muda. Ative o som antes de executar.')
        f=wave.open(a.audio,'rb')
        try:
            if f.getsampwidth()!=2 or f.getnchannels()!=2 or f.getframerate()!=48000:raise RuntimeError('Audio fisico invalido: esperado PCM stereo de 48 kHz e 16 bits.')
        finally:f.close()
    if a.check:
        emit('validated',motor_commands_sent=False,audio_format_checked=a.audio_on_robot,head_activation_required=bool(includes_head and min(status['head']['stiffness'])<.7),hand_activation_required=bool(includes_manual and min(status['manual']['stiffness'])<.6))
        return
    try:from app.stiffness_scope import ConstantStiffness
    except ImportError:from stiffness_scope import ConstantStiffness
    try:from app.joint_activation import JointActivation
    except ImportError:from joint_activation import JointActivation
    manual_activation=JointActivation(motion,manual_names,status['manual']['stiffness'],status['manual']['angles']) if includes_manual else None
    manual_entered=False
    stiffness_scope=ConstantStiffness(motion,enabled=a.constant_stiffness);stiffness_entered=False;terminal=None;head_settings={};head_stiffness_changed=False
    def stopped():return stop.is_set() or (a.stop_file and os.path.exists(a.stop_file))
    def audio_worker(start):
        try:
            f=wave.open(a.audio,'rb')
            if f.getsampwidth()!=2 or f.getnchannels()!=2:raise RuntimeError('Audio do robo deve ser PCM stereo 16 bits.')
            sr=f.getframerate();frames=960;count=0
            while not stopped():
                data=f.readframes(frames)
                if not data:break
                deadline=start+float(count)/sr
                while not stopped() and time.time()<deadline:time.sleep(.002)
                if stopped():break
                if not audio_device.sendRemoteBufferToOutput(len(data)//4,str(data)):raise RuntimeError('O robo rejeitou o buffer de audio.')
                count+=len(data)//4
            f.close()
        except Exception as error:audio_error.append(str(error));stop.set()
    try:
        stiffness_scope.__enter__();stiffness_entered=True
        emit('control_mode',constant_stiffness=a.constant_stiffness,previous_smart_stiffness=status['smart_stiffness'])
        active_abilities=['BackgroundMovement','SpeakingMovement','ListeningMovement']+(['BasicAwareness'] if includes_head else [])
        for ability in active_abilities:
            abilities[ability]=life.getAutonomousAbilityEnabled(ability)
            life.setAutonomousAbilityEnabled(ability,False)
        if includes_head:
            for getter,setter in (('getBreathEnabled','setBreathEnabled'),('getIdlePostureEnabled','setIdlePostureEnabled')):
                head_settings[setter]=getattr(motion,getter)('Head')
                getattr(motion,setter)('Head',False)
            if min(status['head']['stiffness'])<.7:
                # Hold the measured pose before energising relaxed head motors.
                now=motion.getAngles(head_names,True)
                if any(abs(a-b)>.03 for a,b in zip(now,status['head']['angles'])):raise RuntimeError('A cabeca mudou de postura. Tente novamente.')
                motion.setAngles(head_names,now,.04)
                head_stiffness_changed=True
                motion.stiffnessInterpolation(head_names,[max(.7,x) for x in status['head']['stiffness']],.4)
        if manual_activation is not None:
            manual_activation.__enter__();manual_entered=True
        time.sleep(.15)
        if not motion.areResourcesAvailable(names):raise RuntimeError('Os bracos estao ocupados por outro comportamento.')
        if stopped():terminal=('stopped',{});return
        # A Future means the RPC was submitted, not that ALMotion started its task.
        # Wait for scheduler acknowledgement before starting the speech clock.
        previous_tasks=set(row[1] for row in motion.getTaskList())
        task=motion.angleInterpolationBezier(names,plan['times'],plan['control_points'],_async=True)
        submitted=time.time();start=wait_for_motion_start(motion,task,previous_tasks,stopped)
        if start is None:motion.killTasksUsingResources(names);terminal=('stopped',{});return
        emit('scheduled',acknowledgement_delay_s=start-submitted)
        audio_at=start+plan['audio_start_s'];audio_thread=None
        if a.audio_on_robot:
            audio_thread=threading.Thread(target=audio_worker,args=(audio_at,));audio_thread.daemon=True;audio_thread.start()
        emit('moving',audio_start_in_s=plan['audio_start_s'],duration_s=plan['duration_s'],audio_on_robot=a.audio_on_robot)
        audio_announced=False;next_sample=0.
        sampler=PositionSampler(motion,memory,names,status.get('devices'),a.constant_stiffness)
        if a.telemetry:telemetry=io.open(a.telemetry,'w',encoding='utf-8')
        while not task.isFinished():
            if stopped():
                motion.killTasksUsingResources(names)
                if audio_device:audio_device.flushAudioOutputs()
                terminal=('stopped',{});return
            if not plan.get('diagnostic') and not audio_announced and time.time()>=audio_at:
                emit('audio_start');audio_announced=True
            elapsed=time.time()-start
            if telemetry is not None and elapsed>=next_sample and not telemetry_failed:
                next_sample=elapsed+.1
                try:
                    positions=sampler.read(elapsed)
                    measured=positions['measured'];commanded=positions['commanded']
                    requested=planned_angles(plan,elapsed)
                    record={'elapsed_s':elapsed,'read_finished_s':time.time()-start,'requested':requested}
                    record.update(positions)
                    telemetry.write(json.dumps(record)+u'\n');telemetry.flush()
                    tracking.extend([(x-y)**2 for name,x,y in zip(names,requested,measured) if name not in ('LHand','RHand')])
                    motor_tracking.extend([(x-y)**2 for name,x,y in zip(names,commanded,measured) if name not in ('LHand','RHand')])
                    hand_tracking.extend([(x-y)**2 for name,x,y in zip(names,commanded,measured) if name in ('LHand','RHand')])
                except Exception as error:
                    telemetry_failed=True;emit('telemetry_error',message=str(error))
                    if a.constant_stiffness:raise
            time.sleep(.025)
        task.value()
        if audio_thread:audio_thread.join(2.)
        if audio_error:raise RuntimeError(audio_error[0])
        terminal=('complete',dict(physical_motion_tested=True,motor_tracking_rms_deg=math.degrees(math.sqrt(sum(motor_tracking)/len(motor_tracking))) if motor_tracking else None,tracking_rms_deg=math.degrees(math.sqrt(sum(tracking)/len(tracking))) if tracking else None,hand_tracking_rms_fraction=math.sqrt(sum(hand_tracking)/len(hand_tracking)) if hand_tracking else None,telemetry_failed=telemetry_failed))
    finally:
        stop.set()
        try:
            try:
                if telemetry is not None:telemetry.close()
            finally:
                if task is not None and not task.isFinished():motion.killTasksUsingResources(names)
        finally:
            try:
                if stiffness_entered:stiffness_scope.__exit__(*sys.exc_info())
            finally:
                restore_errors=[]
                if manual_entered:
                    try:manual_activation.__exit__(*sys.exc_info())
                    except Exception as error:restore_errors.append('wrist/hand stiffness: '+str(error))
                if head_stiffness_changed:
                    try:motion.stiffnessInterpolation(head_names,status['head']['stiffness'],.4)
                    except Exception as error:restore_errors.append('head stiffness: '+str(error))
                for ability,enabled in abilities.items():
                    try:life.setAutonomousAbilityEnabled(ability,enabled)
                    except Exception as error:restore_errors.append(ability+': '+str(error))
                for setter,enabled in head_settings.items():
                    try:getattr(motion,setter)('Head',enabled)
                    except Exception as error:restore_errors.append(setter+': '+str(error))
                if restore_errors:raise RuntimeError('Falha ao restaurar comportamentos: '+'; '.join(restore_errors))
        if terminal is not None:emit(terminal[0],**terminal[1])

if __name__=='__main__':
    try:main()
    except Exception as error:
        emit('error',message=str(error));sys.exit(1)
