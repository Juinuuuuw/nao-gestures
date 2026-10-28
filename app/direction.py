"""Transparent Portuguese speech-to-gesture rules, anchored to Edge word times.

This is an intent vocabulary, not a general language-understanding model.
Unknown clauses receive a modest explanatory gesture, not invented pointing.
"""
import math
import re
import unicodedata
import numpy as np

MANUAL_NAMES=['LWristYaw','RWristYaw','LHand','RHand']
MANUAL_LIMITS=np.array([[-1.82387,1.82387],[-1.82387,1.82387],[0.,1.],[0.,1.]])
MANUAL_GESTURE_LIMITS=np.array([[-.75,.75],[-.75,.75],[.08,.92],[.08,.92]])
LABELS={'greeting':'saudação','explain':'explicação','contrast':'alternativa',
        'emphasis':'ênfase','question':'pergunta','expand':'ampliar','small':'tamanho pequeno',
        'open':'abrir a mão','close':'fechar a mão'}

def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn')

def plan_intents(speech,duration=None):
    duration=float(speech.get('duration_s',0.) if duration is None else duration)
    if not math.isfinite(duration) or duration<=0 or duration>65:raise ValueError('Duração da fala inválida.')
    words=[]
    for word in speech.get('words',[]):
        at=float(word['start_s']);length=float(word['duration_s'])
        if not math.isfinite(at) or not math.isfinite(length) or at<0 or length<0:raise ValueError('Tempos de palavras inválidos.')
        if at>=duration:continue
        words.append({'word':str(word['text']),'token':normal(str(word['text'])).strip('.,!?;:'),
                      'at':min(duration,at+min(length,.7)*.5),'start_s':at})
    if not words:raise ValueError('Esta geração não tem tempos de palavras. Gere a fala novamente para usar intenção.')
    if any(a['start_s']>b['start_s'] for a,b in zip(words,words[1:])):raise ValueError('Palavras fora de ordem.')
    candidates=[];tokens=[w['token'] for w in words];contrast_count=0;explanation_side=0
    for i,word in enumerate(words):
        token=word['token'];kind=None;priority=1;side='L' if explanation_side%2==0 else 'R'
        nearby=tokens[max(0,i-3):min(len(tokens),i+5)]
        if token in ('abrir','abra','abro','abrindo','fechar','feche','fecho','fechando') and any(x in ('mao','maos') for x in tokens[i+1:i+5]):
            if any(x in ('nao','nunca','jamais','sem') for x in tokens[max(0,i-3):i]):continue
            # "abrir mão de" is the Portuguese idiom for giving something up.
            if any(tokens[k] in ('mao','maos') and k+1<len(tokens) and tokens[k+1]=='de' for k in range(i+1,min(i+5,len(tokens)))):continue
            kind='open' if token.startswith('abr') else 'close';side='both';priority=5
        elif token in ('ola','oi','bem-vindo','bem-vindos','tchau','adeus'):kind='greeting';priority=3
        elif token in ('primeiro','primeira','segundo','segunda','alternativa','alternativas','possibilidades','opcoes'):
            kind='contrast';side='R' if token in ('segundo','segunda') or contrast_count%2 else 'L';contrast_count+=1;priority=3
        elif token=='outro' and i and tokens[i-1] in ('do','por','de'):
            kind='contrast';side='R';priority=3
        elif token in ('importante','principal','essencial','atencao','fundamental'):kind='emphasis';priority=4
        elif token in ('grande','maior','expandir','ampliar','expandindo'):kind='expand';side='both';priority=3
        elif token in ('pequeno','pequena','menor'):kind='small';side='both';priority=3
        if kind:
            candidates.append(dict(kind=kind,side=side,priority=priority,word=word['word'],at_s=word['at'],timing_source='edge_word'))
            explanation_side+=1
    if '?' in speech.get('text',''):
        # Use the last spoken word; no fixed timestamp detached from the audio.
        word=words[-1];candidates.append(dict(kind='question',side='both',priority=2,word=word['word'],at_s=word['at'],timing_source='edge_word'))
    # Prioritise explicit intent; avoid packing several gestures into one clause.
    selected=[]
    for candidate in sorted(candidates,key=lambda e:(-e['priority'],e['at_s'])):
        if all(abs(candidate['at_s']-other['at_s'])>=1.35 for other in selected):selected.append(candidate)
        if len(selected)>=min(16,max(1,int(math.ceil(duration/2.4)))):break
    if not selected:
        word=words[len(words)//2]
        selected=[dict(kind='explain',side='L',priority=0,word=word['word'],at_s=word['at'],timing_source='edge_word',fallback=True)]
    selected.sort(key=lambda e:e['at_s'])
    for event in selected:event['label']=LABELS[event['kind']]
    return {'version':1,'method':'Portuguese intent vocabulary + timed words','events':selected,
            'duration_s':duration,'gaze_source':'measured initial head direction; no person/object tracking'}

def envelope(times,at,prepare=.65,hold=.15,release=.7):
    times=np.asarray(times,float)
    def ease(u):
        u=np.clip(u,0.,1.);return u**3*(10.-15.*u+6.*u*u)
    return np.minimum(ease((times-at+prepare)/prepare),1.-ease((times-at-hold)/release))

def natural_manual(arms,times):
    """Procedural hand articulation from each EMAGE arm, not finger retargeting.

    Opening follows presentation/extension and motion energy. A centered filter
    removes IK chatter without a fixed oscillation or a dependency on keywords.
    The physical planner subsequently enforces manual velocity/acceleration.
    """
    def smooth(values):
        radius=max(1,int(round(.18/np.median(np.diff(times)))))
        kernel=np.hanning(2*radius+3)[1:-1];kernel/=kernel.sum()
        return np.convolve(np.pad(values,(radius,radius),mode='edge'),kernel,mode='valid')
    manual=np.empty((len(times),4))
    for arm in (0,1):
        sign=1 if arm==0 else -1
        q=arms[:,4*arm:4*arm+4]
        speed=smooth(np.linalg.norm(np.gradient(q,times,axis=0),axis=1))
        activity=np.clip(speed/.9,0.,1.)
        extension=np.clip((1.35-np.abs(q[:,3]))/.95,0.,1.)
        presentation=np.clip((1.45-q[:,0])/.85,0.,1.)
        manual[:,arm+2]=np.clip(smooth(.30+.28*extension+.15*presentation+.18*activity),.25,.91)
        manual[:,arm]=np.clip(smooth(sign*(.12+.32*presentation+.10*activity)+.15*(q[:,2]+sign*1.1)),-.70,.70)
    return manual


def direct_motion(arms,head,times,schedule):
    """Preserve EMAGE arms, add continuous hands and modest intent accents."""
    arms=np.asarray(arms,float).copy();times=np.asarray(times,float)
    if arms.shape!=(len(times),8) or not np.isfinite(arms).all():raise ValueError('Braços inválidos para direção.')
    heads=None if head is None else np.asarray(head,float).copy()
    if heads is not None and (heads.shape!=(len(times),2) or not np.isfinite(heads).all()):raise ValueError('Cabeça inválida para direção.')
    manual=natural_manual(arms,times)
    # A listener-facing baseline leaves room for intentional brief glances.
    if heads is not None:
        mean=heads.mean(axis=0);heads=mean+(heads-mean)*.30
    for event in schedule['events']:
        w=envelope(times,event['at_s']);kind=event['kind'];side=event['side']
        active=(0,1) if side=='both' else (0,) if side=='L' else (1,)
        for arm in active:
            sign=1 if arm==0 else -1;sl=slice(4*arm,4*arm+4)
            pose=np.array([.90,sign*.34,-sign*.82,-sign*.92])
            opening=.82;wrist=sign*.40
            if kind=='expand':pose=np.array([.90,sign*.48,-sign*.95,-sign*.65]);opening=.88
            elif kind=='small':pose=np.array([1.03,sign*.25,-sign*.85,-sign*1.03]);opening=.60;wrist=sign*.20
            elif kind=='emphasis':pose=np.array([.82,sign*.31,-sign*.90,-sign*.98]);opening=.60;wrist=sign*.25
            elif kind=='question':pose=np.array([.98,sign*.35,-sign*.72,-sign*.88]);opening=.78
            elif kind=='close':opening=.12;wrist=sign*.10
            elif kind=='open':opening=.88;wrist=sign*.25
            # Intent is an accent; EMAGE remains the dominant arm trajectory.
            # Literal hand instructions should not replace the arm gesture.
            blend=(0. if kind in ('open','close') else .12)*w
            arms[:,sl]=arms[:,sl]*(1.-blend[:,None])+pose*blend[:,None]
            hand_blend=w if kind in ('open','close') else .35*w
            manual[:,arm]=manual[:,arm]*(1.-.35*w)+wrist*.35*w
            manual[:,arm+2]=manual[:,arm+2]*(1.-hand_blend)+opening*hand_blend
        if heads is not None:
            glance=envelope(times,event['at_s']-.12,prepare=.4,hold=.12,release=.45)
            yaw=(.10 if side=='L' else -.10) if kind=='contrast' else 0.
            pitch=.07 if kind=='emphasis' else -.025 if kind=='question' else .015
            head_pose=heads.mean(axis=0)+[yaw,pitch]
            heads=heads*(1.-.65*glance[:,None])+head_pose*(.65*glance[:,None])
    return arms,heads,manual
