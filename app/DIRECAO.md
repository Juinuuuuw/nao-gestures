# Direção inicial de gestos em português

O sistema combina uma proposta EMAGE com um vocabulário de intenções e tempos de palavras do Edge TTS. Não usa LLM adicional nem exige treinar um modelo. É uma camada determinística e auditável, com cobertura limitada; não identifica intenção geral, ironia, objetos ou destinatários.

Intenções reconhecidas: saudação, explicação genérica, alternativas (lados alternados), ênfase, pergunta, expansão/tamanho pequeno e abrir/fechar a mão. A seleção limita a densidade e prioriza comandos literais. Negação próxima e o idioma “abrir mão de” são tratados para evitar alguns falsos comandos; isso não substitui análise linguística completa. Veja os eventos e referências temporais em Gestos previstos.

Cada evento tem preparação, pequeno tempo de sustentação e recuperação. Os braços preservam o EMAGE: os acentos de intenção têm peso máximo de 12%, sem imobilizar o braço do outro lado. Comandos explícitos de mãos não substituem os braços. Punhos e mãos recebem movimento contínuo derivado da extensão, apresentação e atividade de cada braço, filtrado para remover variações rápidas do IK; não há oscilação aleatória nem dependência de palavras específicas. Não usa diretamente os dedos do EMAGE. Eventos genéricos acrescentam 35% de acento à abertura de fundo; comandos explícitos de abrir/fechar continuam prioritários. A cabeça usa menos movimento contínuo de fundo, com pequenos acenos de ênfase e olhares laterais em alternativas. O ponto frontal é ancorado na orientação inicial medida, sem visão computacional ou acompanhamento de pessoas. O ajuste físico pode suavizar/deslocar picos em relação à referência verbal; não há promessa de alinhamento perceptual perfeito.

Ordem de juntas: oito braços, cabeça opcional e [LWristYaw, RWristYaw, LHand, RHand]. As mãos são frações de abertura, 0 fechado e 1 aberto. O plano traz joint_units, mão em open_fraction e demais juntas em radians. O RMS em graus exclui as mãos; sua qualidade é reportada em percentual de abertura. Não há comando de dedos individuais no NAO físico.

Limites adicionais: punhos 0,65 rad/s e 2 rad/s²; mãos 1,0 fração/s e 3 frações/s². A ativação temporária dos motores extras mantém a posição medida e eleva a rigidez até pelo menos 0,6, com restauração em encerramento, STOP e erros tratados. Cabeça conserva seu escopo de ativação próprio. Nenhuma junta de perna é aceita pelo executor físico.

No Webots, as mãos virtuais mapeiam a fração para motores Phalanx do PROTO instalado. Esses segmentos têm rotação inicial -0,96 rad; +0,96 rad os estende. A aproximação acopla os segmentos e não reproduz exatamente o mecanismo de tendão. O vídeo foi revisado nos instantes de abrir/fechar; a gravação não inclui mais overlays das câmeras do NAO.

Teste salvo: geração 2789fd832f8748b3a9cd1aba3fbac0d1, frase “Olá! Primeiro vou abrir a mão. Depois vou fechar a mão. O que você acha?”. Referências: saudação 0,34 s; abrir 2,29 s; fechar 4,57 s; pergunta 6,80 s. O vídeo com voz está em app/data/jobs/2789fd832f8748b3a9cd1aba3fbac0d1/simulation/simulation.mp4.

Amplitude padrão de 100% da variação IK recentrada, limitada pela margem articular disponível. Opções de 80%, 60% e 35% permitem reduzir. As velocidades e acelerações não foram aumentadas. Versão do planejador: 7.
