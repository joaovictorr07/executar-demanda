---
name: executar-demanda
description: Planejar, executar ou retomar demandas de software em ondas, com aceites rastreáveis, evidências, revisão independente e parecer de liberação. Use para organizar ou fechar ondas; não substitui o levantamento de requisitos.
---

# Executar uma demanda em ondas

Leva uma demanda da análise ao parecer de liberação: plano em ondas, tarefas com commit, testes,
mutantes, revisão independente e parecer. **Nenhum gate depende de memória.** Cada gate é um
comando do `demanda.py` que recusa (ERRO, exit 1) quando falta prova. A prova só vale se foi
produzida sobre o código que está aí agora: o fingerprint é por repositório e **pelo conteúdo**,
então commitar sem mudar arquivo não vence teste, revisão nem roteiro.

## Ambiente e Invocação (Gemini / Antigravity, Codex e Claude Code)

Esta skill é global, mas cada demanda usa a pasta explicitamente escolhida pelo usuário.
Não deduza projeto, branch, requisitos ou aprovações. Mensagens de commit somente em PT-BR.
No modo de planejamento, apenas inspecione e elabore o plano na conversa: não execute comandos
que criem estado, decisões, evidências ou arquivos. Inicie a execução quando o modo permitir.
As instruções atuais do usuário e do ambiente prevalecem sobre este fluxo.

### Como Executar os Scripts

**No Gemini / Antigravity (Windows PowerShell):**
```powershell
$PY = (Get-Command python).Source
$D = 'C:\dev\skills\executar-demanda\scripts\demanda.py'
& $PY $D <subcomando> "<pasta-da-demanda>" ...
```

**No Codex / Claude Code:**
```bash
python scripts/demanda.py <subcomando> "<pasta-da-demanda>" ...
```

Os comandos de teste/build armazenados são executados pelo shell nativo do ambiente (no Windows,
com argumentos devidamente tratados).
Use caminho absoluto de Python quando configurar um comando. Dependências destinadas ao scratch
são copiadas ou linkadas preservando a integridade da origem.
Pastas gerais usam `PLANO.md`, `analise.md`, `ESTADO-ATUAL.md` e `PAINEL.html`.
Pastas legadas `NN - AAAA` mantêm os nomes antigos por compatibilidade.

O estado mecânico mora em `<pasta do projeto>/.execucao.json`, escrito só pelo script. Não edite esse
arquivo à mão, nem os blocos entre `<!-- gerado:…:inicio -->` e `<!-- gerado:…:fim -->`. Cada comando
trava o projeto enquanto grava, então revisor e orquestrador podem rodar juntos.

**Pré-requisito para aprovações.** O coletor `hooks/registrar-fala-usuario.py` deve estar
ativo via `hooks.json` (no Antigravity ou Codex):
- No **Antigravity (Gemini)**: configurado em `hooks.json` ouvindo `PreInvocation` (para prompts do usuário) e `PostToolUse` de `ask_question`.
- No **Codex**: configurado em `hooks.json` ouvindo `UserPromptSubmit` e `PostToolUse` de `request_user_input`.
- No **Claude Code**: configurado em `UserPromptSubmit` e `PostToolUse` de `AskUserQuestion`.

Ele registra falas em `~/.gemini/falas-usuario/` (ou `~/.codex/...` / `~/.claude/...`),
com sessão, horário e diretório. Não escreve na memória do modelo. Perguntas e opções não
são aprovação.
Se não houver captura compatível, peça confirmação textual e confira o registro antes de avançar.
Nunca preencha o registro manualmente para fazer uma aprovação passar.

Use a ferramenta interativa do seu ambiente quando disponível:
- No Antigravity: `ask_question`
- No Codex: `request_user_input`
- No Claude Code: `AskUserQuestion`
Fora deles, pergunte na conversa e aguarde a resposta. Não registre ausência de resposta como autorização.

**Integridade da skill.** A instalação vive no repositório `C:\dev\skills\executar-demanda`, com links globais em `~/.gemini/config/plugins/`, `~/.gemini/config/skills/` e `~/.codex/skills/`. O fingerprint do conteúdo congela a skill durante a onda. Mudanças exigem autoteste
verde e o tratamento de `--skill-alterada D<n>` quando houver onda ativa.

**Ondas históricas.** As ondas iniciadas antes da 0.4.0 seguiam versões anteriores das regras. Hoje são
só leitura: aparecem no painel, nas métricas e no parecer. No parecer, o que delas não satisfaz o critério
de hoje vira aviso. Se uma onda histórica ainda estiver aberta, todo comando de onda recusa.

## Porte da onda

| Porte | Quando | Autoconferência | Mínimo de mutantes mortos |
|---|---|---|---|
| leve | até 4 tarefas e `Risco: normal` | dispensada | 2, e um por aceite testável |
| normal | 5 a 10 tarefas, ou risco alto | obrigatória antes da 1ª revisão | 3 (5 se risco alto), e um por aceite testável |
| grande | mais de 10 tarefas | idem | idem; acima de 15 tarefas, só com `**Tamanho:** D<n>` |

## Quem decide o quê

| Quem | Decide | Como fica provado |
|---|---|---|
| **Usuário** | o projeto e os repositórios; as respostas aos pontos em aberto; a aprovação do plano e de cada onda nova ou mudada; o escopo (arquivo fora do `Onde` que não é vizinho, aceite retirado, teste dispensado); seguir sem análise; onda fora de ordem; tarefa sem commit; achado aceito ou fora do escopo; rodar testes; gate da tarefa dispensado; execução anulada; o caminho da onda bloqueada; pendência descartada; skill ou análise alterada no meio da onda; repositório sem suíte; push, banco e deploy | `decisao add --fonte usuario --citacao` e `aprovar-plano --citacao`: o script confere o trecho no log do hook, numa fala dita na pasta do projeto ou num repositório dele |
| **Modelo, com autorização** | mutante equivalente; arquivo **vizinho** (mesma pasta de um item do `Onde`) fora do `Onde` | `decisao engenharia`, só com `--autoriza engenharia` do usuário vigente; cada uma vale uma vez e o parecer as lista |
| **Documento** (análise, ER) | o valor esperado de cada aceite; a origem de cada onda | âncora `(análise: ASSUNTO)` / `ER x.y` / `plano base:`. O revisor cita o literal e o script o procura no documento. Esperado ancorado em `D<n>` é procurado na fala do usuário e nos documentos que ela cita |
| **Modelo (autor)** | como implementar; a redação do plano e da consolidação; que perguntas fazer | um commit por tarefa; nada do que ele escreve relaxa gate |
| **Revisor (subagente)** | se cada aceite está provado; quais mutações tentar; o que **propor** ao usuário | `revisao validar`: evidência e esperado conferidos, e mutantes só da revisão vigente |
| **Script** | nada; só contabiliza e recusa | `.execucao.json`, fingerprint, selo do plano por onda |

O modelo não decide no lugar do usuário e **nunca cita o que o usuário não disse**. Citação é cópia
literal de uma fala dele (mensagem digitada ou resposta de request_user_input), nunca paráfrase nem a
pergunta que você escreveu. Se nenhuma fala sustenta a decisão, pergunte. Em pergunta que define **valor de
produto**, não marque opção como "(Recomendado)". O valor que só aparece na pergunta vale como esperado,
mas fica marcado como "proposto pelo agente" no parecer, e o painel conta as respostas que caíram na opção
recomendada.

**Decisão com finalidade.** Para dispensar um gate, registre a decisão dizendo para quê:
`decisao add … --para sem-teste --alvo T1.1`. Ela só vale para aquela finalidade e aquele alvo, e a fala é
conferida de novo no uso. As de `sem-teste`, `sem-commit`, `desbloquear`, `anular` e `base` valem **uma vez**.
Decisão sem `--para` não relaxa gate nenhum: serve de registro e de âncora de valor. As finalidades são:
sem-teste, sem-commit, sem-mutante, equivalente, fora-do-onde, skill-alterada, analise-alterada, desbloquear,
anular, base, oraculo, sem-padrao, sem-analise, configurar, preexistentes, testar, fora-de-ordem,
descartar-pendencia. Só decisão do usuário revoga decisão do usuário.

**Decisão de engenharia.** Com a autorização do usuário (`decisao add --autoriza engenharia --fonte usuario
--citacao …`, uma vez por projeto), você decide sozinho dois casos: `decisao engenharia --para equivalente
--alvo M<n>` (um sobrevivente de sessão do revisor) e `--para fora-do-onde` (arquivo na mesma pasta de um item
do `Onde`). Nos dois, escreva a justificativa. Cada uma vale uma vez e nunca serve de valor esperado.
`fechar-onda` e o parecer listam todas, para o usuário rever em lote; revogar a autorização derruba as que
ainda não foram usadas.

**O ambiente não é seu.** As variáveis `EXEC_DEMANDA_*` só existem no autoteste. Em projeto real, o comando
que as encontra no ambiente **recusa**: tire-as.

## Regras que não se contornam

1. **Nada é assumido.** O que não foi perguntado vai no plano como `[A VERIFICAR]`, e a onda que o contém
   não inicia. Não existe seção de premissas, e aceite sem origem (análise, ER ou decisão) é recusado.
2. **Erro ou dúvida: pare e espere o usuário.** Não contorne gate, não escolha por ele entre duas leituras
   da análise, não "resolva" teste falhando mexendo no teste.
3. **Rodar teste é decisão do usuário, uma vez por projeto** (`decisao add --autoriza testes`). Com ela, o
   gate roda **por tarefa, antes do commit**, e a suíte inteira da onda em execução fica coberta. Comando com
   `-D` de banco pede decisão a cada vez. Sem teste fresco, nada fecha.
4. **Teste não se apaga, não se desliga e não se afrouxa para passar.** Se o teste está errado segundo a
   análise, pare e pergunte.
5. **Aprovar o plano autoriza trabalho e commit local daquele plano.** O selo é **por onda**: a parte comum
   do plano (contexto, decisões, fora do escopo) mais a seção de cada onda. Mudou a parte comum ou a seção da
   onda em execução: nada anda até nova aprovação. Acrescentar ou mudar uma onda que ainda não começou **não
   para** a que está em execução; ela só precisa ser aprovada antes do `iniciar-onda` dela, e uma fala pode
   aprovar várias de uma vez. A análise também é selada na aprovação. Seção de onda encerrada não muda.
   **Depois da 1ª revisão, o escopo da onda congela:** a correção vai sob a tarefa dona do aceite, e requisito
   novo vira pendência e outra onda. Push, banco, deploy e publicação pedem ok explícito, cada um.
6. Respeite o `AGENTS.md` (ou `GEMINI.md`) aplicável e o escopo aprovado. Alterações de manifests e dependências
   seguem as regras e padrões acordados para o projeto.
7. **Commit:** mensagem descritiva em PT-BR, conforme o projeto, sem pressupor hook de prefixo, sem `Co-Authored-By`, sempre por
   `demanda.py commit` ou ligado depois com `vincular`.
8. **Autor ≠ revisor.** A revisão da onda é de um subagente novo. Quem implementou confere antes
   (autoconferência), mas não revisa e não cria mutante.

## Passo 1 — escolher o projeto

Confirme a pasta da demanda, criando-a somente no modo de execução e quando autorizada. Não deduza pelo diretório. Se já houver `.execucao.json`,
vá para **Retomar** antes de qualquer outra coisa.

## Passo 2 — configurar os repositórios

Para cada repositório que a demanda toca, **confirme com o usuário** o caminho e o perfil, e registre:

```powershell
& $PY $D configurar "<pasta-da-demanda>" --repo api --caminho "C:/caminho/repositorio-api" --perfil maven
& $PY $D configurar "<pasta-da-demanda>" --repo web --caminho "C:/caminho/repositorio-web" --perfil angular --sem-testes --decisao D3
```

Os perfis são `maven`, `angular` e `generico`. Pedem decisão do usuário (`--para configurar`): `--sem-testes`,
trocar o comando de teste ou de build, e afrouxar o gate de padrão. A branch vem do `.documentacao.json` ou
de `--branch`; sem nenhum dos dois, o script recusa. Pergunte; nunca use a branch em que o repositório está.
O gate de padrão (opcional), `--maven-repo-local` e o lint estão em `referencias/executar-onda.md`.

## Passo 3 — planejar

Leia `referencias/planejar.md` e `referencias/formatos.md`. Parta da `analise.md` (e da ER, se houver)
e carregue as lições (`licao list --escopo <repo>`). Cada resposta do usuário que o plano usa vira decisão,
com a fala dele citada literalmente (`decisao add --fonte usuario --citacao "<trecho>"`; `--doc <arquivo>`
quando ele confirma um documento). Escreva `PLANO.md` e rode `validar-plano`. Erro impede seguir.
Sem análise nem ER, só com a decisão do usuário: `validar-plano --sem-analise D<n> --plano-base <arquivo>`.

Mostre ao usuário as ondas, os aceites, as decisões e cada `[A VERIFICAR]` e ponto em aberto, e pergunte se
aprova (request_user_input). **Pare aqui.** Só com a resposta dele:

```powershell
& $PY $D aprovar-plano "<pasta-da-demanda>" --citacao "<o trecho da resposta dele>"
```

A fala tem de ser posterior à validação desta versão do plano. Resposta com ressalva não é aprovação:
ajuste, valide e pergunte de novo. A saída diz quais ondas a aprovação cobre.

## Passo 4 — iniciar a onda

`iniciar-onda "<pasta-da-demanda>" N` recusa se a onda (ou a parte comum) não é a aprovada, se há `[A VERIFICAR]` ou
ponto em aberto ligado à origem dela, se a anterior está aberta (salvo `--fora-de-ordem D<n>`) ou se o
repositório está fora da branch. Mostra as lições confirmadas: aplique-as.

## Passo 5 — tarefas

Leia `referencias/executar-onda.md`. Por tarefa: diga os arquivos, a abordagem e como verificar; implemente;
faça `git add` só do que é da tarefa; e

```powershell
& $PY $D testar "<pasta-da-demanda>" --repo api --classes '<ClasseDaTarefaTest>'
& $PY $D commit "<pasta-da-demanda>" --tarefa T2.1 -m "<assunto>: <o que a tarefa entrega>"
```

O `commit` recusa se as classes do campo **Teste** não rodaram OK sobre o código que vai nele, se há
alteração fora do índice dentro do `Onde`, ou se há arquivo fora do `Onde` — aí vale a decisão do usuário,
a de engenharia (só arquivo vizinho) ou o plano corrigido e aprovado de novo.

Decisão que o plano não previa: **pare**, pergunte (request_user_input, com as opções que o código sugere) e
registre. O que aparecer fora do escopo vai para pendência; não entra de carona. **Depois da 1ª revisão,
todo commit é correção** dela: `commit --tarefa <dona do aceite> --correcao RV<k>`.

## Passo 6 — testes e evidências

`testar` grava log, contagem e fingerprint, e classe pedida que não aparece no relatório reprova a
execução. Não diga "os testes passam" sem um `E<n>` OK. `testar --build` cobre o repositório sem suíte, e
`evidencia --tipo roteiro --arquivo evidencias/<roteiro>.md` registra o roteiro de tela, cujo formato estrito
está em `referencias/formatos.md`. Uma execução registrada por engano se anula com
`execucao anular --id E<n> --decisao D<n>`. `--intencao vermelho-esperado|verde|regressao` é só registro.

## Passo 7 — consolidar

`consolidar "<pasta-da-demanda>" N` cria ou atualiza os blocos gerados de `ONDA-N-consolidacao.md`. O resto é seu:
abertura, decisões, **Verificado** e **Não verificado** (citando `E<n>`, `RV<n>`, `M<n>`, `P<n>`, `D<n>` ou
`A<onda>.<k>`; "Não verificado" pode ser só "nada"), defeitos, pendências e armadilhas. Marque `[x]` no plano
os aceites entregues; isso não quebra o selo. Aceite que caiu é decisão do usuário e pede nova aprovação.

## Passo 8 — autoconferência (ondas normal e grande, antes da 1ª revisão)

Antes de chamar o revisor, confira você mesmo a tabela de aceites que ele vai conferir. Onda leve dispensa.

```powershell
& $PY $D autoconferencia iniciar "<pasta-da-demanda>" N
# preencha "Aceite a aceite" (mesmo formato da revisão) e "Asserções rasas"
& $PY $D autoconferencia validar "<pasta-da-demanda>" N
```

Só passa com todo aceite OK, esperado e evidência conferidos. O autor **não muta**: quem escolhe o mutante é o
revisor. O que não passa vira teste antes da revisão, ou pergunta ao usuário se a análise não define o valor.

**Da 2ª revisão em diante** não há autoconferência. No lugar dela, você reaplica e mata cada sobrevivente da
revisão anterior sobre o código de agora (`mutante preparar --autor`, `mutante reaplicar`, `mutante
limpar`), e o `revisao iniciar` recusa listando o que falta. A rodada mecânica do Passo 9 dispensa isso.
Antes de levar ao usuário o valor de um teste para matar um sobrevivente, rode o caso com o mutante aplicado:
a descrição do que o mutante faz é hipótese até ser conferida.

## Passo 9 — revisão independente

Dispare sem perguntar de novo: fechar a onda é pedido do usuário. Primeiro rode `revisao iniciar "<pasta-da-demanda>"
N`. Ele recusa sem autoconferência válida, ou, da 2ª em diante, sem a reaplicação dos sobreviventes. Depois
lance **um subagente novo** (`invoke_subagent` com `TypeName: "self"` e `Role: "Independent Reviewer"` no Antigravity, `collaboration.spawn_agent` no Codex, ou `Agent` no Claude Code) com o prompt de `referencias/revisor.md`, preenchido.
O subagente lê o código, roda os mutantes (`referencias/mutantes.md`), escreve `revisao-onda-N.md` e devolve o
veredito e as lacunas. Não mande a ele o seu raciocínio de implementação. Use o modelo padrão na 1ª revisão;
em onda leve e nas rodadas de confirmação com subagente, use o modelo herdado da sessão e o prompt incremental.

Toda lacuna ranqueada começa por uma classe: `teste-fraco`, `especificacao`, `defeito`,
`pendencia-nao-bloqueante` ou `equivalente-candidato`.

**REPROVADA:** leve ao usuário, numa rodada de perguntas, tudo o que a rodada pede dele: valores para as
lacunas, equivalentes (os que não forem de engenharia) e requisitos novos. Para achado fora dos aceites, a
opção padrão é **pendência**, com a gravidade que o revisor deu, e reabrir a onda é a opção explícita. Só
regressão de gravidade alta reabre por padrão. Gravidade **alta** é o que quebra um aceite já fechado, perde
dado, abre falha de segurança ou deixa o sistema indisponível; o resto é baixa. Depois:

- **lacuna** → correção sob a tarefa dona do aceite (`commit --correcao RV<k>`), com o teste da tarefa fresco;
- **requisito novo / achado fora dos aceites** → `pendencia add --onda N --origem RV<k> --severidade alta|baixa
  --texto …`, e entra numa onda seguinte com `**Origem:** P<n>`;
- **equivalente** → `mutante equivalente --decisao D<n>` (do usuário, ou de engenharia).

**Rodada de confirmação.** A 2ª e a 3ª revisão confirmam, não reabrem. O revisor roda primeiro `mutante
reconfirmar`, que reaplica os sobreviventes e os mortos que perderam a herança e tira a amostra de alarme da
herança relaxada. Mutante novo só entra em **linha** alterada desde a revisão anterior ou em aceite ainda sem
morto válido; o script recusa mutar código já aprovado.

**Rodada mecânica (`revisao confirmar "<pasta-da-demanda>" N`).** Use-a quando a revisão anterior reprovou só por
`teste-fraco`, `equivalente-candidato` ou `pendencia-nao-bloqueante`, com todo aceite OK e as pendências
registradas, e desde então só mudou arquivo de teste. Ela dispensa o subagente: o script abre a revisão,
reaplica o que a anterior pediu, relocaliza a evidência na linha nova do teste, escreve o relatório e o
valida. A elegibilidade é conferida pelo registro da validação, não pelo arquivo. A rodada mecânica conta
para o teto. Se não for elegível, o script diz por quê e você lança o subagente.

**Teto de 3 revisões.** A 4ª não existe. A 3ª reprovada **bloqueia a onda**. Leve ao usuário os três caminhos
e registre a escolha dele: `onda desbloquear "<pasta-da-demanda>" N --caminho fechar-com-pendencias|replanejar|abandonar
--decisao D<n>`, com uma decisão posterior ao bloqueio. Fechar com pendências só vale com o código igual ao da
3ª revisão; replanejar leva o que falta a uma onda nova (`**Origem:** D<n>`); abandonar obriga o parecer a dizer
o que ficou de fora.

## Passo 10 — fechar

`fechar-onda "<pasta-da-demanda>" N --simular` lista o que falta; sem `--simular`, fecha. Recusa sem qualquer um destes:
- a onda igual à aprovada e sem `[A VERIFICAR]`;
- um commit por tarefa, e nenhum commit sem tarefa;
- teste fresco e verde de toda classe citada ou alterada, sem teste desligado, removido ou pulado além do que
  já estava no início;
- a **suíte inteira** fresca por repositório tocado. A falha preexistente só passa com
  `--preexistentes D<n>`, e depois o fechamento recusa classe nova falhando;
- o mínimo de mutantes mortos pelo porte, em linhas distintas do código alterado, ao menos um por aceite
  testável, com zero sobreviventes;
- a revisão APROVADA e válida, ou REPROVADA com as pendências aceitas pelo `desbloquear`;
- os aceites marcados;
- a consolidação com Verificado e Não verificado;
- a skill igual à do início.

Ao fechar, ele limpa os worktrees órfãos, comprime os logs de mutante, atualiza o painel e lista as pendências
e as decisões de engenharia da onda.

## Passo 11 — lições

Registre uma lição (`referencias/licoes.md`, `--escopo` = o repositório onde ela vale) para cada um destes
sinais: sobrevivente, aceite sem evidência, teste removido, gate que falhou, desvio do plano, armadilha da
consolidação. Armadilha de repositório nasce confirmada; os outros sinais pedem duas ocorrências. Parecida
com uma que existe: `--mesma L-NNN` ou `--nova`. Lição sobre o método não é lição: diga ao usuário, que decide
se a skill muda. Onda limpa não registra nada.

## Passo 12 — parecer de liberação

Com todas as ondas fechadas, leia `referencias/parecer.md`: `parecer iniciar`, o revisor (subagente novo)
preenche, `parecer validar`. O parecer reconfere os mutantes de cada onda fechada pelas regras de hoje, faz a
triagem das pendências sem onda (alta é erro; baixa tem de ser citada) e traz, na seção 6, as decisões de
engenharia e os valores propostos pelo agente, para o usuário rever.

Mostre o veredito, os achados e as condições. **Pare aqui.** Push e homologação são do usuário.

## Painel, grafo e métricas

`estado painel "<pasta-da-demanda>"` (`--html` para a página) e `estado metricas`: tempo × esforço × qualidade por onda,
decisões na opção recomendada e de engenharia, esperados propostos, pendências — e, numa aba, o grafo que amarra
análise → ER/ET → plano → execução e mostra as lacunas entre eles (`grafo "<pasta-da-demanda>"` abre direto nele) —
`referencias/painel.md`. Só leitura, e não é gate.

## Retomar

Antes de qualquer edição numa demanda com `.execucao.json`, rode `estado reconciliar "<pasta-da-demanda>"` e leia
`referencias/retomar.md`. Evidência vence narrativa: o que o git mostra ganha do que o ESTADO-ATUAL diz.
Proponha o próximo passo ao usuário antes de escrever código.

## Quando algo não fecha

O script diz o que falta e recusa: **nunca contorne um gate para passar.** Quando a mensagem pede decisão,
**pare, pergunte ao usuário** e registre a resposta com `decisao add --para …`. As mensagens, uma a uma, com o
que fazer e o que perguntar, estão em `referencias/problemas.md`.

## Limites conhecidos

O script prova muito, mas não tudo. Diga isto ao usuário quando for relevante:
- **Autoria da revisão.** O script não prova que o `revisao-onda-N.md` foi escrito pelo subagente.
- **O log de falas é um arquivo.** Quem tem acesso ao disco pode escrever nele: a prova vale contra erro e
  atalho do modelo, não contra adulteração deliberada.
- **A semântica da citação não é conferida.** O script confere que o trecho foi dito, na resposta e no projeto
  certos, mas não que ele sustenta aquela decisão. Citar uma fala verdadeira para uma decisão que ela não
  cobre é o mesmo que inventar.
- **O que impede e o que só dificulta.** O agente roda como o mesmo usuário. Editar à mão o `.execucao.json`
  ou o log de falas não tem selo; para isso seria preciso controle de acesso do sistema e hook de git. A
  asserção tautológica é recusada como evidência, mas a ligação entre o valor do Esperado e o Trecho não é
  conferida.
- **Ambiente fora do fingerprint.** `.m2`, `node_modules` linkado e banco não entram: um teste "fresco" pode
  ter rodado contra outra dependência (`configurar --maven-repo-local` reduz o risco).
- **ER.** A coordenada `ER x.y` só tem o formato conferido; o literal do esperado é procurado no texto da ER.

## Limites da adaptação

Não depende de outra skill de documentação: use a análise fornecida ou o plano-base autorizado.
A revisão independente usa um subagente novo, sem o raciocínio do autor; se a ferramenta estiver
indisponível, informe o impedimento, sem apresentar autoconferência como revisão independente.
O autoteste usa fixtures sintéticas e não substitui a execução dos testes reais de cada projeto.
