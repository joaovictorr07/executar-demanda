#!/usr/bin/env python3
"""Commits locais de tarefas, com escopo e testes verificados.

Mensagens seguem o projeto e são redigidas em PT-BR. Não exige hook global.
Repositórios com user.sigladev preservam a verificação do prefixo legado e marcadores.
O hash é vinculado à tarefa em .execucao.json e no plano.
"""

import os
import re
import subprocess

import comum as C
import decisoes as DC
import padrao as PD
import plano as P

RE_PREFIXO = re.compile(r'\S+ \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - ')


def _tarefa_e_repo(pasta, estado, tid):
    p = P.Plano(C.arquivo_plano(pasta))
    t = p.tarefa(tid)
    if not t:
        raise SystemExit('tarefa %s não está no plano' % tid)
    onda = estado['ondas'].get(t['onda'])
    if not onda or onda.get('estado') != 'em_execucao':
        if onda and onda.get('estado') == 'bloqueada':
            raise SystemExit('a onda %s está bloqueada (%s foi a 3ª revisão e reprovou) — o caminho é do '
                             'usuário: `onda desbloquear`' % (t['onda'], onda.get('bloqueada_por')))
        raise SystemExit('a onda %s não está em execução — `demanda.py iniciar-onda`' % t['onda'])
    erro_ap = DC.conferir_aprovacao(pasta, estado, t['onda'])
    if erro_ap:
        raise SystemExit('recusado: ' + erro_ap)
    repo = P.repo_de(t)
    cfg = C.repo_cfg(estado, repo)
    return p, t, onda, repo, cfg


def _registro(onda, tid):
    return onda.setdefault('tarefas', {}).setdefault(tid, {'commits': []})


def conferir_mensagem(msg, rel, prefixo_hook=False):
    if not msg.strip():
        rel.erro('mensagem vazia')
    assunto = msg.strip().splitlines()[0] if msg.strip() else ''
    if prefixo_hook and (RE_PREFIXO.match(assunto) or re.match(r'^T\d+-\w+\b', assunto)):
        rel.erro('a mensagem já traz o prefixo de branch/data — o hook global põe; passe só a '
                 'parte descritiva')
    if re.search(r'co-authored-by', msg, re.IGNORECASE):
        rel.erro('Co-Authored-By não entra em commit nenhum')
    if len(assunto) > 150:
        rel.aviso('assunto com %d caracteres' % len(assunto))


def conferir_marcadores(real, rel, diff=None):
    sigla = C.git(real, 'config', 'user.sigladev', checar=False)
    if not sigla:
        return
    padrao = re.compile(r'(DEBUG|WIP)-%s' % re.escape(sigla), re.IGNORECASE)
    if diff is None:
        diff = C.git(real, 'diff', '--cached', '-U0', '--no-color')
    arquivo = None
    for ln in diff.splitlines():
        if ln.startswith('+++ '):
            arquivo = ln[6:] if ln.startswith('+++ b/') else ln[4:]
        elif ln.startswith('+') and padrao.search(ln):
            rel.erro('marcador %s em linha adicionada de %s: %s'
                     % (padrao.search(ln).group(0), arquivo, ln[1:].strip()[:80]))


def conferir_padrao(estado, cfg, itens_sem_padrao, rel, conferir, modo='commit', h=None):
    """Gate de padrão do repositório (campo `padrao`): `conferir(padrao, dispensadas)` devolve as regras
    dispensadas que foram de fato usadas. Sem o campo, nada muda. Devolve esse {regra: {'decisao', 'arquivos'}}."""
    padrao = cfg.get('padrao')
    if not padrao:
        if itens_sem_padrao:
            rel.aviso('--sem-padrao ignorado: o repositório não tem padrão configurado')
        return {}
    dispensadas = PD.dispensas(estado, itens_sem_padrao, rel)
    usadas = conferir(padrao, dispensadas)
    if not rel.erros:
        usadas.update(PD.rodar_lint(padrao, cfg['caminho'], rel, dispensadas, modo, h))
    return usadas


def vizinho(f, onde):
    """O arquivo está na mesma pasta de um item do Onde (o DTO irmão, o teste ao lado)."""
    return any(os.path.dirname(f) == os.path.dirname(x) for x in onde)


def fora_do_onde(estado, decisoes, fora, onde):
    """(D<n> usadas, erro). Arquivo fora do Onde pede decisão do usuário; a de engenharia vale só quando
    todos os arquivos fora são vizinhos de um item do Onde."""
    ds, erro_d = DC.exigir_varias(estado, decisoes, para='fora-do-onde', engenharia=True)
    if erro_d:
        return ds, erro_d
    eng = [d for d in ds if (DC.achar(estado, d) or {}).get('fonte') == 'engenharia']
    distantes = [f for f in fora if not vizinho(f, onde)]
    if eng and distantes:
        return ds, ('%s é decisão de engenharia, e ela só cobre arquivo na mesma pasta de um item do Onde — %s '
                    'pede a decisão do usuário' % (', '.join(eng), ', '.join(distantes)))
    return ds, None


def conferir_correcao(estado, onda, t, correcao, rel):
    """Depois da 1ª revisão, todo commit da onda é correção de uma revisão dela
    (`--correcao RV<k>`), sob a tarefa dona do aceite e dentro do Onde — o plano não muda, e por
    isso não há reaprovação por rodada. Devolve o RV, ou None."""
    revs = [r for r in estado.get('revisoes', []) if r['onda'] == t['onda']]
    if not revs:
        if correcao:
            rel.erro('--correcao %s: a onda %s ainda não teve revisão' % (correcao, t['onda']))
        return correcao
    if not correcao:
        rel.erro('a onda %s já foi revisada (%s): commit agora é correção de lacuna — `--correcao %s`, '
                 'sob a tarefa dona do aceite; requisito novo vai para `pendencia add`'
                 % (t['onda'], revs[-1]['id'], revs[-1]['id']))
        return None
    if not any(r['id'].lower() == correcao.lower() for r in revs):
        rel.erro('--correcao %s não é revisão da onda %s (%s)' % (correcao, t['onda'], ', '.join(r['id'] for r in revs)))
    return correcao.upper()


def gate_vale(onda, t):
    """O gate da tarefa se aplica: tarefa que tem teste automatizado ou gate build.
    Roteiro e `Teste: nenhum` rodam sobre o código pronto, não no commit."""
    gate = P.gate_de(t)
    return not (gate == 'roteiro' or (not P.teste_automatizado(t) and gate != 'build'))


def conferir_gate_da_tarefa(estado, onda, t, cfg, real, sem_teste, rel):
    """O gate da tarefa roda antes do commit, e o script confere (antes era só instrução no
    SKILL.md). Rapido/completo: cada classe do campo Teste rodou OK sobre o código atual e nada falha
    sobre ele; build (ou repo sem suíte): build fresco; roteiro e `Teste: nenhum`: dispensados — o
    roteiro roda sobre o código pronto. Só funciona porque commitar não vence o teste (fingerprint por
    conteúdo). Escape: `--sem-teste D<n>`, decisão do usuário."""
    if not gate_vale(onda, t):
        return
    gate = P.gate_de(t)
    onde = P.onde_de(t)
    soltos = [f for f in C.git(real, 'diff', '--name-only').splitlines() + C.nao_rastreados(real)
              if f and C.casa_padrao(f, onde)]
    if soltos:
        rel.erro('alteração fora do índice dentro do Onde de %s (%s): o teste viu o working tree e o commit '
                 'leva só o staged — `git add` ou desfaça antes' % (t['id'], ', '.join(soltos[:5])))
    if sem_teste:
        erro_d = DC.exigir(estado, sem_teste, para='sem-teste', alvo=t['id'])
        if erro_d:
            rel.erro('--sem-teste: ' + erro_d)
        else:
            rel.aviso('gate da tarefa dispensado por %s' % sem_teste)
        return
    import onda as OND
    import testes as T
    fp = C.fingerprint(real)
    frescas = T.execucoes_frescas(estado, P.repo_de(t), fp)
    if cfg.get('sem_testes_automatizados') or gate == 'build':
        if not [e for e in frescas if e['tipo'] in ('build', 'teste')]:
            rel.erro('%s: gate %s sem build (ou teste) OK sobre o código que vai no commit — `testar --build`'
                     % (t['id'], gate))
        return
    executadas = T.classes_executadas([e for e in frescas if e['tipo'] == 'teste'])
    faltam = [c for c in P.classes_de_teste(t) if not OND._coberto(c, executadas)]
    if faltam:
        rel.erro('%s: %s não rodou OK sobre o código que vai no commit — `testar --classes %s` antes '
                 '(ou `--sem-teste D<n>` com a decisão do usuário)' % (t['id'], ', '.join(faltam), ','.join(faltam)))
    ordem = {e['id']: i for i, e in enumerate(estado['execucoes'])}
    ultima_ok = max([ordem[e['id']] for e in frescas if e['tipo'] == 'teste'] or [-1])
    falhando = [e['id'] for e in estado['execucoes'] if e['repo'] == P.repo_de(t) and e['tipo'] == 'teste'
                and not e.get('ok') and not e.get('anulada') and C.mesmo_fp(e.get('fingerprint'), fp)
                and ordem[e['id']] > ultima_ok]
    if falhando:
        rel.erro('%s: execução falhando sobre o código que vai no commit: %s' % (t['id'], ', '.join(falhando)))


def commit(pasta, args):
    estado = C.carregar_estado(pasta)
    p, t, onda, repo, cfg = _tarefa_e_repo(pasta, estado, args.tarefa)
    real = cfg['caminho']
    rel = C.Relatorio('commit %s (%s)' % (args.tarefa, repo))
    conferir_mensagem(args.m, rel, bool(C.git(real, 'config', 'user.sigladev', checar=False)))
    staged = [f for f in C.git(real, 'diff', '--cached', '--name-only').splitlines() if f]
    if not staged:
        rel.erro('nada staged em %s — `git add` os arquivos da tarefa antes' % real)
    correcao = conferir_correcao(estado, onda, t, getattr(args, 'correcao', None), rel)
    onde = P.onde_de(t)
    fora = [f for f in staged if not C.casa_padrao(f, onde)]
    if fora:
        ds, erro_d = fora_do_onde(estado, args.decisao, fora, onde)
        if erro_d:
            for f in fora:
                rel.erro('%s está fora do Onde de %s (%s) — ampliar escopo é do usuário: '
                         '`--decisao D<n>` ou Onde corrigido e plano aprovado de novo (%s)'
                         % (f, args.tarefa, ', '.join(onde) or 'vazio', erro_d))
        else:
            rel.aviso('%d arquivo(s) fora do Onde de %s, autorizado(s) por %s: %s'
                      % (len(fora), args.tarefa, ', '.join(ds), ', '.join(fora)))
    conferir_marcadores(real, rel)
    padrao_usado = conferir_padrao(
        estado, cfg, getattr(args, 'sem_padrao', None), rel,
        lambda pad, desp: PD.do_indice(real, pad, desp, rel, cfg.get('ignorar_no_codigo', ())))
    conferir_gate_da_tarefa(estado, onda, t, cfg, real, getattr(args, 'sem_teste', None), rel)
    branch = C.branch_atual(real)
    if cfg.get('branch') and branch != cfg['branch']:
        rel.erro('repositório em %r; a branch do projeto é %r' % (branch, cfg['branch']))
    if rel.erros:
        return rel.imprimir()

    proc = subprocess.run(['git', '-C', real, 'commit', '-m', args.m], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    saida = proc.stdout.decode('utf-8', 'replace')
    if proc.returncode != 0:
        print(saida)
        print('ERRO: git commit falhou (exit %d) — nada registrado' % proc.returncode)
        return 1
    h = C.git(real, 'rev-parse', 'HEAD')
    assunto = C.git(real, 'log', '-1', '--format=%s')
    if C.git(real, 'config', 'core.hooksPath', checar=False):
        n = len(RE_PREFIXO.findall(assunto))
        if n != 1:
            rel.aviso('o assunto final tem o prefixo %d vez(es): %r — confira o hook antes de '
                      'seguir (não corrijo com --amend: o hook reprefixaria)' % (n, assunto))
    reg = _registro(onda, args.tarefa)
    reg['commits'].append({'hash': h, 'repo': repo, 'assunto': assunto, 'em': C.agora(),
                           'fora_do_onde': fora, 'decisao': ', '.join(ds) if fora else None,
                           'correcao': correcao})
    PD.registrar(onda, args.tarefa, padrao_usado, h[:9], repo)
    C.salvar_estado(pasta, estado)
    P.registrar_commits(pasta, args.tarefa, [c['hash'][:9] for c in reg['commits']])
    rel.nota('commit %s — %s' % (h[:9], assunto))
    rel.imprimir()
    return 0


def _gate_do_vinculo(estado, onda, t, cfg, real, h, sem_teste, rel):
    """`git commit` direto seguido de `vincular` não pode pular o gate da tarefa. O teste prova o código
    do working tree: só vale para o commit que é o HEAD com a árvore limpa (o código dele é o que rodou).
    Commit antigo não tem como ser conferido — `--sem-teste D<n>`, decisão do usuário."""
    if not gate_vale(onda, t):
        return
    if h == C.git(real, 'rev-parse', 'HEAD') and not C.git(real, 'status', '--porcelain'):
        conferir_gate_da_tarefa(estado, onda, t, cfg, real, sem_teste, rel)
        return
    if not sem_teste:
        rel.erro('%s: o gate da tarefa não tem como ser conferido num commit que não é o HEAD com a árvore '
                 'limpa (o teste prova o código do working tree) — `--sem-teste D<n>` com a decisão do usuário, '
                 'ou refaça o teste sobre o HEAD' % t['id'])
        return
    erro_d = DC.exigir(estado, sem_teste, para='sem-teste', alvo=t['id'])
    if erro_d:
        rel.erro('--sem-teste: ' + erro_d)
    else:
        rel.aviso('gate da tarefa dispensado por %s (commit %s não conferido)' % (sem_teste, h[:9]))


def vincular(pasta, args):
    """Commit feito fora do `demanda.py commit` (à mão, pela IDE) ligado à sua tarefa."""
    estado = C.carregar_estado(pasta)
    p, t, onda, repo, cfg = _tarefa_e_repo(pasta, estado, args.tarefa)
    real = cfg['caminho']
    if not C.commit_existe(real, args.hash):
        raise SystemExit('commit %s não existe em %s' % (args.hash, real))
    h = C.git(real, 'rev-parse', args.hash)
    base = onda['baseline'].get(repo, {}).get('head')
    if base and (h == base or not C.eh_ancestral(real, base, h)):
        raise SystemExit('%s não é posterior ao início da onda (%s)' % (h[:9], base[:9]))
    for outro_tid, r in onda.get('tarefas', {}).items():
        if any(c['hash'] == h for c in r.get('commits', [])):
            raise SystemExit('%s já está ligado a %s' % (h[:9], outro_tid))
    # O commit feito fora do script passa pelas mesmas regras do `commit`: está na branch do
    # projeto, mensagem sem Co-Authored-By e com o prefixo do hook uma vez só, sem marcador.
    rel = C.Relatorio('vincular %s a %s' % (h[:9], args.tarefa))
    if cfg.get('branch'):
        ref = 'refs/heads/%s' % cfg['branch']
        if not C.git_ok(real, 'rev-parse', '--verify', '-q', ref) or not (
                h == C.git(real, 'rev-parse', ref) or C.eh_ancestral(real, h, ref)):
            rel.erro('%s não está na branch do projeto (%s)' % (h[:9], cfg['branch']))
    msg = C.git(real, 'log', '-1', '--format=%B', h)
    if re.search(r'co-authored-by', msg, re.IGNORECASE):
        rel.erro('Co-Authored-By não entra em commit nenhum')
    assunto_h = msg.strip().splitlines()[0] if msg.strip() else ''
    if C.git(real, 'config', 'core.hooksPath', checar=False) and len(RE_PREFIXO.findall(assunto_h)) > 1:
        rel.erro('o assunto tem o prefixo de branch/data %d vezes: %r'
                 % (len(RE_PREFIXO.findall(assunto_h)), assunto_h))
    conferir_marcadores(real, rel, C.git(real, 'show', '-U0', '--no-color', '--format=', h))
    padrao_usado = conferir_padrao(
        estado, cfg, getattr(args, 'sem_padrao', None), rel,
        lambda pad, desp: PD.do_commit(real, h, pad, desp, rel, cfg.get('ignorar_no_codigo', ())), 'vinculo', h)
    correcao = conferir_correcao(estado, onda, t, getattr(args, 'correcao', None), rel)
    _gate_do_vinculo(estado, onda, t, cfg, real, h, getattr(args, 'sem_teste', None), rel)
    if rel.erros:
        return rel.imprimir()
    # o commit feito fora do script passa pela mesma regra de escopo que o `commit`
    arquivos = [f for f in C.git(real, 'show', '--name-only', '--format=', h).splitlines() if f]
    fora = [f for f in arquivos if not C.casa_padrao(f, P.onde_de(t))]
    if fora:
        ds, erro_d = fora_do_onde(estado, args.decisao, fora, P.onde_de(t))
        if erro_d:
            raise SystemExit('recusado: %s traz arquivo(s) fora do Onde de %s (%s) — ampliar escopo é '
                             'do usuário: `--decisao D<n>` (%s)' % (h[:9], args.tarefa, ', '.join(fora), erro_d))
    reg = _registro(onda, args.tarefa)
    reg['commits'].append({'hash': h, 'repo': repo, 'assunto': C.git(real, 'log', '-1', '--format=%s', h),
                           'em': C.agora(), 'vinculado': True, 'fora_do_onde': fora,
                           'decisao': ', '.join(ds) if fora else None, 'correcao': correcao})
    PD.registrar(onda, args.tarefa, padrao_usado, h[:9], repo)
    C.salvar_estado(pasta, estado)
    P.registrar_commits(pasta, args.tarefa, [c['hash'][:9] for c in reg['commits']])
    print('%s ligado a %s' % (h[:9], args.tarefa))
    return 0


def sem_commit(pasta, args):
    estado = C.carregar_estado(pasta)
    p, t, onda, repo, cfg = _tarefa_e_repo(pasta, estado, args.tarefa)
    if len((args.motivo or '').strip()) < 20:
        raise SystemExit('motivo curto demais: diga por que a tarefa fecha sem commit')
    erro_d = DC.exigir(estado, args.decisao, para='sem-commit', alvo=args.tarefa)
    if erro_d:
        raise SystemExit('recusado: fechar tarefa sem commit é decisão do usuário — %s' % erro_d)
    if onda.get('tarefas', {}).get(args.tarefa, {}).get('commits'):
        raise SystemExit('%s já tem commit — sem-commit é para tarefa que não gera código' % args.tarefa)
    reg = _registro(onda, args.tarefa)
    reg['sem_commit'] = '%s (%s)' % (args.motivo.strip(), args.decisao)
    C.salvar_estado(pasta, estado)
    print('%s registrada sem commit: %s' % (args.tarefa, args.motivo.strip()))
    return 0
