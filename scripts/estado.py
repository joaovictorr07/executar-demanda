#!/usr/bin/env python3
"""Retomada e painel.

`reconciliar` é o primeiro comando de qualquer sessão que retoma uma demanda: o que o git diz
agora contra o que o `.execucao.json` e o ESTADO-ATUAL dizem. **Evidência vence narrativa** — o
texto escrito numa sessão envelhece (um "sem push" que já foi feito) e o git não.

`painel` reescreve só o bloco gerado da seção 1 do ESTADO-ATUAL; o resto do arquivo é seu.
"""

import datetime as dt
import json
import os
import re
import subprocess
import urllib.parse

import comum as C
import grafo as GR
import mutantes as M
import plano as P
import revisao as RV
import testes as T


def _repo_fatos(estado, repo, cfg):
    real = cfg['caminho']
    if not os.path.isdir(real):
        return {'repo': repo, 'erro': 'caminho não existe: %s' % real}
    up = C.git(real, 'rev-parse', '--abbrev-ref', '@{u}', checar=False)
    atras = frente = None
    if up:
        try:
            atras, frente = [int(x) for x in C.git(real, 'rev-list', '--left-right', '--count',
                                                    '@{u}...HEAD').split()]
        except (ValueError, C.ErroGit):
            pass
    fp = C.fingerprint(real)
    ultima = [e for e in estado['execucoes'] if e['repo'] == repo and e['tipo'] == 'teste' and not e.get('anulada')]
    return {
        'repo': repo, 'caminho': real, 'branch': C.branch_atual(real), 'branch_projeto': cfg.get('branch'),
        'head': C.git(real, 'rev-parse', '--short=9', 'HEAD'), 'upstream': up or None,
        'atras': atras, 'frente': frente,
        'nao_commitados': len([l for l in C.git(real, 'status', '--porcelain').splitlines() if l]),
        'fingerprint': fp['assinatura'],
        'ultimo_teste': ultima[-1]['id'] if ultima else None,
        'ultimo_teste_fresco': bool(ultima) and C.mesmo_fp(ultima[-1].get('fingerprint'), fp),
        'ultimo_teste_ok': bool(ultima) and ultima[-1].get('ok'),
    }


def fingerprint(pasta, args):
    """Imprime a linha `Código: <assinatura>` que o roteiro leva no cabeçalho, escrita **antes** de
    executá-lo: é o que amarra o roteiro ao código sobre o qual ele rodou."""
    cfg = C.repo_cfg(C.carregar_estado(pasta), args.repo)
    fp = C.fingerprint(cfg['caminho'])
    print('Código: %s' % fp['assinatura'])
    print('  (%s, HEAD %s; copie a linha para o cabeçalho do roteiro antes de executá-lo)'
          % (args.repo, fp['head'][:9]))
    return 0


def reconciliar(pasta, args):
    estado = C.carregar_estado(pasta)
    rel = C.Relatorio('estado reconciliar %s' % C.rotulo(pasta))
    fatos = [_repo_fatos(estado, r, cfg) for r, cfg in sorted(estado['repos'].items())]
    ativa = C.onda_ativa(estado)
    for f in fatos:
        if 'erro' in f:
            rel.erro('%s: %s' % (f['repo'], f['erro']))
            continue
        push = ('sem upstream' if not f['upstream'] else '`origin` == HEAD' if not f['atras'] and not f['frente']
                else '%s à frente, %s atrás de %s' % (f['frente'], f['atras'], f['upstream']))
        rel.nota('%-10s %s @ %s · %s · %d não commitado(s) · último teste %s%s'
                 % (f['repo'], f['branch'], f['head'], push, f['nao_commitados'], f['ultimo_teste'] or '—',
                    '' if not f['ultimo_teste'] else ' (%s, %s)' % ('ok' if f['ultimo_teste_ok'] else 'FALHOU',
                                                               'fresco' if f['ultimo_teste_fresco'] else 'vencido')))
        if f['branch_projeto'] and f['branch'] != f['branch_projeto']:
            rel.erro('%s está em %r; a branch do projeto é %r' % (f['repo'], f['branch'], f['branch_projeto']))
    mudou_analise = C.analise_mudou(pasta, estado, estado['ondas'].get(ativa) if ativa else None)
    if mudou_analise:
        rel.aviso(mudou_analise)
    for oid, eo_ in sorted(estado['ondas'].items()):
        pendente = RV.nao_preenchida(pasta, oid) if eo_.get('estado') in ('em_execucao', 'bloqueada') else None
        if pendente:
            rel.aviso('revisão %s da onda %s ainda está com o modelo (`**<APROVADA | REPROVADA>**`) — o revisor não '
                      'terminou, ou o esqueleto ficou' % (pendente, oid))
    for s in estado['sessoes_mutacao']:
        if s['estado'] == 'preparada':
            rel.aviso('sessão de mutação %s (%s) ficou aberta — `mutante limpar --sessao %s`'
                      % (s['id'], s['repo'], s['id']))
    if ativa:
        eo = estado['ondas'][ativa]
        ligados = {c['hash'] for r in eo.get('tarefas', {}).values() for c in r.get('commits', [])}
        for repo, b in eo.get('baseline', {}).items():
            real = estado['repos'][repo]['caminho']
            for h in C.git(real, 'rev-list', '%s..HEAD' % b['head']).splitlines():
                if h not in ligados:
                    rel.aviso('%s: commit %s na onda %s sem tarefa — `vincular`' % (repo, h[:9], ativa))
        p = P.Plano(C.arquivo_plano(pasta))
        o = p.onda(ativa)
        if o:
            feitas = [t for t in o['ordem_tarefas'] if eo.get('tarefas', {}).get(t, {}).get('commits')
                      or eo.get('tarefas', {}).get(t, {}).get('sem_commit')]
            pendentes = [t for t in o['ordem_tarefas'] if t not in feitas]
            rel.nota('onda em execução: %s — %d/%d tarefas com commit; próximas: %s'
                     % (ativa, len(feitas), len(o['ordem_tarefas']), ', '.join(pendentes[:5]) or 'nenhuma'))
    else:
        rel.nota('nenhuma onda em execução')
    md = C.arquivo_estado_md(pasta)
    if os.path.exists(md):
        texto = C.ler(md)
        for f in fatos:
            if 'erro' in f:
                continue
            if f['frente'] == 0 and f['atras'] == 0 and re.search(r'sem push', texto, re.IGNORECASE) \
                    and f['repo'] in texto:
                rel.aviso('ESTADO-ATUAL menciona "sem push", e %s está com `origin` == HEAD — texto velho?' % f['repo'])
    if args.json:
        print(json.dumps({'repos': fatos, 'onda_ativa': ativa}, ensure_ascii=False, indent=2))
    if getattr(args, 'html', False) or os.path.exists(C.arquivo_painel_html(pasta)):
        # Só leitura do projeto: reescreve apenas o HTML (o ESTADO-ATUAL .md fica como está).
        rel.nota('painel HTML atualizado: %s' % painel_html(pasta, estado))
    return rel.imprimir()


def _situacao_onda(estado, o, fps, pasta=None):
    eo = estado['ondas'].get(o['id'])
    if not eo:
        return '⏳ Não iniciada'
    if eo['estado'] == 'fechada':
        return '✅ Fechada em %s' % eo['fechada_em'][:10]
    if eo['estado'] in ('replanejada', 'abandonada'):
        return '⛔ %s (%s)' % (eo['estado'].capitalize(), eo[eo['estado']]['decisao'])
    if eo['estado'] == 'bloqueada':
        return '🔴 Bloqueada: %s foi a 3ª revisão e reprovou — caminho do usuário (`onda desbloquear`)' % eo.get('bloqueada_por')
    feitas = sum(1 for t in o['ordem_tarefas'] if eo.get('tarefas', {}).get(t, {}).get('commits')
                 or eo.get('tarefas', {}).get(t, {}).get('sem_commit'))
    partes = ['%d/%d tarefas com commit' % (feitas, len(o['ordem_tarefas']))]
    for repo in sorted(eo.get('baseline', {})):
        frescas = [e for e in T.execucoes_frescas(estado, repo, fps.get(repo)) if e['tipo'] == 'teste']
        partes.append('testes %s: %s' % (repo, 'frescos ✅' if frescas else 'não rodados sobre o código atual'))
    validos = M.mutantes_validos(estado, o['id'], fps)
    partes.append('mutantes: %d mortos de %d' % (len([m for m in validos if m['resultado'] == 'morto']), len(validos)))
    revs = [r for r in estado['revisoes'] if r['onda'] == o['id']]
    vazia = RV.nao_preenchida(pasta, o['id']) if (pasta and revs) else None
    partes.append('revisão: %s' % (('revisão %s não preenchida' % vazia) if vazia
                                   else revs[-1]['id'] if revs else 'não iniciada'))
    return '🟡 Em execução — ' + '; '.join(partes)


ESQUELETO = """# {rotulo} — Estado atual e pendências

Atualizado em **{data}**. Este é o painel do projeto: onde o trabalho está e o que falta. O
histórico de cada onda fica nos `ONDA-*-consolidacao.md`.

---

## 1. Onde estamos

{painel}

## 2. Pendências, na ordem
"""


def _contagem(valores):
    c = {}
    for v in valores:
        c[v] = c.get(v, 0) + 1
    return ', '.join('%s %d' % (k, n) for k, n in sorted(c.items())) or '—'


def _veredito(estado, r):
    """Veredito da revisão: o do registro, ou — nas revisões antigas, que não o guardavam — o do
    arquivo (o da onda ou o arquivado `revisao-onda-N.RV<k>.md`) que traz esse RV no cabeçalho."""
    if r.get('veredito'):
        return r['veredito']
    pasta = C.pasta_de(estado)
    if not pasta:
        return None
    base = C.arquivo_revisao(pasta, r['onda'])
    for arq in (base.replace('.md', '.%s.md' % r['id']), base):
        if not os.path.exists(arq):
            continue
        texto = C.ler(arq)
        if not re.search(r'\|\s*Revis[aã]o\s*\|\s*%s\b' % re.escape(r['id']), texto[:1500]):
            continue
        m = re.search(r'## Veredito\s*\n+\s*\*\*([^*]+)\*\*', texto)
        v = m.group(1).strip().upper() if m else None
        return v if v in RV.VEREDITOS else None
    return None


def medicao_dados(estado, p):
    """P8, em dados: uma linha por onda iniciada. Só agregados — nenhum texto de decisão, pendência ou fala.
    Desperdiçado: o mutante não conta para o mínimo (linha que a onda não alterou) ou repete a posição de outro
    mutante anterior da onda."""
    saida = []
    for o in p.ondas:
        oid = o['id']
        eo = estado['ondas'].get(oid)
        if not eo:
            continue
        revs = [r for r in estado['revisoes'] if r['onda'] == oid]
        regras = C.rotulo_regras(eo)
        novos = reconf = desperdicio = 0
        posicoes = set()
        for s_ in estado['sessoes_mutacao']:
            if s_['onda'] != oid or s_.get('tipo') == 'autor':
                continue
            for m in s_.get('mutantes', []):
                if m['resultado'] == 'codigo_removido':
                    continue
                if m.get('reaplica') or m.get('reconfirma'):
                    reconf += 1
                    continue
                novos += 1
                pos = (m['repo'], m['arquivo'], m['linha'])
                if m.get('no_diff_da_onda') is False or pos in posicoes:
                    desperdicio += 1
                posicoes.add(pos)
        classes = {}
        for r in revs:
            for c in (r.get('classes_lacunas') or []):
                classes[c] = classes.get(c, 0) + 1
        falhas = {}
        for e in estado['execucoes']:
            if e.get('onda') == oid and not e.get('ok') and not e.get('anulada'):
                k = e.get('intencao') or 'verde'
                falhas[k] = falhas.get(k, 0) + 1
        saida.append({
            'id': oid, 'titulo': o['titulo'], 'estado': eo.get('estado'), 'regras': regras,
            'tarefas': len(o['ordem_tarefas']),
            'rodadas': [{'id': r['id'], 'veredito': _veredito(estado, r)} for r in revs],
            'classes': classes if regras not in ('r1', 'r2') else None,
            'decisoes': len([d for d in estado.get('decisoes', []) if d.get('onda') == oid
                             and d.get('fonte') == 'usuario' and not d.get('revogada_por')]),
            # a resposta foi a opção que o modelo marcou como recomendada; e o esperado que só está na pergunta dele
            'decisoes_recomendadas': len([d for d in estado.get('decisoes', []) if d.get('onda') == oid
                                          and (d.get('fala') or {}).get('recomendada')]),
            'decisoes_engenharia': len([d for d in estado.get('decisoes', []) if d.get('onda') == oid
                                        and d.get('fonte') == 'engenharia']),
            'esperados_propostos': len((revs[-1].get('esperados_propostos') or []) if revs else []),
            'autoconferencias': len([a for a in estado.get('autoconferencias', []) if a['onda'] == oid]),
            'pre_revisao': len([s_ for s_ in estado['sessoes_mutacao'] if s_['onda'] == oid and s_.get('pre_revisao')]),
            'mutantes_novos': novos, 'mutantes_reconfirmados': reconf, 'mutantes_desperdicados': desperdicio,
            'execucoes_falhas': falhas})
    return saida


def medicao(estado, p):
    """P8 em Markdown, para o bloco gerado do painel."""
    linhas = ['| Onda | Rodadas | Lacunas por classe | Decisões | Autoconferências | Mutantes novos / reconfirmados / '
              'desperdiçados | Execuções que falharam |', '|---|---|---|---|---|---|---|']
    for d in medicao_dados(estado, p):
        rodadas = ', '.join('%s %s' % (r['id'], r['veredito'] or '—') for r in d['rodadas']) or '—'
        classes = (', '.join('%s %d' % (k, n) for k, n in sorted(d['classes'].items())) or '—') \
            if d['classes'] is not None else 'n/d (%s)' % d['regras']
        extras = [x for x in ('%d na recomendada' % d['decisoes_recomendadas'] if d['decisoes_recomendadas'] else '',
                              '%d de engenharia' % d['decisoes_engenharia'] if d['decisoes_engenharia'] else '',
                              '%d esperado(s) proposto(s)' % d['esperados_propostos'] if d['esperados_propostos'] else '')
                  if x]
        linhas.append('| %s | %s | %s | %d%s | %d%s | %d / %d / %d | %s |' % (
            d['id'], rodadas, classes, d['decisoes'], ' (%s)' % ', '.join(extras) if extras else '', d['autoconferencias'],
            ' + %d pré-revisão' % d['pre_revisao'] if d['pre_revisao'] else '',
            d['mutantes_novos'], d['mutantes_reconfirmados'], d['mutantes_desperdicados'],
            _contagem_dict(d['execucoes_falhas'])))
    return '\n'.join(linhas) if len(linhas) > 2 else '_nenhuma onda iniciada_'


def _contagem_dict(d):
    return ', '.join('%s %d' % (k, n) for k, n in sorted(d.items())) or '—'


# ------------------------------------------------------------------------------ tempo × esforço × qualidade

CORTE_OCIOSO = 45 * 60      # intervalo sem evento acima disto não conta como tempo ativo
TETO_CONFERENCIA = 3 * 3600  # sessão/revisão mais longa que isto foi interrompida (noite, almoço): não conta inteira
ORIGENS_DEFEITO = ('revisao', 'parecer', 'posterior')


def _t(x):
    return dt.datetime.fromisoformat(x) if x else None


def eventos_da_onda(estado, oid):
    """Instantes registrados da onda: início e fim, commits, execuções, revisões, autoconferências, sessões de
    mutação e decisões. É o que dá para dizer sobre quando houve trabalho."""
    eo = estado['ondas'][oid]
    ev = [_t(eo.get('iniciada_em')), _t(eo.get('fechada_em'))]
    for tk in (eo.get('tarefas') or {}).values():
        ev += [_t(c.get('em')) for c in tk.get('commits', [])] + [_t(tk.get('inicio'))]
    for x in estado['execucoes']:
        if x.get('onda') == oid:
            ev += [_t(x.get('inicio')), _t(x.get('fim'))]
    for r in estado['revisoes']:
        if r['onda'] == oid:
            ev += [_t(r.get('iniciada_em')), _t(r.get('validada_em'))]
    for a in estado.get('autoconferencias', []):
        if a['onda'] == oid:
            ev += [_t(a.get('iniciada_em')), _t(a.get('validada_em'))]
    for s_ in estado['sessoes_mutacao']:
        if s_['onda'] == oid:
            ev += [_t(s_.get('criada_em')), _t(s_.get('limpa_em'))]
    for d in estado.get('decisoes', []):
        if d.get('onda') == oid:
            ev.append(_t(d.get('registrada_em')))
    return sorted(x for x in ev if x)


def tempo_ativo_h(eventos, corte=CORTE_OCIOSO):
    """Horas ativas estimadas: soma dos intervalos entre eventos consecutivos, cada um limitado a `corte`."""
    return sum(min((b - a).total_seconds(), corte) for a, b in zip(eventos, eventos[1:])) / 3600.0


def intervalos_de_conferencia(estado, oid):
    """(início, fim) de cada atividade de conferência: sessão de mutação, revisão e autoconferência (quando têm
    fim registrado) e execução de teste. Cada uma limitada a `TETO_CONFERENCIA`."""
    iv = []
    def _add(a, b):
        a, b = _t(a), _t(b)
        if a and b and b > a:
            iv.append((a, min(b, a + dt.timedelta(seconds=TETO_CONFERENCIA))))
    for s_ in estado['sessoes_mutacao']:
        if s_['onda'] == oid:
            _add(s_.get('criada_em'), s_.get('limpa_em'))
    for r in estado['revisoes']:
        if r['onda'] == oid:
            _add(r.get('iniciada_em'), r.get('validada_em'))
    for a in estado.get('autoconferencias', []):
        if a['onda'] == oid:
            _add(a.get('iniciada_em'), a.get('validada_em'))
    for x in estado['execucoes']:
        if x.get('onda') == oid and x.get('tipo') == 'teste':
            _add(x.get('inicio'), x.get('fim'))
    return iv


def uniao_h(intervalos):
    """Horas cobertas pela união dos intervalos (sobreposição não conta duas vezes)."""
    total, fim = 0.0, None
    for a, b in sorted(intervalos):
        if fim is None or a > fim:
            total += (b - a).total_seconds()
            fim = b
        elif b > fim:
            total += (b - fim).total_seconds()
            fim = b
    return total / 3600.0


def _linhas_de_producao(estado, oid):
    """Linhas de produção (acrescentadas + removidas, sem arquivo de teste) dos commits da onda. Uma chamada ao git
    por repositório."""
    por_repo = {}
    for tk in (estado['ondas'][oid].get('tarefas') or {}).values():
        for c in tk.get('commits', []):
            por_repo.setdefault(c['repo'], set()).add(c['hash'])
    total = 0
    for repo, hashes in por_repo.items():
        cfg = estado['repos'].get(repo)
        if not cfg or not os.path.isdir(cfg['caminho']) or not hashes:
            continue
        saida = subprocess.run(['git', '-C', cfg['caminho'], 'show', '--numstat', '--format=', '--no-renames'] + sorted(hashes),
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).stdout
        for ln in saida.decode('utf-8', 'replace').splitlines():
            partes = ln.split('\t')
            if len(partes) == 3 and partes[0].isdigit() and not M._eh_teste(partes[2]):
                total += int(partes[0]) + int(partes[1])
    return total


def defeitos_da_onda(estado, oid, medicao_onda=None):
    """(achados pelo processo, escapados). Processo: lacuna de classe `defeito` nas revisões mais o que
    `defeito add` registrou com origem revisao ou parecer. Escapado: `defeito add --origem posterior` (visto depois da
    liberação) — o único sinal de qualidade que não é o próprio gate."""
    classes = (medicao_onda or {}).get('classes') or {}
    regs = [x for x in estado.get('defeitos', []) if x['onda'] == oid]
    processo = classes.get('defeito', 0) + len([x for x in regs if x['origem'] in ('revisao', 'parecer')])
    escapados = len([x for x in regs if x['origem'] == 'posterior'])
    return processo, escapados


def metricas_dados(estado, p, com_linhas=True):
    """Tempo × esforço × qualidade por onda iniciada. Estimativas, não relógio de ponto: o tempo ativo vem dos eventos
    gravados (ver `tempo_ativo_h`); a conferência é a união das sessões de mutação, revisões, autoconferências e
    execuções de teste; a implementação é o resto do tempo ativo (inclui a espera pelo usuário entre decisões)."""
    base = {d['id']: d for d in medicao_dados(estado, p)}
    saida = []
    agora = dt.datetime.now(dt.timezone.utc).astimezone()
    for o in p.ondas:
        oid = o['id']
        eo = estado['ondas'].get(oid)
        if not eo or oid not in base:
            continue
        m = base[oid]
        ev = eventos_da_onda(estado, oid)
        ativo = tempo_ativo_h(ev)
        conf = min(uniao_h(intervalos_de_conferencia(estado, oid)), ativo)
        impl = max(ativo - conf, 0.0)
        ini, fim = _t(eo.get('iniciada_em')), _t(eo.get('fechada_em')) or agora
        wall = (fim - ini).total_seconds() / 3600.0 if ini else None
        commits = sum(len(tk.get('commits', [])) for tk in (eo.get('tarefas') or {}).values())
        linhas = _linhas_de_producao(estado, oid) if com_linhas else None
        achados, escapados = defeitos_da_onda(estado, oid, m)
        muts = m['mutantes_novos'] + m['mutantes_reconfirmados']
        surv = sum(1 for s_ in estado['sessoes_mutacao'] if s_['onda'] == oid and s_.get('tipo') != 'autor'
                   for x in s_.get('mutantes', []) if x['resultado'] == 'sobrevivente')
        altas = len([x for x in estado.get('pendencias', []) if x['onda'] == oid and not x.get('descartada')
                     and (x.get('severidade') or 'alta') == 'alta'])
        rodadas = len(m['rodadas'])
        saida.append({
            'id': oid, 'titulo': o['titulo'], 'estado': eo.get('estado'), 'regras': m['regras'],
            'tempo': {'ativo_h': ativo, 'conferencia_h': conf, 'implementacao_h': impl, 'relogio_h': wall},
            'esforco': {'rodadas': rodadas, 'mutantes': muts, 'decisoes': m['decisoes'], 'commits': commits,
                        'linhas_producao': linhas},
            'qualidade': {'defeitos_no_processo': achados, 'defeitos_escapados': escapados, 'sobreviventes': surv,
                          'taxa_sobrevivencia': (surv / muts) if muts else None, 'pendencias_altas_abertas': altas},
            'derivadas': {
                'conferencia_por_implementacao': (conf / impl) if impl > 0.05 else None,
                'horas_por_defeito': (ativo / achados) if achados else None,
                'rodadas_por_100_linhas': (100.0 * rodadas / linhas) if linhas else None}})
    return saida


def _mediana(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


ENCERRADAS = ('fechada', 'replanejada', 'abandonada')


def ordem_rotulo(rotulo):
    """r1, r2, r3 e, por último, `atual`."""
    return (rotulo == 'atual', rotulo)


def cor_do_rotulo(d):
    return {'r1': '--r1', 'r2': '--r2', 'r3': '--r3'}.get(d['regras'], '--atual')


def resumo_por_regras(dados):
    """Medianas por rótulo de regras (r1–r3 históricas, `atual`), **só das ondas encerradas** (uma onda em andamento tem tempo e rodadas pela
    metade e distorce a mediana); as em andamento vão contadas à parte."""
    saida = []
    for reg in sorted({d['regras'] for d in dados}, key=ordem_rotulo):
        todas = [d for d in dados if d['regras'] == reg]
        ds = [d for d in todas if d['estado'] in ENCERRADAS]
        saida.append({
            'regras': reg, 'ondas': len(ds), 'em_andamento': len(todas) - len(ds),
            'ativo_h': _mediana([d['tempo']['ativo_h'] for d in ds]),
            'conferencia_h': _mediana([d['tempo']['conferencia_h'] for d in ds]),
            'rodadas': _mediana([d['esforco']['rodadas'] for d in ds]),
            'mutantes': _mediana([d['esforco']['mutantes'] for d in ds]),
            'decisoes': _mediana([d['esforco']['decisoes'] for d in ds]),
            'h_por_100_linhas': _mediana([100.0 * d['tempo']['ativo_h'] / d['esforco']['linhas_producao']
                                          for d in ds if d['esforco']['linhas_producao']]),
            'taxa_sobrevivencia': _mediana([d['qualidade']['taxa_sobrevivencia'] for d in ds]),
            'defeitos': sum(d['qualidade']['defeitos_no_processo'] for d in todas),
            'escapados': sum(d['qualidade']['defeitos_escapados'] for d in todas)})
    return saida


def _f(v, casas=1, suf=''):
    return '—' if v is None else ('%.*f%s' % (casas, v, suf))


def metricas(pasta, args=None):
    """`estado metricas`: a tabela de tempo × esforço × qualidade no terminal (ou `--json`)."""
    estado = C.carregar_estado(pasta)
    p = P.Plano(C.arquivo_plano(pasta))
    dados = metricas_dados(estado, p)
    if args is not None and getattr(args, 'json', False):
        print(json.dumps({'ondas': dados, 'por_regras': resumo_por_regras(dados)}, ensure_ascii=False, indent=2))
        return 0
    print('estado metricas %s — estimativas: tempo ativo = eventos gravados, com corte de %d min entre eles' % (
        C.rotulo(pasta), CORTE_OCIOSO // 60))
    print('%-5s %-5s %7s %7s %7s | %5s %5s %5s %6s | %4s %4s %5s %4s | %6s %6s' % (
        'onda', 'reg', 'ativo_h', 'conf_h', 'impl_h', 'rodad', 'mut', 'decis', 'linhas', 'def', 'esc', 'sobr%', 'palt', 'c/i', 'h/def'))
    for d in dados:
        t, e, q, v = d['tempo'], d['esforco'], d['qualidade'], d['derivadas']
        print('%-5s %-5s %7s %7s %7s | %5d %5d %5d %6s | %4d %4d %5s %4d | %6s %6s' % (
            d['id'], d['regras'], _f(t['ativo_h']), _f(t['conferencia_h']), _f(t['implementacao_h']),
            e['rodadas'], e['mutantes'], e['decisoes'], '—' if e['linhas_producao'] is None else e['linhas_producao'],
            q['defeitos_no_processo'], q['defeitos_escapados'],
            _f(None if q['taxa_sobrevivencia'] is None else 100 * q['taxa_sobrevivencia'], 1),
            q['pendencias_altas_abertas'], _f(v['conferencia_por_implementacao'], 2), _f(v['horas_por_defeito'])))
    print('\nmedianas por regras:')
    for r in resumo_por_regras(dados):
        print('  %s (%d encerradas%s): ativo %sh, conferência %sh, %s rodadas, %s mutantes, %s decisões, %s h/100 linhas, '
              'sobrevivência %s, defeitos %d (escapados %d)' % (
                  r['regras'], r['ondas'], ' + %d em andamento' % r['em_andamento'] if r['em_andamento'] else '',
                  _f(r['ativo_h']), _f(r['conferencia_h']), _f(r['rodadas'], 0), _f(r['mutantes'], 0),
                  _f(r['decisoes'], 0), _f(r['h_por_100_linhas'], 2),
                  _f(None if r['taxa_sobrevivencia'] is None else 100 * r['taxa_sobrevivencia'], 1, '%'), r['defeitos'], r['escapados']))
    return 0


# ------------------------------------------------------------------------------ pendências (dados)

def pendencias_dados(estado, p):
    """Cada pendência do projeto com a situação: `sem onda` (aberta, nenhuma onda a tem na Origem), `coberta` (uma onda a
    tem) ou `descartada` (decisão do usuário). Severidade: a gravada; sem o campo, alta."""
    cobertas = {}
    for o in p.ondas:
        for x in P.origens(o):
            if re.fullmatch(r'P\d+', x):
                cobertas.setdefault(x, []).append(o['id'])
    saida = []
    for x in estado.get('pendencias', []):
        ondas = cobertas.get(x['id'], [])
        if x.get('descartada'):
            sit = 'descartada'
        elif ondas:
            sit = 'coberta'
        else:
            sit = 'sem onda'
        estados = [estado['ondas'].get(o, {}).get('estado', 'não iniciada') for o in ondas]
        saida.append({
            'id': x['id'], 'onda': x['onda'], 'origem': x['origem'], 'texto': x['texto'], 'em': x.get('em'),
            'severidade': x.get('severidade') or 'alta', 'severidade_registrada': bool(x.get('severidade')),
            'situacao': sit, 'ondas_que_cobrem': ondas, 'estado_das_ondas': estados,
            'decisao': x.get('descartada')})
    return saida



# ------------------------------------------------------------------------------ painel em HTML

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'painel')


def _esc(x):
    import html as _h
    return _h.escape(str(x), quote=True)


def _barras(dados, valor, cor, rotulo_y):
    """Barras verticais simples em SVG; `valor(d)` é a altura, `cor(d)` a variável CSS."""
    if not dados:
        return '<div class="sub">nenhuma onda iniciada</div>'
    largura, altura, m_esq, m_base, topo = 1000, 220, 30, 28, 14
    maximo = max([valor(d) for d in dados] + [1])
    passo = (largura - m_esq - 10) / len(dados)
    larg = min(34, passo * 0.7)
    partes = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (largura, altura, _esc(rotulo_y))]
    for k in range(0, maximo + 1, max(1, maximo // 4)):
        y = altura - m_base - (altura - m_base - topo) * k / maximo
        partes.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--linha)"/><text x="4" y="%.1f">%d</text>'
                      % (m_esq, largura - 6, y, y, y + 3, k))
    for i, d in enumerate(dados):
        x = m_esq + passo * i + (passo - larg) / 2
        h = (altura - m_base - topo) * valor(d) / maximo
        partes.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="var(%s)"><title>Onda %s: %d</title></rect>'
                      % (x, altura - m_base - h, larg, h, cor(d), _esc(d['id']), valor(d)))
        if passo >= 18:
            partes.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x + larg / 2, altura - 12, _esc(d['id'])))
    partes.append('</svg>')
    return ''.join(partes)


def _barras_empilhadas(dados):
    if not dados:
        return '<div class="sub">nenhuma onda iniciada</div>'
    largura, altura, m_esq, m_base, topo = 1000, 220, 30, 28, 14
    total = lambda d: d['mutantes_novos'] + d['mutantes_reconfirmados']
    maximo = max([total(d) for d in dados] + [1])
    passo = (largura - m_esq - 10) / len(dados)
    larg = min(34, passo * 0.7)
    partes = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Mutantes do revisor por onda">' % (largura, altura)]
    for k in range(0, maximo + 1, max(1, maximo // 4)):
        y = altura - m_base - (altura - m_base - topo) * k / maximo
        partes.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--linha)"/><text x="4" y="%.1f">%d</text>'
                      % (m_esq, largura - 6, y, y, y + 3, k))
    esc = (altura - m_base - topo) / maximo
    for i, d in enumerate(dados):
        x = m_esq + passo * i + (passo - larg) / 2
        base = altura - m_base
        bom = d['mutantes_novos'] - d['mutantes_desperdicados']
        for rotulo, v, cor in (('novos', bom, '--novo'), ('desperdiçados', d['mutantes_desperdicados'], '--desp'),
                               ('reconfirmados', d['mutantes_reconfirmados'], '--reconf')):
            h = v * esc
            if h > 0:
                partes.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="var(%s)"><title>Onda %s — %s: %d</title></rect>'
                              % (x, base - h, larg, h, cor, _esc(d['id']), rotulo, v))
                base -= h
        if passo >= 18:
            partes.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x + larg / 2, altura - 12, _esc(d['id'])))
    partes.append('</svg>')
    return ''.join(partes)


def _dispersao(dados):
    """Dispersão: x = rodadas de revisão (esforço), y = horas ativas (tempo); cor = regras; raio cresce com os defeitos
    achados pelo processo (qualidade)."""
    pts = [d for d in dados if d['esforco']['rodadas'] or d['tempo']['ativo_h']]
    if not pts:
        return '<div class="sub">nenhuma onda iniciada</div>'
    largura, altura, m_esq, m_base, topo = 1000, 260, 38, 30, 14
    mx = max([d['esforco']['rodadas'] for d in pts] + [1])
    my = max([d['tempo']['ativo_h'] for d in pts] + [1.0])
    partes = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Horas ativas por rodadas de revisão">' % (largura, altura)]
    for k in range(0, int(my) + 1, max(1, int(my) // 4)):
        y = altura - m_base - (altura - m_base - topo) * k / my
        partes.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--linha)"/><text x="4" y="%.1f">%d h</text>'
                      % (m_esq, largura - 8, y, y, y + 3, k))
    for k in range(0, mx + 1):
        x = m_esq + (largura - m_esq - 20) * k / mx
        partes.append('<text x="%.1f" y="%d" text-anchor="middle">%d</text>' % (x, altura - 12, k))
    partes.append('<text x="%d" y="%d" text-anchor="end">rodadas de revisão →</text>' % (largura - 10, altura - 2))
    for d in pts:
        x = m_esq + (largura - m_esq - 20) * d['esforco']['rodadas'] / mx
        y = altura - m_base - (altura - m_base - topo) * d['tempo']['ativo_h'] / my
        cor = cor_do_rotulo(d)
        q = d['qualidade']
        partes.append('<circle cx="%.1f" cy="%.1f" r="%d" fill="var(%s)" fill-opacity="0.75" stroke="var(--texto)" stroke-opacity="0.35">'
                      '<title>Onda %s (%s): %.1f h ativas, %d rodadas, %d mutantes, %d decisões, %d defeito(s) no processo, %d escapado(s)</title></circle>'
                      % (x, y, 5 + 2 * min(q['defeitos_no_processo'], 4), cor, _esc(d['id']), d['regras'], d['tempo']['ativo_h'],
                         d['esforco']['rodadas'], d['esforco']['mutantes'], d['esforco']['decisoes'],
                         q['defeitos_no_processo'], q['defeitos_escapados']))
    partes.append('</svg>')
    return ''.join(partes)


def _html_resumo_regras(dados):
    linhas = ''.join(
        '<tr><td>%s</td><td>%d%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d (%d escapados)</td></tr>' % (
            r['regras'], r['ondas'], ' (+%d em andamento)' % r['em_andamento'] if r['em_andamento'] else '',
            _f(r['ativo_h']), _f(r['conferencia_h']), _f(r['rodadas'], 0), _f(r['mutantes'], 0),
            _f(r['decisoes'], 0), _f(r['h_por_100_linhas'], 2),
            _f(None if r['taxa_sobrevivencia'] is None else 100 * r['taxa_sobrevivencia'], 1, '%'), r['defeitos'], r['escapados'])
        for r in resumo_por_regras(dados))
    return ('<div class="tabela"><table><thead><tr><th>Versão</th><th>Ondas encerradas</th><th>Tempo ativo (mediana, h)</th><th>Conferência (h)</th>'
            '<th>Rodadas</th><th>Mutantes</th><th>Decisões</th><th>h por 100 linhas</th><th>Sobrevivência</th><th>Defeitos achados</th></tr></thead>'
            '<tbody>%s</tbody></table></div>' % (linhas or '<tr><td colspan="10">nenhuma onda iniciada</td></tr>'))


def _html_tabela_metricas(dados):
    linhas = []
    for d in dados:
        t, e, q, v = d['tempo'], d['esforco'], d['qualidade'], d['derivadas']
        linhas.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%s</td>'
                      '<td>%d</td><td>%d</td><td>%s</td><td>%d</td><td>%s</td><td>%s</td></tr>' % (
                          _esc(d['id']), d['regras'], _f(t['ativo_h']), _f(t['conferencia_h']), _f(t['implementacao_h']),
                          e['rodadas'], e['mutantes'], e['decisoes'], '—' if e['linhas_producao'] is None else e['linhas_producao'],
                          q['defeitos_no_processo'], q['defeitos_escapados'],
                          _f(None if q['taxa_sobrevivencia'] is None else 100 * q['taxa_sobrevivencia'], 1, '%'),
                          q['pendencias_altas_abertas'], _f(v['conferencia_por_implementacao'], 2), _f(v['horas_por_defeito'])))
    return ('<div class="tabela"><table><thead><tr><th>Onda</th><th>Regras</th><th>Ativo (h)</th><th>Conferência (h)</th><th>Implementação (h)</th>'
            '<th>Rodadas</th><th>Mutantes</th><th>Decisões</th><th>Linhas de produção</th><th>Defeitos achados</th><th>Escapados</th>'
            '<th>Sobrevivência</th><th>Pend. altas abertas</th><th>Conferência ÷ implementação</th><th>h por defeito</th></tr></thead>'
            '<tbody>%s</tbody></table></div>' % (''.join(linhas) or '<tr><td colspan="15">nenhuma onda iniciada</td></tr>'))


def _html_pendencias(dados):
    if not dados:
        return '<div class="sub">nenhuma pendência registrada</div>'
    por = {'sem onda': [], 'coberta': [], 'descartada': []}
    for x in dados:
        por[x['situacao']].append(x)
    altas_abertas = len([x for x in por['sem onda'] if x['severidade'] == 'alta'])
    baixas_abertas = len(por['sem onda']) - altas_abertas
    cards = ''.join('<div class="card"><b>%s</b><span>%s</span></div>' % (_esc(v), _esc(k)) for k, v in (
        ('abertas sem onda — alta', altas_abertas), ('abertas sem onda — baixa', baixas_abertas),
        ('cobertas por uma onda', len(por['coberta'])), ('descartadas', len(por['descartada']))))
    def _tabela(lista, mostra_onda_que_cobre):
        ordem = sorted(lista, key=lambda x: (x['severidade'] != 'alta', int(re.sub(r'\D', '', x['id']) or 0)))
        linhas = []
        for x in ordem:
            if mostra_onda_que_cobre:
                sit = ', '.join('onda %s (%s)' % (o, e) for o, e in zip(x['ondas_que_cobrem'], x['estado_das_ondas'])) or '—'
            else:
                sit = ('decisão %s' % x['decisao']) if x['decisao'] else 'sem onda'
            linhas.append('<tr data-no="pendencia:%s"><td>%s</td><td>%s</td><td>%s</td><td class="sev-%s">%s%s</td><td>%s</td><td class="txt">%s</td></tr>' % (
                _esc(x['id']), _esc(x['id']), _esc(x['onda']), _esc(x['origem']), _esc(x['severidade']), _esc(x['severidade']),
                '' if x['severidade_registrada'] else '*', _esc(sit), _esc(x['texto'])))
        return ('<div class="tabela"><table><thead><tr><th>#</th><th>Onda</th><th>Origem</th><th>Severidade</th><th>Situação</th>'
                '<th>Pendência</th></tr></thead><tbody>%s</tbody></table></div>' % ''.join(linhas))
    blocos = ['<div class="cards">%s</div>' % cards]
    for chave, titulo, abre, cobre in (('sem onda', 'Abertas sem onda', True, False), ('coberta', 'Cobertas por uma onda', False, True),
                                       ('descartada', 'Descartadas', False, False)):
        if por[chave]:
            blocos.append('<details%s><summary>%s (%d)</summary>%s</details>' % (
                ' open' if abre else '', titulo, len(por[chave]), _tabela(por[chave], cobre)))
    blocos.append('<div class="aviso">* sem o campo de severidade (pendência histórica): conta como alta.</div>')
    return ''.join(blocos)



def _href_no(nid):
    return '#grafo/' + urllib.parse.quote(nid, safe='')


def _ondas_html(estado, p, dados):
    por = {d['id']: d for d in dados}
    saida = []
    for o in p.ondas:
        eo = estado['ondas'].get(o['id']) or {}
        est = eo.get('estado') or 'planejada'
        rod = ' · '.join('%s %s' % (r['id'], (r['veredito'] or '—').lower()) for r in (por.get(o['id']) or {}).get('rodadas', []))
        saida.append('<a class="onda est-%s" href="%s" data-no="onda:%s"><b>Onda %s — %s</b><span>%s%s</span></a>' % (
            _esc(est), _href_no('onda:' + o['id']), _esc(o['id']), _esc(o['id']), _esc(o['titulo'].replace('`', '')), _esc(est.replace('_', ' ')),
            _esc(' · ' + rod) if rod else ''))
    return ''.join(saida) or '<div class="sub">nenhuma onda no plano</div>'


def _lacunas_html(modelo, limite=15):
    nos = {n['id']: n for n in modelo['nodes']}
    if not modelo['lacunas']:
        return '<div class="sub">nenhuma lacuna encontrada entre a análise, a ER/ET, o plano e a execução</div>'
    grupos = {}                              # a mesma mensagem em N nós vira uma linha "N× mensagem" que abre a lista
    for l in modelo['lacunas']:
        grupos.setdefault((l['nivel'] == 'aviso', l['msg']), []).append(l['no'])
    itens = []
    for (aviso, msg), ids in sorted(grupos.items(), key=lambda kv: (kv[0][0], -len(kv[1]), kv[0][1])):
        cls = 'avi' if aviso else 'lac'
        links = ''.join('<a href="%s" data-no="%s">%s</a>' % (_href_no(i), _esc(i), _esc(nos[i]['rotulo'] if i in nos else i))
                        for i in ids[:limite])
        mais = '<span class="aviso">e mais %d na aba Grafo</span>' % (len(ids) - limite) if len(ids) > limite else ''
        if len(ids) == 1:
            itens.append('<li class="%s"><a href="%s" data-no="%s">%s — %s</a></li>' % (
                cls, _href_no(ids[0]), _esc(ids[0]), _esc(nos[ids[0]]['rotulo'] if ids[0] in nos else ids[0]), _esc(msg)))
        else:
            itens.append('<li class="%s"><details><summary>%d× %s</summary><div class="nos">%s%s</div></details></li>' % (
                cls, len(ids), _esc(msg), links, mais))
    return '<ul class="lacs">%s</ul>' % ''.join(itens)


def _grafo_do_projeto(pasta):
    """O modelo do grafo; se o projeto tiver algo que ele não entenda, o painel sai sem a aba em vez de não sair."""
    try:
        return GR.montar(pasta), None
    except Exception as ex:                  # noqa: BLE001 — o painel não pode cair por causa do grafo
        return {'nodes': [], 'edges': [], 'lacunas': [], 'contagem': {}, 'recolhidos': list(GR.RECOLHIDOS),
                'colunas': []}, 'grafo não montado: %s' % ex


def painel_html(pasta, estado=None, p=None, fps=None, destino=None, grafo=None):
    """Grava `PAINEL-NN-AAAA.html` (ou `destino`): página única, sem biblioteca externa, com abas. Os números e os
    gráficos saem prontos do servidor (funcionam sem JavaScript); o grafo é desenhado pelo JavaScript da página a
    partir do JSON embutido. Leva o texto de aceites, tarefas, decisões e pendências, nunca a fala nem a citação do
    usuário. Devolve o caminho."""
    estado = estado or C.carregar_estado(pasta)
    p = p or P.Plano(C.arquivo_plano(pasta))
    dados = medicao_dados(estado, p)
    met = metricas_dados(estado, p)
    pend_dados = pendencias_dados(estado, p)
    modelo, falha_grafo = (grafo, None) if grafo else _grafo_do_projeto(pasta)
    rodadas_total = sum(len(d['rodadas']) for d in dados)
    reprovadas = sum(1 for d in dados for r in d['rodadas'] if r['veredito'] == 'REPROVADA')
    fechadas = sum(1 for d in dados if d['estado'] == 'fechada')
    ativa = C.onda_ativa(estado)
    pend = [x for x in estado.get('pendencias', []) if not x.get('descartada')]
    cards = ''.join('<div class="card"><b>%s</b><span>%s</span></div>' % (_esc(v), _esc(k)) for k, v in (
        ('ondas iniciadas', len(dados)), ('ondas fechadas', fechadas), ('onda em execução', ativa or '—'),
        ('revisões', rodadas_total), ('reprovadas', reprovadas),
        ('rodadas por onda (média)', '%.1f' % (rodadas_total / len(dados)) if dados else '—'),
        ('pendências não descartadas', len(pend))))
    lacunas = [l for l in modelo['lacunas'] if l['nivel'] != 'aviso']
    altas = len([x for x in pend_dados if x['situacao'] == 'sem onda' and x['severidade'] == 'alta'])
    chips = ''.join(c for c in (
        '<span class="chip ok"><b>%d</b> onda(s) fechada(s)</span>' % fechadas,
        '<a class="chip" href="%s"><b>onda %s</b> em execução</a>' % (_href_no('onda:' + ativa), _esc(ativa)) if ativa else '',
        '<a class="chip%s" href="#geral"><b>%d</b> lacuna(s)</a>' % (' ruim' if lacunas else '', len(lacunas)),
        '<a class="chip%s" href="#pendencias"><b>%d</b> pendência(s) alta(s) sem onda</a>' % (' ruim' if altas else '', altas)))
    linhas = []
    for d in dados:
        rod = ' '.join('<span class="v-%s">%s&nbsp;%s</span>' % (_esc(r['veredito'] or ''), _esc(r['id']), _esc((r['veredito'] or '—').lower()))
                       for r in d['rodadas']) or '—'
        classes = (_contagem_dict(d['classes']) if d['classes'] else '—') if d['classes'] is not None else 'n/d'
        linhas.append('<tr data-no="onda:%s"><td>%s</td><td>%s</td><td>%s</td><td class="rod">%s</td><td>%s</td><td>%d</td><td>%d%s</td><td>%d / %d / %d</td><td>%s</td></tr>' % (
            _esc(d['id']), _esc(d['id']), _esc(d['estado']), d['regras'], rod, _esc(classes), d['decisoes'], d['autoconferencias'],
            ' + %d pré' % d['pre_revisao'] if d['pre_revisao'] else '',
            d['mutantes_novos'], d['mutantes_reconfirmados'], d['mutantes_desperdicados'], _esc(_contagem_dict(d['execucoes_falhas']))))
    repos = []
    for r, cfg in sorted(estado['repos'].items()):
        f = _repo_fatos(estado, r, cfg)
        if 'erro' in f:
            repos.append('<tr><td>%s</td><td colspan="4">%s</td></tr>' % (_esc(r), _esc(f['erro'])))
            continue
        push = ('sem upstream' if not f['upstream'] else 'origin == HEAD' if not f['atras'] and not f['frente']
                else '%s à frente, %s atrás' % (f['frente'], f['atras']))
        repos.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td></tr>' % (
            _esc(r), _esc(f['branch']), _esc(f['head']), _esc(push), f['nao_commitados']))
    embutido = {'grafo': GR.compactar(modelo), 'ativa': ativa or '',      # a onda em execução: o grafo abre focado nela
                'ondas': [{'id': o['id'], 'titulo': o['titulo']} for o in p.ondas]}
    json_embutido = json.dumps(embutido, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/') \
        .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    valores = {
        'ROTULO': _esc(C.rotulo(pasta)), 'AGORA': _esc(C.agora()), 'CHIPS': chips, 'CARDS': cards,
        'ONDAS': _ondas_html(estado, p, dados),
        'LACUNAS': _lacunas_html(modelo) + ('<div class="aviso">%s</div>' % _esc(falha_grafo) if falha_grafo else ''),
        'GRAFICO_RODADAS': _barras(dados, lambda d: len(d['rodadas']), cor_do_rotulo, 'Rodadas de revisão por onda'),
        'GRAFICO_MUTANTES': _barras_empilhadas(dados),
        'LINHAS_P8': ''.join(linhas) or '<tr><td colspan="9">nenhuma onda iniciada</td></tr>',
        'RESUMO_REGRAS': _html_resumo_regras(met), 'GRAFICO_DISPERSAO': _dispersao(met),
        'TABELA_METRICAS': _html_tabela_metricas(met), 'PENDENCIAS': _html_pendencias(pend_dados),
        'REPOS': ''.join(repos) or '<tr><td colspan="5">nenhum repositório configurado</td></tr>',
        'CSS': C.ler(os.path.join(ASSETS, 'painel.css')), 'JS': C.ler(os.path.join(ASSETS, 'painel.js')),
        'DADOS': json_embutido}
    # uma passada só: um valor (texto de pendência, por exemplo) que contenha @@X@@ não é expandido de novo
    html = re.sub(r'@@([A-Z_0-9]+)@@', lambda m: valores[m.group(1)], C.ler(os.path.join(ASSETS, 'index.html')))
    caminho = destino or C.arquivo_painel_html(pasta)
    C.gravar(caminho, html)
    return caminho


def painel(pasta, args=None, quieto=False):
    estado = C.carregar_estado(pasta)
    p = P.Plano(C.arquivo_plano(pasta))
    fps = {r: C.fingerprint(cfg['caminho']) for r, cfg in estado['repos'].items() if os.path.isdir(cfg['caminho'])}
    linhas = ['| Frente | Situação |', '|---|---|']
    for o in p.ondas:
        linhas.append('| Onda %s — %s | %s |' % (o['id'], o['titulo'], _situacao_onda(estado, o, fps, pasta)))
    for r, cfg in sorted(estado['repos'].items()):
        f = _repo_fatos(estado, r, cfg)
        if 'erro' in f:
            continue
        push = ('sem upstream' if not f['upstream'] else '`origin` == HEAD' if not f['atras'] and not f['frente']
                else '%s commit(s) sem push' % f['frente'])
        linhas.append('| Repositório `%s` | `%s` @ `%s` — %s; %d arquivo(s) não commitado(s) |'
                      % (r, f['branch'], f['head'], push, f['nao_commitados']))
    conteudo = '\n'.join(linhas) + '\n\n**Medição por onda (P8)**\n\n' + medicao(estado, p) + '\n\n_Gerado por `demanda.py estado painel` em %s._' % C.agora()
    md = C.arquivo_estado_md(pasta)
    if not os.path.exists(md):
        C.gravar(md, ESQUELETO.format(rotulo=C.rotulo(pasta), data=C.hoje_br(), painel=C.bloco('painel', conteudo)))
        acao = 'criado'
    else:
        texto = C.ler(md)
        texto, achou = C.trocar_bloco(texto, 'painel', conteudo)
        if not achou:
            raise SystemExit('%s não tem os marcadores <!-- gerado:painel:inicio/fim --> — '
                             'ponha-os na seção 1 para o painel poder ser gerado' % md)
        texto = re.sub(r'Atualizado em \*\*[^*]+\*\*', 'Atualizado em **%s**' % C.hoje_br(), texto, count=1)
        C.gravar(md, texto)
        acao = 'atualizado'
    if not quieto:
        print('painel %s: %s' % (acao, md))
    # O HTML é opcional: `--html` cria; depois de criado, todo painel (inclusive o do fechar-onda) o mantém em dia.
    if getattr(args, 'html', False) or os.path.exists(C.arquivo_painel_html(pasta)):
        caminho = painel_html(pasta, estado, p)
        if not quieto:
            print('painel HTML: %s' % caminho)
    return 0
