# Executar uma onda

## Por tarefa

1. **Declare antes de escrever**: arquivos que vai tocar (os do `Onde`), abordagem em uma frase,
   como vai verificar. O que não souber, pergunte; não anote como suposição.
2. **Teste a partir do aceite, não do código.** O valor esperado vem da análise/ER (a mensagem,
   o limite, o campo). Nunca escreva o teste lendo a implementação e afirmando o que ela faz.
   Sem valor preciso na análise: é pergunta ao usuário, não asserção vaga.
3. **Implemente o mínimo** que entrega o aceite, no padrão do `AGENTS.md` mais próximo.
   Sem refatoração de passagem, sem "já que estou aqui". Onde ele não cobre o caso, siga a prática
   dominante do código do repositório, não o exemplo isolado que achar.
4. **Gate da tarefa:** com a autorização de testes do projeto, `demanda.py testar --classes` das
   classes do campo **Teste** antes do commit. Falhou: mostre o log e pare. O `commit` confere:
   classe da tarefa sem execução OK sobre o código que vai no commit é recusada, e o commit não
   vence o teste — a identidade é o conteúdo. Gate `build` pede build fresco; `roteiro` e `Teste:
   nenhum` não pedem nada no commit. Dispensar o gate é do usuário: `--sem-teste D<n>`.
5. `git add` só o da tarefa e `demanda.py commit --tarefa T<n>.<k> -m "<Domínio>: <o que mudou>"`.
   Quando a convenção legada estiver configurada, o script recusa prefixo manual; também recusa `Co-Authored-By`, marcador `DEBUG-/WIP-<sigla>`, plano
   diferente do aprovado, alteração fora do índice dentro do `Onde` (o teste viu o working tree, o
   commit leva o staged) e arquivo fora do `Onde` (ver **Desvios**). Com o padrão ligado, recusa
   também a violação de padrão (ver **Repositório: perfil, padrão e lint**). **O padrão mecânico é do gate, não do
   revisor: corrija no commit, não deixe para uma onda de limpeza.**
6. Commit feito fora do script (IDE, terminal): `demanda.py vincular --tarefa … --hash …` — com
   as mesmas regras do `commit` (Onde, mensagem, branch do projeto, padrão e o gate de teste da
   tarefa: só confere o HEAD com a árvore limpa; commit antigo pede `--sem-teste D<n>`). Tarefa que
   termina sem commit (só verificação, só banco) é decisão do usuário: `sem-commit --motivo …
   --decisao D<n>`.

## Repositório: perfil, padrão e lint

Configurados por repositório no `configurar` (Passo 2 do SKILL.md):

- **Perfil** (obrigatório na primeira vez): `maven` (teste por classe via `-Dtest={classes}`,
  contagem dos XML do Surefire, `target/` copiado para o scratch), `angular` (`ng build`,
  `node_modules` linkado) ou `generico`. Se o `.m2` não tem o artefato certo da branch,
  `--maven-repo-local <pasta>`: pergunte, não reinstale nada. `--sem-testes` (derruba o gate de teste
  e de mutantes do repositório) e trocar o comando de teste ou de build pedem `--decisao D<n>` do
  usuário: com um `--teste` qualquer, tudo passaria.
- **Gate de padrão** (opcional): `configurar … --padrao maven|angular` liga a conferência do que o
  `AGENTS.md` pede e um script consegue ver nas linhas **acrescentadas**: fim de linha preservado (o
  arquivo mantém o CRLF ou LF que já tem; arquivo novo segue a maioria dos irmãos da pasta; EOL misto
  pede decisão), 120 colunas (HTML fica de fora), `TODO`/`FIXME` em comentário (erro), comentário
  sobre a própria mudança (aviso) e import sem uso (aviso). Sem o campo `padrao`, o repositório fica
  como está. Ligar é livre; `--padrao-desligar eol,colunas,…`, `--padrao-colunas N` acima do atual
  (0 desliga) e `--padrao nenhum` pedem `--decisao D<n>`.
- **Lint**: `--lint "<cmd>"` (pede `--decisao D<n>`) roda no commit e no fechamento; exit ≠ 0 recusa.
  Ele roda no working tree, por isso o `commit` com alteração fora do índice e o `vincular` de commit
  que não é o HEAD com a árvore limpa são recusados.

Com o padrão ligado, o `commit` (e o `vincular`, sobre o commit já feito) confere o diff e recusa a
violação objetiva; o `fechar-onda` confere de novo o diff da onda inteira, inclusive no repositório
sem suíte. Violação intencional (o TODO que o usuário pediu, a linha longa gerada) se dispensa **por
regra**, com a decisão dele: `--sem-padrao colunas=D<n>` (`eol`, `colunas`, `comentario`, `import`,
`lint`). A dispensa usada fica na onda, com os arquivos em que valeu, para o parecer citar; no
`fechar-onda` ela cobre só esses arquivos.

## Asserção que não é rasa

A pergunta de controle: **esse teste passaria com uma implementação errada plausível?** Se sim,
é raso. Os casos que mais aparecem com Mockito:

- só `verify(mock).metodo(any())` sem conferir o estado ou o valor que saiu;
- `any()` onde o argumento é justamente o que o aceite fixa;
- só `assertNotNull` / `assertTrue(lista.size() > 0)` quando o aceite fixa o conteúdo;
- "não lançou exceção" como única asserção, quando o aceite fixa um resultado;
- só o caminho feliz quando o aceite tem exceção, limite ou mensagem de recusa.

Para cada campo de um objeto devolvido, gravado ou emitido que o aceite cita, a asserção é sobre
o **valor** dele, não sobre a chamada que o produziu.

## Testes

Rodar teste é do usuário, uma vez por projeto: `decisao add --autoriza testes` com a resposta dele
autoriza as classes das tarefas e os mutantes do revisor. Sem ela, cada execução leva `--decisao
D<n>`. Rode as classes tocadas. A suíte inteira da onda em execução fica coberta pela autorização
do projeto (o fechamento a exige); `-D` de banco pede decisão a cada vez. `--intencao
vermelho-esperado|verde|regressao` registra o que a execução pretendia provar e não muda gate:

```powershell
& $PY $D testar "<projeto>" --repo api --classes 'FooServiceTest,Bar*Test'
```

Falhou: mostre o log e **pare**. Não mexa no teste para passar; se o teste está errado segundo
a análise, pergunte.

## Desvios

- Decisão que o plano não tinha: **pare e pergunte** (request_user_input, com as opções que o
  código sugere e o `arquivo:linha` de cada uma). Com a resposta, `decisao add --fonte usuario
  --citacao "<trecho dele>"`. Você não decide e depois avisa.
- O código precisa divergir do plano (outra tarefa, aceite que não cabe, arquivo longe do `Onde`):
  pare, mostre ao usuário, e com o ok dele ajuste o plano e aprove de novo (`validar-plano`,
  `aprovar-plano`), ou registre a decisão dele (`commit --decisao D<n>`, finalidade `fora-do-onde`).
- **Arquivo vizinho** (na mesma pasta de um item do `Onde`): com a autorização de engenharia do
  projeto, você decide sozinho — `decisao engenharia --para fora-do-onde --texto "<por que ele entra
  nesta tarefa>"` e `commit --decisao D<n>`. Vale uma vez, só cobre o vizinho (arquivo de outra pasta
  no mesmo commit pede a do usuário) e aparece no `fechar-onda` e no parecer.
- Bug ou melhoria fora do escopo: Pendências, com dono. Não entra na onda. Achado fora dos aceites
  que a revisão traz vira `pendencia add --severidade alta|baixa`; só regressão de gravidade alta
  (quebra comportamento que um aceite já fechado garante, perda de dado, segurança, indisponibilidade)
  reabre a onda, e mesmo assim a escolha é do usuário.
- **Depois da 1ª revisão da onda**, o escopo congela: lacuna se corrige com `commit --correcao
  RV<k>` sob a tarefa dona do aceite; requisito novo é `pendencia add --onda N --origem RV<k>
  --severidade alta|baixa` e entra numa onda seguinte com `**Origem:** P<n>`.

## Roteiro de tela

Antes de executar: `demanda.py estado fingerprint "<projeto>" --repo <repo>` e a linha `Código:
<assinatura>` no cabeçalho do roteiro. Execute, preencha **Obtido** em todo passo e registre com
`evidencia`. O formato é estrito (`formatos.md`): cada passo diz o que obteve, a evidência que o
prova e o aceite que cobre. Código mudou depois: roteiro novo, num arquivo novo.

## Fechamento

1. `consolidar` → escreva as seções humanas; marque `[x]` os aceites entregues no plano. As
   decisões da onda aparecem sozinhas (bloco gerado do livro).
2. **Autoconferência** (onda normal ou grande, **só antes da 1ª revisão**; a leve dispensa):
   `autoconferencia iniciar`, preencha a tabela de aceites e as asserções rasas como o revisor
   faria, `autoconferencia validar`. Só segue com todo aceite OK, esperado e evidência conferidos.
   **O autor não muta**: mutante é do revisor. **Da 2ª revisão em diante** não há autoconferência:
   `mutante preparar --autor` abre a sessão de pré-revisão, e `mutante reaplicar` reaplica e mata
   cada sobrevivente das revisões anteriores sobre o código de agora (mutante novo é recusado).
3. `revisao iniciar` → subagente revisor (`revisor.md`), que roda os mutantes dentro dessa revisão.
   Reprovação só por `teste-fraco`, `equivalente-candidato` ou `pendencia-nao-bloqueante`, corrigida
   só em teste: `revisao confirmar` (rodada mecânica, sem subagente e sem a pré-revisão). No máximo 3
   revisões, a mecânica inclusa: a 3ª reprovada bloqueia a onda, e o caminho é do usuário (`onda
   desbloquear`).
4. `testar --suite-inteira` em cada repositório tocado (a suíte inteira fresca é gate do
   fechamento; falha preexistente só registrada com `--preexistentes D<n>` do usuário, na primeira
   vez). `fechar-onda --simular` → mostre ao usuário o que falta; `fechar-onda`.
5. Lições (`licoes.md`).
