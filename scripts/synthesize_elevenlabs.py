"""ElevenLabs PT speech with real timing, MP3 and padded mono WAV for EMAGE."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.voice_providers import create_speech,DEFAULT_VOICE

def synthesize(args):
    text=args.text_file.read_text(encoding='utf-8').strip()
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise ValueError('ffmpeg não encontrado.')
    audio,words,tagged=create_speech(text,args.voice,args.model,args.emotion)
    args.out.mkdir(parents=True,exist_ok=True);(args.out/'speech.mp3').write_bytes(audio)
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(args.out/'speech.mp3'),'-af','apad=whole_dur=3.2','-ac','1','-ar','16000','-c:a','pcm_s16le',str(args.out/'speech.wav')],check=True)
    info=sf.info(args.out/'speech.wav')
    if any(w['start_s']+w['duration_s']>info.duration+.5 for w in words):raise ValueError('O alinhamento excede a duração do áudio.')
    metadata={'provider':'elevenlabs','voice':args.voice,'model':args.model,'language_code':'pt','locale':'pt-BR',
        'emotion':args.emotion,'text':text,'synthesis_text':tagged,'duration_s':info.duration,'sample_rate':info.samplerate,'words':words,
        'timing_source':'elevenlabs_character_alignment','note':'Portuguese requested; Brazilian accent depends on voice. Online ElevenLabs API.'}
    (args.out/'speech.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in metadata.items() if k not in ('words','synthesis_text')},ensure_ascii=False))

def main():
    p=argparse.ArgumentParser();p.add_argument('--text-file',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--voice',default=DEFAULT_VOICE);p.add_argument('--model',default='eleven_v4');p.add_argument('--emotion',default='neutral')
    try:synthesize(p.parse_args())
    except Exception as error:print(str(error),file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
