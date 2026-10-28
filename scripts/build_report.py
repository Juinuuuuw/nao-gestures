"""Build a portable local result page from measured output, not fabricated metrics."""
import html
import json
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[1]
    load=lambda path:json.loads((root/path).read_text(encoding='utf-8'))
    motion=load('examples/edge_pt/report.json')
    inference=load('examples/edge_pt/inference_report.json')
    speech=load('examples/edge_pt/speech.json')
    simulation=load('webots/results/edge_pt/simulation_report.json')
    page='''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NAO V6 · Laboratório de gestos</title>
<style>*{box-sizing:border-box}body{margin:0;background:#0b1420;color:#e6edf5;font:16px system-ui;line-height:1.6}main{max-width:1060px;margin:auto;padding:32px}h1{font-size:34px;line-height:1.2}h2{font-size:21px;margin-top:30px}p{color:#b4c4d5}small{color:#83e4ce}video{width:100%;border-radius:14px;background:#142336;border:1px solid #294056}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.cards div,section{background:#132235;border:1px solid #294056;border-radius:10px;padding:18px}.cards strong{display:block;font-size:25px}.cards span{font-size:13px;color:#b4c4d5}a{color:#83e4ce}table{width:100%;border-collapse:collapse}td,th{padding:12px;text-align:left;border-bottom:1px solid #294056}pre{background:#08111b;padding:16px;overflow:auto;border-radius:8px;font-size:13px}.links{display:flex;gap:20px;flex-wrap:wrap}.note{color:#ffd28d}@media(max-width:650px){main{padding:18px}.cards{grid-template-columns:1fr 1fr}h1{font-size:28px}}</style>
<main><small>PROTÓTIPO 02 · TESTADO NO WEBOTS R2025a</small><h1>NAO V6 · fala e expressão corporal</h1><p>Edge TTS em português → EMAGE na RTX 3060 → adaptação corporal com tempo preservado → execução física no simulador.</p>
<video controls preload="metadata" poster="webots/results/edge_pt/final.png"><source src="webots/results/edge_pt/demonstracao_com_voz.mp4" type="video/mp4">Seu navegador não suporta vídeo.</video>
<p>Gravação real da simulação. A voz foi colocada sobre os quadros no tempo da simulação, sem esticar áudio ou movimento. Em execução ao vivo, a carga do simulador pode causar atraso em relação ao relógio real.</p>
<div class="cards"><div><strong>__DURATION__ s</strong><span>duração do gesto</span></div><div><strong>__INFERENCE__ s</strong><span>inferência do EMAGE</span></div><div><strong>__TRACKING__°</strong><span>erro RMS dos motores</span></div><div><strong>__FALL__</strong><span>queda detectada neste teste</span></div></div>
<section><h2>O que mudou</h2><table><thead><tr><th>Parte</th><th>Resultado</th></tr></thead><tbody><tr><td>Continuidade</td><td>Otimização com limites de velocidade/aceleração e curva cúbica contínua.</td></tr><tr><td>Sincronização</td><td>Duração preservada. O teste original de 17,7 s antes durava 94,9 s; agora dura 17,7 s.</td></tr><tr><td>Voz</td><td>__VOICE__, com marcações de tempo por palavra.</td></tr><tr><td>Física</td><td>Auto-colisão ativada, base livre e motores com sensores. Sem fixação artificial do robô.</td></tr><tr><td>Ambiente</td><td>Projeto Webots separado, Python isolado, comandos de geração/teste/gravação e telemetria CSV.</td></tr></tbody></table></section>
<h2>Fala usada no teste</h2><p>__TEXT__</p><h2>Arquivos para explorar</h2><div class="links"><a href="examples/edge_pt/preview.html">Comparar movimento humano e NAO</a><a href="webots/results/edge_pt/simulation_report.json">Relatório do Webots</a><a href="webots/results/edge_pt/telemetry.csv">Telemetria</a><a href="README.md">Instruções</a></div>
<h2>Usar nesta máquina</h2><pre>powershell -ExecutionPolicy Bypass -File .\\INICIAR_WEBOTS.ps1
powershell -ExecutionPolicy Bypass -File .\\INICIAR_WEBOTS.ps1 -TesteRapido
powershell -ExecutionPolicy Bypass -File .\\INICIAR_WEBOTS.ps1 -Gravar
powershell -ExecutionPolicy Bypass -File .\\GERAR_FALA_E_GESTOS.ps1 -Texto "Olá! Vamos conversar."</pre>
<p class="note">O teste valida este modelo e esta sequência no simulador. Ainda faltam avaliação humana de naturalidade, integração de olhar/cabeça, interrupções, conversa ao vivo e validação no NAO físico. Gestos rítmicos não garantem correspondência semântica com cada palavra.</p></main></html>'''
    replacements={'__DURATION__':f"{motion['output_duration_s']:.2f}",'__INFERENCE__':f"{inference['inference_s']:.2f}",'__TRACKING__':f"{simulation['arm_tracking_rms_deg']:.2f}",'__FALL__':'Não' if not simulation['fall_detected'] else 'Sim','__VOICE__':html.escape(speech['voice']),'__TEXT__':html.escape(speech['text'])}
    for a,b in replacements.items():page=page.replace(a,b)
    (root/'RESULTADOS.html').write_text(page,encoding='utf-8')
    print(root/'RESULTADOS.html')

if __name__=='__main__':main()
