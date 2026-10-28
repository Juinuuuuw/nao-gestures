# Estado atual — protótipo 02

Atualizado em 27/10/2026. Pipeline executado: **Edge TTS → EMAGE → adaptador com tempo preservado → Webots R2025a / NAO V6**.

- Voz `pt-BR-AntonioNeural`, com MP3, WAV mono 16 kHz e tempos por palavra.
- Fala de 17,568 s; 527 quadros de movimento. A trajetória cobre 17,533 s entre o primeiro e último quadro; a pequena diferença final é a convenção de amostragem, não um esticamento da fala.
- Inferência EMAGE: 1,08 s; pico alocado pelo PyTorch: 609,16 MiB, sem incluir os demais programas da GPU.
- Limites conservadores: 1,2 rad/s e 5 rad/s². A execução amostrada a 12 ms no Webots mediu máximos de 1,194 rad/s e 4,975 rad/s² nos comandos interpolados.
- Rastreamento dos motores no simulador: RMS 2,71°; erro máximo 6,83°.
- Sem queda detectada neste clipe. Altura mínima da base 0,332 m, inclinação máxima 0,084°. Física e auto-colisão ativas; base não fixada nem reposicionada durante a execução.
- O ajuste mantém o tempo e troca fidelidade por continuidade: erro médio de direção dos membros de aproximadamente 6,56°. Isso não é nota de naturalidade.
- Nove testes automatizados. Ambiente Python isolado dos pacotes globais; `pip check` sem conflitos.
- Projeto e controlador de teste criados dentro de `webots/`; exemplos originais do usuário preservados.
- Vídeo com voz em `webots/results/edge_pt/demonstracao_com_voz.mp4`; visão geral em `RESULTADOS.html`.

O áudio do vídeo foi montado no relógio da simulação, sem esticar fala ou movimento. Som ao vivo no Webots pode divergir quando o simulador roda mais lento/rápido que o tempo real: na última execução em tempo real, a diferença máxima entre os relógios foi de 0,65 s. Isso não mede latência acústica. A validação vale para este modelo e clipe no simulador, não para o NAO físico.

Ainda faltam semântica dos gestos em português, movimentos de cabeça/olhar, interrupções, geração em fluxo e integração com visão. O EMAGE está funcional como gerador de gestos a partir de áudio; o sistema conversacional completo ainda não está implementado.

---

# Registro histórico — primeira execução

O problema de duração descrito abaixo foi corrigido no protótipo 02. O exemplo original foi mantido para comparação.

Executado localmente em 27/10/2026, com RTX 3060 12 GB.

## Pipeline real

1. Sintetizada uma fala em português de 17,7055 s com Microsoft Maria Desktop.
2. Executada inferência EMAGE na GPU: 531 quadros, 1,22 s de inferência (carga do modelo separada: 0,79 s).
3. Pico de memória alocada pelo PyTorch: 609,18 MiB. Não é a memória total da GPU nem inclui os outros componentes do futuro sistema.
4. Extraído o esqueleto neutro correspondente e importadas rotações SMPL-X.
5. Convertidas direções dos membros para oito articulações do NAO.
6. Exportados CSV, JSON e prévia HTML para `examples/emage_pt`.

O resultado numérico preservou as direções com erro médio de 2,07° e máximo de 19,29°. **Isso não é uma medida de naturalidade.**

## Problema encontrado

As trajetórias convertidas excederam os limites conservadores definidos neste protótipo: 1,2 rad/s e 5 rad/s² nas diferenças discretas. Não são apresentados como limites máximos oficiais dos motores.

O modo atual preserva a trajetória e aumenta sua duração: fator 5,37, de 17,67 s para 94,85 s. Por isso, a prévia real **não está sincronizada com o áudio original**. A próxima implementação deve reduzir oscilações e variações desnecessárias dos ângulos — incluindo soluções ambíguas do cotovelo — e otimizar amplitude/continuidade mantendo a duração da fala. O fator não prova que o NAO precise mover-se cinco vezes mais devagar; descreve o comportamento deste adaptador inicial sob essas escolhas.

## Verificações

- 7 testes automatizados: geometria de referência, sinais dos cotovelos, alvo alcançável, limites discretos, retiming, dados inválidos e invariância da importação a rotação/translação global.
- Prévia testada no Edge sem interface visível: reprodução, pausa, navegação, câmera, erros JavaScript e largura de tela móvel.
- Inspeção visual das capturas da prévia.
- Sem conexão ou teste físico no NAO. Equilíbrio e colisões não avaliados.

## Próxima etapa

Melhorar continuidade e manter a duração do áudio antes de criar o executor NAOqi. Depois conectar ao NAO V6, ler versão exata, sensores e limites via API e validar movimentos pequenos. Ainda precisamos do IP do robô e da versão exata do firmware para essa integração.
