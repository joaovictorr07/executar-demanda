# Lições

Camada adaptada do tlc-spec-driven: falha real vira regra reaproveitável, e o script cuida da
contabilidade para o arquivo não apodrecer. A loja é global (`~/.codex/executar-demanda/licoes/`), porque as
demandas mudam e os repositórios não — e é por **repositório** que a lição vale.

## Quando registrar

Depois de fechar a onda (ou de uma revisão REPROVADA), uma lição por sinal:

| Sinal | Quando |
|---|---|
| `mutante_sobrevivente` | um mutante sobreviveu e virou tarefa |
| `aceite_sem_evidencia` | a revisão deu LACUNA num aceite |
| `teste_removido_ou_ignorado` | o fechamento pegou teste desligado ou removido |
| `gate_falhou` | teste ou build falhou sobre código que se achava pronto |
| `desvio_do_plano` | o código teve de divergir do plano |
| `armadilha` | cada item de "Armadilhas desta rodada" que vale para outra demanda |

Onda limpa não registra nada. Isso é o resultado certo, não um esquecimento.

```powershell
& $PY $D licao add --projeto "<pasta-da-demanda>" --sinal armadilha --escopo api --onda 2 `
    --fonte "ONDA-2-consolidacao.md §Armadilhas" `
    --texto "Repositório novo só é dado como provado depois de rodar com banco: o driver Informix recusa BigInteger"
```

- **A regra geral, não o incidente.** ✅ "Aceite de período cita o limite de cada ramo" · ❌ "o
  teste da linha 88 estava fraco".
- **A mesma lição com outras palavras soma, não cria.** O `licao add` mostra as lições do mesmo
  repositório com texto parecido (semelhança de palavras ≥ 0,15) e recusa sem uma escolha:
  `--mesma L-NNN` soma a ocorrência àquela lição (o texto dela fica); `--nova` cria outra. O script
  só sugere — quem julga se é a mesma regra é você.
- `licao parecidas [--escopo api]` lista os pares parecidos já registrados; `licao fundir --id L-A
  --em L-B --motivo "…"`, com o ok do usuário, junta A em B (ocorrências e fontes) e tira A do
  playbook.
- `--fonte` é obrigatória: sem âncora é opinião, e o script recusa.
- `--escopo` é o apelido de um repositório **configurado no projeto** (`api`, `ui`); o script grava
  também a pasta dele (`logus-corporativo-api`), que é o que junta a mesma lição entre projetos.
- **Lição é sobre o código, não sobre o método.** O que ensina a usar a skill, o harness ou uma
  ferramenta (fingerprint, hook, Playwright, `TaskStop`) não tem repositório e é recusado: diga ao
  usuário, que decide se a skill muda. É a regra do tlc — opinião sobre o processo é decisão de
  quem mantém, não lição.
- `--onda`: a onda em que o sinal apareceu (padrão: a em execução).

## Ciclo

**Armadilha** de um repositório nasce **confirmada**: esperar a segunda ocorrência deixaria quase
toda armadilha candidata, longe do `iniciar-onda`. Os outros sinais: candidata → **confirmada**
quando aparece em **2 ocorrências distintas (projeto, onda)** no mesmo repositório — o análogo das
features do tlc. Lição sobre o método já registrada, com o ok do usuário: `licao descartar --id
L-NNN --motivo "…"`. O `fechar-onda` avisa quando a onda
teve sinal e nenhuma lição registrada para ela: diga ao usuário por quê. Candidata sem recorrência em
180 dias é podada. Confirmada que foi aplicada e a mesma falha voltou: `licao penalize --id
L-NNN`; duas vezes, quarentena.

## Leitura

No planejamento e no `iniciar-onda` (que já as mostra): `licao list --escopo <repo>`. Só as
confirmadas valem como regra.
