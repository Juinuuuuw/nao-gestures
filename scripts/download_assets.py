"""Fetch public upstream artifacts to a user-specified WORK directory.

Does not redistribute assets or accept gated terms. SMPL-X retains its own license.
"""
import argparse
import json
from pathlib import Path
import urllib.request

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    p.add_argument('--include-rest-model',action='store_true',help='Download the public evaluation skeleton asset; SMPL-X license applies')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    records=[]
    for repo,subdir in [('haiyangliu0/emage_audio','emage')]+([('haiyangliu0/emage_evaltools','evaltools')] if args.include_rest_model else []):
        with urllib.request.urlopen('https://huggingface.co/api/models/'+repo,timeout=60) as r:meta=json.load(r)
        revision=meta['sha']
        files=[x['rfilename'] for x in meta['siblings']]
        if subdir=='evaltools':files=[f for f in files if f=='smplx_models/smplx/SMPLX_NEUTRAL_2020.npz']
        else:files=[f for f in files if f.endswith(('.json','.bin'))]
        for name in files:
            dest=args.out/subdir/name;dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():
                print('Downloading '+repo+'/'+name,flush=True)
                temporary=dest.with_suffix(dest.suffix+'.part')
                req=urllib.request.Request('https://huggingface.co/'+repo+'/resolve/'+revision+'/'+name,headers={'User-Agent':'nao-gesture-prototype/0.1'})
                with urllib.request.urlopen(req,timeout=120) as response,temporary.open('wb') as f:
                    while chunk:=response.read(1024*1024):f.write(chunk)
                temporary.replace(dest)
            records.append({'repo':repo,'revision':revision,'file':name,'bytes':dest.stat().st_size})
    (args.out/'manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print('Assets downloaded; revisions recorded in manifest.json',flush=True)

if __name__=='__main__':main()
