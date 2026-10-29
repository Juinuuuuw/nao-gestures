# Vozes: Edge TTS e ElevenLabs

No painel, escolha o serviço antes de gerar. Gerações anteriores continuam
usando Edge TTS por padrão. Mudar serviço, voz, modelo ou emoção exige gerar
novamente; não é possível trocar o áudio sem refazer os movimentos EMAGE.

## ElevenLabs

1. Selecione **ElevenLabs** no campo Serviço.
2. Abra **Configurar API key** e cadastre sua chave no painel local.
3. Carregue as vozes da conta ou use **Outro Voice ID**.
4. Escolha modelo, emoção e texto em português. Clique em Gerar fala e gestos.

O Voice ID inicial é `NOpBlnGInO9m6vDvFkFC`, informado pelo operador. Sua
existência, disponibilidade e sotaque não foram confirmados sem acesso à conta.
O catálogo prioriza rótulos brasileiros/portugueses, mas permite escolher as
demais vozes. Para sotaque brasileiro, selecione uma voz brasileira.

O modelo inicial é `eleven_v4`. Também há `eleven_v3`,
`eleven_multilingual_v2` e `eleven_flash_v2_5`. Não há troca automática de
modelo nem repetição automática de solicitações de síntese: uma nova geração
pode consumir créditos da conta. Permissões da chave, acesso à voz, modelo e
saldo dependem da conta ElevenLabs.

O parâmetro da API para português é `language_code="pt"`, não `pt-BR`.
`locale="pt-BR"` nos metadados indica o alvo da interface. Multilingual v2 não
suporta esse parâmetro; para ele o idioma é inferido do texto e da voz.

Nos modelos v4/v3, a emoção escolhida acrescenta uma tag de voz, como `[happy]`
ou `[sad]`. Tags como `[whispers]` também podem ser digitadas no texto. O
modelo e a voz determinam como interpretar essas instruções. Nos outros modelos
não são acrescentadas tags emocionais; o perfil corporal continua ativo.
Campos de velocidade/altura/volume do Edge TTS não são enviados à ElevenLabs.
Tags explícitas com modelos v2 são recusadas antes de chamar a API, para não
serem lidas como texto comum. Não há tradução automática do texto.

## Chave e conexão

No Windows, a chave cadastrada é cifrada por DPAPI para o usuário atual em
`runtime/elevenlabs.key`. Esse arquivo e o diretório runtime são ignorados pelo
Git. A chave não é salva no histórico de falas, no navegador ou em comandos de
subprocessos. O campo de senha é limpo depois da tentativa de salvar.

Também é aceita a variável `ELEVENLABS_API_KEY`, no processo ou no ambiente do
usuário Windows. Uma chave local cifrada tem prioridade sobre o ambiente.
Salvar a chave indica apenas que ela está configurada; carregar vozes e gerar
áudio verificam suas respectivas permissões na API. Erros de conta/rede são
mostrados sem expor cabeçalhos, resposta bruta ou chave.

Rotas locais: `GET /api/voice/status` retorna apenas estado não secreto;
`POST /api/voice/elevenlabs/key` salva a chave; e
`POST /api/voice/elevenlabs/voices` consulta até cinco páginas do catálogo.
Os POSTs exigem o token da sessão, a mesma origem e o host local autorizado.
O servidor continua escutando apenas em `127.0.0.1`.

## Áudio e sincronização

A síntese usa a API HTTP oficial com `/with-timestamps`, que retorna MP3 e
alinhamento por caractere. Caracteres são agrupados em palavras usando os
tempos retornados, sem estimar tempos pela quantidade de letras. Tags entre
colchetes são excluídas das palavras, preservando os tempos absolutos.

Alinhamentos ausentes, incompletos ou inválidos interrompem a geração. O MP3 é
convertido para WAV mono PCM de 16 kHz com o mesmo mínimo de silêncio final do
pipeline Edge. EMAGE recebe esse WAV. A direção e o roteiro usam as palavras
salvas em `speech.json`, com `timing_source=elevenlabs_character_alignment`.
Cabeça, braços, mãos e Webots usam o mesmo planejador.

## Referências consultadas

- [Criar fala com tempos](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps)
- [Listar vozes](https://elevenlabs.io/docs/api-reference/voices/search)
- [Modelos e idiomas](https://elevenlabs.io/docs/overview/models)
- [Tags de voz e expressão](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices)

Integração implementada com a biblioteca padrão HTTP do Python; não requer o
SDK `elevenlabs`. Testes locais cobrem solicitações/respostas simuladas, DPAPI,
catálogo, alinhamento e conversão MP3/WAV. A síntese real ElevenLabs permanece
pendente até configurar uma chave válida; não foi simulado um resultado como
se fosse áudio produzido pela conta.

A chave completa atual começa com `sk_`. O ID exibido na lista de chaves não autentica na API. Se não guardou o segredo mostrado na criação, crie ou rotacione uma chave e copie o novo segredo. O app rejeita Key IDs antes de chamar a API. Logs de subprocessos Python são forçados a UTF-8 para preservar mensagens em português.
