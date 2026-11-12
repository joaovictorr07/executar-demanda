#!/usr/bin/env python3
"""Execução de uma demanda em ondas, com gates que o script faz valer.

Uma CLI só, para poupar chamadas (como o er_et.py do skills-documentacao). O primeiro argumento
posicional de quase todo subcomando é o projeto: "NN - AAAA", "NN/AAAA" ou um caminho (só o
número não: o ano é do usuário dizer).

Uso:
    demanda.py configurar PROJ --repo api --caminho C:/repositorio-api --perfil maven [--branch B]
               [--teste CMD] [--build CMD] [--sem-testes] [--maven-repo-local DIR] [--decisao D<n>]
    demanda.py repos PROJ
    demanda.py decisao add PROJ --texto "..." --fonte usuario --citacao "<literal do usuário>" [--autoriza testes]
    demanda.py decisao add PROJ --texto "..." --fonte analise --ref "<ASSUNTO>" | --fonte er --ref 2.3.1
    demanda.py decisao add PROJ ... --fonte usuario --citacao "..." --doc desenho.md   (documento que a fala cita)
    demanda.py decisao anexar PROJ --id D1 --doc desenho.md
    demanda.py decisao revogar PROJ --id D2 --por D5
    demanda.py decisao list PROJ
    demanda.py validar-plano PROJ [--sem-analise D<n> --plano-base plano-base.md]
    demanda.py aprovar-plano PROJ --citacao "<literal do usuário aprovando>"
    demanda.py plano diff PROJ
    demanda.py iniciar-onda PROJ 2 [--fora-de-ordem D<n>]
    demanda.py commit PROJ --tarefa T2.1 -m "Análise Rentabilidade: ..." [--decisao D<n>]
    demanda.py vincular PROJ --tarefa T2.1 --hash abc123 [--decisao D<n>]
    demanda.py sem-commit PROJ --tarefa T2.4 --motivo "..." --decisao D<n>
    demanda.py testar PROJ --repo api --classes 'FooServiceTest,Bar*Test' | --build | --suite-inteira [--intencao vermelho-esperado|verde|regressao]
                       [--preexistentes D<n>] [--decisao D<n>]
    demanda.py evidencia PROJ --repo web --tipo roteiro --arquivo ONDA-2-roteiro.md
    demanda.py mutante preparar PROJ --repo api [--autor] [--decisao D<n>]
    demanda.py mutante aplicar PROJ --arquivo src/.../X.java --linha 42 --de ">" --para ">=" \\
                                     --aceite A2.1 --testes XTest
    demanda.py mutante aplicar PROJ --reaplica M12 [--linha N]       (autoconferência: o sobrevivente de novo)
    demanda.py mutante reaplicar PROJ                                 (todos os sobreviventes pendentes)
    demanda.py mutante equivalente PROJ --id M4 --motivo "..." --decisao D<n>
    demanda.py mutante limpar PROJ [--sessao S1]
    demanda.py consolidar PROJ 2
    demanda.py autoconferencia iniciar|validar PROJ 2
    demanda.py revisao iniciar PROJ 2 [--decisao D<n>]   (da 4ª rodada em diante)
    demanda.py revisao validar PROJ 2
    demanda.py fechar-onda PROJ 2 [--simular]
    demanda.py parecer iniciar|validar PROJ [--arquivo PARECER-...md]
    demanda.py estado reconciliar|painel PROJ [--json] [--html]
    demanda.py estado metricas PROJ [--json]                         (tempo × esforço × qualidade, estimativas)
    demanda.py defeito add PROJ --onda N --origem revisao|parecer|posterior --severidade alta|baixa --texto "..."
    demanda.py estado fingerprint PROJ --repo api        (a linha "Código:" do roteiro)
    demanda.py licao add --projeto "NN - AAAA" --sinal armadilha --fonte ... --texto ... --escopo api [--onda 2]
               [--mesma L-NNN | --nova]
    demanda.py licao parecidas [--escopo api] [--limiar 0.15] | licao fundir --id L-A --em L-B --motivo "..." 
    demanda.py licao list [--status confirmed|candidate|quarantined|discarded|all] [--escopo api] [--busca X]
    demanda.py licao penalize --id L-001 | licao descartar --id L-001 --motivo "..." | licao status

Saída 0 = ok; 1 = gate recusou (ERRO); mensagens fatais saem por SystemExit.
"""

import argparse
import contextlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum as C  # noqa: E402
C.configurar_saida()


def _proj(sub):
    sub.add_argument('projeto', help='caminho absoluto da pasta escolhida para a demanda')


def construir():
    ap = argparse.ArgumentParser(prog='demanda.py', description=__doc__.split('\n')[0])
    sp = ap.add_subparsers(dest='cmd', required=True)

    s = sp.add_parser('configurar', help='registra um repositório e seus comandos')
    _proj(s)
    s.add_argument('--repo', required=True, help='apelido curto: api, web, bo, model…')
    s.add_argument('--caminho', required=True)
    s.add_argument('--perfil', choices=['maven', 'angular', 'generico'],
                   help='obrigatório na primeira configuração do repo')
    s.add_argument('--teste', help='comando de teste; {classes} recebe a seleção')
    s.add_argument('--build')
    s.add_argument('--relatorios', help='glob dos XML do Surefire, relativo ao repo')
    s.add_argument('--maven-repo-local')
    s.add_argument('--copiar-no-scratch', help='pastas copiadas para a worktree de mutação (vírgula)')
    s.add_argument('--linkar-no-scratch', help='pastas linkadas na worktree de mutação (vírgula)')
    s.add_argument('--sem-testes', action='store_true', help='repo sem suíte automatizada')
    s.add_argument('--com-testes', action='store_true', help='desfaz --sem-testes')
    s.add_argument('--ignorar-no-codigo', metavar='PREFIXOS',
                   help='caminhos fora da identidade do código, além de .playwright-mcp/ (vírgula); '
                        'acrescentar exige --decisao')
    s.add_argument('--branch')
    s.add_argument('--timeout', type=int)
    s.add_argument('--padrao', choices=['maven', 'angular', 'nenhum'],
                   help='liga o gate de padrão (EOL, colunas, comentário, import) com o preset do perfil; '
                        'sem o campo o repositório fica como está. `nenhum` desliga (pede --decisao)')
    s.add_argument('--padrao-desligar', metavar='REGRAS',
                   help='desliga regras do padrão (eol,colunas,comentario,import; vírgula): pede --decisao')
    s.add_argument('--padrao-colunas', type=int, metavar='N',
                   help='limite de colunas das linhas adicionadas; acima do atual (ou 0, que desliga) pede --decisao')
    s.add_argument('--lint', metavar='COMANDO',
                   help='comando de lint do repositório, rodado no commit e no fechamento (exit != 0 recusa); '
                        'definir ou trocar pede --decisao. Vazio remove')
    s.add_argument('--decisao', metavar='D<n>',
                   help='decisão do usuário que autoriza --sem-testes, trocar o comando de teste/build ou '
                        'afrouxar o padrão')

    s = sp.add_parser('repos', help='lista os repositórios configurados')
    _proj(s)

    s = sp.add_parser('validar-plano')
    _proj(s)
    s.add_argument('--sem-analise', metavar='D<n>',
                   help='registra a decisão do usuário de seguir sem análise nem ER (só fonte usuario); '
                        'exige --plano-base')
    s.add_argument('--plano-base', metavar='ARQUIVO',
                   help='com --sem-analise: o plano base da pasta do projeto, que vira o documento-fonte')

    s = sp.add_parser('aprovar-plano', help='sela o plano com a aprovação do usuário')
    _proj(s)
    s.add_argument('--citacao', required=True, help='trecho literal do que o usuário disse')

    s = sp.add_parser('plano')
    ps_ = s.add_subparsers(dest='acao', required=True)
    r = ps_.add_parser('diff', help='o que mudou desde a última aprovação')
    _proj(r)

    s = sp.add_parser('decisao')
    ds = s.add_subparsers(dest='acao', required=True)
    r = ds.add_parser('add')
    _proj(r)
    r.add_argument('--texto', required=True)
    r.add_argument('--fonte', required=True, choices=['usuario', 'analise', 'er'])
    r.add_argument('--citacao', help='fonte usuario: trecho literal da fala dele')
    r.add_argument('--ref', help='fonte analise: ASSUNTO; fonte er: coordenada')
    r.add_argument('--doc', help='fonte usuario: documento(s) da pasta do projeto que a fala cita '
                                 '(vírgula); o valor esperado pode vir dele')
    r.add_argument('--autoriza', choices=['testes', 'engenharia'],
                   help='a decisão autoriza, para o projeto: testes — rodar as classes das tarefas e os mutantes '
                        'do revisor sem pedir a cada vez; engenharia — o modelo decide mutante equivalente e arquivo '
                        'vizinho fora do Onde (`decisao engenharia`), e o parecer lista para revisão (só fonte usuario)')
    r.add_argument('--para', metavar='FINALIDADE',
                   help='para que serve (só fonte usuario): a decisão vale só para esse relaxamento, a fala é '
                        'conferida de novo no uso e alguns valem uma vez. Sem ele a decisão não relaxa gate (registro e âncora de valor). '
                        'Finalidades: sem-teste, sem-commit, sem-mutante, equivalente, fora-do-onde, '
                        'skill-alterada, analise-alterada, desbloquear, anular, base, oraculo, sem-padrao, '
                        'sem-analise, configurar, preexistentes, testar, fora-de-ordem, '
                        'descartar-pendencia')
    r.add_argument('--alvo', metavar='ID',
                   help='com --para: a que a decisão se aplica. sem-teste/sem-commit: tarefa (T1.1); equivalente: '
                        'mutante (M4); anular: execução (E7); descartar-pendencia: P<n>; skill-alterada, '
                        'analise-alterada, fora-de-ordem, desbloquear, base: onda (2); '
                        'configurar/preexistentes: repositório (api); sem-padrao: regra (colunas, eol, lint…). '
                        'Sem --alvo, vale para qualquer alvo da finalidade')
    r = ds.add_parser('engenharia', help='decisão do modelo, com a autorização de engenharia do usuário')
    _proj(r)
    r.add_argument('--para', required=True, choices=['equivalente', 'fora-do-onde'])
    r.add_argument('--alvo', help='equivalente: o M<n> sobrevivente do revisor')
    r.add_argument('--texto', required=True, help='a justificativa (o usuário a revê no parecer)')
    r = ds.add_parser('revogar')
    _proj(r)
    r.add_argument('--id', required=True)
    r.add_argument('--por', required=True, help='a decisão (D<n>) que revoga')
    r = ds.add_parser('list')
    _proj(r)
    r = ds.add_parser('anexar', help='liga a uma decisão do usuário o documento que a fala dela cita')
    _proj(r)
    r.add_argument('--id', required=True)
    r.add_argument('--doc', required=True)

    s = sp.add_parser('iniciar-onda')
    _proj(s)
    s.add_argument('onda')
    s.add_argument('--fora-de-ordem', metavar='D<n>',
                   help='decisão do usuário que autoriza iniciar com onda anterior aberta')
    s.add_argument('--analise-alterada', metavar='D<n>',
                   help='decisão do usuário para iniciar a onda depois que a análise mudou (sem reaprovar o plano)')

    s = sp.add_parser('commit')
    _proj(s)
    s.add_argument('--sem-teste', metavar='D<n>',
                   help='decisão do usuário que dispensa o gate de teste da tarefa neste commit')
    s.add_argument('--correcao', metavar='RV<k>',
                   help='depois da 1ª revisão, todo commit é correção de lacuna de uma revisão da onda')
    s.add_argument('--tarefa', required=True)
    s.add_argument('-m', required=True, help='só a parte descritiva: o hook põe branch/data/hora')
    s.add_argument('--decisao', metavar='D<n>', action='append',
                   help='decisão(ões) do usuário que autoriza(m) arquivo fora do Onde: repita, ou D57,D58')
    s.add_argument('--sem-padrao', metavar='REGRA=D<n>', action='append',
                   help='dispensa uma regra do padrão neste commit, com a decisão do usuário (eol, colunas, '
                        'comentario, import, lint); repetível')

    s = sp.add_parser('vincular')
    _proj(s)
    s.add_argument('--correcao', metavar='RV<k>',
                   help='depois da 1ª revisão, todo commit é correção de lacuna de uma revisão da onda')
    s.add_argument('--tarefa', required=True)
    s.add_argument('--hash', required=True)
    s.add_argument('--sem-teste', metavar='D<n>',
                   help='decisão do usuário que dispensa o gate de teste da tarefa para um commit que não é '
                        'o HEAD com a árvore limpa')
    s.add_argument('--decisao', metavar='D<n>', action='append',
                   help='decisão(ões) do usuário que autoriza(m) arquivo fora do Onde: repita, ou D57,D58')
    s.add_argument('--sem-padrao', metavar='REGRA=D<n>', action='append',
                   help='dispensa uma regra do padrão neste commit, com a decisão do usuário; repetível')

    s = sp.add_parser('sem-commit')
    _proj(s)
    s.add_argument('--tarefa', required=True)
    s.add_argument('--motivo', required=True)
    s.add_argument('--decisao', required=True, metavar='D<n>')

    s = sp.add_parser('testar', help='roda testes (só quando o usuário mandar) e registra')
    _proj(s)
    s.add_argument('--repo', required=True)
    s.add_argument('--classes')
    s.add_argument('--build', action='store_true')
    s.add_argument('--suite-inteira', action='store_true')
    s.add_argument('--intencao', choices=['vermelho-esperado', 'verde', 'regressao'], default='verde',
                   help='o que a execução pretende provar (padrão verde); só registro para o ledger e o painel — não muda gate: '
                        'vermelho continua não-OK')
    s.add_argument('--preexistentes', metavar='D<n>',
                   help='a suíte inteira falha pela primeira vez neste repo — decisão do usuário que aceita as '
                        'classes que falham como preexistentes (o fechamento passa a recusar classe nova falhando)')
    s.add_argument('--decisao', metavar='D<n>',
                   help='decisão do usuário para suíte inteira, comando que toca banco, ou execução sem autorização de testes')
    s.add_argument('--onda')
    s.add_argument('--timeout', type=int)

    s = sp.add_parser('evidencia', help='registra evidência manual amarrada ao código atual')
    _proj(s)
    s.add_argument('--repo', required=True)
    s.add_argument('--tipo', choices=['roteiro'], default='roteiro')
    s.add_argument('--arquivo', required=True)
    s.add_argument('--descricao')
    s.add_argument('--onda')

    s = sp.add_parser('mutante')
    ms = s.add_subparsers(dest='acao', required=True)
    m = ms.add_parser('preparar')
    _proj(m)
    m.add_argument('--repo', required=True)
    m.add_argument('--onda')
    m.add_argument('--decisao', metavar='D<n>', help='sem autorização de testes no projeto: a do usuário para esta sessão')
    m.add_argument('--autor', action='store_true',
                   help='pré-revisão do autor: só reaplica os sobreviventes de uma revisão antes da seguinte (não conta para o fechamento)')
    m = ms.add_parser('aplicar')
    _proj(m)
    m.add_argument('--sessao')
    m.add_argument('--repo')
    m.add_argument('--reaplica', metavar='M<n>',
                   help='autoconferência: o sobrevivente da revisão, reaplicado sobre o código de agora '
                        '(arquivo, trecho, aceite e testes vêm dele; a linha é achada, ou --linha)')
    m.add_argument('--arquivo')
    m.add_argument('--linha', type=int)
    m.add_argument('--de')
    m.add_argument('--para')
    m.add_argument('--aceite')
    m.add_argument('--testes')
    m.add_argument('--comando', help='oráculo alternativo, roda no scratch; {scratch} é substituído')
    m.add_argument('--codigos-morto', help='exit codes do --comando que contam como morto (padrão 1)')
    m.add_argument('--decisao', metavar='D<n>',
                   help='decisão do usuário que autoriza o --comando como oráculo (ele não prova aceite que tem teste)')
    m.add_argument('--timeout', type=int)
    m.add_argument('--descricao')
    m = ms.add_parser('reaplicar', help='autoconferência: reaplica todo sobrevivente pendente da onda')
    _proj(m)
    m.add_argument('--sessao')
    m.add_argument('--repo')
    m.add_argument('--timeout', type=int)
    m = ms.add_parser('reconfirmar', help='revisão: reaplica sobreviventes e mortos sem herança das '
                                          'revisões anteriores')
    _proj(m)
    m.add_argument('--sessao')
    m.add_argument('--repo')
    m.add_argument('--timeout', type=int)
    m = ms.add_parser('equivalente')
    _proj(m)
    m.add_argument('--id', required=True)
    m.add_argument('--motivo', required=True)
    m.add_argument('--decisao', required=True, metavar='D<n>', help='decisão do usuário aceitando o equivalente')
    m = ms.add_parser('limpar')
    _proj(m)
    m.add_argument('--sessao')
    m.add_argument('--repo')

    s = sp.add_parser('consolidar')
    _proj(s)
    s.add_argument('onda')

    s = sp.add_parser('revisao')
    rs = s.add_subparsers(dest='acao', required=True)
    for nome in ('iniciar', 'validar'):
        r = rs.add_parser(nome)
        _proj(r)
        r.add_argument('onda')
    r = rs.add_parser('confirmar', help='rodada de confirmação mecânica, sem subagente: a revisão anterior reprovou só '
                                        'por teste fraco, equivalente ou pendência e desde ela só arquivo de teste mudou')
    _proj(r)
    r.add_argument('onda')
    r.add_argument('--decisao', metavar='D<n>', help='sem autorização de testes no projeto: a do usuário para os mutantes')
    r.add_argument('--timeout', type=int)

    s = sp.add_parser('autoconferencia', help='conferência do autor antes de chamar o revisor')
    rs = s.add_subparsers(dest='acao', required=True)
    for nome in ('iniciar', 'validar'):
        r = rs.add_parser(nome)
        _proj(r)
        r.add_argument('onda')

    s = sp.add_parser('onda', help='onda bloqueada ou base da onda')
    os_ = s.add_subparsers(dest='acao', required=True)
    x = os_.add_parser('desbloquear', help='caminho da onda depois da 3ª revisão reprovada (decisão do usuário)')
    _proj(x)
    x.add_argument('onda')
    x.add_argument('--caminho', required=True, choices=['fechar-com-pendencias', 'replanejar', 'abandonar'])
    x.add_argument('--decisao', required=True, metavar='D<n>')
    x = os_.add_parser('base', help='recua a base de uma onda aberta e sem trabalho para um ancestral, '
                                    'para levar um commit feito fora de onda (decisão do usuário)')
    _proj(x)
    x.add_argument('onda')
    x.add_argument('--repo', required=True)
    x.add_argument('--head', required=True, metavar='COMMIT')
    x.add_argument('--decisao', required=True, metavar='D<n>')

    s = sp.add_parser('defeito', help='defeito achado pelo processo ou escapado depois da liberação (alimenta as métricas)')
    ds_ = s.add_subparsers(dest='acao', required=True)
    x = ds_.add_parser('add')
    _proj(x)
    x.add_argument('--onda', required=True)
    x.add_argument('--origem', required=True, choices=['revisao', 'parecer', 'posterior'],
                   help='posterior = escapado: visto depois da liberação, em onda já fechada')
    x.add_argument('--severidade', required=True, choices=['alta', 'baixa'])
    x.add_argument('--texto', required=True)
    x = ds_.add_parser('list')
    _proj(x)

    s = sp.add_parser('pendencia', help='requisito novo achado na revisão, levado para outra onda')
    ps_ = s.add_subparsers(dest='acao', required=True)
    x = ps_.add_parser('add')
    _proj(x)
    x.add_argument('--onda', required=True, help='a onda em que foi achado')
    x.add_argument('--origem', required=True, metavar='RV<n>|AC<n>|usuario')
    x.add_argument('--texto', required=True)
    x.add_argument('--severidade', choices=['alta', 'baixa'],
                   help='obrigatória. Alta: quebra comportamento que um aceite já fechado garante, '
                        'perda de dado, segurança ou indisponibilidade')
    x = ps_.add_parser('list')
    _proj(x)
    x = ps_.add_parser('descartar')
    _proj(x)
    x.add_argument('--id', required=True, metavar='P<n>')
    x.add_argument('--decisao', required=True, metavar='D<n>')

    s = sp.add_parser('execucao', help='execuções registradas')
    xs = s.add_subparsers(dest='acao', required=True)
    x = xs.add_parser('anular', help='anula uma execução registrada por engano (decisão do usuário)')
    _proj(x)
    x.add_argument('--id', required=True, metavar='E<n>')
    x.add_argument('--decisao', required=True, metavar='D<n>')
    x.add_argument('--motivo', required=True)

    s = sp.add_parser('fechar-onda')
    _proj(s)
    s.add_argument('onda')
    s.add_argument('--simular', action='store_true', help='só lista o que falta')
    s.add_argument('--skill-alterada', metavar='D<n>',
                   help='decisão do usuário para fechar uma onda depois que a skill mudou')
    s.add_argument('--analise-alterada', metavar='D<n>',
                   help='decisão do usuário para fechar uma onda depois que a análise mudou')
    s.add_argument('--sem-mutante', action='append', metavar='A<onda>.<k>',
                   help='aceite cuja prova mora só em arquivo de teste, que não se muta: dispensa o mutante '
                        'dele (repetível; pede --sem-mutante-decisao)')
    s.add_argument('--sem-mutante-decisao', metavar='D<n>',
                   help='decisão do usuário que dispensa o mutante dos aceites de --sem-mutante')
    s.add_argument('--sem-padrao', metavar='REGRA=D<n>', action='append',
                   help='dispensa uma regra do padrão no diff da onda inteira, com a decisão do usuário; repetível')

    s = sp.add_parser('parecer')
    ps = s.add_subparsers(dest='acao', required=True)
    r = ps.add_parser('iniciar')
    _proj(r)
    r = ps.add_parser('validar')
    _proj(r)
    r.add_argument('--arquivo')

    s = sp.add_parser('estado')
    es = s.add_subparsers(dest='acao', required=True)
    r = es.add_parser('reconciliar')
    _proj(r)
    r.add_argument('--json', action='store_true')
    r.add_argument('--html', action='store_true',
                   help='cria/atualiza PAINEL.html (só agregados). Depois de criado, o reconciliar e o painel o mantêm em dia')
    r = es.add_parser('metricas', help='tempo × esforço × qualidade por onda (estimativas)')
    _proj(r)
    r.add_argument('--json', action='store_true')
    r = es.add_parser('painel')
    _proj(r)
    r.add_argument('--html', action='store_true', help='cria/atualiza PAINEL.html (página única, só agregados)')
    r = es.add_parser('fingerprint', help='assinatura do código atual, para o cabeçalho do roteiro')
    _proj(r)
    r.add_argument('--repo', required=True)

    s = sp.add_parser('grafo', help='atalho para a aba Grafo do painel: rastreabilidade (análise, ER/ET, plano, execução) e as lacunas')
    _proj(s)
    s.add_argument('--json', action='store_true', help='imprime o modelo (nós, arestas, lacunas) em vez de gravar o painel')
    s.add_argument('--abrir', action='store_true', help='abre o PAINEL.html no navegador, já na aba Grafo')

    s = sp.add_parser('licao')
    ls = s.add_subparsers(dest='acao', required=True)
    r = ls.add_parser('add')
    r.add_argument('--projeto', required=True)
    r.add_argument('--sinal', required=True)
    r.add_argument('--fonte', required=True)
    r.add_argument('--texto', required=True)
    r.add_argument('--escopo', required=True, help='apelido de um repositório configurado no projeto')
    r.add_argument('--onda', help='onda em que o sinal apareceu (padrão: a onda em execução)')
    r.add_argument('--mesma', metavar='L-NNN', help='é a mesma lição de L-NNN, com outras palavras: soma a ocorrência')
    r.add_argument('--nova', action='store_true', help='cria a lição mesmo havendo parecida')
    r = ls.add_parser('parecidas', help='pares de lições do mesmo repositório com texto parecido')
    r.add_argument('--escopo')
    r.add_argument('--limiar', type=float, default=0.15)
    r = ls.add_parser('fundir', help='a lição --id é a mesma de --em (ok do usuário)')
    r.add_argument('--id', required=True)
    r.add_argument('--em', required=True)
    r.add_argument('--motivo', required=True)
    r = ls.add_parser('confirmar', help='promove uma candidata a confirmada (ok do usuário)')
    r.add_argument('--id', required=True)
    r.add_argument('--motivo', required=True)
    r = ls.add_parser('descartar', help='tira do playbook uma lição que não é sobre repositório (ok do usuário)')
    r.add_argument('--id', required=True)
    r.add_argument('--motivo', required=True)
    r = ls.add_parser('list')
    r.add_argument('--status', default='confirmed',
                   choices=['confirmed', 'candidate', 'quarantined', 'discarded', 'merged', 'all'])
    r.add_argument('--escopo')
    r.add_argument('--busca')
    r = ls.add_parser('penalize')
    r.add_argument('--id', required=True)
    ls.add_parser('status')
    return ap


def main(argv=None):
    args = construir().parse_args(argv)
    C.configurar_saida()
    if args.cmd == 'licao':
        _guarda_ambiente(None)
        import licoes
        return licoes.cmd(args)
    pasta = C.resolver(args.projeto)
    _guarda_ambiente(pasta)
    # Comando rápido segura o lock do projeto do começo ao fim. Os longos (rodam testes por minutos)
    # gravam em transações curtas, para não travar o orquestrador enquanto o revisor muta.
    longo = args.cmd == 'testar' or (args.cmd == 'mutante' and args.acao in ('preparar', 'aplicar', 'reaplicar', 'reconfirmar')) \
        or (args.cmd == 'revisao' and args.acao == 'confirmar')
    _avisar_skill_mudou(pasta)
    with (contextlib.nullcontext() if longo else C.trava_projeto(pasta)):
        return _despachar(pasta, args)


def _guarda_ambiente(pasta):
    """`EXEC_DEMANDA_*` troca de onde vêm a prova de fala (FALAS), a versão da skill (SKILL_DIR), a raiz dos
    projetos, o scratch e a loja de lições — coisas que o agente, dono do próprio ambiente, não pode escolher. Só
    o autoteste as usa: elas valem dentro de uma pasta de teste marcada (`.autoteste-demanda`, criada por ele sob
    o diretório temporário), com o projeto e todo caminho que apontam lá dentro. `pasta` None: comando sem
    projeto (`licao`). Fora disso a variável faz o comando recusar, em voz alta."""
    ativas = sorted(k for k in os.environ if k.startswith('EXEC_DEMANDA_'))
    if not ativas:
        return

    def sob(base, caminho):
        base, caminho = os.path.realpath(base), os.path.realpath(caminho)
        return caminho == base or caminho.startswith(base + os.sep)

    marca = os.environ.get('EXEC_DEMANDA_AUTOTESTE') or ''
    if marca and os.path.isfile(os.path.join(marca, '.autoteste-demanda')) \
            and sob(tempfile.gettempdir(), marca) and (pasta is None or sob(marca, pasta)) \
            and all(sob(marca, os.environ[k]) for k in ativas if k != 'EXEC_DEMANDA_AUTOTESTE'):
        return
    raise SystemExit('recusado: %s no ambiente. Essas variáveis trocam a prova de fala, a versão da skill e a '
                     'raiz dos projetos, e só valem no autoteste (projeto dentro de uma pasta de teste marcada, '
                     'sob o diretório temporário). Tire-as do ambiente.' % ', '.join(ativas))


def _avisar_skill_mudou(pasta):
    """Toda chamada avisa quando a skill mudou desde o início da onda em execução: revisor em
    background roda o script que existir na hora, e a skill pode mudar com a onda aberta."""
    try:
        estado = C.carregar_estado(pasta)
        ativa = C.onda_ativa(estado)
        mudou = ativa and C.skill_mudou(estado['ondas'][ativa])
        if mudou:
            print('aviso: onda %s — %s' % (ativa, mudou), file=sys.stderr)
    except Exception:
        pass


# Comandos que fazem uma onda andar: com uma onda histórica (de antes da 0.4.0) ainda aberta, recusam.
COMANDOS_DE_ONDA = ('iniciar-onda', 'commit', 'vincular', 'sem-commit', 'testar', 'evidencia', 'mutante',
                    'consolidar', 'autoconferencia', 'revisao', 'onda', 'pendencia', 'execucao', 'fechar-onda')


def _despachar(pasta, args):
    if args.cmd in COMANDOS_DE_ONDA:
        estado = C.carregar_estado(pasta)
        for oid in sorted(estado.get('ondas') or {}):
            C.exigir_onda_consolidada(estado, oid)
    try:
        if args.cmd == 'configurar':
            import testes
            return testes.configurar(pasta, args)
        if args.cmd == 'repos':
            estado = C.carregar_estado(pasta)
            for nome, cfg in sorted(estado['repos'].items()):
                print('%-8s %s  [%s]  branch=%s  teste=%s' % (nome, cfg['caminho'], cfg.get('perfil'),
                                                              cfg.get('branch'), cfg.get('teste') or '—'))
            return 0
        if args.cmd == 'validar-plano':
            import decisoes
            import plano
            estado = C.carregar_estado(pasta)
            if args.sem_analise:
                erro_d = decisoes.exigir(estado, args.sem_analise, para='sem-analise')
                if erro_d:
                    raise SystemExit('recusado: --sem-analise: ' + erro_d)
                base = args.plano_base and os.path.abspath(os.path.join(pasta, args.plano_base))
                if not base or not base.startswith(os.path.abspath(pasta) + os.sep) or not os.path.isfile(base):
                    raise SystemExit('recusado: --sem-analise só com --plano-base <arquivo da pasta do '
                                     'projeto> — sem análise, o plano base é o documento de onde saem os '
                                     'valores esperados')
                estado['sem_analise'] = {'decisao': args.sem_analise,
                                         'plano_base': os.path.relpath(base, pasta)}
                C.salvar_estado(pasta, estado)
            decisoes.renderizar(pasta, estado)
            rel, _ = plano.validar(pasta, estado)
            if not rel.erros:
                decisoes.registrar_validacao(pasta, estado)
                erro_ap = decisoes.conferir_aprovacao(pasta, estado)
                rel.nota('aprovação: %s' % (erro_ap or 'o plano atual é o aprovado'))
                mudou_analise = C.analise_mudou(pasta, estado)
                if mudou_analise:
                    rel.aviso(mudou_analise)
            return rel.imprimir()
        if args.cmd == 'aprovar-plano':
            import decisoes
            return decisoes.aprovar(pasta, args)
        if args.cmd == 'plano':
            import decisoes
            return decisoes.diff(pasta, args)
        if args.cmd == 'decisao':
            import decisoes
            return {'add': decisoes.add, 'revogar': decisoes.revogar, 'list': decisoes.listar,
                    'anexar': decisoes.anexar, 'engenharia': decisoes.engenharia}[args.acao](pasta, args)
        if args.cmd == 'iniciar-onda':
            import onda
            return onda.iniciar(pasta, args)
        if args.cmd in ('commit', 'vincular', 'sem-commit'):
            import commit
            return {'commit': commit.commit, 'vincular': commit.vincular,
                    'sem-commit': commit.sem_commit}[args.cmd](pasta, args)
        if args.cmd == 'testar':
            import testes
            return testes.testar(pasta, args)
        if args.cmd == 'evidencia':
            import testes
            return testes.evidencia(pasta, args)
        if args.cmd == 'mutante':
            import mutantes
            return {'preparar': mutantes.preparar, 'aplicar': mutantes.aplicar, 'reaplicar': mutantes.reaplicar, 'reconfirmar': mutantes.reconfirmar,
                    'equivalente': mutantes.equivalente, 'limpar': mutantes.limpar}[args.acao](pasta, args)
        if args.cmd == 'consolidar':
            import onda
            onda.consolidar(pasta, args.onda)
            return 0
        if args.cmd == 'autoconferencia':
            import revisao
            return (revisao.iniciar_autoconferencia(pasta, args) if args.acao == 'iniciar'
                    else revisao.cmd_validar_autoconferencia(pasta, args))
        if args.cmd == 'revisao':
            import revisao
            return {'iniciar': revisao.iniciar, 'validar': revisao.cmd_validar,
                    'confirmar': revisao.confirmar}[args.acao](pasta, args)
        if args.cmd == 'onda':
            import onda
            return onda.mudar_base(pasta, args) if args.acao == 'base' else onda.desbloquear(pasta, args)
        if args.cmd == 'pendencia':
            import onda
            return onda.pendencia(pasta, args)
        if args.cmd == 'defeito':
            import onda
            return onda.defeito(pasta, args)
        if args.cmd == 'execucao':
            import testes
            return testes.anular(pasta, args)
        if args.cmd == 'fechar-onda':
            import onda
            return onda.fechar(pasta, args)
        if args.cmd == 'parecer':
            import parecer
            return parecer.iniciar(pasta, args) if args.acao == 'iniciar' else parecer.validar(pasta, args)
        if args.cmd == 'grafo':
            import grafo
            return grafo.grafo(pasta, args)
        if args.cmd == 'estado':
            import estado
            return {'reconciliar': estado.reconciliar, 'painel': estado.painel,
                    'metricas': estado.metricas, 'fingerprint': estado.fingerprint}[args.acao](pasta, args)
    except C.ErroGit as ex:
        raise SystemExit('git falhou: %s' % ex)
    raise SystemExit('subcomando desconhecido')


if __name__ == '__main__':
    raise SystemExit(main())
