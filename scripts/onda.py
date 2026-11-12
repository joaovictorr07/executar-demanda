#!/usr/bin/env python3
"""Início, consolidação e fechamento de uma onda — o gate que concentra todos os outros.

`fechar-onda` não roda teste, não roda mutante, não revisa: ele **confere** que cada uma dessas
coisas aconteceu, deu certo e foi feita sobre o código que está aí agora. Qualquer falta é ERRO,
e a onda continua aberta. `--simular` mostra a lista sem fechar.
"""

import os
import re
import shutil

import comum as C
import decisoes as DC
import mutantes as M
import padrao as PD
import plano as P
import revisao as RV
import testes as T

MIN_MUTANTES = {'normal': 3, 'alto': 5}
MIN_LEVE = 2  # onda leve (até 4 tarefas) e risco normal
RE_DESLIGADO = re.compile(r'@Ignore\b|@Disabled\b|\bxit\s*\(|\bxdescribe\s*\(|'
                          r'\bfit\s*\(|\bfdescribe\s*\(')
# `.skip(` só desliga caso em spec JS/TS (`it.skip`, `describe.skip`); em Java é o `Stream.skip`.
RE_DESLIGADO_JS = re.compile(r'\.skip\s*\(')


def _desligados(arquivo, codigo):
    """Marcas de teste desligado no trecho, pelo tipo do arquivo."""
    achados = RE_DESLIGADO.findall(codigo)
    if not arquivo.endswith('.java'):
        achados += RE_DESLIGADO_JS.findall(codigo)
    return achados


# ------------------------------------------------------------------------------ iniciar

def iniciar(pasta, args):
    estado = C.carregar_estado(pasta)
    rel, p = P.validar(pasta, estado)
    if rel.erros:
        rel.titulo = 'iniciar-onda %s: o plano não passa no validar-plano' % args.onda
        return rel.imprimir()
    rel = C.Relatorio('iniciar-onda %s' % args.onda)
    erro_ap = DC.conferir_aprovacao(pasta, estado, args.onda)
    if erro_ap:
        rel.erro(erro_ap)
    analise_aceita = None
    mudou_analise = C.analise_mudou(pasta, estado)
    if mudou_analise:
        if not getattr(args, 'analise_alterada', None):
            rel.erro('%s — reaprove o plano (`aprovar-plano`) ou, se foi só correção de texto que não muda '
                     'o plano, `--analise-alterada D<n>` com a decisão do usuário' % mudou_analise)
        else:
            erro_d = DC.exigir(estado, args.analise_alterada, para='analise-alterada', alvo=args.onda)
            if erro_d:
                rel.erro('--analise-alterada: ' + erro_d)
            else:
                analise_aceita = {'sha1': C.sha1_arquivo(C.arquivo_analise(pasta)),
                                  'decisao': args.analise_alterada}
    o = p.onda(args.onda)
    if not o:
        raise SystemExit('onda %s não está no plano' % args.onda)
    atual = estado['ondas'].get(args.onda, {})
    if atual.get('estado') in ('em_execucao', 'bloqueada') + C.TERMINAIS:
        rel.erro('onda %s já está %s' % (args.onda, atual['estado']))
    outra = C.onda_ativa(estado)
    if outra and outra != args.onda:
        rel.erro('a onda %s ainda está em execução — uma por vez' % outra)
    anteriores = [x['id'] for x in p.ondas[:p.indice_onda(args.onda)]]
    abertas = [x for x in anteriores if estado['ondas'].get(x, {}).get('estado') not in C.TERMINAIS]
    fora_de_ordem = (args.fora_de_ordem or '').strip()
    if abertas:
        if not fora_de_ordem:
            rel.erro('ondas anteriores não fechadas: %s — iniciar fora de ordem é decisão do '
                     'usuário: `--fora-de-ordem D<n>`' % ', '.join(abertas))
        else:
            erro_d = DC.exigir(estado, fora_de_ordem, para='fora-de-ordem', alvo=args.onda)
            if erro_d:
                rel.erro('--fora-de-ordem: ' + erro_d)
    if o['a_verificar']:
        rel.erro('%d [A VERIFICAR] nesta onda — pergunte ao usuário e registre a resposta '
                 'como decisão antes de começar' % o['a_verificar'])
    if p.a_verificar_fora:
        rel.erro('%d [A VERIFICAR] fora das ondas (contexto, decisões, riscos…) — vale para o '
                 'plano inteiro: nenhuma onda inicia antes da resposta' % p.a_verificar_fora)
    for perg in P.pontos_abertos_da_onda(p, P.ler_analise(pasta), o):
        rel.erro('ponto em aberto da análise sem resposta: %s' % perg[:100])
    repos = sorted({P.repo_de(t) for t in o['tarefas'].values()})
    baseline = {}
    for r in repos:
        cfg = estado['repos'].get(r)
        if not cfg:
            rel.erro('repo %r não configurado' % r)
            continue
        b = C.branch_atual(cfg['caminho'])
        if cfg.get('branch') and b != cfg['branch']:
            rel.erro('%s está em %r; a branch do projeto é %r' % (r, b, cfg['branch']))
        baseline[r] = {'head': C.git(cfg['caminho'], 'rev-parse', 'HEAD'),
                       'fingerprint': C.fingerprint(cfg['caminho'])}
    if rel.erros:
        return rel.imprimir()
    estado['ondas'][args.onda] = {'estado': 'em_execucao', 'iniciada_em': C.agora(),
                                  'baseline': baseline, 'fora_de_ordem': fora_de_ordem or None,
                                  'tarefas': {}, 'consolidada': True, 'skill': C.versao_skill()}
    if analise_aceita:
        estado['ondas'][args.onda]['analise_aceita'] = analise_aceita
    for x in pendencias_sem_onda(estado, p):
        if severidade(x) == 'alta':
            rel.aviso('pendência alta %s (da onda %s, %s) sem onda que a tenha na Origem: %s — o parecer de '
                      'liberação recusa GO com ela aberta' % (x['id'], x['onda'], x['origem'], x['texto'][:80]))
    if estado['ondas'][args.onda]['skill'].get('sujo'):
        rel.aviso('a skill tem alteração não commitada: a onda começa com uma versão que o commit não descreve')
    C.salvar_estado(pasta, estado)
    rel.nota('Onda %s — %s: em execução' % (args.onda, o['titulo']))
    for tid in o['ordem_tarefas']:
        t = o['tarefas'][tid]
        rel.nota('  %s  [%s] %s  (teste: %s)' % (tid, P.repo_de(t), t['titulo'], P.teste_de(t)))
    try:
        import licoes
        nomes = list(repos) + [os.path.basename(os.path.normpath(estado['repos'][r]['caminho']))
                               for r in repos if r in estado['repos']]
        confirmadas = licoes.listar(status='confirmed', escopos=nomes)
        if confirmadas:
            rel.nota('lições confirmadas para %s:' % ', '.join(repos))
            for l in confirmadas:
                rel.nota('  %s: %s' % (l['id'], l['text']))
    except Exception as ex:  # lição é apoio, não gate
        rel.aviso('lições não carregadas: %s' % ex)
    return rel.imprimir()


# ------------------------------------------------------------------------------ consolidar

def _commits_da_onda(estado_onda):
    for tid, r in sorted(estado_onda.get('tarefas', {}).items()):
        for c in r.get('commits', []):
            yield tid, c


def bloco_commits(estado, oid):
    eo = estado['ondas'].get(oid, {})
    linhas = ['| Repo | Commit | Tarefa | Assunto |', '|---|---|---|---|']
    vistos = set()
    for tid, c in _commits_da_onda(eo):
        repo = c['repo'] if c['repo'] not in vistos else ''
        vistos.add(c['repo'])
        linhas.append('| %s | `%s` | %s | %s |' % (repo and '`%s`' % repo, c['hash'][:9], tid,
                                                  c['assunto'].replace('|', '\\|')))
    for tid, r in sorted(eo.get('tarefas', {}).items()):
        if r.get('sem_commit'):
            linhas.append('| — | — | %s | sem commit: %s |' % (tid, r['sem_commit']))
    if len(linhas) == 2:
        return '_nenhum commit registrado_'
    push = []
    for repo in sorted(vistos):
        cfg = estado['repos'][repo]
        push.append('%s: %s' % (repo, _situacao_push(cfg['caminho'])))
    return '\n'.join(linhas) + '\n\n**Push:** ' + '; '.join(push)


def _situacao_push(real):
    up = C.git(real, 'rev-parse', '--abbrev-ref', '@{u}', checar=False)
    if not up:
        return 'sem upstream'
    contagem = C.git(real, 'rev-list', '--left-right', '--count', '@{u}...HEAD', checar=False)
    try:
        atras, frente = [int(x) for x in contagem.split()]
    except ValueError:
        return 'indeterminado'
    if not atras and not frente:
        return '`origin` == HEAD'
    return '%d commit(s) sem push%s' % (frente, ', %d atrás' % atras if atras else '')


def bloco_testes(estado, oid, fps):
    linhas = ['| # | Repo | Tipo | Seleção | Resultado | Fresca? |', '|---|---|---|---|---|---|']
    for e in estado['execucoes']:
        if e.get('onda') != oid:
            continue
        if e['tipo'] == 'teste' and e.get('totais'):
            res = '%(run)d rodados, %(falhas)d falhas, %(erros)d erros, %(pulados)d pulados' % e['totais']
        elif e['tipo'] in ('build', 'teste'):
            res = 'exit %d' % e['exit']
        else:
            res = '`%s`' % e.get('arquivo', '')
        if not e.get('ok'):
            res = '**FALHOU** — ' + '; '.join(e.get('problemas', []))
        if e.get('anulada'):
            res = '~~%s~~ **anulada** — %s (%s)' % (res, e['anulada']['motivo'], e['anulada']['decisao'])
        sel = ', '.join(e.get('classes', [])) or ('suíte inteira' if e.get('suite_inteira') else '—')
        if e.get('intencao') not in (None, 'verde'):
            sel += ' [%s]' % e['intencao']
        fresca = '✅' if C.mesmo_fp(e.get('fingerprint'), fps.get(e['repo'])) else 'vencida'
        linhas.append('| %s | `%s` | %s | %s | %s | %s |' % (e['id'], e['repo'], e['tipo'], sel, res, fresca))
    return '\n'.join(linhas) if len(linhas) > 2 else '_nenhuma execução registrada nesta onda_'


def fps_atuais(estado):
    return C.fingerprints(estado)


ESQUELETO_CONSOLIDACAO = """# Onda {onda} — {titulo}: consolidação ({rotulo})

**{data}.** <veredito da onda em uma frase: o que ficou entregue e o que falta>

Complementa o `{plano}`.

---

## 1. Commits

{commits}

## 2. O que mudou de estrutura

<o que entrou, por repositório, com arquivo:linha onde ajuda>

## 3. Decisões da rodada

{decisoes}

## 4. Testes e evidências

{testes}

### Mutantes

{mutantes}

## 5. Aceite da onda

{aceite}

## 6. Verificado

<o que foi executado e deu certo, com número>

## 7. Não verificado

<o que não foi executado, e por quê — "nada" só se for verdade>

## 8. Defeitos corrigidos na rodada

## 9. Pendências

{pendencias}

## 10. Armadilhas desta rodada
"""


RE_ID_CITADO = re.compile(r'\b(?:E\d+|RV\d+|M\d+|P\d+|D\d+|A\d+[a-z]*\.\d+)\b')


def _ids_existentes(estado):
    """Todo ID que o estado conhece: execuções, revisões, mutantes, pendências, decisões e aceites do plano."""
    ids = {e['id'] for e in estado.get('execucoes', [])}
    ids |= {r['id'] for r in estado.get('revisoes', [])}
    ids |= {m['id'] for s in estado.get('sessoes_mutacao', []) for m in s.get('mutantes', [])}
    ids |= {x['id'] for x in estado.get('pendencias', [])}
    ids |= {d['id'] for d in estado.get('decisoes', [])}
    return ids


def _conferir_ids_da_consolidacao(rel, texto, estado, aceites):
    """Verificado e Não verificado citam o que existe (E<n>, RV<n>, M<n>, P<n>, D<n>, A<onda>.<k>);
    prosa sem referência não prova que algo foi verificado. Não verificado pode ser só "nada"."""
    existentes = _ids_existentes(estado) | set(aceites)
    for nome, rx, vazio_ok in (('Verificado', r'^\d*\.?\s*verificado', False),
                               ('Não verificado', r'^\d*\.?\s*n[aã]o verificado', True)):
        corpo = C.secao(texto, rx)
        if corpo is None or not C.tem_conteudo(corpo):
            continue  # já recusada acima
        citados = RE_ID_CITADO.findall(corpo)
        reais = [c for c in citados if c in existentes]
        if reais:
            continue
        if vazio_ok and C.chave(corpo).strip('.:- *') in ('nada', 'nenhum', 'nenhuma'):
            continue
        rel.erro('consolidação: a seção "%s" não cita nada que exista no estado (E<n>, RV<n>, M<n>, P<n>, D<n> ou '
                 'aceite A<onda>.<k>) — diga o que foi verificado com a referência%s'
                 % (nome, '; "nada" sozinho vale quando não há o que registrar' if vazio_ok else ''))


def bloco_aceite(p, oid):
    o = p.onda(oid)
    return '\n'.join('- [%s] %s' % ('x' if a['marcado'] else ' ', a['texto'])
                     for a in (o['aceites'][i] for i in o['ordem_aceites'])) or '_sem aceite_'


def bloco_decisoes(estado, oid):
    """Decisões registradas no livro enquanto a onda estava em execução. O livro é um só (o do
    plano); a consolidação só as lista — decisão não nasce aqui."""
    daqui = [d for d in estado.get('decisoes', []) if d.get('onda') == oid]
    if not daqui:
        return '_nenhuma decisão registrada durante a onda_'
    return DC.tabela(daqui)


def desbloquear(pasta, args):
    """A 3ª revisão reprovou e a onda bloqueou. Três caminhos, todos decisão do usuário:

    - `fechar-com-pendencias`: o código continua o da última revisão; os aceites não-OK e os
      sobreviventes dela ficam como pendências aceitas, a onda pode fechar, e o parecer tem de
      citá-las (achado ou condição);
    - `replanejar`: a onda para aqui (os commits ficam); o que falta vai para uma onda nova no plano,
      com a Origem citando a decisão, e o plano é aprovado de novo;
    - `abandonar`: a onda para aqui; o parecer tem de dizer o que fica de fora.
    """
    estado = C.carregar_estado(pasta)
    eo = estado['ondas'].get(args.onda)
    revs = RV._revisoes(estado, args.onda)
    if not eo:
        raise SystemExit('onda %s não foi iniciada' % args.onda)
    if eo.get('estado') != 'bloqueada':
        raise SystemExit('onda %s não está bloqueada (estado: %s)' % (args.onda, eo.get('estado')))
    erro_d = DC.exigir(estado, args.decisao, para='desbloquear', alvo=args.onda)
    d = DC.achar(estado, args.decisao) if not erro_d else None
    if d and eo.get('bloqueada_em') and C.epoch_iso(d.get('registrada_em')) < C.epoch_iso(eo['bloqueada_em']):
        erro_d = '%s é anterior ao bloqueio (%s) — a escolha do caminho é uma decisão nova' % (args.decisao, eo['bloqueada_em'])
    if erro_d:
        raise SystemExit('recusado: o caminho de uma onda bloqueada é decisão do usuário — %s' % erro_d)
    ultima = revs[-1]
    if args.caminho == 'fechar-com-pendencias':
        fps = C.fingerprints(estado)
        mudou = [r for r, fp in ultima['fingerprints'].items() if not C.mesmo_fp(fp, fps.get(r))]
        if mudou:
            raise SystemExit('recusado: o código de %s mudou depois da %s — as pendências seriam de um código '
                             'que não existe mais' % (', '.join(mudou), ultima['id']))
        texto = C.ler(C.arquivo_revisao(pasta, args.onda))
        nao_ok = []
        for cel in C.linhas_de_tabela(C.secao(texto, r'^aceite a aceite')):
            aid = cel[0].strip('*` ') if cel else ''
            if C.RE_ACEITE.fullmatch(aid) and len(cel) >= 5:
                res = C.chave(cel[4])
                if not (res.startswith('ok') or res.startswith('✅')):
                    nao_ok.append(aid)
        vivos = [m['id'] for s_ in estado['sessoes_mutacao'] if s_.get('revisao') == ultima['id']
                 for m in s_.get('mutantes', []) if m['resultado'] == 'sobrevivente' and not m.get('equivalente')]
        eo['pendencias_aceitas'] = {'decisao': args.decisao, 'revisao': ultima['id'], 'aceites': nao_ok,
                                    'mutantes': vivos, 'em': C.agora()}
        eo['estado'] = 'em_execucao'
        msg = ('onda %s volta a poder fechar com as pendências da %s: aceites %s; mutantes %s — '
               '`fechar-onda`, e o parecer as cita' % (args.onda, ultima['id'], ', '.join(nao_ok) or '—',
                                                      ', '.join(vivos) or '—'))
    else:
        eo['estado'] = 'replanejada' if args.caminho == 'replanejar' else 'abandonada'
        eo[eo['estado']] = {'decisao': args.decisao, 'revisao': ultima['id'], 'em': C.agora()}
        msg = ('onda %s %s (%s). %s' % (args.onda, eo['estado'], args.decisao,
               'Escreva a onda nova com o que falta, `**Origem:** %s`, e aprove o plano de novo' % args.decisao
               if args.caminho == 'replanejar' else 'O parecer tem de dizer o que ficou de fora (achado citando a Onda %s)' % args.onda))
    C.salvar_estado(pasta, estado)
    print(msg)
    return 0


def mudar_base(pasta, args):
    """A onda começou com o HEAD num commit feito fora de onda que ela devia levar: com a base nele, o
    `vincular` o recusa e nenhuma linha conta como alterada na onda. Só com a decisão do usuário,
    posterior ao início, e só antes de qualquer trabalho da onda (commit ligado, mutação,
    autoconferência ou revisão), a base do repositório recua para um ancestral."""
    estado = C.carregar_estado(pasta)
    eo = estado['ondas'].get(args.onda)
    if not eo or eo.get('estado') != 'em_execucao':
        raise SystemExit('onda %s não está em execução (estado: %s)'
                         % (args.onda, (eo or {}).get('estado', 'não iniciada')))
    b = eo.get('baseline', {}).get(args.repo)
    if not b or not b.get('head'):
        raise SystemExit('a onda %s não tem base no repositório %s' % (args.onda, args.repo))
    erro_d = DC.exigir(estado, args.decisao, para='base', alvo=args.onda)
    d = DC.achar(estado, args.decisao) if not erro_d else None
    # o livro grava a onda ativa de cada decisão; o horário, só em segundos, empataria com o início
    if d and d.get('onda') != args.onda:
        erro_d = '%s é anterior ao início da onda (%s)' % (args.decisao, eo['iniciada_em'])
    if erro_d:
        raise SystemExit('recusado: mudar a base da onda é decisão do usuário — %s' % erro_d)
    feito = []
    if any(r.get('commits') for r in eo.get('tarefas', {}).values()):
        feito.append('commit ligado a tarefa')
    if any(s.get('onda') == args.onda for s in estado['sessoes_mutacao']):
        feito.append('sessão de mutação')
    if RV._autoconferencias(estado, args.onda):
        feito.append('autoconferência')
    if RV._revisoes(estado, args.onda):
        feito.append('revisão')
    if feito:
        raise SystemExit('recusado: a onda %s já tem %s — a base só muda antes de qualquer trabalho dela'
                         % (args.onda, ', '.join(feito)))
    real = estado['repos'][args.repo]['caminho']
    if not C.commit_existe(real, args.head):
        raise SystemExit('commit %s não existe em %s' % (args.head, real))
    novo = C.git(real, 'rev-parse', args.head)
    if novo == b['head'] or not C.eh_ancestral(real, novo, b['head']):
        raise SystemExit('recusado: %s não é ancestral da base atual (%s) — a base só recua'
                         % (novo[:9], b['head'][:9]))
    eo.setdefault('bases_anteriores', []).append({'repo': args.repo, 'head': b['head'],
                                                  'fingerprint': b.get('fingerprint'),
                                                  'decisao': args.decisao, 'em': C.agora()})
    # o fingerprint da base era o do working tree no início, que não é o código do commit novo
    eo['baseline'][args.repo] = {'head': novo, 'fingerprint': None}
    C.salvar_estado(pasta, estado)
    entre = C.git(real, 'rev-list', '--reverse', '%s..%s' % (novo, b['head'])).split()
    print('onda %s: a base de %s recuou de %s para %s (%s). Commits que passam a ser da onda: %s — '
          '`vincular` cada um à sua tarefa' % (args.onda, args.repo, b['head'][:9], novo[:9], args.decisao,
                                               ', '.join(h[:9] for h in entre)))
    return 0


SEVERIDADES = ('alta', 'baixa')


def severidade(x):
    """Gravidade da pendência. Alta: quebra comportamento que um aceite já fechado (desta ou de onda
    anterior) garante, perda de dado, segurança ou indisponibilidade. Sem o campo (pendência
    histórica) conta como alta."""
    return x.get('severidade') or 'alta'


def pendencias_sem_onda(estado, p):
    """Pendências abertas (não descartadas) que nenhuma onda do plano tem na Origem (`P<n>`)."""
    cobertas = {x for o in p.ondas for x in P.origens(o) if re.fullmatch(r'P\d+', x)}
    return [x for x in estado.get('pendencias', []) if x['id'] not in cobertas and not x.get('descartada')]


def bloco_pendencias(estado, oid):
    """O que a revisão achou fora do escopo congelado da onda e foi levado para outra onda."""
    daqui = [x for x in estado.get('pendencias', []) if x['onda'] == oid]
    if not daqui:
        return '_nenhuma pendência levada desta onda_'
    linhas = ['| # | Origem | Severidade | Pendência | Situação |', '|---|---|---|---|---|']
    for x in daqui:
        sit = 'descartada — %s' % x['descartada'] if x.get('descartada') else 'aberta'
        linhas.append('| %s | %s | %s | %s | %s |' % (x['id'], x['origem'], severidade(x),
                                                    x['texto'].replace('|', '\\|'), sit))
    return '\n'.join(linhas)


def pendencia(pasta, args):
    """`pendencia add|list|descartar`: requisito novo achado na revisão vive aqui (não no plano, cujo
    hash o selo confere) até uma onda seguinte o ter na Origem (`P<n>`)."""
    if args.acao == 'list':
        estado = C.carregar_estado(pasta)
        ps = estado.get('pendencias', [])
        if not ps:
            print('nenhuma pendência')
        for x in ps:
            print('%s  onda %s  %s  [%s]  %s%s' % (x['id'], x['onda'], x['origem'], severidade(x), x['texto'],
                                                  '  [descartada: %s]' % x['descartada'] if x.get('descartada') else ''))
        return 0
    with C.transacao(pasta) as estado:
        if args.acao == 'add':
            if args.onda not in estado['ondas']:
                raise SystemExit('onda %s não foi iniciada' % args.onda)
            if not re.fullmatch(r'RV\d+|AC\d+|usuario', args.origem or '', re.IGNORECASE):
                raise SystemExit('--origem é RV<n> (revisão), AC<n> (autoconferência) ou "usuario"')
            if len((args.texto or '').strip()) < 15:
                raise SystemExit('--texto curto demais: o requisito, com o valor esperado se houver')
            sev = getattr(args, 'severidade', None)
            if not sev:
                raise SystemExit('recusado: --severidade alta|baixa é obrigatória. Alta: quebra comportamento '
                                 'que um aceite já fechado (desta ou de onda anterior) garante, perda de dado, '
                                 'segurança ou indisponibilidade; o resto é baixa')
            pid = C.proximo_id(estado, 'P')
            reg = {'id': pid, 'onda': args.onda, 'origem': args.origem.upper() if args.origem.lower() != 'usuario'
                   else 'usuario', 'texto': args.texto.strip(), 'em': C.agora()}
            if sev:
                reg['severidade'] = sev
            estado.setdefault('pendencias', []).append(reg)
            print('%s registrada (onda %s, %s, severidade %s) — entra numa onda seguinte com `**Origem:** %s`'
                  % (pid, args.onda, args.origem, severidade(reg), pid))
            return 0
        if args.acao == 'descartar':
            x = next((x for x in estado.get('pendencias', []) if x['id'].lower() == args.id.lower()), None)
            if not x:
                raise SystemExit('pendência %s não existe' % args.id)
            erro_d = DC.exigir(estado, args.decisao, para='descartar-pendencia', alvo=x['id'])
            if erro_d:
                raise SystemExit('recusado: descartar pendência é decisão do usuário — %s' % erro_d)
            x['descartada'] = args.decisao
            print('%s descartada (%s)' % (x['id'], args.decisao))
            return 0
    raise SystemExit('ação desconhecida')


def defeito(pasta, args):
    """`defeito add|list`: o sinal de qualidade que não é o próprio gate. `--origem revisao|parecer` é defeito que o
    processo achou (também contado pela classe `defeito` das lacunas); `posterior` é defeito **escapado**:
    visto depois da liberação, numa onda já fechada. Alimenta as métricas e o painel; não muda nenhum gate."""
    if args.acao == 'list':
        estado = C.carregar_estado(pasta)
        ds = estado.get('defeitos', [])
        if not ds:
            print('nenhum defeito registrado')
        for x in ds:
            print('%s  onda %s  %s  [%s]  %s' % (x['id'], x['onda'], x['origem'], x['severidade'], x['texto']))
        return 0
    with C.transacao(pasta) as estado:
        if args.onda not in estado['ondas']:
            raise SystemExit('onda %s não foi iniciada' % args.onda)
        if len((args.texto or '').strip()) < 15:
            raise SystemExit('--texto curto demais: o defeito, onde aparece e como se vê')
        eo = estado['ondas'][args.onda]
        if args.origem == 'posterior' and eo.get('estado') not in ('fechada', 'replanejada', 'abandonada'):
            raise SystemExit('recusado: escapado é o defeito visto depois da liberação, e a onda %s está %s — se o processo o '
                             'achou, use --origem revisao ou parecer' % (args.onda, eo.get('estado')))
        did = C.proximo_id(estado, 'DF')
        estado.setdefault('defeitos', []).append({
            'id': did, 'onda': args.onda, 'origem': args.origem, 'severidade': args.severidade,
            'texto': args.texto.strip(), 'em': C.agora()})
        print('%s registrado (onda %s, %s, severidade %s)%s' % (
            did, args.onda, args.origem, args.severidade, ' — escapado' if args.origem == 'posterior' else ''))
        return 0


def consolidar(pasta, oid, quieto=False):
    estado = C.carregar_estado(pasta)
    p = P.Plano(C.arquivo_plano(pasta))
    o = p.onda(oid)
    if not o:
        raise SystemExit('onda %s não está no plano' % oid)
    fps = fps_atuais(estado)
    blocos = {
        'commits': bloco_commits(estado, oid),
        'testes': bloco_testes(estado, oid, fps),
        'mutantes': M.tabela_mutantes(M.mutantes_validos(estado, oid, fps)),
        'aceite': bloco_aceite(p, oid),
        'decisoes': bloco_decisoes(estado, oid),
    }
    opcionais = {'pendencias': bloco_pendencias(estado, oid)}  # consolidações antigas não têm o marcador
    arq = C.arquivo_consolidacao(pasta, oid)
    if not os.path.exists(arq):
        blocos.update(opcionais)
        opcionais = {}
        texto = ESQUELETO_CONSOLIDACAO.format(
            onda=oid, titulo=o['titulo'], rotulo=C.rotulo(pasta), data=C.hoje_br(),
            plano=os.path.basename(C.arquivo_plano(pasta)),
            **{k: C.bloco(k, v) for k, v in blocos.items()})
        C.gravar(arq, texto)
        acao = 'criada'
    else:
        texto = C.ler(arq)
        faltando = []
        for nome, conteudo in opcionais.items():
            texto, _ = C.trocar_bloco(texto, nome, conteudo)
        for nome, conteudo in blocos.items():
            texto, achou = C.trocar_bloco(texto, nome, conteudo)
            if not achou:
                faltando.append(nome)
        C.gravar(arq, texto)
        acao = 'atualizada' + (' (sem marcador para: %s)' % ', '.join(faltando) if faltando else '')
    if not quieto:
        print('consolidação %s: %s' % (acao, arq))
    return arq


# ------------------------------------------------------------------------------ fechar

def aceite_so_de_testes(o, aceite):
    """Aceite cujas tarefas só têm arquivo de teste no Onde (ex.: um teste novo para comportamento
    que já existia). Como a onda **Só testes**, não há linha de produção alterada para mutar."""
    tarefas = [t for t in (o.get('tarefas') or {}).values()
               if aceite in P.lista_ids(t['campos'].get('Aceite', ''), C.RE_ACEITE)]
    return bool(tarefas) and all(P.onde_de(t) and all(M._eh_teste(i) for i in P.onde_de(t))
                                 for t in tarefas)


def morto_por_teste_da_onda(m, testes_da_onda):
    """O mutante morreu por asserção (não por erro nem timeout) numa classe de teste criada ou alterada na onda."""
    if m.get('morto_por') != 'falha':
        return False
    return any(T.casa_classe(t, f) for t in testes_da_onda.get(m['repo'], ())
               for f in (m.get('classes_que_falharam') or []))


def conta_fora_do_diff(o, m, testes_da_onda):
    """Numa onda **Só testes**, ou para um aceite cujas tarefas só mexem em teste, não há linha de
    produção alterada para mutar: vale o mutante em linha anterior à onda que morreu por asserção
    numa classe de teste criada ou alterada nela, porque foi o teste novo que pegou o defeito.
    Morte por erro, timeout ou teste antigo não conta."""
    if not (o.get('so_testes') or aceite_so_de_testes(o, m.get('aceite'))):
        return False
    return morto_por_teste_da_onda(m, testes_da_onda)


# Spec JS/TS -> classe, no padrão do JUnit que o tools/testar.mjs grava (`TEST-<Classe>.xml`):
# o nome do arquivo em PascalCase + Spec (ou Test): app-shortcut.spec.ts -> AppShortcutSpec.
RE_SPEC_JS = re.compile(r'\.(spec|test)\.(ts|js|mjs|tsx|jsx)$')
RE_CASO_JS = re.compile(r'\b(it|test)(\.\w+(\([^)]*\))?)*\s*\(')


def classe_de_spec(rel):
    m = RE_SPEC_JS.search(rel)
    if not m:
        return None
    nome = os.path.basename(rel)[:-len(m.group(0))]
    partes = [p for p in re.split(r'[-.]', nome) if p]
    return ''.join(p[0].upper() + p[1:] for p in partes) + m.group(1).capitalize()


def _testes_alterados(real, base, ate=None):
    """Classes de teste criadas ou alteradas desde o início da onda: Java com @Test, e spec JS/TS
    com algum caso (`it(`/`test(`), pelo nome de classe de `classe_de_spec`. Sem `ate`, até o que
    está no disco agora; com `ate` (um commit), até ele."""
    if ate:
        nomes = set(C.git(real, 'diff', '--name-only', base, ate).splitlines())
    else:
        nomes = set(C.git(real, 'diff', '--name-only', base).splitlines()) | set(C.nao_rastreados(real))
    classes = set()
    for rel in nomes:
        java = rel.endswith('.java') and M._eh_teste(rel)
        spec = classe_de_spec(rel)
        if not (java or spec):
            continue
        if ate:
            texto = C.git(real, 'show', '%s:%s' % (ate, rel), checar=False)
            if not texto:
                continue
        else:
            caminho = os.path.join(real, rel)
            if not os.path.isfile(caminho):
                continue
            with open(caminho, encoding='utf-8', errors='replace') as fh:
                texto = fh.read()
        if java and '@Test' in texto:
            classes.add(_classe_java(rel))
        elif spec and RE_CASO_JS.search(texto):
            classes.add(spec)
    return classes


def _classe_java(rel):
    """Nome qualificado pela posição em `src/test/java/` (o que o Surefire grava); fora desse padrão,
    o nome simples."""
    if 'src/test/java/' in rel:
        return rel.split('src/test/java/', 1)[1][:-len('.java')].replace('/', '.')
    return os.path.splitext(os.path.basename(rel))[0]


def _caso_de_teste(arquivo, codigo):
    """A linha declara um caso de teste: `@Test` em Java, `it(`/`test(` num spec JS/TS."""
    if arquivo.endswith('.java'):
        return bool(re.search(r'@Test\b', codigo))
    return bool(classe_de_spec(arquivo) and RE_CASO_JS.search(codigo))


def _comentada(codigo):
    return codigo.lstrip().startswith(('//', '/*', '*'))


def _integridade_testes(real, base, rel_, repo):
    """Teste desligado, comentado ou removido desde o início da onda — o furo que contagem não pega.
    Vale para Java (`@Test`) e para spec JS/TS (`it(`/`test(`)."""
    diff = C.git(real, 'diff', base, '--no-color', '-U0')
    arquivo = None
    adicionados = removidos = 0
    for ln in diff.splitlines():
        if ln.startswith('+++ '):
            arquivo = ln[6:] if ln.startswith('+++ b/') else None
            continue
        if ln.startswith('--- '):
            continue
        if not arquivo or not (M._eh_teste(arquivo) or classe_de_spec(arquivo)):
            continue
        codigo = ln[1:]
        if ln.startswith('+') and _desligados(arquivo, codigo):
            rel_.erro('%s: teste desligado em %s: %s' % (repo, arquivo, codigo.strip()[:80]))
        if not _caso_de_teste(arquivo, codigo):
            continue
        if _comentada(codigo):
            if ln.startswith('+'):
                rel_.erro('%s: teste comentado em %s: %s' % (repo, arquivo, codigo.strip()[:80]))
            continue
        if ln.startswith('+'):
            adicionados += 1
        elif ln.startswith('-'):
            removidos += 1
    # não rastreados (arquivos de teste novos) só somam — não há o que remover neles
    if removidos > adicionados:
        rel_.erro('%s: %d caso(s) de teste removido(s) e só %d adicionado(s) desde o início da onda — '
                  'teste não se apaga para passar' % (repo, removidos, adicionados))


def _desligados_na_base(real, base, classe):
    """Quantos testes da classe já estavam desligados no início da onda (legado): a classe Java ou
    o spec JS/TS cujo nome de classe é esse."""
    if not base:
        return 0
    padrao = ('*%s.java' % classe.replace('.', '/')) if '.' in classe else '*/%s.java' % classe
    arquivos = [f for f in C.git(real, 'ls-files', padrao, checar=False).splitlines() if f]
    arquivos += [f for f in C.git(real, 'ls-files', '*.spec.*', '*.test.*', checar=False).splitlines()
                 if f and classe_de_spec(f) == classe]
    total = 0
    for f in arquivos:
        conteudo = C.git(real, 'show', '%s:%s' % (base, f), checar=False)
        total += len(_desligados(f, conteudo))
    return total


def _so_recusa_de_selecao(execucao):
    """Execução reprovada só porque uma classe pedida não apareceu no relatório: o comando saiu 0
    e nenhuma classe que rodou teve falha ou erro. Superada por uma execução OK no mesmo código,
    não bloqueia o fechamento (só avisa)."""
    problemas = execucao.get('problemas') or []
    if not problemas or not all(p.startswith('classe pedida não rodou') for p in problemas):
        return False
    if execucao.get('exit') != 0:
        return False
    return all(not (c.get('falhas') or c.get('erros')) for c in (execucao.get('por_classe') or {}).values())


def _pulados(rel_, real, base, repo, exigidas, execucoes):
    """Skipped acima do que já estava desligado no início da onda: teste que não rodou não
    prova nada, e `assume`/`@Ignore` novo é o jeito silencioso de desligar."""
    vistos = {}
    for e in execucoes:
        for classe, tot in (e.get('por_classe') or {}).items():
            if any(_coberto(req, {classe}) for req in exigidas):
                vistos[classe] = max(vistos.get(classe, 0), tot.get('pulados', 0))
    for classe, pulados in sorted(vistos.items()):
        legado = _desligados_na_base(real, base, classe)
        if pulados > legado:
            rel_.erro('%s: %s com %d teste(s) pulado(s) sobre o código atual (no início da onda '
                      'havia %d desligado(s)) — teste pulado não prova o aceite' % (repo, classe, pulados, legado))


def _coberto(requerida, executadas):
    return any(T.casa_classe(requerida, e) for e in executadas)


def higiene_do_fechamento(pasta, estado, oid):
    """Ao fechar: remove worktrees órfãs do scratch das sessões de mutação da onda e comprime os logs de
    mutante dela (`.log` → `.log.gz`, o caminho no ledger acompanha). Nada de evidência se perde: o conteúdo
    continua no `.gz`. Devolve (worktrees removidas, logs comprimidos)."""
    import gzip
    removidas = comprimidos = 0
    mapa = {}  # caminho antigo (relativo à pasta) -> novo

    def _comprimir(rel_log):
        if not rel_log or not rel_log.endswith('.log'):
            return rel_log
        if rel_log in mapa:
            return mapa[rel_log]
        origem = os.path.join(pasta, rel_log)
        if not os.path.isfile(origem):
            return rel_log
        with open(origem, 'rb') as fh_in, gzip.open(origem + '.gz', 'wb') as fh_out:
            shutil.copyfileobj(fh_in, fh_out)
        os.remove(origem)
        mapa[rel_log] = rel_log + '.gz'
        return mapa[rel_log]

    for s_ in estado['sessoes_mutacao']:
        if s_['onda'] != oid:
            continue
        if s_['estado'] != 'preparada' and s_.get('scratch') and os.path.exists(s_['scratch']):
            cfg = estado['repos'].get(s_['repo'])
            if cfg:
                M._remover_worktree(cfg['caminho'], s_['scratch'])
                removidas += 1
        for sel in (s_.get('selecoes') or {}).values():
            if sel.get('log'):
                sel['log'] = _comprimir(sel['log'])
        for m in s_.get('mutantes', []):
            if m.get('log'):
                m['log'] = _comprimir(m['log'])
    return removidas, len(mapa)


def conferir_suite_inteira(rel, estado, repo, fp):
    """Fechamento: o repositório tocado na onda tem uma execução `--suite-inteira` fresca (sobre o
    código atual). Falha só vale se as classes que falham são as que o usuário aceitou como preexistentes da
    suíte do repo (`testar --suite-inteira --preexistentes D<n>`, só na primeira vez que ela falha); classe nova
    falhando é recusada."""
    execs = [e for e in estado['execucoes'] if e['repo'] == repo and e['tipo'] == 'teste' and e.get('suite_inteira')
             and T.vigente(e) and C.mesmo_fp(e.get('fingerprint'), fp)]
    if any(e.get('ok') for e in execs):
        return
    if not execs:
        rel.erro('%s: o fechamento exige a suíte inteira rodada sobre o código atual (`testar --suite-inteira`, '
                 'coberta pela autorização de testes do projeto) — nenhuma fresca' % repo)
        return
    ultima = next((e for e in reversed(execs) if T.so_falhas_de_teste(e)), None)
    if not ultima:
        rel.erro('%s: a suíte inteira (%s) não passou e não foi só falha de teste (%s) — rode de novo'
                 % (repo, execs[-1]['id'], '; '.join(execs[-1].get('problemas') or []) or 'sem detalhe'))
        return
    pre = (estado.get('falhas_preexistentes') or {}).get(repo)
    falhando = set(T.classes_falhando(ultima))
    if not pre:
        rel.erro('%s: a suíte inteira (%s) falha em %s e o repo não tem falhas preexistentes registradas — se já '
                 'falhavam antes da demanda, é decisão do usuário: `testar --suite-inteira --preexistentes D<n>`'
                 % (repo, ultima['id'], ', '.join(sorted(falhando))))
        return
    novas = falhando - set(pre['classes'])
    if novas:
        rel.erro('%s: a suíte inteira (%s) tem classe(s) nova(s) falhando fora das preexistentes (%s): %s'
                 % (repo, ultima['id'], pre['decisao'], ', '.join(sorted(novas))))
        return
    rel.aviso('%s: a suíte inteira (%s) falha só em classe(s) preexistente(s) aceita(s) por %s: %s'
              % (repo, ultima['id'], pre['decisao'], ', '.join(sorted(falhando))))


def dispensa_de_mutante(rel, pasta, estado, o, oid, args):
    """`--sem-mutante A<id>` com `--sem-mutante-decisao D<n>`: o aceite cuja prova mora só em arquivo de
    teste (um `beforeAll`, o próprio spec) não tem linha de produção para mutar, e arquivo de teste não se
    muta. Só com a decisão do usuário, e só se a revisão vigente deu o aceite como OK com toda a evidência
    em arquivo de teste. Devolve o registro da dispensa, ou None."""
    aceites = [a.strip() for a in (getattr(args, 'sem_mutante', None) or []) if a.strip()]
    if not aceites:
        if getattr(args, 'sem_mutante_decisao', None):
            rel.erro('--sem-mutante-decisao sem --sem-mutante: diga de que aceite')
        return None
    did = getattr(args, 'sem_mutante_decisao', None)
    erro_d = (DC.exigir(estado, did, para='sem-mutante') if did
              else 'dispensar o mutante de um aceite é decisão do usuário: `--sem-mutante-decisao D<n>`')
    if erro_d:
        rel.erro('--sem-mutante: ' + erro_d)
        return None
    ultima = (RV._revisoes(estado, oid) or [{}])[-1]
    arq = C.arquivo_revisao(pasta, oid)
    linhas = {}
    if ultima.get('id') and os.path.exists(arq):
        for cel in C.linhas_de_tabela(C.secao(C.ler(arq), r'^aceite a aceite')):
            aid = cel[0].strip('*` ') if cel else ''
            if C.RE_ACEITE.fullmatch(aid) and len(cel) >= 5:
                linhas[aid] = cel
    com_teste = P.aceites_com_teste(o)
    ok = []
    for a in aceites:
        if a not in o['aceites']:
            rel.erro('--sem-mutante: %s não é aceite da onda %s' % (a, oid))
            continue
        if a not in com_teste:
            rel.erro('--sem-mutante: %s não tem teste automatizado — não há mutante a dispensar' % a)
            continue
        cel = linhas.get(a)
        if not cel:
            rel.erro('--sem-mutante: %s não está na tabela de aceites da revisão vigente (%s)' % (a, ultima.get('id')))
            continue
        if cel[-1].strip('* ') != 'OK':
            rel.erro('--sem-mutante: %s não está OK na %s' % (a, ultima.get('id')))
            continue
        caminhos = [ev.strip().split(':')[1] if ev.strip().count(':') >= 2 else ev.strip()
                    for ev in cel[1].strip('` ').split(';') if ev.strip()]
        fora = [c_ for c_ in caminhos if c_.startswith('evidencia') or not M._eh_teste(c_)]
        if not caminhos or fora:
            rel.erro('--sem-mutante: a evidência de %s na %s não está só em arquivo de teste (%s) — o que tem '
                     'linha de produção se prova com mutante' % (a, ultima.get('id'), ', '.join(fora) or 'vazia'))
            continue
        ok.append(a)
    if len(ok) != len(aceites):
        return None
    return {'aceites': ok, 'decisao': did, 'revisao': ultima.get('id')}


def conferir_mutantes(rel, estado, o, eo, oid, fps, ate=None):
    """Gate de mutantes da onda: mínimo de mortos válidos em linhas distintas alteradas na onda, um
    por aceite testável, nenhum sobrevivente sem equivalência decidida pelo usuário. `fps` diz sobre
    que código os mutantes valem: o atual no `fechar`; o do fechamento quando o parecer reconfere uma
    onda já fechada (`ate` = os HEADs do fechamento, para achar as classes de teste da onda)."""
    com_teste = {a for a in P.aceites_com_teste(o)
                 if not o['aceites'].get(a, {}).get('reclassificado')}
    com_teste = {a for a in com_teste if any(
        not estado['repos'].get(P.repo_de(t), {}).get('sem_testes_automatizados')
        for t in o['tarefas'].values() if a in P.lista_ids(t['campos'].get('Aceite', ''), C.RE_ACEITE))}
    validos = [m for m in M.mutantes_validos(estado, oid, fps, ate) if m['aceite'] in o['aceites']]
    testes_da_onda = {}
    for r, b in eo['baseline'].items():
        if b.get('head') and r in estado['repos']:
            testes_da_onda[r] = _testes_alterados(estado['repos'][r]['caminho'], b['head'],
                                                  (ate or {}).get(r))
    mortos = []
    posicoes = set()
    # a cobertura por aceite aceita morto em linha repetida: "uma linha, um mutante" vale para o mínimo;
    # dois aceites cujo comportamento mora na mesma linha não se excluem
    cobertos = set()
    for m in validos:
        if m['resultado'] != 'morto':
            continue
        if m.get('morto_por') == 'oraculo' and m['aceite'] in com_teste:
            rel.aviso('mutante %s morreu pelo oráculo (--comando), não por teste — não prova o aceite %s, que '
                      'tem teste automatizado' % (m['id'], m['aceite']))
            continue
        if m.get('no_diff_da_onda') is False and not conta_fora_do_diff(o, m, testes_da_onda):
            # para a cobertura do aceite vale o teste da onda que pegou o defeito, mesmo em linha que a
            # onda não alterou (o comportamento já existia e o aceite pede o teste dele);
            # para o mínimo, não
            if morto_por_teste_da_onda(m, testes_da_onda):
                cobertos.add(m['aceite'])
            rel.aviso('mutante %s em %s:%d, linha que a onda não alterou — não conta para o mínimo%s'
                      % (m['id'], m['arquivo'], m['linha'],
                         ' (numa onda Só testes, ou para aceite cujas tarefas só mexem em teste, conta '
                         'se morreu por asserção numa classe de teste alterada na onda)'
                         if o.get('so_testes') or aceite_so_de_testes(o, m.get('aceite')) else ''))
            continue
        cobertos.add(m['aceite'])
        pos = (m['repo'], m['arquivo'], m['linha'])
        if pos in posicoes:
            rel.aviso('mutante %s repete a linha %s:%d — para o mínimo, conta uma vez por linha'
                      % (m['id'], m['arquivo'], m['linha']))
            continue
        posicoes.add(pos)
        mortos.append(m)
        if m.get('morto_por') in ('erro', 'timeout'):
            rel.aviso('mutante %s morreu por %s, não por asserção — confira se algum teste de fato '
                      'fixa aquele comportamento' % (m['id'], m['morto_por']))
    pa = (eo or {}).get('pendencias_aceitas') or {}
    isentos_a, isentos_m = set(pa.get('aceites', [])), set(pa.get('mutantes', []))
    md = (eo or {}).get('mutante_dispensado') or {}
    for a in md.get('aceites', []):
        if a in com_teste and a not in cobertos:
            rel.aviso('aceite %s sem mutante: a prova mora só em arquivo de teste, e o usuário dispensou o '
                      'mutante (%s) — o parecer tem de citá-lo' % (a, md.get('decisao')))
    isentos_a |= set(md.get('aceites', []))
    com_teste = {a for a in com_teste if a not in isentos_a}
    minimo = MIN_MUTANTES.get(o['risco'], 3)
    if P.porte(o) == 'leve':
        minimo = MIN_LEVE  # e continua valendo um morto por aceite testável
    if com_teste:
        if len(mortos) < minimo:
            rel.erro('%d mutante(s) morto(s) válido(s); o mínimo para risco %s%s é %d'
                     % (len(mortos), o['risco'] or 'normal',
                        ' (onda leve)' if minimo == MIN_LEVE else '', minimo))
        for a in sorted(com_teste):
            if a not in cobertos:
                rel.erro('aceite %s tem teste automatizado e nenhum mutante morto que o prove' % a)
    else:
        rel.aviso('nenhum aceite com teste automatizado — sem exigência de mutantes; a prova é o roteiro')
    for m in validos:
        if m['resultado'] == 'sobrevivente' and m['id'] in isentos_m:
            rel.aviso('mutante %s sobrevivente aceito como pendência (%s) — vai para o parecer' % (m['id'], pa.get('decisao')))
        elif m['resultado'] == 'sobrevivente' and not m.get('equivalente'):
            rel.erro('mutante %s sobreviveu (%s:%d, %s) — vira tarefa: fortalecer o teste'
                     % (m['id'], m['arquivo'], m['linha'], m['aceite']))
        elif m['resultado'] == 'sobrevivente':
            erro_d = DC.exigir(estado, m.get('equivalente_decisao'), para='equivalente', alvo=m['id'], consumir=False,
                               engenharia=True)
            if erro_d:
                rel.erro('mutante %s marcado equivalente sem decisão válida: %s' % (m['id'], erro_d))
            else:
                rel.aviso('mutante %s aceito como equivalente (%s): %s'
                          % (m['id'], m['equivalente_decisao'], m['equivalente']))
        elif m['resultado'] in ('nao_compila', 'invalido'):
            rel.aviso('mutante %s %s — não conta' % (m['id'], m['resultado']))


def fechar(pasta, args):
    oid = args.onda
    estado = C.carregar_estado(pasta)
    rel = C.Relatorio('fechar-onda %s%s' % (oid, ' (simulação)' if args.simular else ''))
    rel_plano, p = P.validar(pasta, estado)
    for e in rel_plano.erros:
        rel.erro('plano: ' + e)
    if not p:
        return rel.imprimir()
    o = p.onda(oid)
    eo = estado['ondas'].get(oid)
    if not o:
        raise SystemExit('onda %s não está no plano' % oid)
    if not eo or eo.get('estado') != 'em_execucao':
        extra = (' — %s foi a 3ª revisão e reprovou: `onda desbloquear`' % eo.get('bloqueada_por')
                 if (eo or {}).get('estado') == 'bloqueada' else '')
        rel.erro('onda %s não está em execução (estado: %s)%s' % (oid, (eo or {}).get('estado', 'não iniciada'), extra))
        return rel.imprimir()
    pa = eo.get('pendencias_aceitas') or {}

    erro_ap = DC.conferir_aprovacao(pasta, estado, oid)
    if erro_ap:
        rel.erro(erro_ap)
    mudou = C.skill_mudou(eo)
    if mudou:
        # A skill congela durante a onda: o que a onda provou foi sob a skill com que começou.
        if not getattr(args, 'skill_alterada', None):
            rel.erro('%s — fechar assim é decisão do usuário: `--skill-alterada D<n>`' % mudou)
        else:
            erro_d = DC.exigir(estado, args.skill_alterada, para='skill-alterada', alvo=oid)
            if erro_d:
                rel.erro('--skill-alterada: ' + erro_d)
    mudou_analise = C.analise_mudou(pasta, estado, eo)
    if mudou_analise:
        if not getattr(args, 'analise_alterada', None):
            rel.erro('%s — fechar assim é decisão do usuário: `--analise-alterada D<n>`' % mudou_analise)
        else:
            erro_d = DC.exigir(estado, args.analise_alterada, para='analise-alterada', alvo=oid)
            if erro_d:
                rel.erro('--analise-alterada: ' + erro_d)
    if o['a_verificar'] or p.a_verificar_fora:
        rel.erro('%d [A VERIFICAR] no plano — pergunta sem resposta não fecha onda'
                 % (o['a_verificar'] + p.a_verificar_fora))

    fps = fps_atuais(estado)
    repos = sorted({P.repo_de(t) for t in o['tarefas'].values()})

    # 1. Tarefas → commits
    ligados = {}
    for tid in o['ordem_tarefas']:
        r = eo.get('tarefas', {}).get(tid, {})
        if not r.get('commits') and not r.get('sem_commit'):
            rel.erro('%s sem commit registrado (`commit`, `vincular` ou `sem-commit`)' % tid)
        for c in r.get('commits', []):
            real = estado['repos'][c['repo']]['caminho']
            if not C.commit_existe(real, c['hash']):
                rel.erro('%s: commit %s não existe mais em %s (rebase?)' % (tid, c['hash'][:9], c['repo']))
            ligados.setdefault(c['repo'], set()).add(c['hash'])
    for repo in repos:
        cfg = estado['repos'][repo]
        base = eo['baseline'].get(repo, {}).get('head')
        if not base:
            continue
        for h in C.git(cfg['caminho'], 'rev-list', '%s..HEAD' % base).splitlines():
            if h and h not in ligados.get(repo, set()):
                rel.erro('%s: commit %s desde o início da onda sem tarefa (`vincular`)' % (repo, h[:9]))
        if C.git(cfg['caminho'], 'status', '--porcelain'):
            rel.aviso('%s tem alterações não commitadas — entram no fingerprint, e toda evidência '
                      'tem de ter sido produzida com elas' % repo)

    # 2. Padrão, testes frescos e íntegros
    pedidas_sem_padrao = PD.dispensas(estado, getattr(args, 'sem_padrao', None), rel)
    padrao_usado = {}
    for repo in repos:
        cfg = estado['repos'][repo]
        real = cfg['caminho']
        if repo not in fps:
            rel.erro('%s: o caminho %s não existe — sem o repositório não há o que conferir' % (repo, real))
            continue
        base = eo['baseline'].get(repo, {}).get('head')
        if cfg.get('padrao') and base:
            # Antes do `continue` do repositório sem suíte: o padrão vale também onde não há teste.
            rel_padrao = C.Relatorio()
            desp = PD.dispensadas_da_onda(eo, pedidas_sem_padrao, repo)
            usado = PD.da_onda(real, base, cfg['padrao'], desp, rel_padrao, cfg.get('ignorar_no_codigo', ()))
            usado.update(PD.rodar_lint(cfg['padrao'], real, rel_padrao, desp))
            padrao_usado.update({(repo, r): u for r, u in usado.items()})
            rel.absorver(rel_padrao, '%s: ' % repo)
        tarefas_repo = [t for t in o['tarefas'].values() if P.repo_de(t) == repo]
        gates = {P.gate_de(t) for t in tarefas_repo}
        frescas = T.execucoes_frescas(estado, repo, fps[repo])
        if 'roteiro' in gates and not [e for e in frescas if e['tipo'] == 'roteiro']:
            rel.erro('%s: tarefa com gate roteiro e nenhum roteiro registrado sobre o código atual '
                     '(`evidencia --tipo roteiro`)' % repo)
        elif 'roteiro' in gates:
            # Cada aceite de tarefa com gate roteiro precisa de passo num roteiro vigente
            exigidos = {a for t in tarefas_repo if P.gate_de(t) == 'roteiro'
                        for a in P.lista_ids(t['campos'].get('Aceite', ''), C.RE_ACEITE)}
            cobertos_ = {a for e in frescas if e['tipo'] == 'roteiro' for a in (e.get('aceites') or [])}
            sem_passo = sorted(exigidos - cobertos_)
            if sem_passo:
                rel.erro('%s: aceite(s) com gate roteiro sem passo em nenhum roteiro vigente e fresco: %s '
                         '(coluna Aceite do roteiro)' % (repo, ', '.join(sem_passo)))
        if cfg.get('sem_testes_automatizados'):
            if not [e for e in frescas if e['tipo'] in ('build', 'teste')]:
                rel.erro('%s: repo sem testes automatizados precisa de build fresco (`testar --build`)' % repo)
            continue
        if 'build' in gates and not [e for e in frescas if e['tipo'] == 'build']:
            rel.erro('%s: tarefa com gate build e nenhum build fresco' % repo)
        conferir_suite_inteira(rel, estado, repo, fps[repo])
        testes_frescos = [e for e in frescas if e['tipo'] == 'teste']
        exigidas = set()
        for t in tarefas_repo:
            if P.teste_automatizado(t):
                exigidas.update(P.classes_de_teste(t))
        if base:
            exigidas |= _testes_alterados(real, base)
            _integridade_testes(real, base, rel, repo)
        if (exigidas or any(P.teste_automatizado(t) for t in tarefas_repo)) and not testes_frescos:
            vencidas = [e for e in estado['execucoes'] if e['repo'] == repo and e['tipo'] == 'teste' and e.get('ok')
                        and not e.get('anulada')]
            rel.erro('%s: nenhuma execução de teste OK sobre o código atual%s' % (
                repo, ' (%d vencida(s): o código mudou depois delas)' % len(vencidas) if vencidas else ''))
            continue
        executadas = T.classes_executadas(testes_frescos)
        for classe in sorted(exigidas):
            if not _coberto(classe, executadas):
                rel.erro('%s: %s não rodou sobre o código atual' % (repo, classe))
        _pulados(rel, real, base, repo, exigidas, testes_frescos)
        falhas = [e for e in estado['execucoes'] if e['repo'] == repo and e['tipo'] == 'teste'
                  and not e.get('ok') and not e.get('anulada') and C.mesmo_fp(e.get('fingerprint'), fps[repo])]
        ordem = {e['id']: i for i, e in enumerate(estado['execucoes'])}
        superadas = [e for e in falhas if _so_recusa_de_selecao(e)
                     and any(ordem[ok['id']] > ordem[e['id']] for ok in testes_frescos)]
        for e in superadas:
            rel.aviso('%s: %s só recusou a seleção (%s) e foi superada por execução OK no mesmo código'
                      % (repo, e['id'], '; '.join(e.get('problemas') or [])))
        falhas = [e for e in falhas if e not in superadas]
        # a suíte inteira que falha só em preexistentes já foi conferida acima (aviso ou erro)
        falhas = [e for e in falhas if not T.suite_inteira_aceita(estado, e)]
        if falhas:
            rel.erro('%s: execução falhando sobre o código atual: %s' % (repo, ', '.join(e['id'] for e in falhas)))

    # 3. Mutantes
    dispensa = dispensa_de_mutante(rel, pasta, estado, o, oid, args)
    conferir_mutantes(rel, estado, o, dict(eo, mutante_dispensado=dispensa) if dispensa else eo, oid, fps)
    vencidos = M.mutantes_vencidos(estado, oid, fps)
    if vencidos:
        rel.aviso('%d mutante(s) de sessões anteriores venceram (o código mudou) e não contam' % vencidos)
    abertas = [s['id'] for s in estado['sessoes_mutacao'] if s['onda'] == oid and s['estado'] == 'preparada']
    if abertas:
        rel.erro('sessão(ões) de mutação ainda abertas: %s — `mutante limpar`' % ', '.join(abertas))
    invalidas = [s['id'] for s in estado['sessoes_mutacao'] if s['onda'] == oid
                 and s['estado'] == 'limpa' and s.get('integridade_ok') is False]
    if invalidas:
        rel.aviso('sessões com repositório real alterado durante a mutação (não contam): %s' % ', '.join(invalidas))

    # 4. Revisão independente
    rel_rv, veredito = RV.validar(pasta, oid, estado=estado, plano=p, fps=fps)
    rel.absorver(rel_rv, 'revisão: ')
    ultima_rv = (RV._revisoes(estado, oid) or [{}])[-1].get('id')
    if veredito == 'REPROVADA' and pa and pa.get('revisao') == ultima_rv:
        rel.aviso('revisão %s REPROVADA, fechada com pendências aceitas pelo usuário (%s): aceites %s; '
                  'mutantes %s — o parecer tem de citá-las' % (ultima_rv, pa['decisao'], ', '.join(pa['aceites']) or '—',
                                                              ', '.join(pa['mutantes']) or '—'))
    elif veredito != 'APROVADA' and not rel_rv.erros:
        rel.erro('revisão com veredito %s' % veredito)

    # 5. Aceite no plano
    for aid in o['ordem_aceites']:
        a = o['aceites'][aid]
        if not a['marcado'] and not a['reclassificado'] and aid not in pa.get('aceites', []):
            rel.erro('aceite %s não marcado [x] no plano' % aid)
        if a['riscado'] and not a['reclassificado']:
            rel.erro('aceite %s riscado sem a decisão do usuário (D<n>) que o tirou da onda' % aid)

    # 6. Consolidação
    arq = consolidar(pasta, oid, quieto=True)
    texto = C.ler(arq)
    for nome, rx in (('Verificado', r'^\d*\.?\s*verificado'), ('Não verificado', r'^\d*\.?\s*n[aã]o verificado')):
        corpo = C.secao(texto, rx)
        if corpo is None or not C.tem_conteudo(corpo):
            rel.erro('consolidação: seção "%s" ausente ou vazia' % nome)
    _conferir_ids_da_consolidacao(rel, texto, estado, o['aceites'].keys())
    if '<veredito da onda' in texto:
        rel.erro('consolidação: parágrafo de abertura ainda é o texto-guia')
    corpo = C.secao(texto, r'^\d*\.?\s*armadilhas')
    if corpo is None or not C.tem_conteudo(corpo):
        rel.aviso('consolidação: "Armadilhas desta rodada" vazia — nada a registrar como lição?')

    # 7. Lições: houve sinal (sobrevivente, execução que falhou, revisão reprovada) e nenhuma lição
    # registrada para esta onda — o autoteste do tlc: sinal sem lição tem de ser dito em voz alta.
    sinais = []
    sobrev = [m['id'] for s_ in estado['sessoes_mutacao'] if s_['onda'] == oid and s_.get('tipo') != 'autor'
              for m in s_.get('mutantes', []) if m['resultado'] == 'sobrevivente']
    if sobrev:
        sinais.append('%d sobrevivente(s)' % len(sobrev))
    falharam = [e['id'] for e in estado['execucoes'] if e.get('onda') == oid and not e.get('ok')
                and not e.get('anulada')]
    if falharam:
        sinais.append('%d execução(ões) que falharam' % len(falharam))
    rodadas = len([r_ for r_ in estado['revisoes'] if r_['onda'] == oid])
    if rodadas > 1:
        sinais.append('%d rodadas de revisão' % rodadas)
    if sinais:
        try:
            import licoes
            projeto = os.path.basename(pasta)
            registradas = [l['id'] for l in licoes.listar(status='all')
                           if any(o_.get('projeto') == projeto and o_.get('onda') == oid
                                  for o_ in l.get('ocorrencias', []))]
        except Exception:
            registradas = None
        if registradas == []:
            rel.aviso('a onda teve sinal (%s) e nenhuma lição registrada para ela — `licao add` (referencias/'
                      'licoes.md), ou diga ao usuário por que nenhum vale para outra demanda' % ', '.join(sinais))

    if rel.erros or args.simular:
        return rel.imprimir()
    eo['estado'] = 'fechada'
    eo['fechada_em'] = C.agora()
    for (repo, r), u in sorted(padrao_usado.items()):
        if r in pedidas_sem_padrao:
            PD.registrar(eo, 'fechamento', {r: dict(u, decisao=pedidas_sem_padrao[r])}, 'onda', repo)
    if dispensa:
        eo['mutante_dispensado'] = dispensa
    eo['fingerprints_no_fechamento'] = {r: fps[r] for r in repos}
    higiene = higiene_do_fechamento(pasta, estado, oid)
    C.salvar_estado(pasta, estado)
    consolidar(pasta, oid, quieto=True)
    try:
        import estado as E
        E.painel(pasta, quieto=True)
    except Exception as ex:
        rel.aviso('painel do ESTADO não atualizado: %s' % ex)
    rel.nota('Onda %s FECHADA em %s' % (oid, eo['fechada_em']))
    if higiene:
        rel.nota('  higiene: %d worktree(s) órfã(s) removida(s), %d log(s) de mutante comprimido(s) (.log.gz)' % higiene)
    for x in estado.get('pendencias', []):
        if x['onda'] == oid and not x.get('descartada'):
            rel.nota('  pendência %s [%s] levada para uma onda seguinte: %s' % (x['id'], severidade(x), x['texto'][:90]))
    for d in DC.rulings(estado):
        if d.get('onda') == oid:
            rel.nota('  decisão de engenharia %s (%s %s): %s — o usuário revê no parecer'
                     % (d['id'], d.get('para'), d.get('alvo') or '', d['texto'][:90]))
    return rel.imprimir()
