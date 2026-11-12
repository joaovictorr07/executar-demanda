# Quando algo não fecha

Mensagem do script → o que fazer. O script já diz o que falta; aqui está o **caminho com o usuário** que a
mensagem não imprime. Regra geral: o que a mensagem pede como decisão, pergunte (request_user_input) e registre com
`decisao add`; nunca contorne o gate para passar.

- **"nenhuma fala do usuário registrada" / "hook não instalado"** — confira a configuração em
  `~/.codex/hooks.json` e a confiança do hook no Codex. Configuração não comprova ativação.
  Se a resposta de uma ferramenta não foi capturada, peça confirmação textual após ativar o coletor;
  não fabrique o registro nem dispense o gate.
- **"a citação não está em nenhuma fala do usuário"** — você parafraseou, citou a própria
  pergunta ou só o começo da resposta. Copie o trecho literal da resposta dele; se ele não disse,
  pergunte.
- **"a fala citada foi dita fora deste projeto"** — a fala é de uma sessão aberta noutro
  diretório (outro projeto, a home). Pergunte de novo numa sessão aberta no repositório ou na
  pasta do projeto.
- **"rodar testes é decisão do usuário e o projeto não tem autorização de testes"** — pergunte
  se ele autoriza rodar as classes das tarefas e os mutantes do revisor sem pedir a cada vez;
  com o sim, `decisao add --autoriza testes`. Com o não, `--decisao D<n>` por execução.
- **"sem analise.md e sem ER"** — gere a análise, ou registre a decisão dele de seguir
  com o plano base (`validar-plano --sem-analise D<n> --plano-base <arquivo>`).
- **"a fala citada é anterior à versão atual do plano"** — ele aprovou outra versão. Mostre a
  atual (`plano diff`) e pergunte de novo.
- **"o plano mudou depois da aprovação"** (no `validar-plano` e no parecer) / **"a parte comum do plano … mudou"** /
  **"a seção da onda N mudou"** — `plano diff`, mostre ao usuário, `validar-plano`, pergunte,
  `aprovar-plano`. Não desfaça a mudança só para passar sem mostrar. Mudança só numa onda que não
  começou não para a em execução.
- **"a onda N ainda não foi aprovada"** — onda nova ou mudada, no `iniciar-onda` dela. Mostre a seção
  ao usuário e, com a resposta dele, `aprovar-plano`; uma fala pode aprovar várias ondas.
- **"Onda N: a seção mudou depois da aprovação e a onda já está fechada"** — seção de onda encerrada
  não muda. Desfaça a edição nela; o que falta vai para uma onda nova.
- **"a onda … é de antes da 0.4.0 … e não está encerrada"** — onda histórica aberta. Leve ao usuário:
  fechá-la com a versão 0.3.1 da skill, ou replanejar o que falta numa onda nova (com a decisão dele).
- **"a análise … mudou depois da aprovação AP<n>"** — alguém revisou a `analise.md`. Mostre ao
  usuário o que mudou (a cópia selada está em `evidencias/plano-aprovado/AP<n>-analise-…md`; `diff` a
  compara), e se muda o plano, ajuste-o e `aprovar-plano` de novo (isso sela a análise nova). Se foi só
  correção de texto, `--analise-alterada D<n>` com a decisão dele em `iniciar-onda` ou `fechar-onda`.
- **"item #n de ASSUNTO sem aceite"** — o `**Funcional**` da análise tem um item que nenhum aceite cita.
  Cite-o no aceite que o prova, `(análise: ASSUNTO #n)`, ou, se sai da entrega, ponha
  `ASSUNTO #n: fora desta entrega, D<n>` em `## Fora do escopo` com a decisão do usuário. Num plano já
  aprovado é aviso, não bloqueio.
- **"… fonte analise; relaxar um gate é decisão do usuário"** — decisão tirada de documento não
  autoriza exceção de gate. Pergunte.
- **"… foi registrada sem finalidade"** — decisão sem `--para` não relaxa gate: serve de registro e
  de âncora de valor. Pergunte, se a fala dele não cobre este fim, e registre `decisao add … --para
  <finalidade> --alvo <alvo>`.
- **"… foi registrada para … não para …"** — cada decisão serve a uma finalidade e a um alvo.
  Registre outra para este.
- **"não tem autorização de engenharia"** — o projeto não autorizou o modelo a decidir equivalente e
  arquivo vizinho. Peça a decisão do usuário para este caso, ou pergunte se ele dá a autorização
  (`decisao add --autoriza engenharia`).
- **"… é decisão de engenharia … este gate é do usuário"** — a decisão de engenharia só vale para
  `equivalente` e `fora-do-onde`. Para qualquer outro gate, registre a do usuário, com citação.
- **"decisão de engenharia é só para …"** / **"--alvo de equivalente é um M<n> sobrevivente de sessão
  do revisor"** / **"justificativa curta demais"** — engenharia não decide outro caso, nem mutante do
  autor; e a justificativa diz por quê, porque o usuário a revê no parecer.
- **"… (engenharia, …) já foi usada — vale uma vez"** — registre outra, com a justificativa deste caso.
- **"… é decisão de engenharia, e ela só cobre arquivo na mesma pasta de um item do Onde"** — o arquivo
  listado está longe do `Onde`: pede a decisão do usuário (`--para fora-do-onde`) ou o plano corrigido
  e aprovado de novo.
- **"o valor `…` só aparece na pergunta que o modelo escreveu"** (aviso da revisão) — o usuário
  respondeu à pergunta, e o valor vale como esperado, mas o parecer o mostra na seção 6 como
  "proposto pelo agente". Se ele só aceitou a opção que você ofereceu, confirme o valor com ele.
- **"Esperado sem âncora" / "o valor … não está no documento citado"** — o revisor tirou o valor
  do código, ou do texto que você escreveu ao registrar a decisão. Com âncora `D<n>`, o valor tem
  de estar na fala do usuário (a pergunta que ele respondeu conta) ou num documento que ela cita
  e foi ligado à decisão (`--doc`, `decisao anexar`). Se ninguém define o valor, é LACUNA e
  pergunta ao usuário.
- **"… não aparece na fala citada — o usuário não confirmou esse documento"** — pergunte citando
  o nome do arquivo; só então `--doc`.
- **"roteiro recusado: sem a linha Código" / "rodou sobre outro código" / "já foi registrado"** —
  `estado fingerprint --repo` antes de executar o roteiro, a linha no cabeçalho, um arquivo novo
  por execução. Código mudou depois do roteiro: o roteiro roda de novo.

- **"nenhuma execução de teste OK sobre o código atual"** — o código mudou depois do teste.
  Rode de novo (com a autorização de testes; sem ela, peça).
- **"o .execucao.json mudou depois que este comando o leu"** — outra sessão ou o revisor
  gravou no meio. Nada foi gravado; rode o comando de novo.
- **"a réplica no scratch não reproduz o repositório real"** — algo gerado pela cópia ficou fora
  do `.gitignore`. Mostre o arquivo ao usuário; não mexa no `.gitignore` sem ok.
- **"… casou classes homônimas"** (aviso do `testar`) — o nome simples pedido existe em mais de
  um pacote, e o resultado soma todas. Para provar uma só, peça o nome qualificado
  (`logus.….FooServiceTest`), no `testar` e no `--testes` do mutante.
- **"a seleção não passa SEM mutação"** — os testes já falham no scratch (ex.: `.m2` da branch
  errada). Nenhum mutante conta. Pare e mostre o log.
- **Mutante `nao_compila`** — não conta. Escolha uma mutação de comportamento que compile.
- **Sobrevivente que nenhum teste poderia distinguir** — o revisor propõe nas lacunas; decide o
  usuário, ou você com a autorização de engenharia (`decisao engenharia --para equivalente --alvo
  M<n>`); então `mutante equivalente --motivo … --decisao D<n>`. Na dúvida, não é equivalente: o
  teste está fraco.
- **"nenhuma revisão iniciada" / "revisão vencida" no `mutante preparar`** — mutante é trabalho
  do revisor sobre o código que ele revisa: `revisao iniciar` antes.
- **"o autor não muta antes da 1ª revisão"** — a autoconferência é só a tabela de aceites e as
  asserções rasas. `--autor` serve para reaplicar sobreviventes de uma revisão antes da seguinte.
- **"esta é a sessão de pré-revisão do autor"** / **"esta sessão é da rodada mecânica"** — nelas só se
  reaplica (`mutante reaplicar`, `aplicar --reaplica M<n>`); mutante novo é do revisor.
- **"sem autoconferência válida sobre o código atual não há revisão"** — Passo 8. Mudou o código
  depois da autoconferência, ela venceu: inicie outra.
- **"o teto é 3"** / **"onda … bloqueada"** — a 3ª revisão reprovou. Leve ao usuário os três
  caminhos do `onda desbloquear` e registre a escolha dele (decisão nova, posterior ao bloqueio).
  Nunca uma 4ª revisão. A rodada mecânica conta para o teto.
- **"escopo congelado desde a 1ª revisão"** — tarefa ou aceite novo na onda revisada. Desfaça no
  plano: lacuna se corrige com `commit --correcao RV<k>` sob a tarefa dona; o que é novo vira
  `pendencia add` e outra onda.
- **"commit agora é correção de lacuna — `--correcao RV<k>`"** — a onda já foi revisada.
- **"rodada de confirmação — … não mudou desde a RV<k>"** — mutar código já aprovado reabre a
  revisão (vale a linha, não o arquivo). Rode `mutante reconfirmar` e mute só o que a correção mudou.
- **"esta seria a 2ª/3ª revisão … não reaplicou e matou"** — sessão `mutante preparar --autor` +
  `mutante reaplicar` dos sobreviventes listados, `mutante limpar`; sem autoconferência.
- **"a rodada não pode ser mecânica — …"** — o `revisao confirmar` lista os motivos (lacuna de outra
  classe, aceite sem OK, pendência não registrada, código de produção mudado, plano da onda mudado,
  trecho que não se acha uma vez só). Não ajeite o caso para caber: registre a pendência que falta, se
  for só isso; senão, faça a pré-revisão, `revisao iniciar` e lance o subagente.
- **"ALARME: … sobreviveu na amostra da herança relaxada"** — o morto herdado já não morre com o
  código de agora: a herança relaxada da onda cai para a estrita, e o sobrevivente é lacuna.
- **"herança relaxada … a amostra de alarme pede N"** — `mutante reconfirmar` na sessão desta revisão.
- **"lacuna N sem classe"** — o item começa por `teste-fraco`, `especificacao`, `defeito`,
  `pendencia-nao-bloqueante` ou `equivalente-candidato`.
- **"--severidade alta|baixa é obrigatória"** — todo `pendencia add` diz a gravidade: alta é o que
  quebra um aceite já fechado, perde dado, abre falha de segurança ou deixa o sistema indisponível.
- **"o fechamento exige a suíte inteira"** / **"classe(s) nova(s) falhando"** — `testar --suite-inteira`
  sobre o código atual; falha que já existia antes da demanda é decisão do usuário
  (`--preexistentes D<n>`, só na primeira vez); classe nova falhando é defeito.
- **"… não rodou OK sobre o código que vai no commit"** — rode as classes da tarefa e commite em
  seguida (commit não vence o teste). Dispensa: `--sem-teste D<n>` do usuário.
- **"alteração fora do índice dentro do Onde"** — `git add` ou desfaça antes do commit.
- **"a skill mudou desde o início da onda"** — alguém mexeu na skill com a onda aberta. Mostre ao
  usuário; para fechar, `--skill-alterada D<n>` com a decisão dele.
- **"N tarefas — acima de 15 é decisão do usuário"** — divida a onda, ou registre a decisão dele e
  escreva `**Tamanho:** D<n>` na onda.
- **"seção Qualidade e riscos fora dos aceites ausente ou vazia"** — o revisor tem de dizer o que
  leu além dos aceites, mesmo que não ache nada.
- **"teste comentado" / "teste desligado" / "caso(s) de teste removido(s)"** — vale para `@Test` e
  para `it(`/`test(` de spec JS/TS. Teste não se desliga para passar: pare e pergunte.
- **"onda N, reconferida pelas regras atuais"** (no parecer) — a onda fechada não passa hoje no gate
  de mutantes sobre o código do fechamento dela. Leve ao usuário: reabrir a prova (mutantes novos
  sobre o código daquela onda) ou aceitar o risco como achado do parecer, com a D<n> dele. Onda
  histórica não dá erro: o mesmo aparece como aviso ("histórica … não satisfaz o critério atual").
- **"aceite … tem teste automatizado e nenhum mutante morto que o prove"**, com a prova só em arquivo de
  teste (um `beforeAll`, o próprio spec) — não há linha de produção para mutar, e teste não se muta.
  Pergunte ao usuário; com a decisão dele, `fechar-onda --sem-mutante A<id> --sem-mutante-decisao D<n>`.
  O script só aceita se a revisão vigente deu o aceite como OK com toda a evidência em arquivo de teste;
  a dispensa fica na onda e o parecer tem de citá-la.
- **"commit … desde o início da onda sem tarefa"** — `vincular` à tarefa certa; se não pertence
  a tarefa nenhuma, pergunte.
- **"… não é posterior ao início da onda"** no `vincular` — o commit é a própria base da onda (feito
  fora de onda, antes do `iniciar-onda`), e nenhuma linha dele conta como alterada na onda. Com a
  decisão do usuário, antes de qualquer trabalho da onda: `onda base "<projeto>" <onda> --repo <repo>
  --head <commit anterior> --decisao D<n>`, e então `vincular`. Reset no git não
  resolve: a base gravada continua a mesma.
- **"o assunto final tem o prefixo 2 vezes"** — o hook duplicou; mostre ao usuário. Não
  conserte com `--amend` (o hook reprefixa).
- **Revisão vencida** — o código (o conteúdo, não o commit) mudou depois de `revisao iniciar`.
  Inicie outra; ela conta para o teto.
- **Projeto antigo sem `PLANO.md`** (formato anterior) — não
  converta sozinho. Pergunte se quer migrar o plano para o formato novo ou usar só `testar`,
  `mutante`, `estado` e a revisão sobre ele.
