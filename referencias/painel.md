# Painel

`estado painel "<pasta-da-demanda>"` atualiza o bloco do `ESTADO-ATUAL`, e `--html` cria o `PAINEL.html`: uma página
só, sem biblioteca externa, que funciona offline. Depois de criada, `fechar-onda` e `estado reconciliar` a mantêm
em dia. `grafo "<pasta-da-demanda>"` é um atalho que gera a mesma página (`--json` imprime o modelo do grafo, `--abrir` abre
no navegador).

A página tem abas, e o endereço de cada uma funciona como link (`#grafo`, `#ondas`…):
- **Visão geral:** cards, as ondas com o veredito de cada revisão e as lacunas entre os artefatos.
- **Grafo:** a amarração análise → ER/ET → plano → execução (abaixo).
- **Ondas:** rodadas de revisão e mutantes por onda, e a medição P8 (decisões na opção recomendada e de engenharia,
  esperados propostos, lacunas por classe). Clicar numa linha leva à onda no grafo.
- **Métricas:** tempo × esforço × qualidade e as medianas por rótulo de regras.
- **Pendências:** por situação (sem onda, cobertas, descartadas), com a severidade. Clicar leva à pendência no grafo.
- **Repositórios:** branch, HEAD, push e arquivos não commitados.

A página leva o texto de aceites, tarefas, decisões e pendências; **nunca** a fala nem a citação literal do usuário.

`estado metricas` mostra a tabela e as medianas por rótulo de regras (`r1`–`r3` históricas e `atual`). Isso
permite comparar o antes e o depois. Registre defeito com `defeito add --origem revisao|parecer|posterior`.
Sem esse registro, o painel mostra 0 escapados: isso é ausência de registro, não de defeito. As métricas são
estimativas e nada disto é gate.

## O grafo

Os nós e as arestas saem dos arquivos do projeto, sem gravar nada neles. Dá para ver em **Fluxo** (colunas da esquerda
para a direita: análise, assunto, onda, item, aceite, tarefa, execução, revisão, pendência; a especificação numa
faixa abaixo e as decisões e o parecer noutra, cada faixa com o seu título) ou em **Força** (estilo Graph View do
Obsidian). Dá para focar numa onda (o seletor também a seleciona, destacada), buscar por ID ou texto e filtrar por tipo.

**Ler um nó:** passar o mouse abre um balão com o texto inteiro (aceite, tarefa, decisão, pendência) e as lacunas do
nó — sobre o nó no desenho e sobre qualquer item da página que aponte um nó (vizinho, resultado da busca, lacuna,
card de onda, linha das abas Ondas e Pendências). O rótulo no desenho é cortado pela largura da coluna, com `…`, e
aparece sempre que cabe uma linha por nó na tela. Clicar seleciona: o painel lateral mostra o texto e os **vizinhos
agrupados por relação e sentido** (`aceite ▸` é o que o nó aponta, `◂ cobre` é quem aponta para ele), cada um com o
começo do texto; clicar num vizinho desliza até ele. As arestas do nó selecionado levam o nome da relação (cobre,
testa, mira…). Cada nó visitado entra no histórico: **Voltar** do navegador volta ao anterior e o endereço
(`#grafo/aceite:A1.2`) é o link do nó.

**Seguir a amarração:** selecionar um nó já esmaece o que não está na cadeia dele (do que o originou ao que ele
gerou). **Duplo clique** no nó, ou o botão *Isolar a cadeia*, deixa só a cadeia visível e reenquadra; ir a um vizinho
com a cadeia isolada troca para a cadeia do vizinho, sem perder o isolamento. **Esc** sai do isolamento; outro Esc
limpa a seleção. A cadeia anda coluna a coluna; do nó raiz leva também o vizinho da mesma coluna (a decisão ao lado
do aceite). Dentro de cada coluna a ordem é a do plano e dos documentos (`T6.1` antes de `T6.4`). Com uma onda em
execução, o grafo abre focado nela; sem onda ativa, abre com todas.

**Nós:** análise, assunto, item (o `#n` do Funcional e das Mudanças de comportamento), ponto em aberto, título e
requisito da ER e da ET (coordenada `X.Y.Z`, até o terceiro nível), esboço, script de banco, onda, aceite, tarefa,
decisão, revisão, pendência e parecer. Commit, execução, mutante e os requisitos da ER/ET ficam recolhidos num `+N`
do nó pai; clique no pai ou marque o tipo para vê-los. Lição não entra: ela é global.

**Arestas:** assunto→ER e assunto→ET (o `####` de mesmo nome); ER↔ET (mesma coordenada); onda→assunto (`Origem`);
aceite→item (`análise: ASSUNTO #n`); aceite→ER (`ER x.y`); aceite→decisão (`D<n>`); tarefa→aceite; tarefa→tarefa
(`Depende de`); tarefa→commit; execução→tarefa (classe de teste); mutante→aceite; revisão→aceite; pendência→revisão;
ET→esboço (`[[PRINT]]`).

**Lacunas** (borda vermelha no nó, lista na lateral e na Visão geral; a mesma mensagem em vários nós vira uma linha
`N× mensagem` que abre a lista). Faltas de amarração: assunto sem onda e fora do
"Fora do escopo"; item do Funcional sem aceite; aceite sem tarefa; tarefa sem Gate ou sem Teste; `ER x.y` citada que não
existe na ER; ponto em aberto sem resposta. Avisos, que podem errar porque dependem de casar nome: assunto sem `####` de
mesmo nome na ER ou na ET; requisito `2.x` da ER sem par na ET; esboço sem `[[PRINT]]` **na ET** (a ET carrega a
sequência de prints; só na ER também é aviso); aceite de onda iniciada sem mutante, revisão OK nem roteiro.

Sem plano, sem ER/ET ou sem análise o grafo sai com o que existe. O nó da análise some quando nada se liga a ele
(projeto que segue sem análise).
