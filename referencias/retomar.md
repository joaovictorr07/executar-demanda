# Retomar

Toda sessão que pega uma demanda em andamento começa por:

```powershell
& $PY $D estado reconciliar "<projeto>"
```

Ele mostra, por repositório: branch (e se é a do projeto), HEAD, `origin` == HEAD ou quantos
commits sem push, arquivos não commitados, e se o último teste ainda vale para o código atual.
Mostra também a onda em execução com as tarefas pendentes, commits sem tarefa e sessões de
mutação que ficaram abertas.

## Evidência vence narrativa

O que o ESTADO-ATUAL, a consolidação ou a memória da conversa dizem é hipótese. O git e o
`.execucao.json` são o fato.

- Tarefa com commit no repositório e sem registro → `vincular`, não refaça.
- Commit feito fora de onda que uma onda nova vai levar → planeje a onda e, antes de iniciá-la,
  confira que o HEAD não é ele: o `iniciar-onda` grava o HEAD como base, e o `vincular` recusa o
  commit que é a base. Se já iniciou, `onda base --head <anterior> --decisao D<n>` (do usuário).
- Trabalho não commitado que você não reconhece → **pare e pergunte**; não descarte.
- Teste "verde" no texto e vencido no `reconciliar` → está vencido. Rode de novo com a autorização
  de testes do projeto (`decisao list` mostra a `--autoriza testes`); sem ela, pergunte.
- Sessão de mutação aberta → `mutante limpar`; os mutantes dela só valem se o repositório ficou
  intacto.
- ESTADO-ATUAL com "sem push" e `origin` == HEAD → texto velho; `estado painel` regenera a seção 1.
- `validar-plano` diz "o plano mudou depois da aprovação" → alguém editou o plano sem nova
  aprovação. `plano diff` mostra o quê; leve ao usuário antes de qualquer outra coisa — não
  desfaça nem reaprove por conta própria.
- `reconciliar` ou `validar-plano` diz "a análise … mudou depois da aprovação AP<n>" → alguém revisou
  a análise depois de o plano ser selado. `diff` entre a cópia selada (`evidencias/plano-aprovado/`)
  e a análise atual mostra o quê; leve ao usuário: se muda o plano, ajuste-o e `aprovar-plano`; se foi
  só texto, `--analise-alterada D<n>` dele em `iniciar-onda` ou `fechar-onda`.
- Decisão que "ficou combinada" numa sessão anterior e não está no livro (`decisao list`) **não
  existe**. Pergunte de novo.
- Onda **bloqueada** (a 3ª revisão reprovou) → nada anda até o usuário escolher o caminho:
  `onda desbloquear --caminho fechar-com-pendencias|replanejar|abandonar --decisao D<n>`.
- "aviso: onda N — a skill mudou desde o início da onda" → diga ao usuário; fechar assim pede
  `--skill-alterada D<n>` dele.
- Evidência registrada por engano → `execucao anular --id E<n> --decisao D<n>`; não registre por
  cima.

Depois de reconciliar, proponha ao usuário o próximo passo e espere o ok antes de escrever código.

## Pausa

Ao parar no meio de uma onda: `estado painel` (seção 1 atualizada) e, na seção de detalhe do
ESTADO-ATUAL, o que está em andamento (`arquivo:linha`), o próximo passo e o que bloqueia. Não
repita pendência fora do ESTADO-ATUAL.
