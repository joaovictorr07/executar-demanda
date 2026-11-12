# Mutantes

Um mutante é um defeito plausível injetado de propósito. Se os testes continuam verdes, eles não
protegem aquele comportamento — como uma linha de total geral que nunca foi comparada e que
ninguém vê errada, porque tudo passa.

## Como a sessão funciona

- Mutante é do **revisor**: `mutante preparar` só abre com uma revisão da onda iniciada e vigente
  (código igual ao do `revisao iniciar`), e só contam os mutantes da revisão mais recente.
- **O autor não cria mutante.** A autoconferência é só a tabela de aceites e as asserções rasas.
  `mutante preparar --autor` só abre depois de uma revisão, numa sessão de **pré-revisão**: ali só
  `mutante reaplicar` / `aplicar --reaplica M<n>`, e mutante novo é recusado. Esses mutantes não contam
  para o fechamento nem para o parecer.
- **Sobrevivente da revisão volta antes da seguinte.** `mutante reaplicar` aplica de novo, na sessão de
  pré-revisão, todo sobrevivente das revisões da onda (menos os equivalentes decididos), com o mesmo
  `--de/--para/--aceite/--testes`: na linha original se o trecho ainda está lá, senão na única linha do
  arquivo que o tem. Trecho em várias linhas: `mutante aplicar --reaplica M<n> --linha N`. Trecho que
  saiu do código: registrado como `codigo_removido` (aviso). O `revisao iniciar` da 2ª e da 3ª exige
  cada sobrevivente anterior reaplicado e morto sobre o código atual.
- **Rodada de confirmação (2ª e 3ª revisão).** `mutante reconfirmar` reaplica, na sessão do revisor,
  os sobreviventes das revisões anteriores e os mortos delas que perderam a herança. Mutante novo só
  na **linha** que a correção mexeu ou em aceite ainda sem morto válido: mutar código já aprovado é
  recusado. O `reconfirmar` só pula o que o autor já matou quando o aceite já tem morto do revisor — o
  do autor não conta para o fechamento. `revisao validar` recusa sobrevivente anterior que não foi
  reaplicado e morto sobre o código atual.
- **Rodada mecânica (`revisao confirmar`).** O script abre a sessão do revisor sozinho, roda o
  `reconfirmar` e limpa. Essa sessão **só reaplica**: mutante novo é recusado (é de uma revisão com
  subagente). Os mutantes continuam sendo os que o revisor escolheu.
- `--para ''` vale (apagar a chamada é mutação); `--de` vazio, não.
- Mutante roda testes: `mutante preparar` pede a autorização de testes do projeto (ou `--decisao`).
- Timeout encerra o **grupo de processos** inteiro do comando (o `mvn` filho junto): o relatório
  que a execução seguinte lê não é reescrito por um órfão.

- `mutante preparar` cria uma `git worktree` no scratch, replica diff e não rastreados, copia
  `target/` (Maven) e linka `node_modules`, e confere que a réplica tem o fingerprint do real.
- Na primeira mutação de cada seleção de testes, a seleção roda **sem** mutação. Se já falha, a
  seleção é recusada (senão todo mutante "morreria").
- `mutante aplicar` troca **uma** ocorrência de `--de` por `--para` na linha indicada, roda,
  classifica, restaura e confere o sha1 do arquivo.
- `mutante limpar` remove a worktree e confere que o repositório real está igual ao do começo.
- Um mutante só vale enquanto o código for o mesmo da sessão. Mudou o código, os mutantes
  vencem e é preciso rodar de novo — **salvo a herança**: o morto de uma revisão anterior da mesma
  onda continua valendo quando o arquivo mutado e os arquivos das classes de teste que o mataram
  têm o mesmo sha1 gravado nele, e a linha ainda tem o trecho. Sobrevivente não se herda.
- **Herança relaxada.** O mutante grava a `texto_linha` (a linha antes da mutação) e, quando
  morre, cópia dos testes que o mataram em `evidencias/mutantes/blobs/<sha1>`; identidade estável =
  (repo, arquivo, `texto_linha`, `de`, `para`). Herda mesmo com o arquivo de produção mudado em outras
  linhas, desde que a linha mutada (na posição, ou a única do arquivo com o `de`) seja exatamente a de
  antes e cada teste que o matou só tenha ganhado linhas (as antigas seguem lá, na ordem). Mutante sem
  `texto_linha` ou sem cópia herda só pela regra estrita. **Amostra de alarme:** o `reconfirmar`
  reaplica até 3 herdados relaxados (sha1 de revisão + mutante, determinístico); sobrevivente nela
  grava `heranca_relaxada_invalida` na onda (volta à estrita) e reaplica todos os relaxados; o
  `revisao validar` recusa herdado relaxado sem a amostra feita na revisão.

Resultados:

| Resultado | Significa | Conta? |
|---|---|---|
| `morto` | falha ou erro de teste (ou timeout) — o registro diz a causa: `falha` (asserção), `erro`, `timeout`, `oraculo` | sim; `erro`/`timeout` com aviso |
| `sobrevivente` | tudo verde com o defeito | bloqueia o fechamento |
| `nao_compila` | a mutação quebrou a compilação | não |
| `invalido` | resultado sem leitura possível | não |

## Que mutação escolher

Mire o **código novo da onda**, onde o aceite mora. Uma mutação por comportamento, do tipo que
um humano erraria:

| Tipo | Exemplo (Java) |
|---|---|
| fronteira | `> 31` → `>= 31`; `<=` → `<` |
| condição invertida | `if (ce)` → `if (!ce)`; `&&` → `\|\|` |
| valor de retorno | `return HttpStatus.CONFLICT` → `return HttpStatus.OK` |
| constante | `setScale(4, …)` → `setScale(2, …)`; `0.9` → `0.8` |
| efeito colateral removido | `repo.save(x);` → `;` · `fila.liberar(id);` → `;` |
| operador | `custo + imposto` → `custo - imposto` |
| campo trocado | `getDataEmissao()` → `getDataEntrada()` |
| ordem | `sort(porCodigo)` → `sort(porDescricao)` |

- `--de` precisa ocorrer **uma vez** na linha: use um trecho distintivo.
- `--testes` com nome simples roda **todas** as classes homônimas (o `testar` avisa quando há): o
  mutante morre se qualquer uma falhar. Para mirar uma só, use o nome qualificado.
- Arquivo de teste não se muta.
- **Linha alterada nesta onda.** O script grava se a linha mutada mudou desde o início da onda;
  mutante em código que a onda não tocou não conta para o mínimo. **Exceção: a onda `**Só testes:** sim`,
  e o aceite cujas tarefas só têm arquivo de teste no `Onde`** (um teste novo para comportamento
  que já existia). Neles não há linha de produção alterada, e conta o mutante na linha que o teste
  novo protege, desde que morra **por asserção** numa classe de teste criada ou alterada na onda.
  O `validar-plano` lista os aceites só de testes como aviso, para o usuário ver ao aprovar.
  O script grava as classes que falharam em cada mutante (`classes_que_falharam`). Classe de
  teste alterada: Java com `@Test`, ou spec JS/TS (`*.spec.ts`, `*.test.ts`…) com algum `it(`/`test(`,
  pelo nome do arquivo em PascalCase + `Spec`/`Test` (`custom-button.spec.ts` → `CustomButtonSpec`).
- **Uma linha, um mutante** para o mínimo: três mutações na mesma linha contam uma.
- Mínimo de mortos pelo porte da onda: **2 na leve** (até 4 tarefas e risco normal), 3 na normal;
  `Risco: alto`: pelo menos 5, cobrindo cada ramo de cálculo.
- Cada mutante leva `--aceite`: o fechamento exige ao menos um morto por aceite testável. Aceite cuja
  prova mora só em arquivo de teste não tem o que mutar: o usuário decide, e o fechamento leva
  `--sem-mutante A<id> --sem-mutante-decisao D<n>` (recusado se a evidência da revisão aponta código de
  produção ou o aceite não está OK); o parecer cita a dispensa.

## Paridade como oráculo

Numa migração, o oráculo pode ser a comparação com o legado em vez da suíte:

```powershell
demanda.py mutante aplicar … --comando 'python <pasta do projeto>/ferramental/comparar.py <ref> <saida-gerada-no-scratch> --modo chave --chave 1 --tolerancia 0.01 --excecoes …' --codigos-morto 1
```

O `--comando` roda dentro do scratch (`{scratch}` é substituído pelo caminho). Exit 0 é
sobrevivente, os códigos de `--codigos-morto` são morto, o resto é inválido. **Exige `--decisao D<n>`
do usuário** (finalidade `oraculo`), e o texto do comando fica no registro do mutante: um `grep`
qualquer "mataria" qualquer mutação sem teste nenhum. Por isso o morto por oráculo **não prova aceite
que tem teste automatizado** (o fechamento avisa e não o conta): serve ao aceite que não tem. Timeout
(exit 124) não é morte: vira inválido. E o scratch não pode mudar entre a rodada limpa e os mutantes:
arquivo rastreado alterado fora do mutante em curso recusa o seguinte (`mutante limpar` e `preparar`).

## Sobrevivente equivalente

Às vezes nenhum teste poderia distinguir (a mutação não muda comportamento observável). O
revisor **propõe** nas lacunas (`equivalente-candidato`). Quem decide:

- o **usuário**, com a resposta dele registrada (`decisao add --para equivalente --alvo M<n>`); ou
- você, com a autorização de engenharia do projeto: `decisao engenharia --para equivalente --alvo
  M<n> --texto "<por que nenhum teste distingue>"`. Só para sobrevivente de sessão do revisor; vale
  uma vez, e o `fechar-onda` e a seção 6 do parecer a listam para o usuário rever.

Depois, `mutante equivalente --id M<n> --motivo "<por que nenhum teste distingue>" --decisao D<n>`.
Marcar a cópia reaplicada marca também o original (é o mesmo defeito). Aparece como aviso no
fechamento e no parecer. Na dúvida, não é equivalente — o teste é que está fraco.

## Custo

A primeira execução de uma seleção no scratch compila o que mudou; as seguintes, só o arquivo
mutado. Mantenha a seleção pequena (as classes do aceite), agrupe mutantes da mesma seleção numa
sessão, e limpe a sessão no fim.
