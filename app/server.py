"""Loopback-only local operator app. No shell input or arbitrary RPC methods."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
import uuid
import numpy as np
from app.sdk_bridge import launch_bridge
from app.robot_plan import build_plan,build_diagnostic_plan,PACES
from nao_gestures.__main__ import export

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'runtime'
JOBS=ROOT/'app/data/jobs'
ASSETS=ROOT/'app/ui'
TOKEN=secrets.token_urlsafe(32)
LOCK=threading.RLock()
JOBS.mkdir(parents=True,exist_ok=True)
STATE={'busy':False,'operation':None,'message':'Pronto para criar.','robot':None,'execution':None}
STOP=threading.Event()
ACTIVE={}

def read_json(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def update(**values):
    with LOCK:STATE.update(values)
def save_job(job):
    (JOBS/job['id']/'job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
def get_job(identifier):
    if identifier=='demo':
        d=ROOT/'examples/edge_pt';s=read_json(d/'speech.json')
        return {'id':'demo','text':s['text'],'voice':s['voice'],'status':'ready','duration':s['duration_s'],'created':0}
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Geração não encontrada.')
    return read_json(JOBS/identifier/'job.json')
def job_dir(identifier):
    get_job(identifier)
    return ROOT/'examples/edge_pt' if identifier=='demo' else JOBS/identifier
def history():
    jobs=[]
    for p in JOBS.glob('*/job.json'):
        try:jobs.append(read_json(p))
        except (ValueError,OSError):pass
    return sorted(jobs,key=lambda j:j['created'],reverse=True)[:15]+[get_job('demo')]
def claim(operation,message):
    with LOCK:
        if STATE['busy']:raise ValueError('Aguarde a operação atual terminar.')
        STATE.update(busy=True,operation=operation,message=message,execution=None,quality=None)
        STOP.clear()
def run_command(command,log,env=None):
    with log.open('a',encoding='utf-8') as output:
        process=subprocess.Popen(list(map(str,command)),cwd=str(ROOT),stdout=output,stderr=subprocess.STDOUT,env=env)
        ACTIVE['process']=process
        while process.poll() is None:
            if STOP.wait(.15):process.terminate();process.wait(timeout=8);raise RuntimeError('Operação cancelada.')
        if process.returncode:raise RuntimeError('Falha no processamento. '+log.read_text(encoding='utf-8',errors='replace')[-1600:])
    ACTIVE.pop('process',None)
def generate(job):
    directory=JOBS/job['id'];log=directory/'pipeline.log'
    try:
        update(message='Gerando a voz com Edge TTS…')
        run_command([sys.executable,ROOT/'scripts/synthesize_edge.py','--text-file',directory/'text.txt','--out',directory,'--voice',job['voice']],log)
        if read_json(directory/'speech.json')['duration_s']>60:raise ValueError('A fala ultrapassou 60 segundos. Reduza o texto e gere novamente.')
        update(message='Criando os movimentos com EMAGE…')
        run_command([sys.executable,ROOT/'scripts/infer_emage.py','--repo',WORK/'character-policy','--weights',WORK/'weights/emage','--audio',directory/'speech.wav','--rest-model',WORK/'weights/evaltools/smplx_models/smplx/SMPLX_NEUTRAL_2020.npz','--out',directory],log)
        if STOP.is_set():raise RuntimeError('Operação cancelada.')
        update(message='Suavizando e adaptando os braços…')
        export(directory/'emage_motion.npz',directory,directory/'rest_joints.npy',audio=directory/'speech.wav')
        job.update(status='ready',duration=read_json(directory/'speech.json')['duration_s'])
        update(message='Fala e gestos prontos.')
    except Exception as error:
        job.update(status='error',error=str(error));update(message=str(error))
    finally:
        save_job(job);update(busy=False,operation=None)

def bridge_probe():
    config=read_json(ROOT/'robot_connection.json')
    process=launch_bridge(['--host',config['host'],'--port',config['naoqi_port'],'--probe'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace')
    try:stdout,stderr=process.communicate(timeout=15)
    except subprocess.TimeoutExpired:process.kill();process.communicate();raise ValueError('O NAO não respondeu. Verifique a rede e a porta.')
    messages=[]
    for line in stdout.splitlines():
        try:messages.append(json.loads(line))
        except ValueError:pass
    status=next((m['status'] for m in messages if m.get('event')=='status'),None)
    if process.returncode or not status:
        message=next((m.get('message') for m in messages if m.get('event')=='error'),stderr[-300:])
        raise ValueError('Não foi possível conectar ao NAO. '+str(message))
    status.update(connected=True,host=config['host'],port=config['naoqi_port'],checked=time.time())
    update(robot=status)
    return status

def simulate(identifier,body_mode='arms',pace='natural',intensity=1.,intent_enabled=True):
    directory=job_dir(identifier)
    result=JOBS/(uuid.uuid4().hex) if identifier=='demo' else directory/'simulation'
    result.mkdir(parents=True,exist_ok=True)
    try:
        update(message='Abrindo o teste no Webots…')
        world=ROOT/'webots/worlds'/('app_'+uuid.uuid4().hex+'.wbt')
        text=(ROOT/'webots/worlds/gesture_lab.wbt').read_text(encoding='utf-8')
        start=text.index('  controllerArgs [');end=text.index(']',start)+1
        relative=lambda p:p.relative_to(ROOT).as_posix()
        from app.pace_source import load_execution_trajectory
        from app.upper_body import load_upper_body,torso_coefficients
        from app.plan_preview import speech_preview
        from app.direction import plan_intents
        from nao_gestures.kinematics import REST
        trajectory=load_execution_trajectory(directory)
        upper=load_upper_body(directory) if body_mode!='arms' else None
        direction=plan_intents(read_json(directory/'speech.json'),trajectory['times_s'][-1]) if intent_enabled else None
        plan=build_plan(trajectory,REST,intensity,pace=pace,
                        head_targets=upper['head_rad'] if upper is not None else None,current_head=[0.,0.] if upper is not None else None,
                        direction=direction,current_manual=[0.,0.,.42,.42] if intent_enabled else None)
        plan['initial_angles']=REST.tolist()+([0.,0.] if upper is not None else [])+([0.,0.,.42,.42] if intent_enabled else [])
        torso=torso_coefficients(upper['torso_pitch_rad'],upper['fps']) if body_mode=='torso' else None
        preview=speech_preview(plan,torso,upper['fps'] if upper is not None else 30.)
        trajectory_path=result/'upper_trajectory.json';trajectory_path.write_text(json.dumps(preview),encoding='utf-8')
        (result/'plan.json').write_text(json.dumps(plan),encoding='utf-8')
        arguments=['--trajectory',relative(trajectory_path),'--audio',relative(directory/'speech.wav'),'--out',relative(result),'--quit','--mute','--capture']
        text=text[:start]+'  controllerArgs [ '+' '.join(json.dumps(x) for x in arguments)+' ]'+text[end:]
        world.write_text(text,encoding='utf-8')
        settings=ROOT/'webots/worlds/.gesture_lab.wbproj'
        if settings.exists():world.with_name('.'+world.stem+'.wbproj').write_text(settings.read_text(encoding='utf-8-sig'),encoding='utf-8')
        exe=Path(os.environ['LOCALAPPDATA'])/'Programs/Webots/msys64/mingw64/bin/webots.exe'
        env=os.environ.copy()
        for key in ('NAO_LAB_OUT','NAO_LAB_QUIT','NAO_LAB_MUTE','NAO_LAB_CAPTURE'):env.pop(key,None)
        launched=time.time()
        run_command([exe,'--mode=fast','--batch','--stdout','--stderr',world],result/'simulation.log',env)
        report=result/'simulation_report.json'
        if not report.is_file() or report.stat().st_mtime<launched or not read_json(report).get('checks_passed'):raise RuntimeError('A simulação não passou nas verificações. Consulte o relatório.')
        import shutil
        ffmpeg=shutil.which('ffmpeg')
        update(message='Preparando o vídeo da simulação…')
        run_command([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',result/'webots_motion.mp4','-i',directory/'speech.mp3','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-shortest','-movflags','+faststart',result/'simulation.mp4'],result/'simulation.log')
        # Store the result link separately from immutable generated audio/motion.
        (JOBS/(identifier+'_simulation.json')).write_text(json.dumps({'directory':relative(result),'report':read_json(report)}),encoding='utf-8')
        update(message='Simulação concluída, sem falhas nas verificações.')
    except Exception as error:update(message=str(error))
    finally:update(busy=False,operation=None)

def execute_robot(identifier,audio_on_robot,intensity=1.,diagnostic=False,constant_stiffness=False,compare=False,pace='natural',head_enabled=False,intent_enabled=False):
    from app.motion_quality import analyze_telemetry
    process=None;stop_file=None;results=[]
    modes=[('A · padrão',False),('B · rigidez constante',True)] if compare else [('execução',constant_stiffness)]
    try:
        directory=job_dir(identifier);root_run=JOBS/('run_'+uuid.uuid4().hex);root_run.mkdir()
        stop_file=root_run/'STOP';ACTIVE['stop_file']=stop_file
        trajectory=None;head_targets=None;direction=None
        if not diagnostic:
            from app.pace_source import load_execution_trajectory
            update(message='Preparando o ritmo dos gestos…')
            trajectory=load_execution_trajectory(directory)
            if intent_enabled:
                from app.direction import plan_intents
                direction=plan_intents(read_json(directory/'speech.json'),trajectory['times_s'][-1])
            if head_enabled:
                from app.upper_body import load_upper_body
                head_targets=load_upper_body(directory)['head_rad']
        for index,(label,constant) in enumerate(modes):
            if STOP.is_set():break
            run_dir=root_run/('A_default' if index==0 else 'B_constant') if compare else root_run
            run_dir.mkdir(exist_ok=True)
            update(message=label+': verificando postura e motores…')
            status=bridge_probe()
            if compare and not status.get('smart_stiffness',True):
                raise ValueError('Smart Stiffness já está desligado; os modos A e B seriam iguais. Execute uma fala no modo Padrão do NAO para registrar as pausas.')
            if head_enabled and not status.get('head',{}).get('available'):raise ValueError('Atualize a conexão: leitura da cabeça indisponível.')
            current_head=status['head']['angles'] if head_enabled else None
            if intent_enabled and not status.get('manual',{}).get('available'):raise ValueError('Leitura de punhos/mãos indisponível. Desative gestos com intenção para executar somente o EMAGE.')
            current_manual=status['manual']['angles'] if intent_enabled else None
            plan=build_diagnostic_plan(status['angles']) if diagnostic else build_plan(trajectory,status['angles'],intensity,pace=pace,head_targets=head_targets,current_head=current_head,direction=direction,current_manual=current_manual)
            plan['initial_angles']=status['angles']+(current_head if current_head is not None else [])+(current_manual if current_manual is not None else []);plan['constant_stiffness']=constant
            plan_path=run_dir/'plan.json';plan_path.write_text(json.dumps(plan),encoding='utf-8')
            audio=directory/'speech.wav'
            if audio_on_robot:
                import shutil
                audio=run_dir/'robot_audio.wav'
                run_command([shutil.which('ffmpeg'),'-hide_banner','-loglevel','error','-y','-i',directory/'speech.wav','-ac','2','-ar','48000','-af','volume=0.65','-c:a','pcm_s16le',audio],run_dir/'run.log')
            if STOP.is_set():break
            config=read_json(ROOT/'robot_connection.json')
            args=['--host',config['host'],'--port',config['naoqi_port'],'--execute','--plan',plan_path,'--audio',audio,'--stop-file',stop_file,'--telemetry',run_dir/'telemetry.jsonl']
            if audio_on_robot:args.append('--audio-on-robot')
            if constant:args.append('--constant-stiffness')
            with (run_dir/'run.log').open('a',encoding='utf-8') as log:
                process=launch_bridge(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
                ACTIVE['robot_process']=process
                execution={'id':uuid.uuid4().hex,'job_id':identifier,'phase':'preparing','audio_on_robot':audio_on_robot,'audio_started':False,'label':label}
                update(execution=execution,message=label+': preparando braços…')
                error=None
                for line in process.stdout:
                    log.write(line);log.flush()
                    try:event=json.loads(line)
                    except ValueError:continue
                    if event.get('event')=='moving':
                        execution.update(phase='moving');update(execution=execution.copy(),message=label+': movimento em execução.')
                    elif event.get('event')=='audio_start':
                        execution.update(audio_started=True);update(execution=execution.copy())
                    elif event.get('event')=='error':error=event.get('message')
                    elif event.get('event') in ('complete','stopped'):
                        execution['phase']=event['event'];execution['tracking_rms_deg']=event.get('motor_tracking_rms_deg');update(execution=execution.copy())
            process.wait()
            if process.returncode or error:raise RuntimeError(error or 'A conexão com o executor foi encerrada.')
            if STOP.is_set() or execution['phase']=='stopped':break
            telemetry=run_dir/'telemetry.jsonl'
            if telemetry.exists():
                records=[json.loads(row) for row in telemetry.read_text(encoding='utf-8').splitlines() if row.strip()]
                if len(records)>=3:
                    bounds=None if diagnostic else (plan['audio_start_s'],plan['audio_start_s']+read_json(directory/'trajectory.json')['times_s'][-1])
                    quality=analyze_telemetry(records,plan['names'],bounds)
                    quality.update(label=label,constant_stiffness=constant)
                    (run_dir/'quality.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
                    results.append(quality)
        if STOP.is_set():update(message='Execução interrompida.')
        elif results:
            summary=' · '.join('%s: %d pausas nas juntas, %.1f° RMS'%(r['label'],r['unplanned_pause_count'],r['tracking_rms_deg']) for r in results)
            if compare and len(results)!=2:raise RuntimeError('Comparação incompleta: não foi possível avaliar os dois testes.')
            report={'comparison':compare,'summary':summary,'results':results,'note':'Pausas em juntas podem coincidir; esta contagem não é o número de pausas do corpo inteiro. Não diagnostica a causa.'}
            (root_run/'quality_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            update(quality=report,message='Comparação concluída.' if compare else 'Execução concluída.')
        else:update(message='Execução concluída; dados insuficientes para avaliar pausas.')
    except Exception as error:update(message=str(error),execution={'phase':'error','message':str(error)})
    finally:
        if process is not None and process.poll() is None:
            failure_message=STATE.get('message')
            try:
                if stop_file is not None:stop_file.touch()
            except OSError as error:
                update(message='Falha ao solicitar parada pelo arquivo: '+str(error))
            # Keep the operation reserved until the worker has restored its settings.
            while process.poll() is None:
                update(message='Aguardando o executor encerrar e restaurar os ajustes do NAO…')
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:continue
            if STATE.get('execution',{}).get('phase')=='error':update(message=failure_message)
        ACTIVE.pop('robot_process',None);ACTIVE.pop('stop_file',None);update(busy=False,operation=None)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def json(self,value,status=200):
        raw=json.dumps(value,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def file(self,path,tokenize=False):
        raw=path.read_bytes()
        if tokenize:raw=raw.replace(b'__TOKEN__',TOKEN.encode())
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        try:
            path=urlsplit(self.path).path
            if path=='/':return self.file(ASSETS/'index.html',True)
            if path in ('/ui.css','/ui.js'):return self.file(ASSETS/path[1:])
            direction_match=re.fullmatch('/api/direction/(demo|[a-f0-9]{32})',path)
            if direction_match:
                from app.direction import plan_intents
                directory=job_dir(direction_match.group(1))
                return self.json(plan_intents(read_json(directory/'speech.json'),read_json(directory/'trajectory.json')['times_s'][-1]))
            if path=='/api/state':
                with LOCK:state=STATE.copy()
                state['jobs']=history();state['simulations']={}
                for j in state['jobs']:
                    p=JOBS/(j['id']+'_simulation.json')
                    if p.exists():state['simulations'][j['id']]=read_json(p)['report']
                return self.json(state)
            match=re.fullmatch('/media/([a-z0-9]+)/([a-z0-9_.]+)',path)
            if match:
                identifier,name=match.groups()
                if name=='simulation.mp4':
                    directory=ROOT/read_json(JOBS/(identifier+'_simulation.json'))['directory'];return self.file(directory/name)
                if name not in ('speech.wav','speech.mp3','preview.html','trajectory.json','report.json'):raise ValueError('Arquivo não disponível.')
                return self.file(job_dir(identifier)/name)
            return self.json({'error':'Não encontrado.'},404)
        except (OSError,ValueError,KeyError) as error:self.json({'error':str(error)},404)
    def do_POST(self):
        try:
            host=self.headers.get('Host','')
            expected='http://'+host
            if host not in ('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)):raise ValueError('Host não permitido.')
            if self.headers.get('Origin',expected)!=expected or self.headers.get('X-NAO-Token')!=TOKEN:raise ValueError('Sessão inválida. Recarregue a página local.')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<=length<=10000:raise ValueError('Requisição muito grande.')
            data=json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data,dict):raise ValueError('Formato de requisição inválido.')
            path=urlsplit(self.path).path
            if path=='/api/generate':
                if not isinstance(data.get('text'),str):raise ValueError('Informe o texto da fala.')
                text=data.get('text','').strip();voice=data.get('voice')
                if not 1<=len(text)<=1200:raise ValueError('Escreva entre 1 e 1.200 caracteres.')
                if voice not in ('pt-BR-AntonioNeural','pt-BR-FranciscaNeural'):raise ValueError('Voz não disponível.')
                claim('generate','Preparando a geração…')
                job={'id':uuid.uuid4().hex,'text':text,'voice':voice,'created':time.time(),'status':'generating'}
                directory=JOBS/job['id'];directory.mkdir();(directory/'text.txt').write_text(text,encoding='utf-8');save_job(job)
                threading.Thread(target=generate,args=(job,),daemon=True).start();return self.json({'id':job['id']},202)
            if path=='/api/robot/probe':
                try:return self.json(bridge_probe())
                except Exception:
                    config=read_json(ROOT/'robot_connection.json')
                    update(robot={'connected':False,'host':config['host'],'port':config['naoqi_port']},message='NAO indisponível. Verifique a rede e atualize a conexão.')
                    raise
            if path in ('/api/simulate','/api/robot/execute','/api/robot/diagnostic','/api/robot/compare'):
                compare=path=='/api/robot/compare'
                diagnostic=compare or path=='/api/robot/diagnostic'
                identifier='demo' if diagnostic else data.get('id');job=get_job(identifier)
                body_mode=data.get('body_mode','arms')
                if body_mode not in ('arms','arms_head','torso'):raise ValueError('Modo de movimento inválido.')
                pace=data.get('pace','natural');intensity=float(data.get('intensity',1.));intent_enabled=data.get('intent_enabled',True)
                if not isinstance(pace,str) or pace not in PACES:raise ValueError('Ritmo inválido.')
                if not .1<=intensity<=1.:raise ValueError('Intensidade fora do intervalo permitido.')
                if not isinstance(intent_enabled,bool):raise ValueError('Modo de intenção inválido.')
                if job['status']!='ready':raise ValueError('Gere a fala e os gestos primeiro.')
                if path=='/api/simulate':target=simulate;args=(identifier,body_mode,pace,intensity,intent_enabled);claim('simulate','Iniciando o Webots…')
                else:
                    if body_mode=='torso' and not diagnostic:raise ValueError('Inclinação do corpo está disponível somente no Webots nesta versão.')
                    if os.environ.get('NAO_APP_NO_MOTION')=='1':raise ValueError('Execução física desabilitada nesta sessão de teste.')
                    intensity=float(data.get('intensity',1.))
                    if not .1<=intensity<=1.:raise ValueError('Intensidade fora do intervalo permitido.')
                    constant=data.get('constant_stiffness',False)
                    if not isinstance(constant,bool):raise ValueError('Modo de rigidez inválido.')
                    pace=data.get('pace','natural')
                    if not isinstance(pace,str) or pace not in PACES:raise ValueError('Ritmo inválido.')
                    target=execute_robot;args=(identifier,False if diagnostic else bool(data.get('audio_on_robot',True)),intensity,diagnostic,constant,compare,pace,not diagnostic and body_mode=='arms_head',not diagnostic and intent_enabled);claim('robot','Verificando o NAO…')
                threading.Thread(target=target,args=args,daemon=True).start();return self.json({'started':True},202)
            if path=='/api/stop':
                STOP.set()
                stop_file=ACTIVE.get('stop_file')
                if stop_file:stop_file.touch()
                update(message='Solicitando parada…');return self.json({'stopping':True})
            return self.json({'error':'Ação não disponível.'},404)
        except (ValueError,OSError,KeyError) as error:self.json({'error':str(error)},400)

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8766);args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print('NAO Studio: http://127.0.0.1:%d'%args.port,flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:STOP.set()
    finally:
        stop_file=ACTIVE.get('stop_file')
        if stop_file:stop_file.touch()
        process=ACTIVE.get('process')
        if process and process.poll() is None:process.terminate()
        robot_process=ACTIVE.get('robot_process')
        if robot_process:
            try:robot_process.wait(timeout=3)
            except subprocess.TimeoutExpired:pass
        server.server_close()

if __name__=='__main__':main()
