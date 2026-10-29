# Emoções no NAO Studio

Escolha a emoção junto da voz, antes de gerar. As seis opções são Alegria,
Tristeza, Medo, Raiva, Nojo e Surpresa; Neutra mantém o comportamento anterior.
A emoção é imutável em uma geração. Para alterá-la, gere outra fala. Gerações
antigas são tratadas como neutras.

| Opção | Voz aproximada | Corpo e olhos |
| --- | --- | --- |
| Alegria | +8% de ritmo, +8 Hz | Braços receptivos, mãos mais abertas, amarelo suave |
| Tristeza | -14%, -8 Hz, volume -8% | Gestos contidos, cabeça baixa, azul |
| Medo | +5%, +12 Hz, volume -5% | Braços recolhidos, expressão de atenção, violeta |
| Raiva | +4%, -5 Hz, volume +2% | Gestos assertivos, fechamento parcial, vermelho suave |
| Nojo | -6%, -5 Hz, volume -3% | Desvio breve do olhar, gesto de recusa, verde suave |
| Surpresa | +10%, +16 Hz | Cabeça elevada, mãos abertas, branco azulado |

São presets autorais sobre o EMAGE, e não um modelo treinado de emoções ou
estilos emocionais nativos do Edge TTS. Não há reconhecimento de emoção,
reescrita livre do significado ou garantia de que um observador reconhecerá a
emoção. O conteúdo digitado é preservado e a prosódia é ajustada. As cores são
convenções expressivas do projeto, não associações psicológicas universais.

O roteiro separado usa o formato **[Emoção Selecionada]** e **[Fala e Gestos]**,
com ações entre parênteses. Ele é um resumo da direção da cena, e não uma lista
de comandos livres para os motores. Referências temporais usam os tempos reais
das palavras do Edge TTS. O EMAGE e a camada de intenção continuam dando o
ritmo dos braços. A pontualidade perceptiva dos acentos depende da adaptação e
dos limites físicos; o roteiro não garante poses exatas em cada palavra.

O NAO tem rosto rígido. A interface não promete sorriso, franzir do rosto,
arregalar dos olhos ou dedos independentes. Não há comandos novos para pernas,
tronco físico, golpes ou mãos junto ao rosto. Perfis passam pelos mesmos
limites de posição, velocidade e aceleração dos movimentos anteriores. O ritmo
do áudio muda antes da inferência; o EMAGE usa esse áudio e o relógio da fala
permanece preservado no planejamento.

Na execução física, o executor salva as intensidades individuais dos 48 canais
de FaceLeds antes de agendar o movimento, aplica a cor no início da fala e
restaura todos os canais no encerramento, cancelamento e erros tratados. Falha
de acesso aos LEDs permite continuar o corpo/voz com aviso no painel; falha de
restauração é reportada como erro. Isso segue a interface ALLeds documentada
pelo fabricante ([documentação Aldebaran](https://www.bx.psu.edu/~thanh/naoqi/naoqi/sensors/alleds.html)).

No Webots, os dispositivos Face/Led/Left e Face/Led/Right mostram a cor durante
a seção de fala e recuperam seu valor anterior ao sair dessa seção. O vídeo
reproduz o plano da geração escolhida. A prévia cinemática de origem não inclui
o perfil emocional; veja a aba Webots.

Arquivos: `job.json` guarda a chave da emoção, `speech.json` registra a prosódia
efetiva, `expression.json` salva o roteiro, e o plano físico v9 registra emoção
e cor dos olhos. `GET /api/expression/{id}` retorna o roteiro; `/api/generate`
aceita `emotion` com chave de uma opção fixa. As demais ações usam a emoção
salva na geração, sem aceitar parâmetros livres para comandos motores.

Com ElevenLabs, v4/v3 recebem tags emocionais em vez dos ajustes numéricos do Edge TTS. Multilingual v2 e Flash v2.5 mantêm o perfil corporal, sem tags automáticas na voz. O roteiro e a direção usam o alinhamento real do serviço escolhido. Veja `VOZES.md`.


## Sustentação da expressão e controle dos olhos (v9)

As posturas agora se mantêm pela maior parte da frase: aberta/receptiva na alegria, recolhida na tristeza, antebraços protegidos no medo, acentos firmes na raiva, afastamento/olhar lateral no nojo e abertura inicial na surpresa. Preparação e retorno continuam suaves e os limites físicos permanecem iguais. Acentos usam referências das palavras realmente sintetizadas. O EMAGE continua sendo a base do movimento.

O executor reserva somente Left eye leds e Right eye leds por meio do ALResourceManager, com proprietário temporário registrado na sessão. A piscada autônoma é suspensa e a cor é renovada a 2 Hz. Recursos são liberados em sucesso, STOP e erro, antes de retomar as habilidades anteriores. A reserva impede que outras expressões de conversação substituam partes do anel dos olhos. Não são reservados motores, LEDs do peito ou LEDs de alerta.

A aba Origem EMAGE mostra deliberadamente a origem cinemática; para ver o perfil emocional aplicado, teste na aba Webots. Gerações já prontas recebem o novo planejamento sem refazer voz/EMAGE. Para mudar a emoção da voz, gere novamente, como antes.

Validação física limitada aos LEDs: três leituras dos 48 canais durante aproximadamente 3 segundos mantiveram a cor alvo com erro máximo inferior a 0,000001; liberação dos dois recursos e restauração da configuração de piscada confirmadas. Nenhuma trajetória foi enviada aos motores. O instantâneo RGB anterior foi reenviado, mas sua igualdade exata não foi confirmada: o controle autônomo volta a produzir suas animações ao recuperar o recurso. Esse ensaio não valida a percepção humana das emoções.
