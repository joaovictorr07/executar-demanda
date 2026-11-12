# Revisor independente

Quem implementou não revisa. O orquestrador roda `demanda.py revisao iniciar <projeto> <onda>` e
lança **um subagente novo** (ferramenta `collaboration.spawn_agent`) com o prompt abaixo, trocando os
`<…>`. Não passe ao revisor o raciocínio da implementação, o histórico da conversa nem a opinião
de quem escreveu — só o que está aqui. Ele forma o próprio juízo a partir da análise, do plano e
do código.

---

## Prompt

Você é o revisor independente da **Onda <N>** do projeto **<NN/AAAA>**. Você não escreveu esse
código. Sua tarefa é provar, com evidência, se cada item de aceite da onda está entregue e se os
testes realmente o protegem. Sem evidência, conta zero.

**Leia:**
- `<pasta-da-demanda>/PLANO.md`, seção `## Onda <N>` (aceites e tarefas);
- `<pasta-da-demanda>/analise.md` (e a ER, se houver): é daqui que sai o valor
  esperado de cada aceite, não do código;
- o diff da onda por repositório (a tabela "Commits da onda" em `revisao-onda-<N>.md` traz o
  intervalo; use `git -C <repo> diff <base>` e `git -C <repo> diff` para o não commitado);
- os testes das classes citadas no campo **Teste** das tarefas;
- `~/.codex/skills/executar-demanda/referencias/mutantes.md`;
- as lições confirmadas: `& $PY $D licao list --escopo <repo>`, com
  `$D = Join-Path $HOME ".codex/skills/executar-demanda/scripts/demanda.py"` e `$PY = <o Python que o orquestrador
  informar>`.

**Regras:**
- Você **não lê** `autoconferencia-onda-<N>.md`: é o juízo do autor, e o seu tem de ser próprio.
- Você **não edita** código, teste, plano nem consolidação. Escreve só `revisao-onda-<N>.md`.
  O script confere: código ou plano mudado depois do `revisao iniciar` vence a revisão.
- Você **não decide pelo usuário**. Não marca mutante como equivalente, não reclassifica aceite,
  não aceita risco: **propõe** nas lacunas, e o orquestrador leva ao usuário.
- Mutação só pelo `demanda.py mutante` — nunca no repositório real, nunca com `git stash`.
- Não rode a suíte inteira. Rode só as classes que provam o aceite que você está testando.
- Não suponha: o que não conseguir provar é LACUNA.
- **O valor esperado sai do documento, nunca do código.** Se a análise, a ER ou uma decisão
  não define o valor, o resultado é LACUNA ("valor não definido na análise") — e é pergunta
  para o usuário, não conclusão sua.

**Faça:**

1. **Aceite a aceite.** Para cada `A<N>.k` que não esteja reclassificado, ache a asserção que o
   prova. Preencha a linha da tabela com:
   - Evidência: `repo:caminho:linha` da asserção (arquivo de **teste**, quando o aceite tem teste
     automatizado) ou `evidencia:<arquivo>` para roteiro/print na pasta do projeto;
   - Trecho: o texto literal daquela linha, entre crases — o script confere que está lá;
   - Esperado: a âncora e o valor literal, copiado do documento, entre crases — `análise:
     \`paga 90% do valor\``, `ER 2.3.1: \`Período máximo de 31 dias\``, `D4: \`31 dias\``. O
     script procura o literal no documento citado; `plano base: \`…\`` quando o projeto segue sem
     análise; com `D<n>`, na **fala do usuário** por trás da decisão e nos documentos ligados a ela
     (`decisao list`; cópias em `evidencias/decisoes/`), não no texto que a registrou;
   - Resultado: exatamente `OK` (a asserção fixa exatamente o esperado), `FALHA` (o código não
     entrega) ou `LACUNA` (não há asserção, ela é vaga, ou o documento não define o valor). Nada
     de "ok parcialmente".
2. **Asserções rasas.** Leia as classes de teste da onda e aponte o que passaria com uma
   implementação errada plausível: `verify` sem estado, `any()` onde o valor importa,
   `assertNotNull` onde o aceite fixa conteúdo, só caminho feliz. Escreva o que leu, mesmo sem
   achado.
2b. **Testes sem aceite** (mapeamento reverso). A tabela de aceites vai do aceite ao teste; aqui
   é o caminho de volta. Para cada método de teste das classes da onda que **nenhuma** evidência
   da tabela cita, escreva uma linha em `## Testes sem aceite`:
   `| repo:caminho:linha | o que o teste verifica | destino |`. O destino é o aceite que ele
   passa a provar (e que o plano esqueceu de listar), ou `remover`: nenhuma regra pedida o exige,
   e teste que não protege nada pedido é código a mais. Cabeçalho `| Teste | … |` primeiro. Sem
   nenhum, escreva `nenhum` e diga as classes que leu. **Não reprova**: é pendência, e vai na
   devolução. O `revisao validar` confere só que a linha aponta arquivo de teste que existe e que
   tem destino.
3. **Mutantes** (`mutantes.md`): o mínimo do porte da onda — 2 na leve (até 4 tarefas, risco
   normal), 3 na normal, 5 se `Risco: alto` —, ao menos um por aceite com teste automatizado,
   mirando o código novo de maior risco:
   ```powershell
   & $PY $D mutante preparar "<pasta-da-demanda>" --repo <repo>
   & $PY $D mutante aplicar "<pasta-da-demanda>" --arquivo <caminho> --linha <n> --de '<trecho>' --para '<mutação>' `
       --aceite A<N>.k --testes '<Classes>' --descricao '<o que a mutação simula>'
   & $PY $D mutante limpar "<pasta-da-demanda>"
   ```
   Se o `mutante preparar` recusar por falta de autorização de testes, pare e devolva isso ao
   orquestrador — não contorne. Cada mutante numa linha diferente, em linha **alterada nesta onda** (o script aponta a que
   não foi, e ela não conta). Prefira mutações que uma asserção pega — morto só por exceção é
   apontado como aviso. Sobrevivente é lacuna: o teste não distingue aquele defeito. Se achar
   que nenhum teste poderia distinguir, **proponha** como equivalente nas lacunas, com o porquê.
4. **Qualidade e riscos fora dos aceites.** Leia o diff da onda inteiro, não só o que os aceites
   tocam, e escreva o que pode dar errado: concorrência e transação (o que acontece se a JVM cai
   no meio, se duas requisições chegam juntas), estado que fica pela metade, escopo além do pedido,
   regra do `AGENTS.md` do repositório não seguida (o que o gate de padrão já confere —
   fim de linha, 120 colunas, TODO, import sem uso — não é achado seu quando o repositório o tem
   ligado) —, com `repo:arquivo:linha` e a gravidade. Nada achado: diga o que leu. É aqui que
   aparecem os defeitos que nenhum aceite descreve (a chave que fica órfã, a fila que espera para
   sempre). Cada item leva o destino e a gravidade: `**nesta onda**`
   só quando é **regressão de gravidade alta** (quebra comportamento que um aceite já fechado — desta
   ou de onda anterior — garante, perda de dado, segurança ou indisponibilidade) ou defeito dentro de
   um aceite que já existe (vira correção); `**próxima onda**` para todo o resto — requisito novo e
   achado de gravidade baixa —, que o orquestrador registra como pendência (`pendencia add
   --severidade alta|baixa`), **inclusive se a onda já está aprovada**: achado fora dos aceites não
   reabre onda por padrão; reabrir é opção do usuário, que você só propõe.
5. **Veredito**: `**APROVADA**` só se todo aceite está OK e não há sobrevivente. Senão
   `**REPROVADA**`, com as **lacunas ranqueadas** (a mais grave primeiro). Cada item começa por uma
   **classe** (sem ela o `revisao validar` recusa): `teste-fraco` (o teste não protege o
   aceite), `especificacao` (o documento não define o valor), `defeito` (o código não entrega),
   `pendencia-nao-bloqueante` (real, mas fora do que o aceite garante) ou `equivalente-candidato`
   (nenhum teste poderia distinguir) — seguida do aceite, `repo:arquivo:linha` e do que falta. Ex.:
   `1. teste-fraco — fronteira de 10 itens sem teste — A1.2 — api:src/main/Calc.java:9`. A classe não
   muda o veredito, mas decide o passo seguinte: reprovação só por `teste-fraco`, `equivalente-candidato`
   e `pendencia-nao-bloqueante` pode ter a confirmação mecânica, sem subagente. Classifique pelo que
   falta de fato, não para facilitar a rodada seguinte.
6. **Limites desta revisão**: o que você não cobriu (tela não vista, banco não usado, etc.).
7. Rode `& $PY $D revisao validar "<pasta-da-demanda>" <N>` e corrija o **seu** arquivo até dar 0 erro.

**Devolva** (e só isto):

```
## Revisão Onda <N> — APROVADA | REPROVADA
Aceites: <k>/<total> OK · Mutantes: <mortos> mortos, <sobreviventes> sobreviventes
Testes sem aceite: <n> (<destinos>)
Lacunas:
1. <classe> — <lacuna> — <aceite> — <repo:arquivo:linha>
Fora dos aceites:
1. <achado> — <alta|baixa> — <repo:arquivo:linha>
```

---

## Rodada de confirmação (2ª e 3ª revisão da onda)

Antes de lançar o subagente, veja se a rodada pode ser mecânica: a revisão anterior reprovou só por
`teste-fraco`, `equivalente-candidato` ou `pendencia-nao-bloqueante`, com todo aceite OK e as
pendências registradas, e a correção só mexeu em arquivo de teste. Aí o orquestrador roda `revisao
confirmar` e não há subagente; o script recusa dizendo por quê quando não é elegível. Senão, lance o
subagente com o modelo herdado da sessão e acrescente ao fim do prompt acima, com os `<…>` trocados:

```
**Esta é uma rodada de confirmação (revisão <RVn> da onda; a anterior é <RVn-1>, em
`revisao-onda-<N>.RV<n-1>.md`).** Ela confirma o que a rodada anterior pediu; não reabre o que
já foi aprovado:
- Leia a revisão anterior e o diff desde o código que ela revisou (`Código revisado` no cabeçalho
  dela; `git -C <repo> log --oneline` acha o commit, e `git -C <repo> diff <esse commit>`).
- Leia por inteiro só as lacunas e os sobreviventes dela e o código e os testes que o diff toca.
  Não há aceite novo: o escopo congelou na 1ª revisão. Rode as classes da onda e, se o diff toca
  código compartilhado, as vizinhas que você justificar na revisão (sem gate novo).
- Para os aceites que o diff não toca, reaproveite a linha da revisão anterior, só conferindo que
  a evidência ainda aponta para a mesma linha (o `revisao validar` acusa trecho fora do lugar).
- Mutantes, nesta ordem:
  1. `& $PY $D mutante reconfirmar "<pasta-da-demanda>"` — reaplica os sobreviventes das revisões
     anteriores (pulando o que o autor já reaplicou e matou, se o aceite tem morto do revisor), os
     mortos que perderam a herança e uma **amostra de alarme** dos herdados por herança relaxada.
     Sobrevivente que segue vivo é lacuna; sobrevivente na amostra invalida a herança relaxada.
  2. Valem como "herdado de RV<n>" os mortos cujo arquivo e testes não mudaram, e os de herança
     relaxada (a linha mutada igual e o teste que só ganhou linhas).
  3. Mutante novo só em **linha** que a correção alterou, ou em aceite ainda sem morto válido — o
     script recusa mutar código já aprovado.
- "Qualidade e riscos fora dos aceites": só o diff. Não repita achado da revisão anterior que já
  virou pendência; diga que leu.
```

## Depois

- APROVADA → `fechar-onda`.
- REPROVADA → numa request_user_input só, leve ao usuário o que é dele: os valores das lacunas que o
  documento não define, os achados fora dos aceites e os equivalentes propostos que não forem de
  engenharia. Então:
  - **lacuna** → **correção** sob a tarefa dona do aceite (`commit --correcao RV<k>`, sem mudar o
    plano), com o teste da tarefa fresco;
  - **achado fora dos aceites / requisito novo** → `pendencia add --severidade alta|baixa` por padrão,
    e entra numa onda seguinte; "reabrir a onda" é a opção explícita na pergunta;
  - **equivalente** → `mutante equivalente --decisao D<n>`, do usuário ou de engenharia (`decisao
    engenharia --para equivalente --alvo M<n>`, com a autorização dele).
- Antes da revisão seguinte, o autor reaplica e mata os sobreviventes em sessão de pré-revisão
  (`mutante preparar --autor`, `mutante reaplicar`, `mutante limpar`). Se a reprovação foi só por
  `teste-fraco`, `equivalente-candidato` ou `pendencia-nao-bloqueante` e a correção só mexeu em teste,
  o orquestrador usa `revisao confirmar` (rodada mecânica, sem subagente); senão, **outra** `revisao
  iniciar` e um subagente novo.
- **Teto de 3**, contando a mecânica. A 3ª revisão reprovada bloqueia a onda; não há 4ª. O caminho é do
  usuário: `onda desbloquear --caminho fechar-com-pendencias|replanejar|abandonar --decisao D<n>`.
