"""Edge TTS online synthesis + word boundaries + PCM WAV for EMAGE/Webots."""
import argparse
import asyncio
import json
import shutil
import subprocess
from pathlib import Path
import soundfile as sf

async def synthesize(args):
    import edge_tts
    text=args.text_file.read_text(encoding='utf-8').strip()
    args.out.mkdir(parents=True,exist_ok=True)
    voices=await edge_tts.list_voices()
    if args.voice not in {v['ShortName'] for v in voices}:
        raise ValueError('Voice unavailable: '+args.voice)
    words=[]
    communicate=edge_tts.Communicate(text,args.voice,rate=args.rate,pitch=args.pitch,volume=args.volume,boundary='WordBoundary')
    with (args.out/'speech.mp3').open('wb') as f:
        async for chunk in communicate.stream():
            if chunk['type']=='audio':f.write(chunk['data'])
            elif chunk['type']=='WordBoundary':
                words.append({'text':chunk['text'],'start_s':chunk['offset']/1e7,'duration_s':chunk['duration']/1e7})
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise RuntimeError('ffmpeg not found in PATH')
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(args.out/'speech.mp3'),'-af','apad=whole_dur=3.2','-ac','1','-ar','16000','-c:a','pcm_s16le',str(args.out/'speech.wav')],check=True)
    info=sf.info(args.out/'speech.wav')
    metadata={'provider':'edge-tts','voice':args.voice,'rate':args.rate,'pitch':args.pitch,'volume':args.volume,'text':text,'duration_s':info.duration,'sample_rate':info.samplerate,'words':words,'note':'Online Microsoft speech service; this script sends the supplied text for synthesis.'}
    (args.out/'speech.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in metadata.items() if k!='words'},ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('--text-file',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--voice',default='pt-BR-AntonioNeural');p.add_argument('--rate',default='+0%');p.add_argument('--pitch',default='+0Hz');p.add_argument('--volume',default='+0%');asyncio.run(synthesize(p.parse_args()))

if __name__=='__main__':main()
