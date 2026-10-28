# NAO Studio · interface local

## Preparação de um clone

Este repositório contém código, testes, documentação e exemplos pequenos em `examples/demo` e `examples/edge_pt`. O ambiente Python, repositório upstream e pesos em `runtime/` são locais e não são enviados ao GitHub. Histórico de falas, telemetria e vídeos gerados também ficam fora do Git.

Use Python 3.10 e crie `runtime/gesture-env` com `python -m venv runtime/gesture-env`. Nesse ambiente, instale primeiro PyTorch 2.6.0 pelo índice CUDA 12.4 oficial, depois `python -m pip install -r requirements-inference.txt`. Clone `https://github.com/haiyangliu0/character-policy.git` em `runtime/character-policy` e use a revisão `c4fe19d7fcbc5249106b62456d1b0d71cd7a3a6d`. Baixe os pesos com `python scripts/download_assets.py --out runtime/weights`; o modelo corporal necessário à inferência tem termos próprios, descritos em Referências e ativos.

Para Webots, instale R2025a e configure o Python do controlador com `scripts/prepare_webots.py` conforme a seção do ambiente abaixo. O arquivo `runtime.ini` é específico da máquina e não é versionado. A execução física usa o SDK da instalação local Choregraphe 2.8.7.4, conforme `app/sdk_bridge.py`.

Para verificar o código: `runtime/gesture-env/Scripts/python.exe -m unittest discover -s tests -q`.

## Usar a interface

Execute `powershell -ExecutionPolicy Bypass -File .\ABRIR_STUDIO.ps1` nesta pasta e abra **http://127.0.0.1:8766**. Mantenha o processo aberto enquanto usar a tela.

1. Escreva o texto e escolha Antonio ou Francisca.
2. Clique em **Gerar fala e gestos** e aguarde. A voz usa o serviço Edge TTS online; EMAGE e adaptação rodam localmente. Gerações são salvas separadamente em `app/data/jobs/`.
3. Ouça a fala e visualize os braços. **Testar no Webots** executa uma simulação e disponibiliza o vídeo na aba Webots.
4. **Executar no NAO** verifica o robô em `192.168.17.62:9561` e executa os oito motores dos braços e, no modo **Braços + cabeça**, os dois motores HeadYaw/HeadPitch. O robô deve estar em Stand/StandInit, com rigidez já ativada e bateria de pelo menos 20%. O app não levanta o robô nem envia movimentos físicos às pernas.
5. **Parar execução** solicita cancelamento dos movimentos dos braços e do áudio desta execução. Se a rede cair, uma parada remota não é garantida; o controle físico do robô continua sendo necessário.

As trajetórias físicas usam amplitude padrão de 100% da adaptação IK (com opções de 80%, 60% e 35%), com os gestos centralizados numa postura de braços à frente. A posição medida é usada na entrada e no retorno. A fala espera a confirmação de agendamento do movimento no ALMotion. Movimentos autônomos de fundo/escuta/fala são suspensos durante a execução e restaurados ao terminar.

**Gestos com intenção e mãos:** selecione **EMAGE + intenção + mãos naturais**. O texto e os tempos de palavras do Edge TTS são usados para selecionar saudações, explicação, alternativas, ênfases, perguntas e tamanho; expressões literais como “abrir a mão”/“fechar a mão” também são reconhecidas. Abra **Gestos previstos** para revisar as referências na fala. É uma primeira camada de regras em português, não compreensão livre por uma LLM. Frases sem uma intenção conhecida recebem um gesto explicativo discreto. “EMAGE sem direção” mantém a trajetória sem esta camada e não inclui mãos/punhos extras.

Com intenção, o executor passa a incluir LWristYaw, RWristYaw, LHand e RHand, além dos braços e da cabeça opcional. As mãos usam abertura normalizada de 0 a 1; não são ângulos em graus. Punhos/mãos inicialmente desenergizados são ativados gradualmente até rigidez mínima de 0,6 durante o gesto e retornam à configuração anterior ao terminar/parar. A postura inicial é mantida antes de energizar. As amplitudes de fechamento de fala ficam acima do fechamento total e não há gesto de agarrar objetos.

A direção preserva os braços do EMAGE e aplica acentos leves de até 12%, antes dos limites físicos. Punhos e abertura das mãos acompanham continuamente a postura e a atividade de cada braço; isso não depende de palavras sobre mãos e não é retargeting dos dedos do EMAGE. Os braços se alternam conforme o gesto, as mãos abrem/fecham suavemente e o olhar fica mais concentrado na direção frontal, com desvios breves. Não há rastreamento de pessoa/objeto nesta etapa. O Webots agora reproduz a seção de fala do mesmo plano selecionado, incluindo ritmo, amplitude, mãos e intenção. No modelo instalado, LHand/RHand são aproximados por oito motores de falanges em cada mão; a pose fechada está embutida no PROTO e +0,96 rad estende os dedos. Veja detalhes e limites em `app/DIRECAO.md`.

**Cabeça e inclinação:** o seletor **Movimento** oferece Somente braços, Braços + cabeça (padrão) e + Inclinação · Webots. A cabeça usa as rotações locais de pescoço/cabeça já produzidas pelo EMAGE, adaptadas aos eixos do NAO e suavizadas, com limites próprios de 0,45 rad/s e 1,5 rad/s². O plano começa e termina na pose medida. Se a cabeça estiver desenergizada, o worker mantém a pose medida e sobe gradualmente a rigidez apenas da cabeça até pelo menos 0,7, restaurando os valores anteriores ao fim, inclusive em falhas/parada. BasicAwareness, respiração e postura de repouso da cabeça também são restaurados.

O NAO não tem uma junta independente de cintura; a inclinação do corpo usa quadris/pernas. Nesta versão, o modo de inclinação faz um deslocamento pequeno e simétrico de HipPitch **somente no Webots**, com física ativa e sem fixar a base. O executor físico rejeita planos com juntas das pernas. A prévia simplificada mostra apenas braços; cabeça e inclinação aparecem no vídeo da aba Webots. Não é preciso gerar outra voz ou executar EMAGE novamente nas gerações que já têm o arquivo de movimento.

**Amplitude:** a opção padrão é **Origem EMAGE · 100%**, com alternativas de 80%, 60% e 35%. O percentual se refere às variações da adaptação IK para o NAO, recentradas na postura de gesticulação; limites articulares, de velocidade e aceleração podem reduzir o movimento. Não é uma cópia integral do esqueleto humano.

**Velocidade:** o seletor **Ritmo dos gestos** tem Suave, Natural (padrão) e Ágil. O perfil replaneja os gestos mantendo o relógio da fala, com limites físicos aplicados depois da amplitude: Suave 0,8 rad/s e 3,5 rad/s²; Natural 1,05 e 4,5; Ágil 1,2 e 5. Os perfis Natural/Ágil também encurtam preparação e retorno quando a distância permite. Não aceleram o áudio nem comprimem toda a trajetória. A prévia simplificada mostra os braços de origem; a aba Webots mostra o plano com as opções atuais, inclusive mãos e intenção.

Gerações antigas recuperam os alvos IK dos arquivos EMAGE/rest já salvos, num cache separado `execution_source.json`. Não é necessário gerar a voz ou executar EMAGE novamente. Se faltarem os arquivos originais, o planejador utiliza a trajetória suavizada disponível e registra `raw_targets_available=false`, com benefício de ritmo potencialmente menor. A conversão dos gestos para Bézier agora reproduz a spline nos nós originais com derivadas exatas e verifica os limites da curva final.

**Investigar trancos e pausas:** clique em **Comparar fluidez · A/B**. São dois arcos de braços conhecidos, sem EMAGE ou áudio: A preserva o modo padrão; B desativa temporariamente o Smart Stiffness para manter os valores de rigidez solicitados. Essa configuração é global no NAO e é restaurada ao fim do teste, inclusive em cancelamento/erro tratado. Os comandos de trajetória continuam limitados às oito juntas dos braços. O teste B exige sensores disponíveis sem alerta térmico. Não são alterados os reflexos de colisão, queda ou diagnóstico. Se o Smart Stiffness já estiver desligado, a comparação é recusada porque A e B seriam iguais.

O resultado compara pausas por junta e diferença comando/sensor. Eventos simultâneos podem aparecer em várias juntas; a contagem não é o número de pausas do robô inteiro. Não há conclusão automática sobre a causa ou confirmação de naturalidade. O seletor **Controle dos motores** também permite testar rigidez constante numa fala, mas permanece em **Padrão do NAO** por padrão.

**Validado:** geração, prévia, simulação/vídeo, conexões e execuções físicas anteriores iniciadas pelo usuário. A telemetria confirmou trechos em que os sensores pausam apesar do comando continuar, mesmo com erro RMS pequeno. A nova comparação A/B passou nos testes com serviços simulados e na interface; ainda aguarda execução física. Há 89 testes automatizados aprovados, incluindo restauração após falhas e cancelamento. Em 28/10/2026 o endpoint `192.168.17.62:9561` deixou de responder durante a validação de conexão, impedindo o ensaio A/B real.

A saída padrão da voz é o computador. **No NAO · experimental** envia PCM estéreo via ALAudioDevice; execuções anteriores completaram o envio sem erro do SDK, mas a qualidade auditiva não é medida pelo app. O volume global não é alterado.

Se editar o texto ou trocar a voz, gere novamente antes de executar. Falas curtas recebem silêncio no WAV para atender ao mínimo de entrada do EMAGE. Nesta interface, use até 60 segundos de áudio. O modelo ainda não garante significado correto dos gestos em português.

O servidor aceita somente loopback e usa um token de sessão nas ações. Não há hospedagem externa. Não exponha este servidor por túnel, proxy ou encaminhamento de porta. Os exemplos e a interface anterior continuam disponíveis em `RESULTADOS.html`.

---

# Adaptador e Webots

Adaptador local de movimentos para os oito motores dos braços do NAO V6.
Não usa ALAnimatedSpeech. Executa movimentos no **Webots**, sem conexão com o NAO físico.

## Conexão com o NAO físico

A conexão de diagnóstico foi confirmada em `tcp://192.168.17.62:9561`, com NAOqi **2.8.7.7**. `robot_connection.json` registra o endereço; `physical_robot_status.json` contém uma leitura de bateria, postura, ângulos e limites. O app também consulta esses valores ao atualizar a conexão. Os diagnósticos executados pelo agente foram somente leitura; a execução física foi iniciada pela interface, separadamente.

Para atualizar apenas as leituras, execute `runtime\gesture-env\Scripts\python.exe scripts/probe_nao.py`. O script utiliza o `qicli.exe` oficial da instalação do Choregraphe e uma lista fixa de métodos de leitura; não altera rigidez, postura ou Autonomous Life.

## Abrir e testar agora

Abra `RESULTADOS.html` para assistir à gravação com voz e consultar as medições. O projeto do Webots está em `webots/worlds/gesture_lab.wbt`.

No PowerShell, a partir desta pasta:

```powershell
powershell -ExecutionPolicy Bypass -File .\INICIAR_WEBOTS.ps1
powershell -ExecutionPolicy Bypass -File .\INICIAR_WEBOTS.ps1 -TesteRapido
powershell -ExecutionPolicy Bypass -File .\INICIAR_WEBOTS.ps1 -Gravar
powershell -ExecutionPolicy Bypass -File .\GERAR_FALA_E_GESTOS.ps1 -Texto "Olá! Agora podemos testar uma nova conversa." -Voz pt-BR-AntonioNeural
```

Sem opções, o Webots executa em tempo real e pausa ao terminar. Use **Reset Simulation** para repetir desde o início. Se estiver mudo no aplicativo, habilite o alto-falante na barra do Webots. `-TesteRapido` mede a física e fecha o simulador; `-Gravar` também produz o vídeo com voz, usando o relógio da simulação. Feche outra instância deste laboratório antes de iniciar uma nova execução automatizada.

O Edge TTS usa o serviço online da Microsoft: envia o texto informado e retorna MP3 e tempos por palavra. O FFmpeg instalado converte para WAV PCM mono 16 kHz. Voz alternativa: `pt-BR-FranciscaNeural` (a disponibilidade é verificada no serviço).

## O que está implementado

- Importação de posições de ombro/cotovelo/punho em JSON ou juntas SMPL-X em NPZ.
- Importação de rotações SMPL-X/EMAGE com o esqueleto de repouso correspondente.
- Cinemática dos braços com o deslocamento lateral do cotovelo.
- Cinemática inversa limitada por articulação e regularizada pela pose anterior.
- Otimização convexa das trajetórias com tempo preservado, limites de velocidade/aceleração e interpolação cúbica contínua.
- Exportação JSON/CSV e prévia HTML interativa independente de servidor.
- Script de inferência EMAGE com pesos locais e relatório de uso da GPU.
- Mundo Webots com NAO V6, física/auto-colisão, transições de entrada/saída, reprodução de áudio e telemetria dos oito motores.
- Edge TTS e vídeo com voz. A voz não altera o ritmo para acompanhar uma trajetória lenta.

## Executar o exemplo sem IA

No PowerShell, entre nesta pasta e execute:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m nao_gestures demo
```

Abra `examples/demo/preview.html`. O exemplo é **sintético**, gerado a partir de trajetórias conhecidas para verificar a conversão entre proporções corporais. Seu erro baixo não mede naturalidade nem qualidade de um modelo.

## Converter movimento externo

```powershell
python -m nao_gestures retarget origem.json --out examples/minha_previa
python -m nao_gestures retarget emage_motion.npz --rest-joints rest_joints.npy --out examples/minha_previa
```

JSON de entrada: `fps`, `source`, `coordinate_system="nao_torso_x_forward_y_left_z_up"` e `arms` com formato `[quadros,2,3,3]`: braço esquerdo/direito, ombro/cotovelo/punho, coordenadas XYZ em metros. Veja `examples/demo/source.json`.

JSON exportado v2: `angles_rad` contém **coeficientes de controle da curva** quando `interpolation=uniform_cubic_control_points`. Use `nao_gestures.trajectory.UniformCubic`, como o controlador Webots. Não trate os coeficientes como posições a interpolar por outro método. O CSV contém posições avaliadas nos instantes indicados. O modo antigo está disponível com `--timing stretch` para comparação.

NPZ: `poses[T,165]` em eixo-ângulo radianos ou `joints[T,J>=22,3]` na ordem SMPL-X; `mocap_frame_rate` escalar, padrão 30. Para `poses`, forneça `rest_joints.npy[J>=22,3]` consistente com a forma corporal usada na geração. O script EMAGE usa forma neutra (betas zero) e pode extrair as juntas do modelo neutro correspondente. A importação remove orientação global e movimento do tronco usando uma base anatômica. Não importa animação facial, dedos, pernas ou translação.

## EMAGE nesta máquina

O ambiente de pesquisa **isolado dos pacotes globais** está em `runtime/gesture-env`. O código de terceiros está em `runtime/character-policy`, revisão `c4fe19d7fcbc5249106b62456d1b0d71cd7a3a6d`. Pesos e ativos grandes ficam em `runtime/weights`, dentro do projeto. Revisões dos ativos são registradas em `manifest.json`. `environment-local.txt` registra o ambiente completo; `pip check` foi executado sem conflitos.

Da pasta deste projeto:

```powershell
$pythonGesture = 'runtime\gesture-env\Scripts\python.exe'
& $pythonGesture scripts/infer_emage.py --repo runtime\character-policy --weights runtime\weights\emage --audio examples\fala_pt.wav --rest-model runtime\weights\evaltools\smplx_models\smplx\SMPLX_NEUTRAL_2020.npz --out examples\emage_pt
& $pythonGesture -m nao_gestures retarget examples\emage_pt\emage_motion.npz --rest-joints examples\emage_pt\rest_joints.npy --out examples\emage_pt
```

Não instalamos a cadeia completa de renderização do repositório: usamos apenas suas classes de inferência e nossa visualização reduzida. O script foi baseado na assinatura real do código da revisão acima; alguns exemplos do AGENTS.md upstream divergem dessa assinatura.

Para recriar, use Python 3.10 em ambiente virtual, instale primeiro PyTorch 2.6.0 com CUDA 12.4 pelo índice oficial e depois `pip install -r requirements-inference.txt`. O downloader público é `scripts/download_assets.py --out DIRETORIO --include-rest-model`. `scripts/prepare_webots.py --source PASTA_DOS_PROTOS --python PYTHON_DO_AMBIENTE` copia os ativos do simulador e configura o interpretador por controlador; não altera as preferências globais de Python do Webots.

## Limites atuais e próxima etapa

O HTML de comparação é cinemático. Já o Webots executa o modelo físico instalado, registra rastreamento dos motores, altura/inclinação da base e contatos. Auto-colisão está ativada, mas contagem de contatos não certifica ausência de colisões indesejadas. A base não é fixada nem reposicionada durante a execução. Não valida torque, temperatura ou desempenho do robô físico.

O modo padrão preserva a duração e aceita alguma perda de fidelidade para limitar a velocidade a 1,2 rad/s e a aceleração a 5 rad/s²; são escolhas conservadoras do projeto, não limites máximos oficiais. A curva cúbica tem seus limites verificados entre quadros por testes e na amostragem de 12 ms do Webots. O modo antigo `stretch` desacelera e sinaliza perda de sincronização. O vídeo final é sincronizado no relógio da simulação; áudio ao vivo pode divergir se o Webots não acompanhar o tempo real.

O controlador inclui transições suaves a partir da postura inicial e retorno ao repouso. A interface integra braços, cabeça, mãos, cancelamento e execução NAOqi. Ainda faltam integração de fala em fluxo e visão para acompanhamento de pessoas. Não há LoRA nem treinamento nesta etapa. O EMAGE foi treinado em inglês: executar português não comprova adequação semântica ou naturalidade.

Os exemplos originais em `C:\Users\eduardo\nao_v6_webots` foram preservados. Os PROTOs foram copiados para este projeto. Como o Webots exige que a faixa do motor inclua zero, os limites físicos mais estreitos dos cotovelos são aplicados pelo controlador. A origem dos ativos e os ajustes estão em `webots/assets_manifest.json`.

## Referências e ativos

- [Código EMAGE/PantoMatrix](https://github.com/haiyangliu0/character-policy).
- [Pesos EMAGE](https://huggingface.co/haiyangliu0/emage_audio).
- [Ativos de avaliação](https://huggingface.co/haiyangliu0/emage_evaltools).
- [SMPL-X: licença própria dos ativos corporais](https://smpl-x.is.tue.mpg.de/modellicense.html). Os pesos e o modelo corporal completo ficam no runtime local, ignorado pelo Git; disponibilização pública não elimina suas condições.
- [Documentação Aldebaran: juntas](https://fileadmin.cs.lth.se/robot/nao/doc/family/robots/joints_robot.html) e [segmentos](https://fileadmin.cs.lth.se/robot/nao/doc/family/robots/links_robot.html).
- [Ficha NAO V6 do fabricante](https://cdn.robotshop.com/media/A/Ald/RB-Ald-18/pdf/nao-6-humanoid-robot-datasheet.pdf).
- [Exemplo de adaptação geométrica de gestos ao NAO](https://arxiv.org/html/2609.13876v1#S4.SS4).


Projeto transferido para `C:\Users\eduardo\Juino\nao-gestures`. O Python isolado, repositório EMAGE e pesos ficam em `runtime/`. Para instalar pacotes, use `runtime\gesture-env\Scripts\python.exe -m pip` (launchers pip.exe do ambiente transferido podem conter o caminho antigo). O Studio usa esses caminhos internos.
