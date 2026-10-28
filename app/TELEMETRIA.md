# Fontes e resolução da telemetria

Na investigação de velocidade em 28/10/2026, o registro
`run_f2d8e20db71a4f6ab17539b8083b0438` mostrou que as posições de
`ALMemory.getListData` eram uma cópia atualizada com frequência inferior à do
controle. Os vetores completos dos oito comandos e oito sensores se repetiam
simultaneamente em 64,76% dos intervalos registrados. A cópia mudava a cada
aproximadamente 0,34–0,38 segundo, embora o aplicativo consultasse a cada 0,1 s.

Isso produz degraus artificiais na telemetria e picos de velocidade calculada.
Não demonstra que os motores físicos pararam durante os intervalos. O registro
anterior `run_c3e5571263ad4b8aa99682ca0e134949`, obtido por `getAngles`, tinha
atualizações de comandos em aproximadamente 0,10–0,13 s sem repetição do vetor
inteiro. As pausas observadas visualmente pelo operador continuam relevantes;
contagens de pausas baseadas nas posições em cache precisam de nova medição.

## Leitura corrigida

- `measured` vem de `ALMotion.getAngles(names, True)`.
- `commanded` vem de `ALMotion.getAngles(names, False)`.
- `position_source` registra `ALMotion.getAngles` em cada amostra.
- Rigidez efetiva, corrente e temperatura vêm de um snapshot separado do
  `ALMemory`, consultado no máximo uma vez a cada 0,4 s. As posições presentes
  nesse snapshot legado de pré-condições são descartadas pelo amostrador e não
  podem sobrescrever as posições de movimento.
- `device_sample_elapsed_s` indica o instante local da última consulta de
  metadados. Não é um timestamp do firmware nem garantia de atualização física.

O aplicativo continua consultando posições aproximadamente a cada 0,1 s. As
chamadas remotas de sensores e comandos são sequenciais; sua diferença de tempo
e a rede ainda limitam estimativas de velocidade e de erro. A telemetria não é
um sistema de medição externo nem uma leitura do ciclo completo dos motores.

Uma falha em metadados opcionais é registrada em `device_read_error` sem
substituir posições por valores antigos. No teste de rigidez constante, uma
falha na leitura exigida de metadados ou um alerta térmico interrompe a execução
e segue o caminho de restauração dos ajustes. O analisador de pausas utiliza
somente `measured` e `commanded`; os valores de potência e temperatura em cache
não participam desse cálculo.
