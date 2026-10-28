"""Mux the Edge voice on simulation-time Webots recording; no timing stretch."""
import json
import shutil
import subprocess
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[1]
    result=root/'webots/results/edge_pt'
    video=result/'webots_motion.mp4';audio=root/'examples/edge_pt/speech.mp3'
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise RuntimeError('ffmpeg not found')
    output=result/'demonstracao_com_voz.mp4'
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(video),'-i',str(audio),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(output)],check=True)
    # Offline mux uses simulation-time frames; independent of live wall-clock speed.
    (result/'video_report.json').write_text(json.dumps({'video':output.name,'motion_source':video.name,'audio_source':'examples/edge_pt/speech.mp3','audio_stretched':False,'motion_stretched':False,'synchronization':'Audio placed at t=0 of motion-only simulation recording. Output ends at shorter stream.','note':'This does not measure speaker latency in the live simulator or physical robot.'},indent=2),encoding='utf-8')
    print(output)

if __name__=='__main__':main()
