import argparse
import base64
import csv
import json
from pathlib import Path
import numpy as np
from .inputs import load_json, load_npz
from .kinematics import NAMES, REST, arm_fk
from .retarget import fit
from .trajectory import UniformCubic

def demo(path):
    """Deterministic engineering fixture; deliberately NOT a learned gesture."""
    fps=30
    times=np.arange(361)/fps
    frames=[]
    for t in times:
        envelope=np.sin(np.pi*t/12)**2
        q=REST.copy()
        q[[0,4]]-=.7*envelope
        q[1]+=.35*envelope*(.6+.4*np.sin(t*1.2))
        q[5]-=.35*envelope*(.6-.4*np.sin(t*1.2))
        q[2]+=.3*envelope*np.sin(t)
        q[6]-=.3*envelope*np.sin(t)
        q[3]-=.2*envelope
        q[7]+=.2*envelope
        points=[]
        for s,side in enumerate(('L','R')):
            p=arm_fk(q[s*4:s*4+4],side)
            # Human-scale limbs, preserving directions; tests retargeting across scale.
            shoulder=np.array([0.,(.18 if side=='L' else -.18),.12])
            elbow=shoulder+(p[1]-p[0])*2.7
            wrist=elbow+(p[2]-p[1])*4.1
            points.append(np.stack([shoulder,elbow,wrist]).tolist())
        frames.append(points)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'fps':fps,'coordinate_system':'nao_torso_x_forward_y_left_z_up','source':'Demonstração sintética de engenharia; não gerada por IA e sem relação com áudio.','arms':frames}),encoding='utf-8')

def export(input_path,output,rest=None,timing='preserve',audio=None):
    arms,fps,source=load_npz(input_path,rest) if input_path.suffix.lower()=='.npz' else load_json(input_path)
    q,times,robot,report,raw_q=fit(arms,fps,timing=timing,include_raw=True)
    output.mkdir(parents=True,exist_ok=True)
    trajectory={'schema':'nao-gesture-trajectory-v2','interpolation':'uniform_cubic_control_points' if timing=='preserve' else 'pchip','units':'radians','coordinate_system':'nao_torso_x_forward_y_left_z_up','joint_names':NAMES,'times_s':times.tolist(),'angles_rad':q.tolist(),'source':source,'report':report,'deployment_ready':False}
    trajectory['angles_representation']='cubic control coefficients' if timing=='preserve' else 'joint position samples'
    trajectory['source_joint_targets_rad']=raw_q.tolist()
    trajectory['source_joint_targets_representation']='unfiltered IK joint positions; not spline control coefficients'
    (output/'trajectory.json').write_text(json.dumps(trajectory,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with (output/'trajectory.csv').open('w',newline='',encoding='utf-8') as f:
        sampled=UniformCubic(q,fps)(times) if timing=='preserve' else q
        w=csv.writer(f);w.writerow(['time_s']+NAMES);w.writerows(np.column_stack([times,sampled]))
    payload={'human':arms.tolist(),'robot':robot.tolist(),'times':times.tolist(),'source':source,'report':report}
    if audio:
        payload['audio_data_url']='data:audio/wav;base64,'+base64.b64encode(audio.read_bytes()).decode('ascii')
        trajectory['audio_file']=str(audio.resolve())
        (output/'trajectory.json').write_text(json.dumps(trajectory,ensure_ascii=False,indent=2),encoding='utf-8')
    template=Path(__file__).with_name('viewer.html').read_text(encoding='utf-8')
    encoded=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')
    (output/'preview.html').write_text(template.replace('__DATA__',encoded),encoding='utf-8')
    print(json.dumps(report,indent=2))
    print('Preview: '+str((output/'preview.html').resolve()))

def main():
    parser=argparse.ArgumentParser(description='Offline motion-to-NAO adapter; no network or motor commands')
    commands=parser.add_subparsers(dest='command',required=True)
    d=commands.add_parser('demo');d.add_argument('--out',type=Path,default=Path('examples/demo'))
    r=commands.add_parser('retarget');r.add_argument('input',type=Path);r.add_argument('--out',required=True,type=Path);r.add_argument('--rest-joints',type=Path);r.add_argument('--timing',choices=['preserve','stretch'],default='preserve');r.add_argument('--audio',type=Path)
    args=parser.parse_args()
    if args.command=='demo':
        path=args.out/'source.json';demo(path);export(path,args.out)
    else:
        export(args.input,args.out,args.rest_joints,args.timing,args.audio)

if __name__=='__main__':
    main()
