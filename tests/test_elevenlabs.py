import base64
import io
import json
import os
import shutil
import sys
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import urllib.error
import soundfile as sf
from app import voice_providers as voices
from app.direction import plan_intents
from scripts.synthesize_elevenlabs import synthesize

def alignment(text,step=.07):
    return {'characters':list(text),'character_start_times_seconds':[i*step for i in range(len(text))],
            'character_end_times_seconds':[(i+1)*step for i in range(len(text))]}

class ElevenLabsTests(unittest.TestCase):
    def test_portuguese_and_supported_models_no_fake_brazil_language_code(self):
        for model in voices.MODELS:
            payload=voices.tts_payload('Uma descoberta.',voices.DEFAULT_VOICE,model,'joy')
            self.assertEqual(payload['model_id'],model)
            if model=='eleven_multilingual_v2':self.assertNotIn('language_code',payload)
            else:self.assertEqual(payload['language_code'],'pt')
            self.assertEqual(payload['text'].startswith('[happy]'),model in ('eleven_v4','eleven_v3'))

    def test_tags_removed_from_word_times_without_compressing_time(self):
        data=alignment('[happy] Olá, equipe! [whispers] Tudo bem?')
        words=voices.alignment_words(data)
        self.assertEqual([w['text'] for w in words],['Olá,','equipe!','Tudo','bem?'])
        self.assertAlmostEqual(words[0]['start_s'],.07*8)
        script=plan_intents({'provider':'elevenlabs','text':'Olá, equipe! Tudo bem?','words':words,'duration_s':4})
        self.assertTrue(all(e['timing_source']=='elevenlabs_word' for e in script['events']))

    def test_malformed_or_missing_alignment_is_rejected(self):
        for data in [None,{},dict(characters=['x'],character_start_times_seconds=[],character_end_times_seconds=[]),alignment('[whispers]')]:
            with self.assertRaises(ValueError):voices.alignment_words(data)
        data=alignment('Oi');data['character_start_times_seconds'][1]=float('nan')
        with self.assertRaises(ValueError):voices.alignment_words(data)

    def test_create_uses_timing_endpoint_and_single_request(self):
        response={'audio_base64':base64.b64encode(b'fixture MP3').decode(),'normalized_alignment':alignment('Oi!')}
        with patch.object(voices,'request_json',return_value=response) as request:
            audio,words,text=voices.create_speech('Oi!',voices.DEFAULT_VOICE,'eleven_v4','surprise')
        self.assertEqual(request.call_count,1)
        self.assertIn('/with-timestamps?',request.call_args.args[0])
        self.assertEqual(request.call_args.args[1]['language_code'],'pt')
        self.assertEqual(audio,b'fixture MP3');self.assertEqual(words[0]['text'],'Oi!')
        self.assertTrue(text.startswith('[surprised]'))

    def test_http_error_does_not_expose_upstream_body_or_key(self):
        secret='sk_private_key_fixture_not_real'
        error=urllib.error.HTTPError('https://api.elevenlabs.io',401,'bad',{},io.BytesIO(secret.encode()))
        with patch.object(voices.urllib.request,'urlopen',side_effect=error):
            with self.assertRaises(ValueError) as context:voices.request_json('/v2/voices',key=secret)
        self.assertNotIn(secret,str(context.exception));self.assertIn('401',str(context.exception))

    def test_missing_key_fails_before_network(self):
        with patch.object(voices,'api_key',return_value=''),patch.object(voices.urllib.request,'urlopen') as request:
            with self.assertRaises(ValueError):voices.request_json('/v2/voices')
        request.assert_not_called()

    def test_quota_reported_separately_from_invalid_key(self):
        body=json.dumps({'detail':{'status':'quota_exceeded','message':'not echoed'}}).encode()
        error=urllib.error.HTTPError('https://api.elevenlabs.io',401,'quota',{},io.BytesIO(body))
        with patch.object(voices.urllib.request,'urlopen',side_effect=error):
            with self.assertRaisesRegex(ValueError,'Créditos insuficientes'):voices.request_json('/v2/voices',key='sk_fixture_not_a_real_api_key')

    def test_old_models_reject_audio_tags_before_paid_request(self):
        with patch.object(voices,'request_json') as request:
            with self.assertRaises(ValueError):voices.create_speech('[whispers] Uma descoberta.',voices.DEFAULT_VOICE,'eleven_multilingual_v2')
        request.assert_not_called()

    def test_catalog_paginates_and_prioritizes_brazil(self):
        pages=[{'voices':[dict(voice_id='abcdefghij123',name='<script>remote</script>',labels={'accent':'American'})],'has_more':True,'next_page_token':'page2'},
               {'voices':[dict(voice_id='brasileiro123',name='Voz brasileira',labels={'accent':'Brazilian','language':'pt'})],'has_more':False}]
        with patch.object(voices,'request_json',side_effect=pages) as request:result=voices.voice_catalog()
        self.assertEqual(request.call_count,2);self.assertEqual(result['voices'][0]['name'],'Voz brasileira')
        self.assertEqual(result['locale'],'pt-BR')

    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg required for audio conversion')
    def test_real_mp3_conversion_and_metadata_with_mocked_provider(self):
        fixture=Path(__file__).resolve().parents[1]/'examples/edge_pt/speech.mp3'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);text=root/'text.txt';text.write_text('Uma descoberta.',encoding='utf-8')
            args=types.SimpleNamespace(text_file=text,out=root,voice=voices.DEFAULT_VOICE,model='eleven_v4',emotion='joy')
            with patch('scripts.synthesize_elevenlabs.create_speech',return_value=(fixture.read_bytes(),[dict(text='Uma',start_s=.2,duration_s=.3)],'[happy] Uma descoberta.')):
                synthesize(args)
            metadata=json.loads((root/'speech.json').read_text(encoding='utf-8'));wave=sf.info(root/'speech.wav')
            self.assertEqual(wave.samplerate,16000);self.assertEqual(wave.channels,1)
            self.assertEqual(metadata['locale'],'pt-BR');self.assertEqual(metadata['provider'],'elevenlabs')
            self.assertEqual(metadata['words'][0]['start_s'],.2)

    @unittest.skipUnless(os.name=='nt','Windows DPAPI')
    def test_windows_credential_round_trip_is_encrypted_and_not_returned(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(voices,'KEY_FILE',Path(directory)/'provider.key'):
            key='sk_fixture_api_key_not_a_real_credential_1234'
            voices.save_key(key)
            self.assertNotIn(key.encode(),voices.KEY_FILE.read_bytes())
            self.assertEqual(voices.api_key(),key)
            status=voices.provider_status();self.assertTrue(status['elevenlabs_configured'])
            self.assertNotIn(key,json.dumps(status))

    def test_invalid_voice_and_model_cannot_change_url(self):
        for voice,model in [('../injection','eleven_v4'),(voices.DEFAULT_VOICE,'other'),(None,'eleven_v4')]:
            with self.assertRaises(ValueError):voices.validate_voice(voice,model)

    def test_key_id_rejected_without_network_or_replacing_existing_key(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(voices,'KEY_FILE',Path(directory)/'provider.key'),patch.object(voices.urllib.request,'urlopen') as request:
            voices.KEY_FILE.write_bytes(b'previous encrypted credential')
            with self.assertRaisesRegex(ValueError,'ID da chave'):voices.save_key('api_key_id_not_a_secret_12345')
            self.assertEqual(voices.KEY_FILE.read_bytes(),b'previous encrypted credential')
            with self.assertRaisesRegex(ValueError,'ID da chave'):voices.request_json('/v1/models',key='api_key_id_not_a_secret_12345')
            request.assert_not_called()

    def test_status_flags_old_saved_key_id_without_exposing_it(self):
        with patch.object(voices,'api_key',return_value='api_key_id_not_a_secret_12345'):
            result=voices.provider_status()
        self.assertFalse(result['elevenlabs_configured']);self.assertIn('sk_',result['credential_error'])
        self.assertNotIn('api_key_id_not_a_secret_12345',json.dumps(result))

    def test_api_key_id_error_from_upstream_gets_actionable_message(self):
        body=json.dumps({'detail':{'status':'api_key_id_used_as_api_key','message':'not echoed'}}).encode()
        error=urllib.error.HTTPError('https://api.elevenlabs.io',400,'bad key',{},io.BytesIO(body))
        with patch.object(voices.urllib.request,'urlopen',side_effect=error):
            with self.assertRaisesRegex(ValueError,'ID da chave'):voices.request_json('/v1/models',key='sk_fixture_not_a_real_api_key')

    def test_pipeline_log_preserves_portuguese_with_cp1252_parent(self):
        from app.server import run_command,STOP
        previous=STOP.is_set();STOP.clear()
        try:
            with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'PYTHONIOENCODING':'cp1252'}):
                log=Path(directory)/'pipeline.log'
                run_command([sys.executable,'-c',"print('Solicitação inválida: copie a chave.')"],log)
                self.assertEqual(log.read_text(encoding='utf-8').strip(),'Solicitação inválida: copie a chave.')
        finally:
            if previous:STOP.set()
