# NAO Studio — validação em 27/10/2026

- Interface local em http://127.0.0.1:8766, com servidor vinculado somente ao loopback.
- Geração de uma frase nova pelo navegador: Edge TTS, EMAGE, adaptação e prévia, sem erros JavaScript.
- Teste no Webots iniciado pela interface; vídeo de aproximadamente 8,9 segundos retornado para a aba Webots e relatório aprovado.
- Frase curta "Olá!" gerada com WAV estendido por silêncio a 3,2 segundos para o EMAGE.
- Edição de texto ou voz bloqueia executar/simular até regenerar; escolha da geração persiste após recarregar.
- Layout verificado em 1380 e 390 pixels, sem transbordamento horizontal.
- Requisição de execução sem token de sessão rejeitada; nenhum comando físico foi enviado pelos testes automatizados de navegador.
- Quinze testes automatizados aprovados: adaptador, interpolação contínua, plano físico de braços e pré-condições de diagnóstico/execução com serviços simulados.
- SDK Python 2.7 instalado com Choregraphe validado por diagnóstico real, incluindo formato WAV, limites e rigidez, sem movimentos.
- Uma execução dos braços iniciada pela interface terminou com `phase=complete`, usando voz no computador. O registro correspondente está em `app/data/jobs/run_16e2b4e3cb144d8d96a4671008550bdb/run.log`.

A execução física acima é confirmação do NAOqi, não medição externa de precisão, colisões ou naturalidade. Áudio no alto-falante do NAO ainda não foi validado em reprodução; a opção permanece experimental. A cabeça não é animada pelo app.

## Correção após avaliação no robô

O usuário relatou movimentos pequenos e aparência de rigidez na versão inicial. O retorno `complete` do SDK não comprova naturalidade. O plano anterior misturava 35% da trajetória com 65% da postura inicial, mantendo os braços próximos ao corpo.

O planejador v2 centraliza os gestos numa postura de braços à frente, usa amplitude padrão de 60% e preserva entradas/saídas quinticas e interpolação Bézier. A interface permite selecionar 35% ou 60%; o percentual afeta somente a execução física, não a prévia original nem o teste Webots existente. A rigidez dos motores e as proteções de colisão não foram alteradas.

Validação: 18 testes passaram, incluindo independência da postura inicial, limites das tangentes, velocidade menor que 0,9 rad/s e aceleração menor que 5 rad/s² na trajetória de demonstração. Pré-condições verificadas com o SDK real em modo `--check`, sem comandos de movimento. A naturalidade física desta revisão ainda depende de nova observação.

Cada nova execução salva `telemetry.jsonl` junto do `plan.json` e `run.log` em `app/data/jobs/run_*`, com ângulos planejados, comandos informados pelo ALMotion e sensores a aproximadamente 10 Hz. O resumo RMS mede diferença plano/sensor, incluindo atrasos; não identifica sozinho a causa de uma limitação.

## Investigação da execução run_75e0ee7b23584ed2816b258e860bbc41

A execução do usuário registrou variações reais de 22,6° e 32,4° em ShoulderPitch, mas apenas 4,2° e 10,1° em ShoulderRoll. Diferenças RMS entre comando ALMotion e sensor ficaram entre 1,1° e 3,1° nas oito juntas. A comparação do plano com os comandos mostrou defasagem de aproximadamente 1,2 s; portanto o RMS plano/sensor de 11,1° misturava atraso de relógio com erro de execução. A evidência não indica motores completamente imobilizados.

O executor passou a aguardar uma nova tarefa angleInterpolationBezier no agendador ALMotion antes de iniciar o relógio da fala; a confirmação e seu atraso ficam no run.log. Essa aproximação reduz a incerteza de envio, mas ainda depende de validação na próxima execução física. O resumo na interface agora usa diferença comando/sensor, com o erro plano/sensor preservado nos registros.

Foi acrescentado o botão Testar braços · sem fala: cinco poses Bézier, arcos simétricos de ombro de 40,1°, duração nominal 8,84 s, sem EMAGE ou áudio. Mantém a rigidez, as proteções e as pernas/cabeça; entra e retorna à postura inicial. A duração de entrada/saída cresce para posturas mais afastadas, respeitando limites de 0,7 rad/s e 2 rad/s².

Vinte e um testes passaram, incluindo cancelamento e confirmação do agendamento antes do relógio de áudio, amplitude e derivadas do diagnóstico. A interface, conexão e bloqueio de POST sem token foram verificados. O plano diagnóstico passou nas pré-condições do SDK físico em --check, sem envio de movimento. O novo arco físico e a nova sincronização ainda aguardam execução pelo operador.

## Comparação de rigidez em 28/10/2026

O usuário esclareceu que o problema são trancos e pausas. A nova análise identifica intervalos de sensor quase parado (faixa menor que 0,15°, duração mínima 0,20 s) enquanto o comando percorre pelo menos 0,8°. Lacunas acima de 0,3 s não são interpretadas como pausas; pausas planejadas sem deslocamento de comando são excluídas. A leitura nova agrupa posições, rigidez efetiva, corrente e temperatura numa chamada ALMemory.getListData, usando Device/SubDeviceList. A leitura anterior getStiffnesses representava rigidez solicitada, não o valor efetivo enviado ao atuador.

Em leitura real parada, Smart Stiffness estava ligado e rigidez solicitada era 1,0, com Hardness/Actuator aproximadamente 0,31–0,42. Temperaturas dos braços estavam em 38–42°C e os estados térmicos eram zero. Isso confirma atuação da gestão de rigidez, sem confirmar sua relação com os trancos. A documentação descreve a ativação em postura estática e prioridade dos comandos durante movimento: [Smart Stiffness, documentação Aldebaran](https://fileadmin.cs.lth.se/robot/nao/doc/naoqi/motion/reflexes-smart-stiffness.html).

A interface agora oferece Comparar fluidez · A/B: trajetória diagnóstica com modo padrão e depois com Smart Stiffness temporariamente desativado, retornando ao estado anterior. Não muda valores solicitados de rigidez ou proteções de colisão/queda/diagnóstico. O modo constante é experimental e não foi ativado como padrão. O resumo por junta é salvo em quality.json e quality_summary.json; dados brutos incluem hardness, current_a, temperature_c e temperature_status.

Validação local: 45 testes aprovados, incluindo modos/flags A/B, ausência de áudio, relatório, STOP antes de B, falhas de diretório/log e fechamento da telemetria, cancelamento de tarefa ativa e restauração. Sucesso/parada só são emitidos após cleanup. O servidor mantém a operação ocupada até o worker encerrar. Importação/argumentos do worker foram verificados no SDK Python 2.7 instalado. O layout de 390 px e as requisições da interface foram verificados com POSTs físicos interceptados.

A comparação A/B NÃO foi executada no hardware: o diagnóstico de leitura expirou em 15 s e a conexão TCP à porta 9561 não respondeu. Requer reconexão do NAO e execução pelo operador para comparar pausas e observação visual. Nenhum teste automatizado desta revisão enviou movimento físico.

## Ritmo e correção de amostragem em 28/10/2026

Implementado planejador físico v4 com perfis Suave/Natural/Ágil. A escala de amplitude é aplicada aos alvos IK brutos antes da otimização de velocidade e aceleração, eliminando a redução dupla do limite de velocidade. A duração da seção de fala permanece fixa. Entrada e retorno quinticos têm duração calculada por distância, velocidade e aceleração; mínimos de 2 s / 1 s / 0,8 s conforme perfil. A conversão usa nós originais e derivadas exatas da B-spline, seguida de verificação das derivadas e posições da Bézier final.

Na mesma geração 0d1250790ad94444aa0d607f3f461e8e, fala de 7,967 s: média angular planejada anterior 11,29°/s; Natural 14,30°/s (+26,7%); Ágil 15,87°/s (+40,6%). Picos anteriores 41,26°/s; Natural 59,86°/s; Ágil 68,41°/s. Duração total caiu de 12,404 s para 11,009 s e 10,696 s, reduzindo transições sem comprimir a fala. Valores são offline e agregados nas oito juntas; não são medições de velocidade física. Detalhes em RELATORIO_RITMO.json.

Teste Webots do perfil Ágil: amostragem do plano físico completo a 120 Hz e reprodução cúbica, com pequena suavização adicional. Relatório fresco em webots/results/pace_brisk/simulation_report.json aprovado: sem queda, RMS de rastreamento 2,058°, máximo 6,762°, inclinação máxima 0,053°, velocidade alvo 1,194 rad/s, aceleração 4,975 rad/s². Teste mudo, em modo rápido; não valida latência ou sincronia de áudio físico. O teste Webots comum da interface ainda reproduz a trajetória original, não o perfil físico selecionado.

Correção de medição: as posições espelhadas por ALMemory nos registros recentes atualizavam apenas a cada 0,34–0,38 s, criando patamares artificiais. Essas repetições não comprovam pausas mecânicas. A telemetria agora sempre usa ALMotion.getAngles para posições/comandos, com position_source explícito; ALMemory fornece apenas metadados de rigidez, corrente e temperatura em frequência menor. Ver TELEMETRIA.md. A causa dos trancos visuais continua em avaliação, sem atribuição automática ao Smart Stiffness.

Validação final: 62 testes automatizados passaram; interface validada em 390 px, seletor de ritmo encaminhado ao backend e persistido após recarregar, sem erros JavaScript. POSTs físicos foram interceptados no teste de navegador. O endpoint físico ainda não respondeu na verificação TCP; os novos perfis não foram executados pelo agente no hardware.

## Cabeça e inclinação em 28/10/2026

Implementado planejador v5: oito juntas de braços e, opcionalmente, HeadYaw/HeadPitch. Origem das rotações: EMAGE neck(12) * head(15), relativas à parte superior da coluna, convertidas pela base anatômica do esqueleto de repouso. Inclinação simulada deriva de spine1(3) * spine2(6) * spine3(9), com root removido. A cabeça fica limitada em sua variação, suavizada com velocidade 0,45 rad/s e aceleração 1,5 rad/s²; o executor verifica também o envelope acoplado yaw/pitch.

Cabeça: a leitura real confirmou limites e disponibilidade das APIs de respiração, postura de repouso e BasicAwareness. A rigidez inicial da cabeça era zero. Foi implementada ativação gradual da cabeça, com pose medida mantida antes de energizar e restauração ao terminar. Os testes simulados cobrem sucesso, STOP e falha de telemetria nessa restauração. Nenhum comando às pernas é aceito pelo executor físico.

Inclinação: suporte somente no Webots, por offset simétrico e pequeno de HipPitch. Não há um motor independente de tronco no NAO; referência: [datasheet Aldebaran NAO V6, posição dos motores](https://cdn.robotshop.com/media/A/Ald/RB-Ald-18/pdf/nao-6-humanoid-robot-datasheet.pdf). Não foi habilitado envio físico de inclinação ou modificação de restrições de equilíbrio.

Teste real de simulação pela API com body_mode=torso na geração 0d125...: checks_passed=true, sem queda, cabeça com variação de 24,95° yaw e 9,07° pitch, RMS de rastreamento da cabeça 0,903°, máximo 2,553°. Offset de quadril máximo 1,204° e inclinação da base máxima 1,240°. RMS dos braços 2,576°. Vídeo com voz gerado em app/data/jobs/0d1250790ad94444aa0d607f3f461e8e/simulation/simulation.mp4 e disponibilizado na aba Webots. A captura e o áudio foram combinados pelo relógio da simulação; não medem a latência física de áudio.

Setenta e um testes passaram. Interface verificada em 390 px, seleção persistente e envio de modos correto; execução física de inclinação fica bloqueada na interface e no backend. POSTs físicos da validação de interface foram interceptados.

A tentativa de pré-condições no SDK físico foi recusada porque o NAO estava em Crouch com rigidez dos braços zero. Nenhum movimento físico de cabeça nem ativação de rigidez foi enviado pelo agente. A nova cabeça deve ser observada no hardware com o robô em Stand/StandInit e braços já energizados.

## Intenção, punhos e mãos em 28/10/2026

Planejador v6: direção baseada em vocabulário de intenções em português e referências WordBoundary do Edge TTS, com EMAGE mantido como base. Inclui quatro motores opcionais LWristYaw/RWristYaw/LHand/RHand, totalizando 14 juntas no modo com cabeça. Mãos em abertura normalizada e estatísticas próprias, sem misturar frações com graus. Restauração de rigidez de punhos/mãos coberta em sucesso, STOP, falha de entrada e falha de restauração.

Pipeline completo executado pela API: nova voz Edge, inferência EMAGE, adaptação, seleção de eventos, Webots, captura e mux do áudio. Geração 2789fd832f8748b3a9cd1aba3fbac0d1, fala de aproximadamente 7,83 s, referências “Olá” 0,34 s, “abrir” 2,29 s, “fechar” 4,57 s e pergunta 6,80 s.

A primeira revisão visual encontrou inversão na aproximação das falanges. Foi corrigida usando a rotação inicial do PROTO, e o vídeo foi refeito e inspecionado em abrir/fechar. As configurações .wbproj agora são copiadas para cada mundo de teste, removendo o overlay preto de câmera. Após correção, relatório checks_passed=true, sem queda, amplitude medida de abertura aproximadamente 0,753 em ambas as mãos, RMS das mãos 0,0428 (4,28 pontos percentuais), RMS da cabeça 0,440° e dos braços 1,751°. É validação desse modelo e frase, sem certificação de colisão física ou de naturalidade.

Oitenta e sete testes passaram. Interface validada no desktop e em 390 px: eventos previstos, chave de intenção, desativação, parâmetros do simulador, bloqueio em Crouch e ausência de erros JavaScript. POSTs físicos de QA foram interceptados.

Leituras reais confirmaram os quatro atuadores extras, seus limites, posição e sensores térmicos sem alerta; rigidez inicial de punhos/mãos era zero. O SDK em --check recusou o teste porque a postura era Crouch, antes de qualquer comando de movimento/rigidez. Nenhum novo gesto físico de mãos foi enviado pelo agente. A observação no NAO continua pendente com o robô em Stand/StandInit.


## Mais movimento de origem e mãos contínuas — 28/10/2026

Planejador v7: amplitude padrão de 100% da variação IK (opções 80/60/35%), preservando a postura central de gesticulação e limites anteriores de posição/velocidade/aceleração. Na direção, o peso máximo de poses de intenção caiu de 62% para 12%; eliminada a contenção de 35% do braço passivo. Comandos literais de mão não substituem os braços.

Abertura e punhos agora seguem continuamente apresentação, extensão e atividade de cada braço, com filtro temporal e otimização de limites; não requerem menções a mãos e não são dedos gerados pelo EMAGE. Comandos literais continuam opcionais e prioritários.

89 testes passaram, incluindo preservação do braço passivo, variação manual sem eventos e amplitude de 100% dentro das derivadas permitidas. QA de interface confirmou padrão 100%, envio à API, alternância de modo, mobile sem overflow e bloqueio em Crouch; POSTs de motores interceptados. Nenhum novo movimento físico foi disparado nesta atualização.

Mesma fala recente (geração 578c8d8843c145da9609d0e324590614), sem abrir/fechar no texto: amplitude articular média dos oito braços antes 37.57°, agora 55.56° no perfil Ágil. Essa média de amplitudes por junta não mede naturalidade. A margem articular reduziu automaticamente o ganho efetivo para 0.854. Webots: checks_passed=True, sem queda, RMS braços 2.86°, cabeça 0.53°, mãos 2.09 pontos percentuais. Variação medida das mãos 31.5/43.4 pontos. A validação física anterior tinha erro de motores aproximadamente 1,88°; a nova versão ainda precisa ser experimentada pelo operador no robô.


## Emoções selecionáveis — 28/10/2026

Perfis autorais para Alegria, Tristeza, Medo, Raiva, Nojo e Surpresa, mais Neutra compatível com gerações antigas. A chave é validada na API, salva no job e usada na prosódia Edge TTS e no planejador v8. O texto falado permanece intacto; não há LLM de reescrita. Roteiro escrito separado com [Emoção Selecionada]/[Fala e Gestos] e referências WordBoundary. Corpo completo exige braços/cabeça e modo com mãos.

99 testes passaram: seis perfis + neutro, distinção das trajetórias, preservação da duração/limites, pontuação temporal, rejeição de chaves inválidas, snapshot de LEDs, restauração após falha e caminho completo do worker em sucesso/STOP/erro de restauração sem omitir cabeça/comportamentos. Worker importou normalmente com o SDK Python 2 local.

QA em Edge isolado: sete entradas de menu, seis payloads, bloqueio de executar/simular ao alterar emoção, roteiro, viewport de 390 px sem overflow e ausência de erros JS. Requisições de motores foram interceptadas.

Geração real f2724f19224444a7ae19c87e411e3e58: Francisca + Surpresa (+10%, +16 Hz), 5,232 s. Pipeline Edge TTS/EMAGE/retarget concluído e Webots aprovado, sem queda: braços 2,649° RMS, cabeça 0,299° RMS, mãos 2,14 pontos percentuais de abertura. Vídeo inspecionado com olhos iluminados e gestos. Não mede percepção humana da emoção.

Consulta física somente leitura confirmou ALLeds.listGroup(FaceLeds) com 48 canais e formato numérico de getIntensity em um canal. Nenhum comando novo de motor/LED foi enviado ao NAO por esta validação; a execução física emocional ainda aguarda ensaio do operador.


## ElevenLabs e português brasileiro — 28/10/2026

Integração HTTP com o endpoint oficial de áudio + tempos por caractere. Seletor Edge TTS/ElevenLabs, Voice ID inicial informado pelo operador, modelos v4/v3/Multilingual v2/Flash v2.5 e catálogo paginado da conta. O padrão v4 usa language_code=pt; o alvo da interface é pt-BR e o sotaque depende da voz. Multilingual v2 omite language_code, conforme documentação. V4/v3 recebem tags emocionais; os demais mantêm a direção corporal.

Chave local protegida por Windows DPAPI ou variável ELEVENLABS_API_KEY. Não é retornada pela API de estado, gravada nos jobs, incluída nos argumentos de processos ou armazenada pelo app no navegador. Não há fallback/repetição automática de solicitações pagas. Respostas HTTP são traduzidas sem eco de corpos ou cabeçalhos; quota pode ser distinguida de chave inválida.

111 testes passaram, incluindo DPAPI real no Windows, catálogo paginado, requisição de síntese única, pt/modelos, remoção de tags do alinhamento preservando tempos, rejeição de alinhamento inválido, falhas HTTP sem vazamento e conversão real do MP3 de fixture para WAV mono de 16 kHz com chamada ElevenLabs simulada. A fixture é áudio Edge existente, não uma alegação de síntese ElevenLabs real.

QA isolado em Edge: seleção de serviço, bloqueio sem chave, carregamento de vozes simulado, Voice ID manual, payload de modelo/emoção, limpeza do campo de chave, nomes de voz não executam HTML/JS e mobile 390 px sem overflow. Regressão dos seis perfis emocionais aprovada. Rotas de robô e escritas de chave foram interceptadas. API local real recusou geração sem chave e Voice ID inválido antes de criar job.

Não havia chave de API configurada. Nenhuma síntese real ElevenLabs nem cobrança foi feita, e nenhum comando físico foi enviado ao NAO. A confirmação com a conta depende de cadastrar chave válida no painel local; acesso ao Voice ID informado permanece não confirmado.


### Correção de autenticação e acentos — 28/10/2026

A geração 5e0445be6a814d73928ddd7f27ecfcc3 falhou com HTTP 400 genérico. Uma consulta somente leitura a /v1/models revelou detail.status=api_key_id_used_as_api_key: foi usado o ID, não o segredo sk_. Nenhuma síntese foi repetida. Foram adicionados bloqueio local de Key IDs, tradução desse erro da API, estado de credencial inválida e orientação no formulário. A chave cifrada anterior permanece para ser substituída pelo operador; não foi exposta em logs/saídas de diagnóstico. O erro exibido no histórico recebeu a causa confirmada, preservando o log original.

O subprocesso usava saída CP1252 e o log era lido como UTF-8. run_command agora força PYTHONIOENCODING=utf-8 e PYTHONUTF8=1 apenas no ambiente filho. 115 testes passaram, incluindo Key ID sem rede/substituição de credencial, erro HTTP correspondente e regressão de mensagem portuguesa sob ambiente pai CP1252. A confirmação da voz/modelo continua pendente de chave secreta válida.


## Expressão corporal v9 e retenção dos olhos — 28/10/2026

Os registros anteriores confirmavam a cor de Raiva e a emoção selecionada, mas a escrita única permitia interferência do controle autônomo. Pausar apenas a piscada ou renovar ALLeds sem reservar os recursos não bastou no teste físico. A correção reserva apenas Left eye leds/Right eye leds com um proprietário temporário e libera ambos em encerramento/STOP/erro. AutonomousBlinking é salvo, suspenso e restaurado. A cor é renovada a 2 Hz, com fade curto, sem alterar LEDs de peito/orelhas ou reflexos.

Teste físico exclusivamente de LEDs: três amostras de 48 canais durante aproximadamente 3 s, erro máximo do alvo inferior a 0,000001, recursos liberados e piscada restaurada. Não foram enviadas trajetórias aos motores. O instantâneo anterior é reenviado, mas sua reprodução RGB exata não foi confirmada no ensaio; o controle autônomo retoma suas animações após a liberação.

Perfis v9 sustentam posturas distintas ao longo da fala, com acentos ancorados em palavras reais e preservação do EMAGE. Sobre um mesmo áudio de 23,4 s, diferenças RMS dos braços frente ao neutro: Alegria 4,81°, Tristeza 7,74°, Medo 8,11°, Raiva 4,80°, Nojo 4,93°, Surpresa 6,22°. Esses valores demonstram diferença planejada, não reconhecimento humano de emoção.

123 testes aprovados, incluindo manutenção e falha de cor, retorno da piscada inicialmente desabilitada, reserva/liberação dos dois recursos e restauração no fluxo completo do executor. QA da interface passou nas seis opções e em mobile; requisições de motores interceptadas. A aba de origem foi renomeada para Origem EMAGE para distingui-la do plano emocional no Webots.

Simulação da geração e74dee1d1feb4fad8c295dc96086835d, Raiva com braços/cabeça/mãos: checks_passed=true, sem queda, RMS braços 2,346°, cabeça 0,281°, mãos 2,335 pontos percentuais. Áudio existente reutilizado, sem nova chamada paga à ElevenLabs. A nova trajetória corporal ainda precisa de ensaio pelo operador no NAO físico.
