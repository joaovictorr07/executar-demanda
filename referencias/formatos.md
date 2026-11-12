# Formatos

Os artefatos ficam na pasta do projeto (`<pasta-da-demanda>/`), nunca nos repositórios.

| Arquivo | Quem escreve |
|---|---|
| `.execucao.json` | só o `demanda.py` |
| `PLANO.md` | você (o script só grava a linha `**Commits:**` de cada tarefa e o bloco de decisões) |
| `ONDA-N-consolidacao.md` | você; blocos `gerado:` pelo script |
| `ONDA-N-andamento.md` | opcional, diário de bordo com horário |
| `autoconferencia-onda-N.md` | você (o autor), antes da 1ª revisão |
| `revisao-onda-N.md` | o subagente revisor; bloco de mutantes pelo script; na rodada mecânica, todo pelo script |
| `ESTADO-ATUAL.md` | você; seção 1 (painel) pelo script |
| `PAINEL.html` | só o script (`estado painel --html`, `estado reconciliar --html` ou `grafo`; opcional, se mantém em dia depois de criado; inclui o grafo) |
| `PARECER-LIBERACAO-AAAA-MM-DD.md` | o revisor; seções 2, 3 e 6 pelo script |
| `evidencias/testes/`, `evidencias/mutantes/` | só o script (logs; os de mutante viram `.log.gz` no fechamento; `mutantes/blobs/<sha1>` guarda as cópias para a herança relaxada) |
| `evidencias/plano-aprovado/` | só o script (cópia de cada versão aprovada, para o `plano diff`) |
| `evidencias/decisoes/` | só o script (cópia congelada do documento que cada decisão cita) |
| `.execucao.json.lock` | só o script (trava do projeto enquanto um comando grava; pode ficar na pasta) |

## Identificadores — namespaces fechados

| Prefixo | O quê | Escopo |
|---|---|---|
| `D<n>` | decisão | numerada pelo `decisao add`; livro único, no plano |
| `R<n>` | risco | plano |
| `A<onda>.<k>` | item de aceite | onda (`A2.1`, `A4b.3`) |
| `T<onda>.<k>` | tarefa | onda (`T2.1`) |
| `A<n>` (sem ponto) | achado de parecer | parecer; continua a numeração entre rodadas |
| `C<n>` | condição de liberação | parecer |
| `P<n>` | pendência: requisito novo achado na revisão, levado para outra onda | projeto; `pendencia add`, e a onda seguinte a cita na `**Origem:**` |
| `DF<n>` | defeito registrado (achado pelo processo ou escapado) | projeto; `defeito add`; só alimenta as métricas |
| `E<n>`, `S<n>`, `M<n>`, `AC<n>`, `RV<n>`, `AP<n>` | execução, sessão de mutação, mutante, autoconferência, revisão, aprovação do plano (com as ondas que ela aprovou) | gerados pelo script |
| letra (`a`…`bd`) | divergência de paridade | na ordem em que aparecem |

Defeito corrigido **não** ganha código D. Revogar uma decisão: `decisao revogar --id D2 --por D5`
(a tabela gerada mostra `~~D2~~ … **Revogada por D5**`).

## PLANO.md

````markdown
# <Nome da demanda> (NN/AAAA)

> Análise: `analise.md` · ER: `ER - NN／AAAA - Nome.docx` · Repos: `api`, `web` · Branch: `T27784-JVP`

## Contexto

<o problema, o que já existe (arquivo:linha), armadilhas confirmadas no código>

## Decisões

<!-- gerado:decisoes:inicio -->
<!-- gerado:decisoes:fim -->

## Fora do escopo

- <o que não entra, e por quê>

## Riscos

| # | Risco | Mitigação |
|---|---|---|
| R1 | <risco> | <mitigação> |

## Matriz de gate

| Repo | Camada | Teste exigido | Comando |
|---|---|---|---|
| api | service / builder | Mockito, por classe | `mvn -o test -Dtest=…` |
| web | tela | build + roteiro Playwright | `ng build` |

## Pontos em aberto da análise

| Assunto | Pergunta | Situação |
|---|---|---|
| <ASSUNTO> | <pergunta copiada literalmente da análise> | `Aberto` · ou · `Respondido — D3` · ou · `Fora desta entrega — D4` |

# Ondas

## Onda 1 — <assunto funcional, como na análise>

**Origem:** <ASSUNTO da análise>; ER 2.3.1–2.3.4
**Risco:** normal

**Aceite 1**

- [ ] A1.1 <resultado verificável, com valor concreto: "período de 32 dias no CE é recusado com a mensagem X"> (análise: <ASSUNTO>)
- [ ] A1.2 <…> — ER 2.3.2

### Tarefas

#### T1.1 — <uma entrega>

- **Repo:** api
- **Onde:** `src/main/java/.../FooService.java`, `src/test/java/.../FooServiceTest.java`
- **Aceite:** A1.1
- **Teste:** `FooServiceTest`
- **Gate:** rapido
- **Depende de:** —

#### T1.2 — <tela>

- **Repo:** web
- **Onde:** `src/app/.../foo.component.ts`
- **Aceite:** A1.2
- **Teste:** roteiro — passos 1 a 4 pela tela
- **Gate:** roteiro
- **Depende de:** T1.1
````

Regras que o `validar-plano` confere (ERRO): seções Contexto, Decisões (com o bloco gerado),
Fora do escopo e Matriz de gate; nenhuma seção ou linha de premissa; nenhuma linha `D<n>` fora
do bloco gerado, e toda `D<n>` citada existe no livro e não foi revogada; `**Origem:**` com
assuntos de grafia exata da análise (ou `ER x.y`, `D<n>`, `P<n>` existente); `**Risco:**` normal ou alto; onda com
`**Só testes:** sim` sem arquivo de produção no `Onde`; todo
aceite com ID, com origem (`(análise: …)`, `ER x.y`, `D<n>`) e com tarefa; **cada item de primeiro
nível do `**Funcional**` da análise** (e de `## Mudanças de comportamento`, quando é lista) citado por um
aceite não riscado como `(análise: ASSUNTO #n)` — `#1-3` e `#1,3` valem — ou em `## Fora do escopo`
(`ASSUNTO #n: …, D<n>` do usuário; sem `#n`, tira o assunto inteiro), ERRO num plano ainda não aprovado e
AVISO num já aprovado (e o `#n` além do último item do assunto é sempre erro); aceite riscado só com
`D<n>`; toda tarefa com Repo (da matriz), Onde, Aceite (existente na onda), Teste e Gate
(`rapido`, `completo`, `build`, `roteiro`); `Teste: nenhum` em repo com suíte só com `D<n>` do
usuário; aceite riscado, ponto `Respondido`/`Fora desta entrega` e assunto em `## Fora do escopo`
só com `D<n>` do **usuário** (decisão tirada da análise não tira nada do escopo); sem análise nem
ER, só com `validar-plano --sem-analise D<n>`; nenhuma frase que assume ("supõe-se", "assumimos",
"presume-se") nem `[A VERIFICAR]` em qualquer caixa fora do lugar;
dependência só para trás; IDs únicos; Situação dos pontos no vocabulário fechado; todo ponto da
análise copiado; todo assunto da análise numa onda ou fora do escopo com `D<n>`; **nenhuma tarefa
nem aceite novo numa onda depois da 1ª revisão dela**; nenhuma mudança na seção de onda encerrada.
Avisa: pendência `P<n>` sem onda
que a cite na Origem; tarefa
com mais de 3 itens em Onde, onda com mais de 10 tarefas, aceite só de testes (o mínimo de
mutantes fica mais brando para ele), teste automatizado sem classe entre crases, `[A VERIFICAR]`
(que bloqueia o `iniciar-onda`).

**Tamanho:** `**Tamanho:** D<n>` na onda, junto de `**Risco:**`, é a decisão do usuário que permite
uma onda **não fechada** com mais de 15 tarefas (sem ela, o `validar-plano` recusa; acima de 10,
avisa). Onda já fechada fica como está.

**Gates de tarefa:** `rapido` — as classes do campo **Teste**; `completo` — todas as classes de
teste do módulo tocado (nunca a suíte do repositório, que pede decisão do usuário); `build` — só
o build; `roteiro` — roteiro de tela registrado com `evidencia`.

Depois de validado, o plano é aprovado pelo usuário (`aprovar-plano --citacao`) e fica selado **por
onda**: a parte comum (tudo fora das seções `## Onda N —`) e a seção de cada onda. O registro `AP<n>`
guarda o hash da parte comum, o de cada onda e quais ondas ele aprovou (as novas ou mudadas desde a
aprovação anterior), mais a cópia do plano e da análise em `evidencias/plano-aprovado/`. Mudança fora
de `[x]`, `**Commits:**` e do bloco de decisões exige nova aprovação: na parte comum, para tudo; numa
onda, só para ela.

Classe de teste pode ser citada pelo nome simples ou qualificado; o script lê o relatório pelo
nome qualificado e casa os dois (registros antigos, gravados pelo nome simples, continuam valendo).

**Teste** com classe entre crases é o que o fechamento cobra: cada classe citada (e cada classe
de teste alterada na onda) tem de ter rodado sobre o código final. Globs valem (`Foo*Test`).
`nenhum — <motivo>` e `roteiro — <o quê>` não são automatizados.

## ONDA-N-consolidacao.md

Gerado por `demanda.py consolidar`. Seções, na ordem (o script cobra 6 e 7):

1. Commits — **gerado** (repo, commit, tarefa, assunto; situação do push)
2. O que mudou de estrutura
3. Decisões da rodada — **gerado** do livro (as `D<n>` registradas durante a onda)
4. Testes e evidências — **gerado** (execuções, fresca ou vencida) + Mutantes — **gerado**
5. Aceite da onda — **gerado** a partir do plano
6. Verificado — o que rodou e deu certo, com número
7. Não verificado — o que não rodou e por quê
8. Defeitos corrigidos na rodada — com hash
9. Pendências — com dono: `(do usuário)`, `(do DBA)`; as `P<n>` levadas desta onda, **gerado**
10. Armadilhas desta rodada — viram lição

Abertura: `**DD/MM/AAAA.**` + o veredito da onda numa frase.

**Tamanho (orientação, sem gate).** Uma consolidação lê-se de uma vez: em torno de 150 linhas, com
Verificado e Não verificado em listas curtas, números em vez de narrativa, e o histórico das
rodadas só por ponteiro para `revisao-onda-N.RV<k>.md` e `ONDA-N-andamento.md`. Consolidação longa
demais ninguém relê.

## revisao-onda-N.md

Gerado por `revisao iniciar`. Seções: Veredito (`**APROVADA**` ou `**REPROVADA**`), Aceite a aceite
(tabela), Asserções rasas, Testes sem aceite (mapeamento reverso: `| repo:caminho:linha | o que verifica |
destino |`, ou "nenhum" com as classes lidas; conferida quando o relatório tem a seção), Qualidade e
riscos fora dos aceites, Mutantes (gerado), Lacunas ranqueadas (cada item começa por `teste-fraco |
especificacao | defeito | pendencia-nao-bloqueante | equivalente-candidato`), Limites desta revisão.
Asserções rasas, Qualidade e Limites são obrigatórias, mesmo sem achado (diga o que foi lido).

Tabela de aceite: `| Aceite | Evidência | Trecho | Esperado (análise/ER) | Resultado |`.
Evidência `repo:caminho:linha` (várias separadas por `;`) ou `evidencia:<arquivo na pasta do
projeto>`. Trecho: o texto literal entre crases, que o script procura na linha citada e nas 3
seguintes. Esperado: a âncora (`análise`, `ER x.y` ou `D<n>`) e o valor literal entre crases, que
o script procura no documento citado — com âncora `plano base:`, no plano base do projeto que
segue sem análise; com âncora `D<n>`, na fala do usuário por trás da decisão (para resposta de
request_user_input, pergunta + resposta) e nas cópias congeladas dos documentos ligados a ela
(`--doc`/`decisao anexar`, em `evidencias/decisoes/`), não no texto que a registrou. O valor que
só aparece na pergunta vale, mas fica marcado como "proposto pelo agente" (aviso na revisão, seção 6
do parecer). Resultado: exatamente `OK`, `FALHA` ou `LACUNA`.

**Rodada mecânica.** O `revisao confirmar` escreve o `revisao-onda-N.md` inteiro, com "rodada mecânica
(`revisao confirmar`)" na linha Revisão do cabeçalho: a tabela de aceites é a da revisão anterior,
com a evidência relocalizada na linha nova do teste; Asserções rasas e Qualidade dizem que vale o que a
anterior registrou; Mutantes é o bloco gerado da reaplicação; as Lacunas são os sobreviventes que
voltaram a sobreviver (`teste-fraco`), ou "nenhuma". Não edite: o script já o validou.

## autoconferencia-onda-N.md

Gerado por `autoconferencia iniciar`, só antes da 1ª revisão de onda normal ou grande. Seções: Aceite
a aceite (mesma tabela e mesmas regras da revisão) e Asserções rasas. Não há seção de mutantes: o autor
não muta. Sem veredito: passa no `autoconferencia validar` só com todo aceite `OK`, esperado e
evidência conferidos, sobre o código atual. O `revisao iniciar` da 1ª revisão exige que passe; da 2ª em
diante, o exigido é a reaplicação dos sobreviventes pelo autor, sem arquivo de autoconferência.

## Roteiro (evidência de tela)

`.md` com a tabela de passos (`| Passo | Esperado | Obtido | Evidência | Aceite |`; Obtido preenchido em
todo passo) e, no cabeçalho, a linha `Código: <assinatura>` que `estado fingerprint --repo <repo>` imprime —
escrita **antes** de executar. O `evidencia` recusa assinatura diferente da do código atual e
arquivo já registrado. O formato é estrito: a tabela tem passos; o Obtido diz o que se obteve (não
"ok", não o Esperado copiado); a Evidência cita arquivo existente em `evidencias/` (selado no registro:
se ele mudar, o roteiro perde a vigência); o Aceite diz o `A<onda>.<k>` que o passo prova, e o
fechamento exige todo aceite de tarefa com gate roteiro coberto. Execução reprovada só porque uma
classe pedida não apareceu no relatório (exit 0, nenhuma falha), superada por execução OK posterior
sobre o mesmo código, não bloqueia o fechamento — só avisa.

## ESTADO-ATUAL.md

````markdown
# NN/AAAA — Estado atual e pendências

Atualizado em **DD/MM/AAAA**. …

## 1. Onde estamos

<!-- gerado:painel:inicio -->
(tabela Frente | Situação, com ✅ fechada · 🟡 em execução · ⏳ não iniciada, e uma linha por repositório;
depois, "Medição por onda (P8)": rodadas e vereditos, classes das lacunas, decisões do usuário,
autoconferências, mutantes novos / reconfirmados / desperdiçados, execuções que falharam por intenção)
<!-- gerado:painel:fim -->

### Onda N em detalhe

**Verificado:** …
**Não verificado:** … (motivo)

## 2. Pendências, na ordem

### 2.1 <fase> — do usuário
1. …
````

Pendência mora aqui e só aqui; as consolidações apontam para cá.

## PARECER-LIBERACAO-AAAA-MM-DD.md

Seções: Veredito, 1. Estado dos achados, 2. O que foi alterado (gerado), 3. Validação executada
(gerado), 4. Condições para a subida, 5. Limites deste parecer e 6. Decisões do modelo (blocos gerados
`engenharia` e `propostos`). Regras em `parecer.md`.
