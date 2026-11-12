# Planejar

Sai da análise (e da ER, quando existir) para um `PLANO.md` que o `validar-plano` aceite
e que o usuário aprove.

## Antes de escrever

0. **Sem `analise.md` nem ER**, o `validar-plano` recusa: o método pressupõe o documento
   de onde saem os valores esperados e os pontos em aberto. Solicite ou prepare a análise dentro do escopo autorizado
   ou pergunte ao usuário se segue com o **plano base** da pasta do projeto no lugar dela — e com
   o sim, `validar-plano --sem-analise D<n> --plano-base <arquivo>`. O plano base vira o
   documento-fonte: aceite com `(plano base: …)` e esperado com âncora `plano base:`.
1. Leia a `analise.md` inteira: assuntos, blocos Funcional/Técnico, Mudanças de
   comportamento, Fora do escopo, **Pontos em aberto**.
2. Leia o `AGENTS.md` de cada repositório que a demanda toca: eles dizem o padrão de
   teste, o que não se toca e o que precisa de validação manual.
3. Carregue as lições confirmadas: `demanda.py licao list --escopo <repo>`.
4. Leia o código no ponto que a demanda muda, o suficiente para saber **onde** mexer e **o que
   perguntar**. Ancore toda afirmação em `arquivo:linha`.

## Ondas

- **Uma onda por assunto funcional** (ou por análise/tela, numa migração), na ordem em que faz
  sentido entregar. A onda é vertical: back, front e teste do mesmo assunto juntos. Onda "de
  camada" (`Onda 1 — Backend`) só quando o assunto não existe sem a base (ferramental e núcleo
  compartilhado).
- **Até cerca de 10 tarefas por onda.** Acima disso o `validar-plano` avisa: divida num ponto
  real de dependência. Acima de 15, recusa — só com a decisão do usuário, escrita na onda como
  `**Tamanho:** D<n>`. A revisão e os mutantes cobrem a onda inteira de uma vez, e onda grande
  é revisão de muitas rodadas.
- `**Origem:**` cita o `### ASSUNTO` da análise com a **grafia exata** (vários separados por
  `;`), ou `ER x.y`, ou `D<n>`. O `validar-plano` recusa assunto que não existe na análise — é
  assim que o `iniciar-onda` acha os pontos em aberto que bloqueiam a onda, e grafia errada
  faria o bloqueio sumir.
- Todo assunto da análise tem onda, ou vai para `## Fora do escopo` com a decisão do usuário
  (`D<n>` na mesma linha). Assunto que some sem decisão é recusado.
- **Todo item do `**Funcional**` tem aceite.** O aceite cita o item pela posição, sem ID novo:
  `(análise: DESCONTO #2)` é o 2º item de primeiro nível (sub-item indentado é desdobramento, não item)
  do Funcional de DESCONTO; `#1-3` e `#1,3` valem. Vale igual para os itens de `## Mudanças de
  comportamento` da análise, quando são lista (`(análise: Mudanças de comportamento #1)`). O que sai da
  entrega vai para `## Fora do escopo` como `DESCONTO #2: fora desta entrega, D<n>` com a decisão do
  usuário. Os itens de `## Fora do escopo` da própria análise também reaparecem no plano (aviso). Reordenar
  a análise depois de aprovada muda o que o `#n` aponta: é por isso que o plano sela a análise.
- `**Risco:** alto` para cálculo fiscal, valor, estoque, integridade de dados, concorrência. Exige
  5 mutantes mortos em vez de 3.
- `**Só testes:** sim` na onda que só cria ou reforça testes, sem nenhuma linha de produção. O
  `validar-plano` recusa arquivo de produção no `Onde` dela. No fechamento, o mutante em linha
  anterior à onda conta se morreu por asserção numa classe de teste criada ou alterada na onda.
  Use só com a decisão do usuário.

## Aceite

- Um item por comportamento, **com o valor concreto**: a mensagem literal, o limite exato, o
  campo e o valor. "Tratar erro" não é aceite; "período acima de 31 dias no CE é recusado com
  409 e a mensagem 'Período máximo de 31 dias'" é.
- **Todo aceite cita de onde vem o valor**: `(análise: <ASSUNTO>)`, `ER 2.3.1` ou a decisão
  `D<n>`. Aceite sem origem é critério inventado — o `validar-plano` recusa. Se o valor não está
  em lugar nenhum, é pergunta ao usuário (e a resposta vira `D<n>`).
- Numa migração, o aceite de paridade diz contra o quê e com qual tolerância ("CSV idêntico ao
  legado nos 10 cenários, exceto divergências registradas em `excecoes.json`").

## Tarefas

- Uma entrega por tarefa: 1 a 3 arquivos, um componente, um endpoint, um builder.
- `**Onde:**` é caminho a partir da raiz do repositório: o arquivo (`src/app/foo.ts`), uma pasta
  que contém os arquivos (`src/app/foo/`) ou um glob em que `*` fica dentro da pasta e `**`
  atravessa (`src/app/**/*.spec.ts`). Nome solto (`package.json`) é o arquivo da raiz, não
  "qualquer arquivo com esse nome".
- **O teste mora na mesma tarefa** que o código que ele prova. "Testado em outra tarefa" é
  adiamento de teste.
- `**Teste:**` com as classes entre crases. Repositório sem suíte (web, api-logus-report):
  `roteiro — <passos>` com `**Gate:** roteiro`, ou `nenhum — só build` com `**Gate:** build`.
  `nenhum` num repositório **com** suíte só com a decisão do usuário que dispensou (`D<n>`).

## O que não foi perguntado

Não existe premissa. Tudo o que você não sabe e o usuário não disse:

- vira pergunta ao usuário agora, com as opções que o código sugere (em pergunta que define **valor
  de produto** — limite, mensagem, regra de cálculo —, nenhuma opção marcada "(Recomendado)": o hook
  grava as opções e a recomendada, e o painel conta as respostas que caíram nela); ou
- vai para o plano como `[A VERIFICAR]` na onda que depende disso — e essa onda não inicia
  enquanto o marcador existir.

Cada linha de `## Pontos em aberto` da análise é copiada **literalmente** (o script compara o
texto inteiro) para `## Pontos em aberto da análise` do plano, com a Situação num vocabulário
fechado:

| Situação | Quando |
|---|---|
| `Aberto` | ninguém respondeu ainda — a onda cuja origem tem esse assunto não inicia |
| `Respondido — D<n>` | a resposta foi registrada com `decisao add` (fonte usuário, com a fala dele citada) |
| `Fora desta entrega — D<n>` | o usuário tirou da entrega |

"A confirmar", "Pendente", "Respondido" sem `D<n>`: recusados. Ponto cujo assunto não é origem
de nenhuma onda tem de estar `Fora desta entrega`.

## Decisões

Toda resposta do usuário que o plano usa entra por `decisao add`, nunca à mão:

```powershell
& $PY $D decisao add "<projeto>" --texto "<a decisão, em uma frase>" `
    --fonte usuario --citacao "<trecho literal da fala dele>"
& $PY $D decisao add "<projeto>" --texto "…" --fonte analise --ref "<ASSUNTO>"
```

A citação é cópia do que ele digitou ou respondeu — não paráfrase, não a pergunta que você fez.
Se a fala confirma um documento da pasta do projeto, passe `--doc <arquivo>` (o nome tem de estar
na fala); o conteúdo é congelado e o revisor pode tirar o valor esperado dele.
O script confere no log do hook. A tabela de `## Decisões` do plano é o bloco gerado
`<!-- gerado:decisoes:inicio -->…<!-- gerado:decisoes:fim -->`: deixe os marcadores no esqueleto e
não escreva linhas `D<n>` fora dele. Revogar: `decisao revogar --id D2 --por D5` (a revogação
também é uma decisão).

## Autorizações do projeto

No começo, numa pergunta só, ofereça as duas como opções (ele escolhe nenhuma, uma ou as duas):

- **testes** — rodar as classes das tarefas, a suíte inteira da onda em execução e os mutantes do
  revisor sem pedir a cada vez: `decisao add --autoriza testes --fonte usuario --citacao "<trecho
  dele>"`. `-D` de banco, push e deploy continuam pedindo ok a cada vez.
- **engenharia** — você decide sozinho, com justificativa, dois casos: mutante equivalente (só
  sobrevivente do revisor) e arquivo vizinho fora do `Onde` (mesma pasta de um item dele):
  `decisao add --autoriza engenharia --fonte usuario --citacao "<trecho dele>"`. Cada decisão de
  engenharia vale uma vez, nunca serve de valor esperado, e o `fechar-onda` e o parecer as listam
  para ele rever; revogar a autorização derruba as que ainda não foram usadas.

Sem a de testes, cada execução leva `--decisao D<n>`; sem a de engenharia, esses dois casos são
decisão dele.

## Validar e parar

```powershell
& $PY $D validar-plano "<projeto>"
```

Erro: corrija e valide de novo. Aviso: mostre ao usuário. Depois mostre as ondas, os aceites e
as perguntas pendentes e **pare** até ele aprovar. Com a resposta dele:

```powershell
& $PY $D aprovar-plano "<projeto>" --citacao "<trecho literal da aprovação>"
```

**O selo é por onda.** A aprovação sela a parte comum (contexto, decisões, fora do escopo…), a seção
de cada onda e a análise. A saída diz quais ondas ela cobre: as novas ou mudadas desde a anterior —
uma fala aprova várias de uma vez. Depois (menos `[x]` nos aceites, linhas `**Commits:**` e decisões
novas):

- mudou a **parte comum** ou a seção da **onda em execução**: nada anda até mostrar o `plano diff` e
  aprovar de novo;
- acrescentou ou mudou uma onda **que não começou**: a em execução segue; a nova só precisa ser
  aprovada antes do `iniciar-onda` dela;
- seção de onda **encerrada** não muda: o que falta vai para uma onda nova.
