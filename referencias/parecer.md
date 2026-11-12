# Parecer de liberação

Documento de decisão, emitido quando todas as ondas estão fechadas. Um por rodada: a segunda revisão não apaga a primeira; o topo diz qual sucede qual.

## Fluxo

1. `demanda.py parecer iniciar "<projeto>"` → `PARECER-LIBERACAO-AAAA-MM-DD.md`, com as seções 2
   (o que mudou por repositório), 3 (validação executada) e 6 (decisões do modelo) geradas do git e
   do `.execucao.json`.
2. Um **subagente novo** revisa a entrega inteira (o diff de cada repositório desde o início da
   primeira onda), com o mesmo método do `revisor.md`, e preenche veredito, achados, condições e
   limites.
3. `demanda.py parecer validar "<projeto>"` até dar 0 erro. Parecer que não veio do `parecer
   iniciar` é recusado (não há como saber sobre que código foi escrito).
4. Mostre ao usuário veredito, achados e condições. **Pare.** Push e homologação são dele.

## Veredito

Primeiro negrito da seção `## Veredito`, um de três:

- **GO** — nenhum achado pendente;
- **GO COM CONDIÇÕES** — há condição `C<n>` em aberto na seção 4 e nenhum pendente bloqueante;
- **NO-GO** — o resto.

Logo abaixo: quantos achados, quantos bloqueantes, quantos corrigidos, improcedentes, fora do
escopo.

O script recusa GO ou GO COM CONDIÇÕES se: o plano não é o aprovado; alguma onda não está
fechada; alguma onda fechada não passa, **pelas regras de hoje**, no gate de mutantes sobre o
código do fechamento dela; algum repositório não tem teste (ou build, no repositório sem suíte)
OK sobre o código atual; há mutante sobrevivente válido; o código mudou depois do `parecer iniciar`; a tabela de achados
está vazia sem a frase "nenhum achado" na seção 1.

**Ondas históricas** (iniciadas antes da 0.4.0): o que delas não satisfaz o critério de hoje, nos
mutantes ou numa pendência sem severidade, aparece como **aviso**, não como erro.

**Pendências sem onda.** `pendencia add` registra o achado com severidade. No GO e no GO COM
CONDIÇÕES: pendência **alta** sem onda que a tenha na `**Origem:**` (`P<n>`) e não descartada pelo
usuário (`pendencia descartar --decisao D<n>`) é erro; pendência **baixa** sem onda precisa estar
citada (`P<n>`) num achado ou numa condição.

**Ondas que pararam pelo `onda desbloquear`.** Onda `replanejada` não conta como
aberta (o que faltava foi para outra onda). Onda `abandonada` exige que o parecer diga o que
ficou de fora — cite "Onda N" num achado ou condição. Onda fechada **com pendências aceitas**
exige cada pendência (o aceite `A<n>.k` e o mutante `M<n>`) citada num achado ou numa condição.

## 1. Estado dos achados

`| # | Achado | Onde | Estado |`. `A<n>`, com a numeração continuando entre rodadas. Estado
começa por um de:

| Estado | Exige |
|---|---|
| **Corrigido** | o commit entre crases (tem de existir) |
| **Não procede** | a seção que explica (`§n`) |
| **Fora do escopo** | a decisão `D<n>` do usuário que tirou do escopo (fonte usuário, com citação) |
| **Aceito** | a decisão `D<n>` do usuário aceitando o risco (fonte usuário, com citação) |
| **Pendente** | acrescente "bloqueante" se impede a subida |

Aceitar risco e tirar do escopo são decisões do usuário: o revisor propõe, o usuário responde,
`decisao add`, e só então o achado muda de estado. Revisão sem achado nenhum: escreva "nenhum
achado" na seção, dizendo o que foi lido — tabela vazia não distingue revisão limpa de revisão
não feita.

Achado novo encontrado durante a correção entra em negrito na tabela.

## 4. Condições para a subida

Lista numerada `C<n>`. Cumprida: `~~C2 …~~ **Cumprida em DD/MM/AAAA** — como`.

## 5. Limites deste parecer

Obrigatório. O que não foi verificado: tela não vista, banco não usado, fluxo que só roda no
pooling, carga concorrente.

## 6. Decisões do modelo

Dois blocos gerados, que o `parecer validar` reescreve; não os edite:

- `<!-- gerado:engenharia:… -->` — as decisões de engenharia (`decisao engenharia`): para quê, o
  alvo, a justificativa, quem autorizou e se foi usada. Com alguma no livro, o parecer sem este bloco
  é recusado.
- `<!-- gerado:propostos:… -->` — os **valores esperados propostos pelo agente**: o literal da revisão
  que só aparece na pergunta que o modelo escreveu (o usuário respondeu a ela). Vale como esperado,
  mas fica aqui para o usuário conferir se é o valor que ele quis.

Mostre a seção ao usuário junto com o veredito. A decisão de engenharia que ele não aceitar, ele
revoga (`decisao revogar --id D<n> --por D<m>`), e o caso volta a ser decisão dele.

## Supersessão

Parecer novo que muda o que um anterior dizia: no topo do novo, "Sucede o [parecer de DD/MM](…)";
no antigo, uma linha de citação no topo: `> **Parcialmente superado pelo [parecer de DD/MM](…).**
<o que deixou de valer>`.
