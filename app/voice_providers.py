"""ElevenLabs HTTP API, account voice catalog and local encrypted credentials."""
import base64
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
KEY_FILE=ROOT/'runtime/elevenlabs.key'
DEFAULT_VOICE='NOpBlnGInO9m6vDvFkFC'
MODELS={'eleven_v4':'Eleven v4 · expressivo','eleven_v3':'Eleven v3 · expressivo',
        'eleven_multilingual_v2':'Multilingual v2 · estável','eleven_flash_v2_5':'Flash v2.5 · rápido'}
EMOTION_TAGS={'neutral':'','joy':'[happy]','sadness':'[sad]','fear':'[scared]',
              'anger':'[angry]','disgust':'[appalled]','surprise':'[surprised]'}

def validate_voice(voice,model):
    if not isinstance(voice,str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,100}',voice):raise ValueError('Voice ID ElevenLabs inválido.')
    if not isinstance(model,str) or model not in MODELS:raise ValueError('Modelo ElevenLabs inválido.')

def _crypt(data,decrypt=False):
    if os.name!='nt':raise ValueError('Fora do Windows, configure ELEVENLABS_API_KEY no ambiente.')
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    if decrypt:
        fn=crypt.CryptUnprotectData;fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    else:
        fn=crypt.CryptProtectData;fn.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL;kernel.LocalFree.argtypes=[ctypes.c_void_p]
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):
        raise ValueError('O Windows não conseguiu proteger/ler a chave local.')
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(target.data)

KEY_ID_MESSAGE='Foi informado o ID da chave. Cole a chave secreta completa, que começa com sk_, e não o Key ID. Crie ou rotacione a chave na ElevenLabs para copiá-la.'

def validate_api_key(key):
    if not isinstance(key,str) or not key.strip():raise ValueError('Cadastre a API key da ElevenLabs no painel de voz.')
    if not key.strip().startswith('sk_'):raise ValueError(KEY_ID_MESSAGE)
    if not re.fullmatch(r'sk_[A-Za-z0-9_-]{13,509}',key.strip()):raise ValueError('A API key da ElevenLabs está incompleta ou tem caracteres inválidos.')

def save_key(key):
    validate_api_key(key)
    encrypted=_crypt(key.strip().encode('utf-8'))
    KEY_FILE.parent.mkdir(parents=True,exist_ok=True)
    temporary=KEY_FILE.with_suffix('.key.tmp');temporary.write_bytes(encrypted);temporary.replace(KEY_FILE)

def api_key():
    if KEY_FILE.is_file():return _crypt(KEY_FILE.read_bytes(),decrypt=True).decode('utf-8')
    value=os.environ.get('ELEVENLABS_API_KEY','').strip()
    if not value and os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:value=str(winreg.QueryValueEx(key,'ELEVENLABS_API_KEY')[0]).strip()
        except OSError:pass
    return value

def provider_status():
    try:key=api_key();error=None
    except ValueError:key='';error='Não foi possível ler a chave protegida. Cadastre-a novamente.'
    configured=bool(key)
    if key:
        try:validate_api_key(key)
        except ValueError as problem:configured=False;error=str(problem)
    return {'elevenlabs_configured':configured,'credential_error':error,'default_voice':DEFAULT_VOICE,
            'language_code':'pt','locale':'pt-BR','models':MODELS}

def request_json(path,payload=None,key=None,timeout=30):
    key=key or api_key()
    if not key:raise ValueError('Cadastre a API key da ElevenLabs no painel de voz ou configure ELEVENLABS_API_KEY.')
    validate_api_key(key)
    req=urllib.request.Request('https://api.elevenlabs.io'+path,
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None,
        headers={'xi-api-key':key,'Content-Type':'application/json','Accept':'application/json'},method='POST' if payload is not None else 'GET')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        # Do not propagate upstream response bodies or request headers to logs/UI.
        messages={401:'Chave inválida ou expirada.',402:'Créditos ou plano insuficientes.',403:'A chave não tem permissão para esta operação.',
                  404:'Voz ou modelo não disponível nesta conta.',422:'Parâmetros não aceitos por esta voz/modelo.',429:'Limite de uso ou créditos atingido. Aguarde e consulte a conta.'}
        message=messages.get(error.code,'A API recusou a solicitação. Verifique o modelo e a voz.')
        try:
            body=json.loads(error.read(4096));detail=body.get('detail',{}) if isinstance(body,dict) else {}
            if isinstance(detail,dict) and detail.get('status') in ('quota_exceeded','insufficient_credits'):
                message='Créditos insuficientes na conta ElevenLabs.'
            elif isinstance(detail,dict) and detail.get('status')=='api_key_id_used_as_api_key':message=KEY_ID_MESSAGE
            elif isinstance(detail,dict) and detail.get('status') in ('invalid_api_key','invalid_key'):
                message='A chave secreta é inválida ou foi revogada. Cadastre uma chave sk_ válida.'
        except (ValueError,OSError):pass
        raise ValueError('ElevenLabs HTTP %d: %s'%(error.code,message)) from None
    except (urllib.error.URLError,TimeoutError):raise ValueError('Não foi possível conectar à ElevenLabs. Verifique a internet e tente novamente.') from None

def voice_catalog():
    voices=[];token=None;seen=set()
    for _ in range(5):
        query={'page_size':100}
        if token:query['next_page_token']=token
        data=request_json('/v2/voices?'+urllib.parse.urlencode(query))
        for voice in data.get('voices',[]):
            identifier=voice.get('voice_id','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{10,100}',identifier):continue
            labels=voice.get('labels') or {}
            voices.append({'voice_id':identifier,'name':str(voice.get('name',identifier))[:150],
                'accent':str(labels.get('accent',''))[:80],'language':str(labels.get('language',''))[:80]})
        token=data.get('next_page_token')
        if not data.get('has_more') or not token or token in seen:break
        seen.add(token)
    voices.sort(key=lambda v:(not any(x in (v['accent']+' '+v['language']).lower() for x in ('brazil','brasil','portugu','pt-br')),v['name'].lower()))
    return {'voices':voices,'has_more':bool(data.get('has_more')),'language_code':'pt','locale':'pt-BR'}

def tts_payload(text,voice,model,emotion='neutral'):
    validate_voice(voice,model)
    if emotion not in EMOTION_TAGS:raise ValueError('Emoção inválida.')
    if model not in ('eleven_v4','eleven_v3') and re.search(r'\[[^\]]+\]',text):
        raise ValueError('Para usar tags de áudio entre colchetes, selecione Eleven v4 ou v3.')
    tag=EMOTION_TAGS[emotion] if model in ('eleven_v4','eleven_v3') else ''
    payload={'text':(tag+' '+text).strip(),'model_id':model}
    # The multilingual v2 API explicitly does not accept language_code.
    if model!='eleven_multilingual_v2':payload['language_code']='pt'
    return payload

def alignment_words(alignment):
    """Use real character times, excluding non-spoken bracketed audio tags."""
    if not isinstance(alignment,dict):raise ValueError('A ElevenLabs não retornou alinhamento temporal. Gere novamente; não foram inventados tempos.')
    chars=alignment.get('characters',[]);starts=alignment.get('character_start_times_seconds',[]);ends=alignment.get('character_end_times_seconds',[])
    if not chars or len(chars)!=len(starts) or len(chars)!=len(ends):raise ValueError('Alinhamento da ElevenLabs incompleto.')
    text='';char_starts=[];char_ends=[];previous=-1.
    for char,start,end in zip(chars,starts,ends):
        start=float(start);end=float(end)
        if not isinstance(char,str) or not char or not math.isfinite(start) or not math.isfinite(end) or start<0 or end<start or start<previous-.001:
            raise ValueError('Alinhamento da ElevenLabs inválido.')
        text+=char;char_starts.extend([start]*len(char));char_ends.extend([end]*len(char));previous=start
    ignored=set()
    for match in re.finditer(r'\[[^\]]*\]',text):ignored.update(range(match.start(),match.end()))
    clean=''.join(' ' if i in ignored else char for i,char in enumerate(text))
    words=[]
    for match in re.finditer(r'\S+',clean):
        if not any(c.isalnum() for c in match.group()):continue
        first=match.start();last=match.end()-1
        words.append({'text':match.group(),'start_s':char_starts[first],'duration_s':max(0.,char_ends[last]-char_starts[first])})
    if not words:raise ValueError('Alinhamento sem palavras faladas. Não foi possível sincronizar os gestos.')
    return words

def create_speech(text,voice,model,emotion='neutral'):
    payload=tts_payload(text,voice,model,emotion)
    # One paid request, no automatic retry or switch to another provider/model.
    response=request_json('/v1/text-to-speech/'+voice+'/with-timestamps?output_format=mp3_44100_128',payload,timeout=120)
    words=alignment_words(response.get('normalized_alignment') or response.get('alignment'))
    try:audio=base64.b64decode(response['audio_base64'],validate=True)
    except (ValueError,KeyError):raise ValueError('Áudio inválido na resposta da ElevenLabs.') from None
    if not audio:raise ValueError('A ElevenLabs retornou áudio vazio.')
    return audio,words,payload['text']
