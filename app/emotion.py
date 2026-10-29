"""Authored expressive presets, not emotion recognition or a trained policy."""
import re
import numpy as np

# rate, pitch and volume are supported Edge TTS prosody controls. These are
# approximations, not vendor emotion styles or claims of perceptual accuracy.
PROFILES={
    'neutral':dict(label='Neutra',rate='+0%',pitch='+0Hz',volume='+0%',gain=1.,spread=0.,pitch_bias=0.,opening=0.,color=None,
        cues=['Mantém postura de conversa e olhar à frente.','Mãos e punhos acompanham os braços.','Conclui e retorna à postura inicial.']),
    'joy':dict(label='Alegria',rate='+8%',pitch='+8Hz',volume='+0%',gain=1.10,spread=.07,pitch_bias=-.025,opening=.08,color=0xFFD060,
        cues=['Abre levemente os braços; olha à frente; olhos em amarelo suave.','Apresenta as palmas e acompanha a ênfase com a cabeça.','Conclui com mãos receptivas e recupera a postura inicial.']),
    'sadness':dict(label='Tristeza',rate='-14%',pitch='-8Hz',volume='-8%',gain=.70,spread=-.025,pitch_bias=.09,opening=-.12,color=0x4060A0,
        cues=['Aproxima os braços do corpo e inclina discretamente a cabeça para baixo; olhos azuis.','Mantém gestos contidos, mãos parcialmente recolhidas e voz mais lenta.','Sustenta brevemente o olhar baixo e recupera a postura inicial.']),
    'fear':dict(label='Medo',rate='+5%',pitch='+12Hz',volume='-5%',gain=.82,spread=-.015,pitch_bias=-.035,opening=-.08,color=0x8060B0,
        cues=['Recolhe discretamente os braços; olha à frente com a cabeça ligeiramente elevada; olhos violetas.','Mantém as mãos próximas do corpo, com movimentos curtos de atenção.','Relaxa o recolhimento e retorna à postura inicial.']),
    'anger':dict(label='Raiva',rate='+4%',pitch='-5Hz',volume='+2%',gain=1.04,spread=.015,pitch_bias=.035,opening=-.18,color=0xB04030,
        cues=['Firma a orientação da cabeça à frente; mãos parcialmente fechadas; olhos vermelhos suaves.','Marca a fala com gestos contidos e assertivos, sem golpes ou fechamento total.','Reduz a tensão dos gestos e recupera a postura inicial.']),
    'disgust':dict(label='Nojo',rate='-6%',pitch='-5Hz',volume='-3%',gain=.78,spread=.025,pitch_bias=-.02,opening=-.06,color=0x609040,
        cues=['Desvia levemente o olhar; afasta discretamente os antebraços; olhos verdes suaves.','Mantém as mãos parcialmente abertas e uma orientação breve de recusa.','Volta o olhar à frente e recupera a postura inicial.']),
    'surprise':dict(label='Surpresa',rate='+10%',pitch='+16Hz',volume='+0%',gain=1.12,spread=.08,pitch_bias=-.055,opening=.12,color=0xA0C0D0,
        cues=['Eleva discretamente a cabeça e abre os braços; olhos em branco azulado.','Abre as mãos e sustenta brevemente o gesto, sem levar as mãos ao rosto.','Recolhe gradualmente a expressão e retorna à postura inicial.']),
}

# Distinct bilateral postures, in the eight NAO arm coordinates. These are
# modest authored offsets over EMAGE, not poses copied onto human anatomy.
BODY_STYLES={
    'neutral':dict(label='Conversa natural',offset=[0.]*8,wrist=0.,yaw_bias=0.),
    'joy':dict(label='Aberta e receptiva',offset=[-.08,.12,.07,.05,-.08,-.12,-.07,-.05],wrist=.09,yaw_bias=0.),
    'sadness':dict(label='Recolhida e lenta',offset=[.22,-.06,.06,-.10,.22,.06,-.06,.10],wrist=-.08,yaw_bias=0.),
    'fear':dict(label='Protegida e atenta',offset=[-.10,-.03,-.08,-.25,-.10,.03,.08,.25],wrist=-.10,yaw_bias=0.),
    'anger':dict(label='Firme e marcada',offset=[-.08,.04,-.10,-.10,-.08,-.04,.10,.10],wrist=-.06,yaw_bias=0.),
    'disgust':dict(label='Afastamento e recusa',offset=[.10,.10,.12,.08,.06,-.04,-.05,-.02],wrist=.10,yaw_bias=.10),
    'surprise':dict(label='Abertura e sustentação',offset=[-.16,.13,-.06,-.03,-.16,-.13,.06,.03],wrist=.12,yaw_bias=0.),
}

def profile(key):
    if not isinstance(key,str) or key not in PROFILES:raise ValueError('Emoção inválida. Escolha uma das opções do menu.')
    return PROFILES[key]

def expression_script(speech,key='neutral'):
    cfg=profile(key);words=speech.get('words',[])
    cues=[]
    if words:
        for index,description in zip(sorted(set([0,len(words)//2,len(words)-1])),cfg['cues']):
            word=words[index]
            cues.append(dict(at_s=float(word['start_s']),word=word['text'],description=description))
    text=speech.get('text','')
    # Written stage directions are a readable score. Timing comes from the
    # actual synthesized words; it is never included in the TTS input.
    tokens=re.findall(r'\S+',text)
    cuts=sorted(set([0,len(tokens)//2,len(tokens)]));parts=[]
    for i,(start,end) in enumerate(zip(cuts,cuts[1:])):
        parts.append('('+cfg['cues'][min(i,2)]+') "'+' '.join(tokens[start:end])+'"')
    if parts:parts.append('('+cfg['cues'][2]+')')
    prosody=({k:cfg[k] for k in ('rate','pitch','volume')} if speech.get('provider')!='elevenlabs' else
             {'provider':'elevenlabs','model':speech.get('model'),'emotion':key,'control':'Audio tags for v4/v3; voice delivery depends on selected model and voice'})
    return {'emotion':key,'emotion_label':cfg['label'],'speech_and_gestures':' '.join(parts),
            'cues':cues,'prosody':prosody,
            'eye_color':cfg['color'],'body_style':BODY_STYLES[key]['label'],
            'method':'Authored NAO expression presets over EMAGE; approximate expressive prosody'}

def apply_emotion(arms,head,manual,times,key,cue_times=None):
    cfg=profile(key)
    if key=='neutral':return arms,head,manual
    arms=np.asarray(arms,float).copy();times=np.asarray(times,float)
    from app.direction import envelope
    style=BODY_STYLES[key]
    # Sustain the posture through most of the phrase, rather than reaching
    # full expression only at its midpoint. Physical entry/exit remain separate.
    ramp=min(.8,max(.1,times[-1]/4))
    def ease(u):
        u=np.clip(u,0.,1.);return u**3*(10.-15.*u+6.*u*u)
    weight=ease(times/ramp)*ease((times[-1]-times)/ramp)
    anchors=[float(x) for x in (cue_times or []) if np.isfinite(x) and 0<=x<=times[-1]]
    beats=np.zeros(len(times))
    for anchor in anchors:beats=np.maximum(beats,envelope(times,anchor,prepare=.28,hold=.10,release=.45))
    center=arms.mean(axis=0)
    arms=center+(arms-center)*cfg['gain']
    arms+=weight[:,None]*np.asarray(style['offset'])
    if key=='anger':
        arms[:,0]-=.08*beats;arms[:,4]-=.08*beats
        arms[:,3]-=.035*beats;arms[:,7]+=.035*beats
    elif key=='joy':
        arms[:,1]+=.045*beats;arms[:,5]-=.045*beats
    elif key=='surprise' and anchors:
        initial=envelope(times,anchors[0],prepare=.4,hold=.25,release=1.1)
        arms[:,0]-=.08*initial;arms[:,4]-=.08*initial
    if head is not None:
        head=np.asarray(head,float).copy()
        head=head.mean(axis=0)+(head-head.mean(axis=0))*min(cfg['gain'],1.05)
        if key=='joy':head[:,1]+=.04*beats
        elif key=='fear':head[:,0]+=.035*beats
        elif key=='anger':head[:,1]+=.045*beats
        elif key=='surprise':head[:,1]-=.04*beats
    if manual is not None:
        manual=np.asarray(manual,float).copy()
        manual[:,2:]=np.clip(manual[:,2:]+cfg['opening']*weight[:,None],.08,.92)
        manual[:,0]+=(style['wrist']*weight);manual[:,1]-=(style['wrist']*weight)
        if key=='anger':manual[:,2:]=np.clip(manual[:,2:]-.06*beats[:,None],.08,.92)
    return arms,head,manual
