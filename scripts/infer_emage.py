"""Minimal EMAGE inference using upstream classes and local, pinned weights.

Run only with the separately provisioned research environment. No rendering
dependencies required. The source repository is not copied into this project.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
import numpy as np

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repo',required=True,type=Path)
    p.add_argument('--weights',required=True,type=Path)
    p.add_argument('--audio',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--rest-model',type=Path)
    args=p.parse_args()
    os.environ.setdefault('HF_HOME',str((args.weights.parent/'hf-cache').resolve()))
    os.environ.setdefault('TORCH_HOME',str((args.weights.parent/'torch-cache').resolve()))
    os.environ.setdefault('USE_TF','0')
    os.environ.setdefault('USE_FLAX','0')
    import faulthandler
    faulthandler.dump_traceback_later(60,repeat=True)
    sys.path.insert(0,str(args.repo.resolve()))
    print('Importing inference dependencies...',flush=True)
    import torch
    import soundfile as sf
    from scipy.signal import resample_poly
    from math import gcd
    from models.emage_audio import EmageAudioModel,EmageVQVAEConv,EmageVAEConv,EmageVQModel
    torch.manual_seed(7)
    audio,sr=sf.read(args.audio,dtype='float32',always_2d=True)
    audio=audio.mean(axis=1)
    if sr!=16000:
        g=gcd(sr,16000);audio=resample_poly(audio,16000//g,sr//g).astype(np.float32)
    if len(audio)<16000*3:raise ValueError('Use audio >=3 seconds for the initial model test')
    if not np.isfinite(audio).all():raise ValueError('Audio contains non-finite samples')
    device='cuda' if torch.cuda.is_available() else 'cpu'
    print('Device: '+device,flush=True)
    torch.set_num_threads(4)
    if device=='cuda':torch.cuda.reset_peak_memory_stats()
    start=time.perf_counter()
    components={}
    for part in ('face','upper','lower','hands'):
        print('Loading '+part,flush=True)
        components[part]=EmageVQVAEConv.from_pretrained(str(args.weights),subfolder='emage_vq/'+part,local_files_only=True).to(device).eval()
    global_model=EmageVAEConv.from_pretrained(str(args.weights),subfolder='emage_vq/global',local_files_only=True).to(device).eval()
    vq=EmageVQModel(face_model=components['face'],upper_model=components['upper'],lower_model=components['lower'],hands_model=components['hands'],global_model=global_model).to(device).eval()
    print('Loading audio-to-motion model...',flush=True)
    model=EmageAudioModel.from_pretrained(str(args.weights),local_files_only=True).to(device).eval()
    load_s=time.perf_counter()-start
    start=time.perf_counter()
    print('Generating motion...',flush=True)
    with torch.inference_mode():
        out=model.inference(torch.from_numpy(audio.copy()).to(device)[None],torch.zeros((1,1),dtype=torch.long,device=device),vq)
        cfg=model.cfg
        decoded=vq.decode(
            face_latent=out['rec_face'] if cfg.lf>0 and cfg.cf==0 else None,
            upper_latent=out['rec_upper'] if cfg.lu>0 and cfg.cu==0 else None,
            hands_latent=out['rec_hands'] if cfg.lh>0 and cfg.ch==0 else None,
            lower_latent=out['rec_lower'] if cfg.ll>0 and cfg.cl==0 else None,
            face_index=out['cls_face'].argmax(-1) if cfg.cf>0 else None,
            upper_index=out['cls_upper'].argmax(-1) if cfg.cu>0 else None,
            hands_index=out['cls_hands'].argmax(-1) if cfg.ch>0 else None,
            lower_index=out['cls_lower'].argmax(-1) if cfg.cl>0 else None,
            get_global_motion=False)
        poses=decoded['motion_axis_angle'][0].cpu().numpy()
    if device=='cuda':torch.cuda.synchronize()
    elapsed=time.perf_counter()-start
    args.out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.out/'emage_motion.npz',poses=poses,mocap_frame_rate=30,betas=np.zeros(300,dtype=np.float32))
    if args.rest_model:
        with np.load(args.rest_model,allow_pickle=False) as rest:
            reg=rest['J_regressor'];vertices=rest['v_template']
            if reg.dtype==object:raise ValueError('Object-based regressor not accepted')
            np.save(args.out/'rest_joints.npy',reg@vertices)
    metrics={'device':device,'audio_duration_s':len(audio)/16000,'motion_frames':len(poses),'motion_duration_s':len(poses)/30,'model_load_s':load_s,'inference_s':elapsed,'peak_gpu_allocated_mib':torch.cuda.max_memory_allocated()/1024**2 if device=='cuda' else None,'model':'EMAGE audio','weights_path':str(args.weights.resolve()),'note':'Offline inference benchmark; no conversation, vision or robot connection.'}
    (args.out/'inference_report.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    print(json.dumps(metrics,indent=2))
    faulthandler.cancel_dump_traceback_later()

if __name__=='__main__':main()
