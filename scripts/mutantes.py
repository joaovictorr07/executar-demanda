#!/usr/bin/env python3
"""Injeção de defeitos (o "discrimination sensor" do tlc) num scratch isolado.

O revisor escolhe a mutação — é julgamento: que condição inverter, que valor trocar, que efeito
colateral remover. O script faz o resto, e é aí que mora a garantia:

- **o repositório real nunca é tocado.** A sessão cria uma `git worktree` no scratch, replica
  nela o estado não commitado (diff + não rastreados — uma onda inteira pode estar fora de
  commit) e confere que a réplica tem o mesmo fingerprint do real. Ao limpar, confere que o
  porcelain e o fingerprint do real são os mesmos do começo. Nunca `git stash`: um stash grava o
  estado *antes* da mutação, e o pop não a desfaz.
- **`target/` é copiado, nunca hardlinkado**: o Maven sobrescreve `.class` no lugar e levaria o
  original junto. Isso evita a compilação a frio de 1.300 classes por sessão.
- **morto só conta se a seleção passava sem a mutação.** Antes do primeiro mutante de cada
  seleção de testes (ou comando-oráculo), ela roda limpa no scratch; se já falha, a seleção é
  recusada — senão todo mutante "morreria".
- **mutante que não compila não é morto.** É `nao_compila`, e não conta.
- **o arquivo é restaurado e conferido por sha1** depois de cada mutante.
- **arquivo de teste não se muta.** Mutar o teste mede o teste contra ele mesmo.
- **quem escolhe a mutação é o revisor.** A sessão só abre com uma revisão da onda iniciada e
  vigente (código igual ao do `revisao iniciar`), e só contam os mutantes da revisão mais
  recente — o autor não deixa mutantes fáceis prontos antes dela.
- **o mutante mira o código da onda.** Cada um grava se a linha mutada foi alterada desde o
  início da onda; fora disso, não conta para o mínimo.
- **equivalente é decisão do usuário**, ou de engenharia com a autorização dele (`--decisao D<n>`).
  O revisor só propõe.
"""

import argparse
import hashlib
import os
import shutil
import time

import comum as C
import decisoes as DC
import testes as T

RESULTADOS_QUE_CONTAM = ('morto',)
PADROES_TESTE = ('/src/test/', '/test/', '/tests/', '/testes/', '.spec.ts', '.spec.js',
                 'Test.java', 'Tests.java', 'IT.java', '_test.py', '/e2e/')


def _eh_teste(rel):
    r = '/' + rel.replace('\\', '/')
    base = os.path.basename(r)
    return any(p in r for p in PADROES_TESTE) or base.startswith('test_')


def _sessao(estado, sid=None, repo=None, aberta=True):
    candidatas = [s for s in estado['sessoes_mutacao']
                  if (sid is None or s['id'] == sid) and (repo is None or s['repo'] == repo)
                  and (not aberta or s['estado'] == 'preparada')]
    if sid and not candidatas:
        raise SystemExit('sessão %s não encontrada%s' % (sid, ' ou já limpa' if aberta else ''))
    if len(candidatas) != 1:
        raise SystemExit('informe --sessao: %d sessões abertas%s (%s)'
                         % (len(candidatas), ' para ' + repo if repo else '',
                            ', '.join(s['id'] for s in candidatas) or 'nenhuma'))
    return candidatas[0]


def _por_id(estado, sid):
    for s in estado['sessoes_mutacao']:
        if s['id'] == sid:
            return s
    raise SystemExit('sessão %s sumiu do estado' % sid)


def _ignorar(cfg):
    return list(cfg.get('copiar_no_scratch', [])) + list(cfg.get('linkar_no_scratch', []))


# ------------------------------------------------------------------------------ preparar

def preparar(pasta, args):
    estado = C.carregar_estado(pasta)
    cfg = C.repo_cfg(estado, args.repo)
    real = cfg['caminho']
    onda = args.onda or C.onda_ativa(estado)
    if not onda:
        raise SystemExit('informe --onda (nenhuma onda em execução)')
    autor = getattr(args, 'autor', False)
    # O autor não cria mutante. Depois de uma revisão, abre uma sessão `pre_revisao` só para reaplicar
    # os sobreviventes dela sobre o código de agora, antes da revisão seguinte.
    revs = [r for r in estado.get('revisoes', []) if r['onda'] == onda]
    if autor and not revs:
        raise SystemExit('recusado: o autor não muta antes da 1ª revisão — a autoconferência é a tabela de aceites; '
                         '`--autor` serve para reaplicar os sobreviventes de uma revisão antes da seguinte')
    if not revs:
        raise SystemExit('nenhuma revisão iniciada para a onda %s — mutante é trabalho do revisor: '
                         '`revisao iniciar` antes' % onda)
    pre_revisao = autor
    rv = None if autor else revs[-1]
    import decisoes as DC
    erro_aut = DC.exigir_autorizacao_de_testes(estado, getattr(args, 'decisao', None))
    if erro_aut:
        raise SystemExit('recusado: mutante roda testes — ' + erro_aut)
    if rv and args.repo in rv['fingerprints'] and not C.mesmo_fp(rv['fingerprints'][args.repo], C.fingerprint(real)):
        raise SystemExit('%s está vencida (o código de %s mudou depois dela) — inicie outra revisão'
                         % (rv['id'], args.repo))
    sid = C.atualizar(pasta, lambda e: C.proximo_id(e, 'S'))
    identidade = C.sha1_bytes(os.path.normcase(os.path.abspath(pasta)).encode('utf-8'))[:16]
    scratch = os.path.join(C.dir_scratch(), '%s-%s-%s' % (identidade, sid, args.repo))
    if os.path.exists(scratch):
        shutil.rmtree(scratch)
    base_real = {'porcelain': C.porcelain_sha1(real), 'fingerprint': C.fingerprint(real)}

    C.git(real, 'worktree', 'add', '--detach', scratch, 'HEAD')
    try:
        diff = C.git(real, 'diff', 'HEAD', '--binary', bruto=True)
        if diff.strip():
            C.git(scratch, 'apply', '--binary', '--whitespace=nowarn', '-', entrada=diff)
        for rel in C.nao_rastreados(real):
            origem = os.path.join(real, rel)
            destino = os.path.join(scratch, rel)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            if os.path.islink(origem):
                shutil.copy2(origem, destino) if os.name == 'nt' else os.symlink(os.readlink(origem), destino)
            elif os.path.isfile(origem):
                shutil.copy2(origem, destino)
        for d in cfg.get('copiar_no_scratch', []):
            if os.path.isdir(os.path.join(real, d)):
                shutil.copytree(os.path.join(real, d), os.path.join(scratch, d),
                                symlinks=(os.name != 'nt'), dirs_exist_ok=True)
        for d in cfg.get('linkar_no_scratch', []):
            if os.path.exists(os.path.join(real, d)) and not os.path.exists(os.path.join(scratch, d)):
                shutil.copytree(os.path.join(real, d), os.path.join(scratch, d)) if os.name == 'nt' else os.symlink(os.path.join(real, d), os.path.join(scratch, d))
        fp_replica = C.fingerprint(scratch, _ignorar(cfg), excluir=C.excluir_de(real))
    except Exception:
        _remover_worktree(real, scratch)
        raise
    if not C.mesmo_fp(fp_replica, base_real['fingerprint']):
        _remover_worktree(real, scratch)
        raise SystemExit('a réplica no scratch não reproduz o repositório real (fingerprint %s ≠ %s). '
                         'Arquivo fora do .gitignore gerado na cópia? Sessão abortada.'
                         % (fp_replica['assinatura'], base_real['fingerprint']['assinatura']))
    sessao = {'id': sid, 'repo': args.repo, 'onda': onda, 'scratch': scratch,
              'revisao': None if autor else rv['id'], 'tipo': 'autor' if autor else 'revisor',
              'autoconferencia': None, 'pre_revisao': pre_revisao,
              'criada_em': C.agora(), 'base_real': base_real, 'estado': 'preparada',
              'selecoes': {}, 'integridade_ok': None}
    C.atualizar(pasta, lambda e: e['sessoes_mutacao'].append(sessao))
    print('sessão %s preparada para %s (onda %s, %s)\n  scratch: %s\n  fingerprint: %s'
          % (sid, args.repo, onda, 'pré-revisão do autor: só `reaplicar`' if pre_revisao else 'revisão %s' % rv['id'],
             scratch, base_real['fingerprint']['assinatura']))
    return 0


def _remover_worktree(real, scratch):
    C.git(real, 'worktree', 'remove', '--force', scratch, checar=False)
    if os.path.exists(scratch):
        shutil.rmtree(scratch, ignore_errors=True)
    C.git(real, 'worktree', 'prune', checar=False)


# ------------------------------------------------------------------------------ aplicar

def _chave_selecao(args):
    if args.comando:
        return 'comando:' + args.comando
    classes = ','.join(sorted(c.strip() for c in (args.testes or '').split(',') if c.strip()))
    if not classes:
        raise SystemExit('informe --testes (classes) ou --comando (oráculo, p.ex. comparar.py)')
    return 'testes:' + classes


def _rodar_selecao(pasta, cfg, sessao, chave_sel, rotulo_log, timeout):
    scratch = sessao['scratch']
    if chave_sel.startswith('comando:'):
        comando = chave_sel[len('comando:'):].replace('{scratch}', scratch)
    else:
        comando = T.montar_comando(cfg, chave_sel[len('testes:'):].split(','), False, False)
    log = os.path.join(pasta, 'evidencias', 'mutantes', '%s-%s-%s.log'
                       % (sessao['id'], rotulo_log, time.strftime('%Y%m%d-%H%M%S')))
    relatorios_antes = T.retratar_relatorios(scratch, cfg.get('relatorios', ''))
    inicio = time.time()
    codigo, saida = C.rodar(comando, scratch, log, timeout=timeout)
    totais, por_classe = None, {}
    if chave_sel.startswith('testes:'):
        totais, por_classe = T.extrair_totais(scratch, cfg.get('relatorios', ''), inicio, saida, relatorios_antes)
    falharam = sorted(c for c, v in (por_classe or {}).items() if v.get('falhas') or v.get('erros'))
    return comando, codigo, totais, os.path.relpath(log, pasta), falharam


def _causa(chave_sel, codigo, totais):
    """Por que o mutante morreu: `falha` (asserção), `erro` (exceção), `timeout` ou `oraculo`."""
    if codigo == 124:
        return 'timeout'
    if chave_sel.startswith('comando:'):
        return 'oraculo'
    if totais and totais['falhas']:
        return 'falha'
    return 'erro'


def _no_diff_da_onda(estado, sessao, cfg, rel):
    base = estado['ondas'].get(sessao['onda'], {}).get('baseline', {}).get(sessao['repo'], {}).get('head')
    if not base:
        return None
    return C.linhas_alteradas(cfg['caminho'], base, rel)


def _diff_rastreado(scratch):
    """sha1 do que está modificado nos arquivos rastreados do scratch. Fora o mutante em curso (que é
    restaurado), nada deve mexer neles entre a rodada limpa e os mutantes."""
    return C.sha1_bytes(C.git(scratch, '-c', 'core.quotepath=false', 'diff', '--no-color', 'HEAD',
                              bruto=True, checar=False))


def _classificar(chave_sel, codigo, totais, codigos_morto):
    if codigo == 124:
        # timeout não é morte: com `--timeout 1` toda mutação "morreria" sem teste nenhum. Laço infinito
        # provocado por mutação é achado do revisor, não contagem.
        return 'invalido'
    if chave_sel.startswith('comando:'):
        if codigo == 0:
            return 'sobrevivente'
        return 'morto' if codigo in codigos_morto else 'invalido'
    if totais and (totais['falhas'] or totais['erros']):
        return 'morto'
    if codigo != 0:
        return 'nao_compila' if not totais or not totais['run'] else 'invalido'
    if not totais or not totais['run']:
        return 'invalido'
    return 'sobrevivente'


def sobreviventes_pendentes(estado, onda):
    """Sobreviventes das revisões da onda (sessões do revisor, todas as rodadas) não aceitos como
    equivalentes: o teste que fecha cada um tem de ser provado antes da revisão seguinte (pré-revisão
    do autor), reaplicando o mesmo mutante."""
    saida, vistos = [], set()
    for s in estado['sessoes_mutacao']:
        if s['onda'] != onda or s.get('tipo') == 'autor':
            continue
        for m in s.get('mutantes', []):
            if m['resultado'] == 'sobrevivente' and not m.get('equivalente') and m['id'] not in vistos:
                vistos.add(m['id'])
                saida.append(m)
    return saida


def reaplicado_e_morto(estado, onda, mid, fps_atuais, aceita_removido=False):
    """O sobrevivente `mid` foi reaplicado (autoconferência, pré-revisão ou revisão) e morreu, numa
    sessão limpa e íntegra sobre o código atual. `aceita_removido`: também vale o trecho
    ter sumido do código (`codigo_removido`) — não há o que reaplicar, e o revisor confere o código novo."""
    validos = ('morto', 'codigo_removido') if aceita_removido else ('morto',)
    for s_ in estado['sessoes_mutacao']:
        if s_['onda'] != onda or s_['estado'] != 'limpa' or not s_.get('integridade_ok'):
            continue
        if not C.mesmo_fp(s_['base_real']['fingerprint'], fps_atuais.get(s_['repo'])):
            continue
        if any(m.get('reaplica') == mid and m['resultado'] in validos for m in s_.get('mutantes', [])):
            return True
    return False


def _mutante(estado, mid):
    for s_ in estado['sessoes_mutacao']:
        for m in s_.get('mutantes', []):
            if m['id'].lower() == (mid or '').lower():
                return s_, m
    return None, None


def _localizar_linhas(linhas, de, linha):
    """Núcleo de `localizar`, sobre as linhas já lidas."""
    if 1 <= linha <= len(linhas) and linhas[linha - 1].count(de) == 1:
        return linha, 'ok'
    com = [i for i, ln in enumerate(linhas, 1) if de in ln]
    if not com:
        return None, 'codigo_removido'
    unicas = [i for i in com if linhas[i - 1].count(de) == 1]
    if len(com) == 1 and unicas:
        return unicas[0], 'ok'
    return com, 'ambiguo'


def localizar(caminho, de, linha):
    """(linha, situação) do `--de` no código de agora: a linha original se ele ainda está lá uma vez;
    senão a única linha do arquivo que o tem uma vez. Situação: 'ok', 'codigo_removido' (o trecho não
    existe mais) ou 'ambiguo' (aparece em várias linhas; `linha` vira a lista delas)."""
    try:
        with open(caminho, encoding='utf-8', errors='replace') as fh:
            linhas = fh.read().splitlines()
    except OSError:
        return None, 'codigo_removido'
    return _localizar_linhas(linhas, de, linha)


# ------------------------------------------------------------------------------ blobs

LIMITE_BLOB = 5 * 1024 * 1024


def _dir_blobs(pasta):
    return os.path.join(pasta, 'evidencias', 'mutantes', 'blobs')


def guardar_blob(pasta, origem, nome):
    """Copia `origem` para `evidencias/mutantes/blobs/<nome>`, uma vez só por nome (o nome é um sha1
    do conteúdo). É o que deixa comparar, numa revisão seguinte, o arquivo como estava antes."""
    if not nome or not os.path.isfile(origem) or os.path.getsize(origem) > LIMITE_BLOB:
        return None
    destino = os.path.join(_dir_blobs(pasta), nome)
    if not os.path.exists(destino):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copyfile(origem, destino)
    return destino


def caminho_blob(estado, nome):
    pasta = C.pasta_de(estado)
    if not pasta or not nome:
        return None
    destino = os.path.join(_dir_blobs(pasta), nome)
    return destino if os.path.isfile(destino) else None


def identidade(m):
    """O que faz dois registros serem o mesmo mutante, mesmo em revisões e sessões diferentes:
    arquivo, a linha como era antes da mutação, e o que foi trocado. Sem `texto_linha` (registro de
    antes da herança por linha), a identidade é só aproximada e não é usada."""
    if not m.get('texto_linha'):
        return None
    return (m['repo'], m['arquivo'], m['texto_linha'].strip(), m['de'], m['para'])


def _preencher_reaplica(estado, sessao, args):
    """`--reaplica M<n>`: o mesmo mutante que sobreviveu numa revisão, sobre o código de agora (na
    pré-revisão do autor ou na revisão seguinte). `--reconfirma M<n>`: o mesmo mutante que
    morreu numa revisão anterior e perdeu a herança (o teste dele mudou ao corrigir a lacuna)."""
    if getattr(args, 'reconfirma', None):
        s_o, orig = _mutante(estado, args.reconfirma)
        if not orig or orig['onda'] != sessao['onda'] or orig['resultado'] != 'morto' or s_o.get('tipo') == 'autor' \
                or orig.get('revisao') == sessao.get('revisao'):
            raise SystemExit('%s não é morto de uma revisão anterior da onda %s' % (args.reconfirma, sessao['onda']))
        args.reconfirma = orig['id']
    else:
        orig = next((m for m in sobreviventes_pendentes(estado, sessao['onda'])
                     if m['id'].lower() == args.reaplica.lower()), None)
        if not orig:
            raise SystemExit('%s não é sobrevivente pendente da onda %s' % (args.reaplica, sessao['onda']))
        args.reaplica = orig['id']
    args.arquivo = args.arquivo or orig['arquivo']
    args.de = args.de or orig['de']
    args.para = args.para if args.para is not None else orig['para']
    args.aceite = args.aceite or orig['aceite']
    sel = orig.get('selecao') or ''
    if not (args.testes or args.comando):
        if sel.startswith('testes:'):
            args.testes = sel[len('testes:'):]
        elif sel.startswith('comando:'):
            args.comando = sel[len('comando:'):]
    args.descricao = args.descricao or '%s %s: %s' % ('reconfirma' if getattr(args, 'reconfirma', None)
                                                      else 'reaplica', orig['id'], orig.get('descricao') or '')
    if args.linha is None:
        # A dica é a linha da última reaplicação (o código andou desde a revisão); sem ela, a original.
        anteriores = [m for s_ in estado['sessoes_mutacao'] for m in s_.get('mutantes', [])
                      if (m.get('reaplica') or m.get('reconfirma')) == orig['id'] and m.get('linha')]
        dica = anteriores[-1]['linha'] if anteriores else orig['linha']
        linha, situacao = localizar(os.path.join(sessao['scratch'], args.arquivo), args.de, dica)
        if situacao == 'ambiguo':
            raise SystemExit('%s: `%s` aparece nas linhas %s de %s — escolha: `mutante aplicar --reaplica %s '
                             '--linha N`' % (orig['id'], args.de, ', '.join(map(str, linha)), args.arquivo, orig['id']))
        args.linha = linha
        return situacao
    return 'ok'


def aplicar(pasta, args):
    # Dois `aplicar` na mesma sessão mexeriam no mesmo scratch ao mesmo tempo: um por vez.
    sid = _sessao(C.carregar_estado(pasta), args.sessao, args.repo)['id']
    with C.trava(os.path.join(C.dir_scratch(), 'sessao-%s-%s' % (C.sha1_bytes(os.path.normcase(os.path.abspath(pasta)).encode('utf-8'))[:16], sid))):
        estado = C.carregar_estado(pasta)
        sessao = _por_id(estado, sid)
        if sessao.get('mecanica') and not (getattr(args, 'reaplica', None) or getattr(args, 'reconfirma', None)):
            raise SystemExit('recusado: esta sessão é da rodada mecânica (`revisao confirmar`) — só reaplica o que '
                             'a revisão anterior pediu; mutante novo é do revisor, numa revisão com subagente')
        if sessao.get('pre_revisao') and not getattr(args, 'reaplica', None):
            raise SystemExit('recusado: esta é a sessão de pré-revisão do autor — só `mutante reaplicar` '
                             'ou `aplicar --reaplica M<n>`; mutante novo é do revisor')
        if getattr(args, 'reaplica', None) or getattr(args, 'reconfirma', None):
            if _preencher_reaplica(estado, sessao, args) == 'codigo_removido':
                return _registrar_removido(pasta, sessao, args)
        # `--para ''` é mutação legítima (apagar a chamada); `--de` vazio não é.
        faltam = [n for n in ('arquivo', 'linha', 'de', 'aceite') if getattr(args, n) in (None, '')]
        if args.para is None:
            faltam.append('para')
        if faltam:
            raise SystemExit('informe %s (ou --reaplica M<n>)' % ', '.join('--' + n for n in faltam))
        return _aplicar(pasta, args, estado, sessao)


def _registrar_removido(pasta, sessao, args):
    """O trecho do sobrevivente não existe mais no código: não há o que reaplicar. Fica registrado,
    e a autoconferência mostra como aviso."""
    mid = C.atualizar(pasta, lambda e: C.proximo_id(e, 'M'))
    reg = {'id': mid, 'sessao': sessao['id'], 'repo': sessao['repo'], 'onda': sessao['onda'],
           'revisao': None, 'reaplica': args.reaplica, 'reconfirma': getattr(args, 'reconfirma', None), 'aceite': args.aceite, 'arquivo': args.arquivo,
           'linha': 0, 'de': args.de, 'para': args.para, 'selecao': '', 'resultado': 'codigo_removido',
           'exit': None, 'totais': None, 'classes_que_falharam': [], 'log': None, 'em': C.agora(),
           'equivalente': None, 'morto_por': None, 'no_diff_da_onda': None,
           'descricao': 'o trecho de %s não existe mais no código' % args.reaplica}
    C.atualizar(pasta, lambda e: _por_id(e, sessao['id']).setdefault('mutantes', []).append(reg))
    print('%s reaplica %s: o trecho `%s` não existe mais em %s — CODIGO_REMOVIDO'
          % (mid, args.reaplica, args.de, args.arquivo))
    return 0


def reaplicar(pasta, args):
    """Reaplica, na sessão de pré-revisão do autor, todo sobrevivente pendente das revisões da onda que
    ainda não foi reaplicado e morto sobre o código atual."""
    estado = C.carregar_estado(pasta)
    sessao = _sessao(estado, args.sessao, args.repo)
    if sessao.get('tipo') != 'autor':
        raise SystemExit('recusado: reaplicar é da pré-revisão do autor (sessão `mutante preparar --autor`)')
    fps = C.fingerprints(estado)
    feitos = {m.get('reaplica') for m in sessao.get('mutantes', [])}
    pendentes = [m for m in sobreviventes_pendentes(estado, sessao['onda'])
                 if m['id'] not in feitos and m['repo'] == sessao['repo']
                 and not reaplicado_e_morto(estado, sessao['onda'], m['id'], fps, True)]
    if not pendentes:
        print('nenhum sobrevivente pendente para reaplicar na onda %s' % sessao['onda'])
        return 0
    codigo = 0
    for m in pendentes:
        a = argparse.Namespace(sessao=sessao['id'], repo=None, arquivo=None, linha=None, de=None, para=None,
                               aceite=None, testes=None, comando=None, codigos_morto=None,
                               timeout=getattr(args, 'timeout', None), descricao=None, reaplica=m['id'])
        try:
            if aplicar(pasta, a):
                codigo = 1
        except SystemExit as ex:
            print('%s: %s' % (m['id'], ex))
            codigo = 1
    return codigo


def _conferir_rodada_confirmatoria(estado, sessao, args, rel, alvo):
    """Revisão a partir da 2ª: a rodada confirma, não reabre. Mutante novo só onde a correção mexeu, ou
    em aceite que ainda não tem morto válido. O critério é a **linha**: quase toda correção mexe no
    arquivo, e com o arquivo como unidade o alvo seguia móvel — cada revisor novo achava "uma mutação
    nova por rodada" em código já aprovado, e a onda não convergia."""
    if sessao.get('tipo') == 'autor' or getattr(args, 'reaplica', None) or getattr(args, 'reconfirma', None):
        return
    revs = [r for r in estado.get('revisoes', []) if r['onda'] == sessao['onda']]
    ids = [r['id'] for r in revs]
    if sessao.get('revisao') not in ids or ids.index(sessao['revisao']) == 0:
        return
    anterior = revs[ids.index(sessao['revisao']) - 1]
    retrato = (anterior.get('arquivos') or {}).get(sessao['repo'])
    if retrato is None:
        return  # revisão anterior sem retrato: nada a comparar
    blob = C.git(sessao['scratch'], 'hash-object', alvo)
    if retrato.get(rel) is None or retrato.get(rel) != blob:
        # o arquivo mudou desde a revisão anterior (ou entrou na onda agora)
        antigo = caminho_blob(estado, retrato.get(rel)) if retrato.get(rel) else None
        if antigo is None:
            return
        novas = C.linhas_novas(antigo, alvo)
        if novas is None or args.linha in novas:
            return  # a linha é nova ou foi alterada pela correção
        unidade = 'a linha %d de %s' % (args.linha, rel)
    else:
        unidade = rel
    fps = C.fingerprints(estado)
    # os mortos que valem (herdados e de sessões limpas) e os desta revisão, mesmo em sessão aberta
    desta = [m for s_ in estado['sessoes_mutacao'] if s_.get('revisao') == sessao.get('revisao')
             and s_.get('tipo') != 'autor' and s_['estado'] != 'invalida' for m in s_.get('mutantes', [])]
    com_morto = [m for m in mutantes_validos(estado, sessao['onda'], fps) + desta
                 if m['resultado'] == 'morto' and m['aceite'] == args.aceite]
    if com_morto:
        raise SystemExit('recusado: rodada de confirmação — %s não mudou desde a %s e o aceite %s já tem morto '
                         'válido (%s). Mutar código já aprovado reabre a revisão; aqui se confirma o que a rodada '
                         'anterior pediu (`mutante reconfirmar`) e se muta só o que a correção mudou'
                         % (unidade, anterior['id'], args.aceite, com_morto[0]['id']))


AMOSTRA_RELAXADA = 3


def origem_do_mutante(estado, m):
    """O id do mutante de origem: segue `reconfirma` e `reaplica` até o primeiro, que não reaplica
    ninguém. A reaplicação de uma reaplicação é a mesma mutação: o morto da RV2 que reconfirma o da
    RV1, reconfirmado de novo na RV3 a partir do da RV1, conta como o mesmo mutante."""
    vistos = set()
    while m is not None and (m.get('reconfirma') or m.get('reaplica')) and m['id'] not in vistos:
        vistos.add(m['id'])
        _, anterior = _mutante(estado, m.get('reconfirma') or m.get('reaplica'))
        if anterior is None:
            return m.get('reconfirma') or m.get('reaplica')
        m = anterior
    return m['id']


def amostra_relaxada(rid, relaxados, n=AMOSTRA_RELAXADA):
    """Até `n` mutantes de herança relaxada, escolhidos de forma determinística (sha1 de revisão +
    mutante): quem reconfere e quem valida chegam à mesma lista, e o autor não escolhe os fáceis."""
    chave = lambda m: hashlib.sha1(('%s:%s' % (rid, m['id'])).encode('utf-8')).hexdigest()
    return sorted(relaxados, key=chave)[:n]


def reconfirmar(pasta, args):
    """Revisor: reaplica mecanicamente, nesta revisão, (a) os sobreviventes das revisões anteriores e
    (b) os mortos delas que perderam a herança (o arquivo ou o teste que os matava mudou na correção).
    (c) uma **amostra de alarme** dos mortos de herança relaxada — até 3, escolha
    determinística; um sobrevivente na amostra invalida a herança relaxada da onda e todos os relaxados
    são reaplicados. Sem julgamento e sem mutante novo — é a parte da rodada de confirmação que não
    depende de escolha."""
    estado = C.carregar_estado(pasta)
    sessao = _sessao(estado, args.sessao, args.repo)
    if sessao.get('tipo') == 'autor':
        raise SystemExit('recusado: reconfirmar é do revisor; na autoconferência é `mutante reaplicar`')
    onda = sessao['onda']
    fps = C.fingerprints(estado)
    relaxada = relaxada_vale(estado, onda)
    feitos = {m.get('reaplica') or m.get('reconfirma') for s_ in estado['sessoes_mutacao']
              if s_.get('revisao') == sessao.get('revisao') and s_.get('tipo') != 'autor' for m in s_.get('mutantes', [])}
    alvos, relaxados = [], []
    # Aceites que já têm morto do revisor (herdado, ou desta revisão em sessão limpa ou aberta): o que o
    # autor reaplicou e matou não precisa ser refeito. Aceite sem morto do revisor ainda precisa de um —
    # o do autor não conta para o fechamento.
    desta = [m for s_ in estado['sessoes_mutacao'] if s_.get('revisao') == sessao.get('revisao')
             and s_.get('tipo') != 'autor' and s_['estado'] != 'invalida' for m in s_.get('mutantes', [])]
    aceites_com_morto = {m['aceite'] for m in mutantes_validos(estado, onda, fps) + desta if m['resultado'] == 'morto'}
    for m in sobreviventes_pendentes(estado, onda):
        if m.get('revisao') != sessao.get('revisao') and m['repo'] == sessao['repo'] and m['id'] not in feitos:
            if m['aceite'] in aceites_com_morto and reaplicado_e_morto(estado, onda, m['id'], fps):
                continue  # o autor já o reaplicou e matou sobre o código de agora, e o aceite tem morto do revisor
            alvos.append(('reaplica', m))
    for s_ in estado['sessoes_mutacao']:
        if s_['onda'] != onda or s_.get('tipo') == 'autor' or s_.get('revisao') == sessao.get('revisao'):
            continue
        if s_['repo'] != sessao['repo'] or s_['estado'] != 'limpa' or not s_.get('integridade_ok'):
            continue
        for m in s_.get('mutantes', []):
            if m['resultado'] == 'morto' and m['id'] not in feitos \
                    and not (m.get('reaplica') or m.get('reconfirma')):
                tipo = tipo_heranca(estado, m, None, relaxada)
                if tipo is None:
                    alvos.append(('reconfirma', m))
                elif tipo == 'relaxada':
                    relaxados.append(m)
    amostra = amostra_relaxada(sessao.get('revisao') or sessao['id'], relaxados)
    if not alvos and not amostra:
        print('nada a reconfirmar na onda %s (%s): sobreviventes já reaplicados e mortos anteriores herdados'
              % (onda, sessao['repo']))
        return 0
    codigo = 0

    def _aplicar_alvos(lista):
        nonlocal codigo
        for tipo, m in lista:
            a = argparse.Namespace(sessao=sessao['id'], repo=None, arquivo=None, linha=None, de=None, para=None,
                                   aceite=None, testes=None, comando=None, codigos_morto=None,
                                   timeout=getattr(args, 'timeout', None), descricao=None,
                                   reaplica=m['id'] if tipo == 'reaplica' else None,
                                   reconfirma=m['id'] if tipo == 'reconfirma' else None)
            try:
                if aplicar(pasta, a):
                    codigo = 1
            except SystemExit as ex:
                print('%s: %s' % (m['id'], ex))
                codigo = 1

    _aplicar_alvos(alvos + [('reconfirma', m) for m in amostra])
    if amostra:
        # O que a amostra mostrou: sobrevivente invalida a herança relaxada da onda inteira.
        depois = C.carregar_estado(pasta)
        ids = {m['id'] for m in amostra}
        vivos = [m for s_ in depois['sessoes_mutacao'] if s_.get('revisao') == sessao.get('revisao')
                 for m in s_.get('mutantes', []) if m.get('reconfirma') in ids and m['resultado'] == 'sobrevivente']

        def _gravar(e):
            rv = next(r for r in e['revisoes'] if r['id'] == sessao.get('revisao'))
            rv['amostra_relaxada'] = {'mutantes': sorted(ids), 'relaxados': len(relaxados), 'em': C.agora()}
            if vivos:
                e['ondas'][onda]['heranca_relaxada_invalida'] = {
                    'revisao': rv['id'], 'mutante': vivos[0]['reconfirma'], 'em': C.agora()}
        C.atualizar(pasta, _gravar)
        if vivos:
            print('ALARME: %s sobreviveu na amostra da herança relaxada — a herança relaxada da onda %s está '
                  'invalidada (volta a estrita); reaplicando todos os relaxados' % (vivos[0]['reconfirma'], onda))
            resto = [('reconfirma', m) for m in relaxados if m['id'] not in ids]
            _aplicar_alvos(resto)
            codigo = 1
        else:
            print('amostra da herança relaxada: %d de %d mutante(s) reaplicado(s), todos mortos'
                  % (len(amostra), len(relaxados)))
    return codigo


def _aplicar(pasta, args, estado, sessao):
    cfg = C.repo_cfg(estado, sessao['repo'])
    rel = args.arquivo.replace('\\', '/').lstrip('/')
    if _eh_teste(rel):
        raise SystemExit('recusado: %s é arquivo de teste. Mutante vai no código de produção.' % rel)
    if not args.aceite or not C.RE_ACEITE.fullmatch(args.aceite):
        raise SystemExit('informe --aceite A<onda>.<k>: é o que liga o mutante ao aceite que ele prova')
    if args.de == args.para:
        raise SystemExit('--de e --para iguais: não é mutação')
    alvo = os.path.join(sessao['scratch'], rel)
    if not os.path.isfile(alvo):
        raise SystemExit('arquivo não existe no scratch: %s' % rel)
    _conferir_rodada_confirmatoria(estado, sessao, args, rel, alvo)
    chave_sel = _chave_selecao(args)
    codigos_morto = {int(c) for c in (args.codigos_morto or '1').split(',')}
    timeout = args.timeout or cfg.get('timeout', 1800)
    oraculo_decisao = None
    if chave_sel.startswith('comando:') and not getattr(args, 'reaplica', None) \
            and not getattr(args, 'reconfirma', None):
        # Um comando qualquer como oráculo (`grep -q`, `cmp`) "mata" mutante sem teste nenhum: é decisão do
        # usuário, e o texto do comando fica no registro do mutante.
        erro_d = DC.exigir(estado, getattr(args, 'decisao', None), para='oraculo') if getattr(args, 'decisao', None) \
            else '--comando exige --decisao D<n> do usuário (oráculo alternativo ao teste)'
        if erro_d:
            raise SystemExit('recusado: ' + erro_d)
        oraculo_decisao = args.decisao

    # 1. A seleção precisa passar sem mutação, uma vez por sessão.
    sel = sessao['selecoes'].get(chave_sel)
    if sel is None:
        comando, codigo, totais, log, _ = _rodar_selecao(pasta, cfg, sessao, chave_sel, 'limpo', timeout)
        limpo = _classificar(chave_sel, codigo, totais, codigos_morto)
        sel = {'comando': comando, 'exit': codigo, 'totais': totais, 'log': log,
               'ok': limpo == 'sobrevivente', 'em': C.agora(), 'diff_limpo': _diff_rastreado(sessao['scratch'])}
        sessao['selecoes'][chave_sel] = sel
        C.atualizar(pasta, lambda e: _por_id(e, sessao['id'])['selecoes'].__setitem__(chave_sel, sel))
        if not sel['ok']:
            raise SystemExit('a seleção não passa SEM mutação no scratch (exit %d, %s) — nenhum '
                             'mutante dela pode contar. Log: %s' % (codigo, limpo, log))
    elif not sel['ok']:
        raise SystemExit('seleção já recusada nesta sessão (falha sem mutação). Log: %s' % sel['log'])
    elif sel.get('diff_limpo') and sel['diff_limpo'] != _diff_rastreado(sessao['scratch']):
        # a rodada limpa vale para o scratch como estava; se alguém mexeu num arquivo rastreado (um teste
        # quebrado de propósito), todo mutante seguinte "morreria" por isso
        raise SystemExit('recusado: o scratch mudou desde a rodada limpa (arquivo rastreado alterado fora '
                         'do mutante em curso) — `mutante limpar` e `mutante preparar` de novo')

    # 2. Aplica a mutação, exatamente uma ocorrência na linha indicada.
    with open(alvo, 'rb') as fh:
        original = fh.read()
    sha_original = C.sha1_bytes(original)
    try:
        texto, codificacao = original.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        texto, codificacao = original.decode('latin-1'), 'latin-1'
    linhas = texto.splitlines(True)
    if not 1 <= args.linha <= len(linhas):
        raise SystemExit('linha %d fora do arquivo (%d linhas)' % (args.linha, len(linhas)))
    alvo_linha = linhas[args.linha - 1]
    ocorrencias = alvo_linha.count(args.de)
    if ocorrencias != 1:
        raise SystemExit('--de ocorre %d vez(es) na linha %d (precisa ser exatamente 1): %r'
                         % (ocorrencias, args.linha, alvo_linha.rstrip()))
    linhas[args.linha - 1] = alvo_linha.replace(args.de, args.para)
    mid = C.atualizar(pasta, lambda e: C.proximo_id(e, 'M'))
    with open(alvo, 'wb') as fh:
        fh.write(''.join(linhas).encode(codificacao))
    try:
        comando, codigo, totais, log, falharam = _rodar_selecao(pasta, cfg, sessao, chave_sel, mid, timeout)
    finally:
        with open(alvo, 'wb') as fh:
            fh.write(original)
    restaurado = C.sha1_arquivo(alvo) == sha_original
    resultado = _classificar(chave_sel, codigo, totais, codigos_morto)
    if not restaurado:
        sessao['estado'] = 'invalida'
        resultado = 'invalido'
    alteradas = _no_diff_da_onda(estado, sessao, cfg, rel)
    reg = {'id': mid, 'sessao': sessao['id'], 'repo': sessao['repo'], 'onda': sessao['onda'],
           'revisao': sessao.get('revisao'), 'reaplica': getattr(args, 'reaplica', None),
           'reconfirma': getattr(args, 'reconfirma', None),
           'no_diff_da_onda': None if alteradas is None else args.linha in alteradas,
           'morto_por': _causa(chave_sel, codigo, totais) if resultado == 'morto' else None,
           'aceite': args.aceite, 'arquivo': rel, 'linha': args.linha, 'de': args.de,
           'para': args.para, 'selecao': chave_sel, 'resultado': resultado, 'exit': codigo,
           'totais': totais, 'classes_que_falharam': falharam, 'log': log, 'em': C.agora(), 'equivalente': None,
           'descricao': args.descricao or '', 'oraculo_decisao': oraculo_decisao,
           # A linha como era antes da mutação: com o arquivo, o `de` e o `para`, é a identidade do mutante
           # e o que a herança relaxada confere.
           'texto_linha': alvo_linha.rstrip('\r\n'),
           # O que a herança confere: o arquivo mutado e os testes que o mataram, como estavam.
           'sha_arquivo': sha_original,
           'sha_testes': {f: C.sha1_arquivo(os.path.join(sessao['scratch'], f))
                          for c in (falharam or []) for f in arquivos_de_classe(sessao['scratch'], c)}}
    if resultado == 'morto':
        # Cópia dos testes que o mataram (só os mortos): a herança relaxada compara o teste de agora com ele.
        for f, sha in reg['sha_testes'].items():
            guardar_blob(pasta, os.path.join(sessao['scratch'], f), sha)

    def _gravar(e):
        s = _por_id(e, sessao['id'])
        if not restaurado:
            s['estado'] = 'invalida'
        s.setdefault('mutantes', []).append(reg)
    C.atualizar(pasta, _gravar)
    print('%s %s:%d  %r → %r  [%s]  → %s%s' % (mid, rel, args.linha, args.de, args.para,
                                              args.aceite, resultado.upper(),
                                              ' (por %s)' % reg['morto_por'] if reg['morto_por'] else ''))
    if reg['no_diff_da_onda'] is False:
        print('  aviso: a linha %d não foi alterada nesta onda — o mutante não conta para o mínimo, salvo '
              'numa onda Só testes ou para aceite cujas tarefas só mexem em teste, se morreu por asserção '
              'numa classe de teste alterada nela' % args.linha)
    if totais:
        print('  testes: %(run)d rodados, %(falhas)d falhas, %(erros)d erros' % totais)
    print('  log: %s' % log)
    if not restaurado:
        print('  ERRO: o arquivo não voltou ao original no scratch — sessão invalidada')
        return 1
    return 0


def equivalente(pasta, args):
    estado = C.carregar_estado(pasta)
    for s in estado['sessoes_mutacao']:
        for m in s.get('mutantes', []):
            if m['id'] == args.id:
                if m['resultado'] != 'sobrevivente':
                    raise SystemExit('%s não é sobrevivente (%s)' % (m['id'], m['resultado']))
                if len((args.motivo or '').strip()) < 20:
                    raise SystemExit('motivo curto demais: diga por que nenhum teste poderia distinguir')
                erro_d = DC.exigir(estado, args.decisao, para='equivalente', alvo=m['id'], engenharia=True)
                if erro_d:
                    raise SystemExit('recusado: equivalente é decisão do usuário, ou de engenharia com a autorização '
                                     'dele (o revisor só propõe, nas lacunas) — %s' % erro_d)
                m['equivalente'] = args.motivo.strip()
                m['equivalente_decisao'] = args.decisao
                if m.get('reaplica'):
                    # A cópia reaplicada é o mesmo defeito: o original deixa de ser pendente.
                    for s2 in estado['sessoes_mutacao']:
                        for o2 in s2.get('mutantes', []):
                            if o2['id'] == m['reaplica'] and not o2.get('equivalente'):
                                o2['equivalente'] = args.motivo.strip()
                                o2['equivalente_decisao'] = args.decisao
                C.salvar_estado(pasta, estado)
                print('%s marcado como equivalente' % m['id'])
                return 0
    raise SystemExit('mutante %s não encontrado' % args.id)


# ------------------------------------------------------------------------------ limpar

def limpar(pasta, args):
    estado = C.carregar_estado(pasta)
    sessao = _sessao(estado, args.sessao, args.repo)
    cfg = C.repo_cfg(estado, sessao['repo'])
    real = cfg['caminho']
    _remover_worktree(real, sessao['scratch'])
    porcelain = C.porcelain_sha1(real)
    fp = C.fingerprint(real)
    ok = porcelain == sessao['base_real']['porcelain'] and C.mesmo_fp(fp, sessao['base_real']['fingerprint'])
    sessao['integridade_ok'] = ok
    sessao['estado'] = 'limpa' if sessao['estado'] == 'preparada' else sessao['estado']
    sessao['limpa_em'] = C.agora()
    C.salvar_estado(pasta, estado)
    contagem = {}
    for m in sessao.get('mutantes', []):
        contagem[m['resultado']] = contagem.get(m['resultado'], 0) + 1
    print('sessão %s limpa. Mutantes: %s' % (sessao['id'], ', '.join(
        '%d %s' % (v, k) for k, v in sorted(contagem.items())) or 'nenhum'))
    if not ok:
        print('ERRO: o repositório real mudou durante a sessão (porcelain ou fingerprint '
              'diferentes do início). Os mutantes desta sessão não contam.')
        return 1
    print('repositório real intacto (porcelain e fingerprint iguais ao início)')
    return 0


# ------------------------------------------------------------------------------ consultas

def revisao_vigente(estado, onda):
    revs = [r['id'] for r in estado.get('revisoes', []) if r['onda'] == onda]
    return revs[-1] if revs else None


def arquivos_de_classe(repo_dir, classe):
    """Arquivos da classe de teste (como o relatório a nomeia) no repositório: Java pelo caminho do
    pacote em `src/test/java/` (ou pelo nome simples), spec JS/TS pelo nome de classe do testar.mjs."""
    import onda as OND
    simples = classe.rsplit('.', 1)[-1]
    todos = [f for f in C.git(repo_dir, 'ls-files', '-co', '--exclude-standard', checar=False).splitlines() if f]
    if '.' in classe:
        alvo = '/' + classe.replace('.', '/') + '.java'
        achados = [f for f in todos if ('/' + f).endswith(alvo)]
        if achados:
            return achados
    java = [f for f in todos if os.path.basename(f) == simples + '.java']
    if java:
        return java
    return [f for f in todos if OND.classe_de_spec(f) == simples]


def _sha_no_codigo(repo_dir, rel, ate):
    if ate:
        conteudo = C.git(repo_dir, 'show', '%s:%s' % (ate, rel), checar=False, bruto=True)
        return C.sha1_bytes(conteudo) if conteudo else None
    caminho = os.path.join(repo_dir, rel)
    return C.sha1_arquivo(caminho) if os.path.isfile(caminho) else None


def _texto_no_codigo(repo_dir, rel, ate):
    """Texto do arquivo no commit `ate` ou no working tree; None se não existe."""
    if ate:
        bruto = C.git(repo_dir, 'show', '%s:%s' % (ate, rel), checar=False, bruto=True)
        return bruto.decode('utf-8', 'replace') if bruto else None
    caminho = os.path.join(repo_dir, rel)
    return _ler_solto(caminho) if os.path.isfile(caminho) else None


def _linha_tem(repo_dir, rel, linha, de, ate):
    linhas = (_texto_no_codigo(repo_dir, rel, ate) or '').splitlines()
    return 1 <= linha <= len(linhas) and linhas[linha - 1].count(de) == 1


def _ler_solto(caminho):
    with open(caminho, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _subsequencia(antigas, novas):
    """As linhas antigas aparecem, na mesma ordem, entre as novas (o teste só ganhou linhas)."""
    it = iter(novas)
    return all(any(a == n for n in it) for a in antigas)


def _herdavel_estrito(estado, m, ate=None):
    if m.get('resultado') != 'morto' or not m.get('sha_arquivo') or not m.get('sha_testes'):
        return False
    cfg = estado['repos'].get(m['repo'])
    if not cfg:
        return False
    real = cfg['caminho']
    a = (ate or {}).get(m['repo'])
    if _sha_no_codigo(real, m['arquivo'], a) != m['sha_arquivo']:
        return False
    if any(_sha_no_codigo(real, f, a) != sha for f, sha in m['sha_testes'].items()):
        return False
    return _linha_tem(real, m['arquivo'], m['linha'], m['de'], a)


def _herdavel_relaxado(estado, m, ate=None):
    """Herança relaxada: o arquivo de produção pode ter mudado em outras linhas, desde que a linha mutada (na
    posição ou a única do arquivo que tem o `de`) seja exatamente a de antes, e que cada teste que
    matou o mutante só tenha ganhado linhas (as antigas seguem lá, na mesma ordem). A copia do teste
    como era vem de `blobs/`; mutante sem `texto_linha` ou sem cópia só herda pela regra estrita."""
    if m.get('resultado') != 'morto' or not m.get('texto_linha') or not m.get('sha_testes'):
        return False
    cfg = estado['repos'].get(m['repo'])
    if not cfg:
        return False
    real = cfg['caminho']
    a = (ate or {}).get(m['repo'])
    texto = _texto_no_codigo(real, m['arquivo'], a)
    if texto is None:
        return False
    linhas = texto.splitlines()
    pos, situacao = _localizar_linhas(linhas, m['de'], m['linha'])
    if situacao != 'ok' or linhas[pos - 1].rstrip() != m['texto_linha'].rstrip():
        return False
    for f, sha in m['sha_testes'].items():
        if _sha_no_codigo(real, f, a) == sha:
            continue
        copia, atual = caminho_blob(estado, sha), _texto_no_codigo(real, f, a)
        if copia is None or atual is None:
            return False
        if not _subsequencia([ln.rstrip() for ln in _ler_solto(copia).splitlines()],
                             [ln.rstrip() for ln in atual.splitlines()]):
            return False
    return True


def tipo_heranca(estado, m, ate=None, relaxada=False):
    """'estrita', 'relaxada' ou None. Estrita: o arquivo mutado e os testes que o mataram estão iguais
    (sha1) e a linha ainda tem o trecho. Relaxada (só se `relaxada`): ver `_herdavel_relaxado`."""
    if _herdavel_estrito(estado, m, ate):
        return 'estrita'
    if relaxada and _herdavel_relaxado(estado, m, ate):
        return 'relaxada'
    return None


def herdavel(estado, m, ate=None, relaxada=False):
    """Mutante morto de uma revisão anterior que ainda vale. Mutante sem os sha (gravado antes da
    herança) não herda."""
    return tipo_heranca(estado, m, ate, relaxada) is not None


def relaxada_vale(estado, onda):
    """A herança relaxada vale na onda enquanto nenhum sobrevivente da amostra a invalidou."""
    eo = estado['ondas'].get(onda) or {}
    return not eo.get('heranca_relaxada_invalida')


def mutantes_validos(estado, onda, fps_atuais, ate=None, relaxada=None):
    """Mutantes de sessões limpas, íntegras, da revisão mais recente da onda e cujo código de
    partida ainda é o atual — mais os **herdados**: mortos de revisões anteriores da onda cujo
    arquivo e testes não mudaram (a rodada de confirmação não precisa refazê-los) e os de herança
    relaxada (marcados `heranca: relaxada`). Sobrevivente não se herda: volta pela
    reaplicação. `ate`: {repo: commit}, para conferir a herança sobre o código do fechamento
    (parecer). `relaxada`: None = o que a onda manda (`relaxada_vale`)."""
    saida = []
    rv = revisao_vigente(estado, onda)
    if relaxada is None:
        relaxada = relaxada_vale(estado, onda)
    for s in estado['sessoes_mutacao']:
        if s['onda'] != onda or s['estado'] != 'limpa' or not s.get('integridade_ok'):
            continue
        if s.get('tipo') == 'autor':
            continue
        if s.get('revisao') == rv:
            if C.mesmo_fp(s['base_real']['fingerprint'], fps_atuais.get(s['repo'])):
                saida.extend(s.get('mutantes', []))
            continue
        for m in s.get('mutantes', []):
            tipo = tipo_heranca(estado, m, ate, relaxada)
            if tipo:
                saida.append(dict(m, herdado_de=s.get('revisao'), heranca=tipo))
    return saida


def mutantes_vencidos(estado, onda, fps_atuais):
    n = 0
    for s in estado['sessoes_mutacao']:
        if s['onda'] == onda and s['estado'] == 'limpa' and s.get('integridade_ok') and \
                not C.mesmo_fp(s['base_real']['fingerprint'], fps_atuais.get(s['repo'])):
            n += len(s.get('mutantes', []))
    return n


def tabela_mutantes(mutantes):
    if not mutantes:
        return '_nenhum mutante registrado_'
    linhas = ['| # | Aceite | Onde | Mutação | Resultado |', '|---|---|---|---|---|']
    for m in mutantes:
        res = m['resultado']
        if m.get('morto_por'):
            res += ' (%s)' % m['morto_por']
        if m.get('no_diff_da_onda') is False:
            res += ' — fora do código da onda'
        if m.get('equivalente'):
            res += ' (equivalente, %s: %s)' % (m.get('equivalente_decisao'), m['equivalente'])
        if m.get('reaplica'):
            res += ' — reaplica %s' % m['reaplica']
        if m.get('herdado_de'):
            res += ' — herdado de %s%s' % (m['herdado_de'], ' (herança relaxada)' if m.get('heranca') == 'relaxada' else '')
        linhas.append('| %s | %s | `%s:%s:%d` | `%s` → `%s` | %s |' % (
            m['id'], m['aceite'], m['repo'], m['arquivo'], m['linha'],
            m['de'].replace('|', '\\|'), m['para'].replace('|', '\\|'), res))
    return '\n'.join(linhas)
