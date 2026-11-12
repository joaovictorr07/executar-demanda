#!/usr/bin/env python3
"""Repositórios da demanda, execução de testes e evidência manual.

Regras que moram aqui:

- **Testes só quando o usuário mandar.** Este módulo não é chamado por nenhum outro gate; ele
  só roda o que foi pedido e **registra**. Quem fecha a onda exige que exista um registro
  fresco — não roda nada no lugar do usuário.
- **Nunca a suíte inteira por engano.** Comando com `{classes}` e seleção vazia é recusado;
  suíte inteira só com `--suite-inteira` (o normal é rodar só as classes tocadas).
- **O resultado vem do relatório, não do texto.** No Maven, `-q` esconde o resumo do Surefire;
  por isso a contagem sai dos `TEST-*.xml` gerados durante a execução e, só na falta deles, da
  saída do comando.
"""

import fnmatch
import glob
import os
import re
import shlex
import subprocess

def citar_argumento(valor):
    return subprocess.list2cmdline([valor]) if os.name == "nt" else shlex.quote(valor)

import time
import xml.etree.ElementTree as ET

import comum as C

PERFIS = {
    'maven': {
        'teste': 'mvn -o test -Dtest={classes} -DfailIfNoTests=false',
        'build': 'mvn -o -q compile',
        'relatorios': 'target/surefire-reports/TEST-*.xml',
        'copiar_no_scratch': ['target'],
        'linkar_no_scratch': [],
    },
    'angular': {
        'teste': 'npx ng test --watch=false --browsers=ChromeHeadless',
        'build': 'npx ng build',
        'relatorios': '',
        'copiar_no_scratch': [],
        'linkar_no_scratch': ['node_modules'],
    },
    'generico': {
        'teste': '', 'build': '', 'relatorios': '',
        'copiar_no_scratch': [], 'linkar_no_scratch': [],
    },
}

# `-D` que aponta o teste para um banco: o teste deixa de ser unitário e passa a mexer em dados.
RE_D_BANCO = re.compile(r'-D[\w.-]*(datasource|jdbc|database|\bdb\.)', re.IGNORECASE)

RE_SUREFIRE = re.compile(
    r'Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)(.*)$')


# ------------------------------------------------------------------------------ configurar

def configurar(pasta, args):
    estado = C.carregar_estado(pasta)
    caminho = os.path.abspath(os.path.expanduser(args.caminho))
    if not C.git_ok(caminho, 'rev-parse', '--git-dir'):
        raise SystemExit('não é um repositório git: %s' % caminho)
    anterior = estado['repos'].get(args.repo, {})
    if not args.perfil and not anterior.get('perfil'):
        raise SystemExit('informe --perfil (maven, angular ou generico): é o que decide o comando de '
                         'teste, e não se deduz')
    args.perfil = args.perfil or anterior['perfil']
    perfil = dict(PERFIS[args.perfil])
    cfg = dict(anterior) if anterior else {}
    cfg.update({k: v for k, v in perfil.items() if k not in cfg or args.perfil != anterior.get('perfil')})
    cfg['perfil'] = args.perfil
    cfg['caminho'] = caminho
    # Trocar o comando de teste ou de build muda o que "teste OK" quer dizer: com `--teste 'echo
    # Tests run: 1…'` qualquer coisa passaria. Fora o default do perfil (ou a primeira configuração
    # de um perfil sem default), é decisão do usuário.
    exigem = []
    for campo in ('teste', 'build'):
        valor = getattr(args, campo)
        if valor is None:
            continue
        atual = _sem_m2(anterior.get(campo) or '')
        if _sem_m2(valor) == (atual or _sem_m2(perfil.get(campo) or '')):
            continue
        if atual or perfil.get(campo):
            exigem.append('--%s diferente do %s' % (campo, 'configurado' if atual else 'default do perfil'))
        elif valor:
            # perfil sem comando padrão (generico): o comando que o agente escolhe é quem diz o que
            # "teste OK" quer dizer — `echo "Tests run: 1, Failures: 0…"` seria execução OK
            exigem.append('--%s próprio (o perfil %s não tem comando padrão: o comando decide o que passa)'
                          % (campo, args.perfil))
    for campo in ('teste', 'build'):
        if RE_D_BANCO.search(getattr(args, campo) or ''):
            exigem.append('--%s com -D de banco' % campo)
    if args.sem_testes and not anterior.get('sem_testes_automatizados'):
        exigem.append('--sem-testes (derruba o gate de teste e de mutantes do repositório)')
    # Gate de padrão: ligar é sempre livre (pede mais); afrouxar, desligar e `--lint` são do usuário.
    import padrao as PD
    mexe_no_padrao = any(getattr(args, c, None) is not None for c in
                         ('padrao', 'padrao_desligar', 'padrao_colunas', 'lint'))
    if mexe_no_padrao:
        novo_padrao, exigem_padrao = PD.configurar(
            anterior.get('padrao'), getattr(args, 'padrao', None), getattr(args, 'padrao_desligar', None),
            getattr(args, 'padrao_colunas', None), getattr(args, 'lint', None))
        exigem += exigem_padrao
    novos_excl = []
    if args.ignorar_no_codigo is not None:
        novos_excl = sorted({x.strip().strip('/') for x in args.ignorar_no_codigo.split(',') if x.strip().strip('/')})
        if set(novos_excl) - set(anterior.get('ignorar_no_codigo', [])):
            # Tirar caminho da identidade do código é deixar de ver mudança nele.
            exigem.append('--ignorar-no-codigo (tira caminhos da identidade do código)')
    if exigem:
        import decisoes as DC
        erro_d = DC.exigir(estado, args.decisao, para='configurar', alvo=args.repo) if args.decisao else 'sem --decisao'
        if erro_d:
            raise SystemExit('recusado: %s — é decisão do usuário: --decisao D<n> (%s)'
                             % ('; '.join(exigem), erro_d))
        cfg.setdefault('decisoes', []).append({'decisao': args.decisao, 'para': exigem, 'em': C.agora()})
    if mexe_no_padrao:
        if novo_padrao:
            cfg['padrao'] = novo_padrao
        else:
            cfg.pop('padrao', None)
    for campo in ('teste', 'build', 'relatorios'):
        valor = getattr(args, campo)
        if valor is not None:
            cfg[campo] = valor
    if args.maven_repo_local is not None:
        # trocar de .m2 troca o comando: o valor anterior sai antes de o novo entrar
        extra = ' -Dmaven.repo.local=%s' % citar_argumento(os.path.expanduser(args.maven_repo_local)) \
            if args.maven_repo_local else ''
        for campo in ('teste', 'build'):
            atual = re.sub(r'\s+-Dmaven\.repo\.local=("[^"]*"|\'[^\']*\'|\S+)' , '', cfg.get(campo, '') or '')
            cfg[campo] = atual + extra if atual.startswith('mvn') else atual
    if args.ignorar_no_codigo is not None:
        cfg['ignorar_no_codigo'] = novos_excl
    if args.copiar_no_scratch is not None:
        cfg['copiar_no_scratch'] = [p for p in args.copiar_no_scratch.split(',') if p]
    if args.linkar_no_scratch is not None:
        cfg['linkar_no_scratch'] = [p for p in args.linkar_no_scratch.split(',') if p]
    if args.sem_testes and args.com_testes:
        raise SystemExit('--sem-testes e --com-testes juntos')
    if args.sem_testes:
        cfg['sem_testes_automatizados'] = True
    elif args.com_testes:
        cfg['sem_testes_automatizados'] = False
    else:
        cfg.setdefault('sem_testes_automatizados', False)
    # A branch do projeto é do projeto — nunca "a branch em que o repositório está agora".
    branch = args.branch or cfg.get('branch') or _branch_do_projeto(pasta)
    if not branch:
        raise SystemExit('branch do projeto desconhecida: sem --branch e sem "branch" no '
                         '.documentacao.json. Pergunte ao usuário; não use a branch atual do repositório')
    cfg['branch'] = branch
    if args.timeout:
        cfg['timeout'] = args.timeout
    estado['repos'][args.repo] = cfg
    C.salvar_estado(pasta, estado)
    print('repo %s configurado:' % args.repo)
    for k in sorted(cfg):
        print('  %-24s %s' % (k, cfg[k]))
    atual = C.branch_atual(caminho)
    if atual != cfg['branch']:
        print('  aviso: o repositório está em %r, e a branch do projeto é %r' % (atual, cfg['branch']))
    return 0


def _sem_m2(comando):
    return re.sub(r'\s+-Dmaven\.repo\.local=("[^"]*"|\'[^\']*\'|\S+)' , '', comando or '').strip()


def _branch_do_projeto(pasta):
    arq = os.path.join(pasta, '.documentacao.json')
    if os.path.exists(arq):
        import json
        with open(arq, encoding='utf-8') as fh:
            return json.load(fh).get('branch')
    return None


# ------------------------------------------------------------------------------ resultado

def retratar_relatorios(cwd, padrao_relatorios):
    """mtime (ns) de cada relatório antes da execução. Um relatório que continua igual depois dela
    é de outra execução: sem isso, o XML da rodada anterior (a seleção sem mutação, gravada
    menos de 1 s antes) era lido como resultado de uma execução que nem compilou."""
    retrato = {}
    if padrao_relatorios:
        for arq in map(os.path.normpath, glob.glob(os.path.join(cwd, padrao_relatorios))):
            try:
                retrato[arq] = os.stat(arq).st_mtime_ns
            except OSError:
                pass
    return retrato


def extrair_totais(cwd, padrao_relatorios, inicio_epoch, saida, antes=None):
    """(totais, por_classe) a partir dos XML do Surefire gerados pela execução, ou da saída.

    Com `antes` (o retrato_relatorios tirado antes de rodar), só conta o relatório novo ou
    reescrito. Sem ele, vale o mtime a partir de `inicio_epoch`, sem tolerância."""
    por_classe = {}
    if padrao_relatorios:
        for arq in map(os.path.normpath, glob.glob(os.path.join(cwd, padrao_relatorios))):
            try:
                if antes is not None:
                    if arq in antes and os.stat(arq).st_mtime_ns == antes[arq]:
                        continue
                elif os.path.getmtime(arq) < inicio_epoch:
                    continue
                raiz = ET.parse(arq).getroot()
            except (OSError, ET.ParseError):
                continue
            suites = [raiz] if raiz.tag == 'testsuite' else raiz.findall('testsuite')
            for s in suites:
                # Pelo nome qualificado: duas classes com o mesmo nome simples em pacotes diferentes
                # são duas entradas, e o total soma as duas (senão a homônima antiga sobrescreve a
                # nova, e um mutante morto é lido como vivo).
                nome = s.get('name') or re.sub(r'^TEST-|\.xml$', '', os.path.basename(arq))
                por_classe[nome] = {k: int(float(s.get(a, 0) or 0)) for k, a in
                                    (('run', 'tests'), ('falhas', 'failures'),
                                     ('erros', 'errors'), ('pulados', 'skipped'))}
    resumo = None
    if not por_classe:
        for ln in saida.splitlines():
            m = RE_SUREFIRE.search(ln)
            if not m:
                continue
            valores = {'run': int(m.group(1)), 'falhas': int(m.group(2)),
                       'erros': int(m.group(3)), 'pulados': int(m.group(4))}
            cauda = m.group(5)
            mi = re.search(r'\bin\s+([\w.$]+)\s*$', cauda)
            if mi:
                por_classe[mi.group(1)] = valores
            else:
                resumo = valores
    if por_classe:
        totais = {k: sum(v[k] for v in por_classe.values()) for k in ('run', 'falhas', 'erros', 'pulados')}
        return totais, por_classe
    return resumo, {}


def simples(classe):
    return classe.rsplit('.', 1)[-1]


def casa_classe(pedida, executada):
    """A classe que rodou (`executada`, qualificada como o Surefire a nomeia, ou só o nome simples
    em registros antigos e em relatórios que não trazem pacote) é a `pedida`: nome simples ou
    qualificado, com glob (`Foo*Test`, `a.b.*Test`)."""
    if '.' in pedida:
        if '.' in executada:
            return fnmatch.fnmatch(executada, pedida)
        return fnmatch.fnmatch(executada, simples(pedida))
    return fnmatch.fnmatch(simples(executada), pedida)


def homonimos(pedida, executadas):
    """Classes qualificadas distintas que um nome simples pedido casou (mais de uma = ambíguo)."""
    if '.' in pedida:
        return []
    achadas = sorted({e for e in executadas if '.' in e and casa_classe(pedida, e)})
    nomes = {simples(e) for e in achadas}
    return [e for e in achadas if sum(simples(x) == simples(e) for x in achadas) > 1] if len(nomes) < len(achadas) else []


# ------------------------------------------------------------------------------ testar

def montar_comando(cfg, classes, build, suite_inteira):
    if build:
        if not cfg.get('build'):
            raise SystemExit('repo sem comando de build configurado')
        return cfg['build']
    modelo = cfg.get('teste') or ''
    if not modelo:
        raise SystemExit('repo sem comando de teste configurado (`configurar --teste`)')
    if '{classes}' in modelo:
        if not classes:
            if not suite_inteira:
                raise SystemExit('seleção de classes vazia: a regra é rodar só as classes tocadas. '
                                 'Use --classes, ou --suite-inteira se foi isso que o usuário pediu.')
            return re.sub(r'\s*-Dtest=\{classes\}', '', modelo).replace('{classes}', '')
        return modelo.replace('{classes}', citar_argumento(','.join(classes)))
    if classes:
        raise SystemExit('o comando de teste deste repo não aceita seleção de classes ({classes})')
    return modelo


def testar(pasta, args):
    estado = C.carregar_estado(pasta)
    cfg = C.repo_cfg(estado, args.repo)
    onda = args.onda or C.onda_ativa(estado)
    classes = [c.strip() for c in (args.classes or '').split(',') if c.strip()]
    comando = montar_comando(cfg, classes, args.build, args.suite_inteira)
    import decisoes as DC
    erro_aut = DC.exigir_autorizacao_de_testes(estado, args.decisao)
    if erro_aut:
        raise SystemExit('recusado: ' + erro_aut)
    exigem = []
    suite_inteira = bool(args.suite_inteira and not classes)
    # Dentro de uma onda em execução, a suíte inteira (que o fechamento exige) fica coberta pela autorização
    # de testes do projeto. Fora de onda, ou sem a autorização, continua pedindo decisão.
    coberta = bool(onda and (estado['ondas'].get(onda) or {}).get('estado') == 'em_execucao'
                   and DC.autorizacao(estado, 'testes'))
    if suite_inteira and not coberta:
        exigem.append('--suite-inteira')
    preex = getattr(args, 'preexistentes', None)
    if preex:
        erro_p = DC.exigir(estado, preex, para='preexistentes', alvo=args.repo)
        if erro_p:
            raise SystemExit('recusado: --preexistentes é decisão do usuário — %s' % erro_p)
        if not suite_inteira:
            raise SystemExit('recusado: --preexistentes é da suíte inteira (`--suite-inteira`)')
        if (estado.get('falhas_preexistentes') or {}).get(args.repo):
            raise SystemExit('recusado: %s já tem a lista de falhas preexistentes (%s) — só a primeira falha da suíte '
                             'se registra; classe nova falhando é defeito, não preexistência'
                             % (args.repo, estado['falhas_preexistentes'][args.repo]['decisao']))
    if RE_D_BANCO.search(comando):
        exigem.append('comando com -D de banco')
    if exigem:
        import decisoes as DC
        erro_d = DC.exigir(estado, args.decisao, para='testar') if args.decisao else 'sem --decisao'
        if erro_d:
            raise SystemExit('recusado: %s — é decisão do usuário, a cada vez: --decisao D<n> (%s)'
                             % (' e '.join(exigem), erro_d))
    eid = C.atualizar(pasta, lambda e: C.proximo_id(e, 'E'))
    log = os.path.join(pasta, 'evidencias', 'testes', '%s-%s-%s.log'
                       % (eid, args.repo, time.strftime('%Y%m%d-%H%M%S')))
    fp_antes = C.fingerprint(cfg['caminho'])
    relatorios_antes = retratar_relatorios(cfg['caminho'], cfg.get('relatorios', ''))
    inicio_epoch = time.time()
    inicio = C.agora()
    print('rodando em %s:\n  %s' % (cfg['caminho'], comando))
    codigo, saida = C.rodar(comando, cfg['caminho'], log, timeout=args.timeout or cfg.get('timeout', 3600))
    fp_depois = C.fingerprint(cfg['caminho'])
    tipo = 'build' if args.build else 'teste'
    totais, por_classe = (None, {}) if args.build else extrair_totais(
        cfg['caminho'], cfg.get('relatorios', ''), inicio_epoch, saida, relatorios_antes)
    reg = {
        'id': eid, 'tipo': tipo, 'repo': args.repo, 'onda': onda, 'comando': comando,
        'classes': classes, 'suite_inteira': bool(args.suite_inteira and not classes),
        'inicio': inicio, 'fim': C.agora(), 'exit': codigo, 'totais': totais,
        'por_classe': por_classe, 'fingerprint': fp_antes, 'decisao': args.decisao,
        'intencao': getattr(args, 'intencao', None) or 'verde',
        'log': os.path.relpath(log, pasta),
    }
    avisos = []
    problemas = []
    if not C.mesmo_fp(fp_antes, fp_depois):
        # O próprio comando mexeu no que é rastreado (gerou arquivo fora do .gitignore?). A
        # evidência não descreve nenhum estado estável do código.
        problemas.append('o código mudou durante a execução (fingerprint antes ≠ depois)')
    if tipo == 'teste':
        if codigo != 0:
            problemas.append('exit %d' % codigo)
        if not totais:
            problemas.append('nenhuma contagem de testes encontrada (relatório ou saída) — %s' % _causa_sem_contagem(
                cfg, saida))
        elif totais['run'] == 0:
            problemas.append('nenhum teste rodou — seletor errado?')
        elif totais['falhas'] or totais['erros']:
            problemas.append('%d falha(s), %d erro(s)' % (totais['falhas'], totais['erros']))
        for pedida in classes:
            if not por_classe:
                problemas.append('sem contagem por classe — não há como provar que %s rodou' % pedida)
            elif not any(casa_classe(pedida, c) for c in por_classe):
                problemas.append('classe pedida não rodou: %s (nome errado?)' % pedida)
            elif homonimos(pedida, por_classe):
                avisos.append('%s casou classes homônimas (%s): o resultado soma todas; para uma só, '
                              'peça o nome qualificado' % (pedida, ', '.join(homonimos(pedida, por_classe))))
    elif codigo != 0:
        problemas.append('build com exit %d' % codigo)
    reg['ok'] = not problemas
    reg['problemas'] = problemas
    reg['avisos'] = avisos
    registrou_preex = []

    def _gravar(e):
        e['execucoes'].append(reg)
        _marcar_inicio_das_tarefas(e, pasta, onda, args.repo, classes, inicio)
        if preex and suite_inteira and not reg['ok'] and so_falhas_de_teste(reg):
            e.setdefault('falhas_preexistentes', {})[args.repo] = {
                'classes': classes_falhando(reg), 'decisao': preex, 'execucao': eid, 'em': C.agora()}
            registrou_preex.extend(classes_falhando(reg))
    C.atualizar(pasta, _gravar)

    print()
    print('%s  %s  %s  onda=%s  intenção=%s  fingerprint=%s' % (eid, args.repo, tipo, onda or '—', reg['intencao'],
                                                              fp_antes['assinatura']))
    if totais:
        print('  testes: %(run)d rodados, %(falhas)d falhas, %(erros)d erros, %(pulados)d pulados' % totais)
    print('  log: %s' % reg['log'])
    for a_ in avisos:
        print('  aviso: ' + a_)
    print('  resultado: %s' % ('OK' if reg['ok'] else 'FALHOU — ' + '; '.join(problemas)))
    if registrou_preex:
        print('  falhas preexistentes de %s registradas (%s): %s — o fechamento aceita falha só dentro desta lista'
              % (args.repo, preex, ', '.join(registrou_preex)))
    elif preex and reg['ok']:
        print('  aviso: a suíte passou — --preexistentes não registrou nada')
    elif preex:
        print('  aviso: --preexistentes só registra falha de teste contada por classe; esta execução falhou por outro motivo')
    elif suite_inteira and not reg['ok'] and so_falhas_de_teste(reg) and not (estado.get('falhas_preexistentes') or {}).get(args.repo):
        print('  a suíte inteira falhou pela primeira vez em %s. Se as classes que falham já falhavam antes da demanda, '
              'o usuário decide: `testar --suite-inteira --preexistentes D<n>`' % args.repo)
    return 0 if reg['ok'] else 1


def _marcar_inicio_das_tarefas(e, pasta, onda, repo, classes, inicio):
    """O primeiro `testar` que roda classes do campo **Teste** de uma tarefa sem commit marca o `inicio` dela —
    é o único instante de implementação que o estado passa a ter (o commit marca o fim). Só alimenta as métricas."""
    eo = e['ondas'].get(onda) if onda else None
    if not eo or eo.get('estado') != 'em_execucao' or not classes:
        return
    try:
        import plano as P
        o = P.Plano(C.arquivo_plano(pasta)).onda(onda)
    except Exception:
        return
    for tid, t in ((o or {}).get('tarefas') or {}).items():
        if P.repo_de(t) != repo or not P.teste_automatizado(t):
            continue
        registro = eo.setdefault('tarefas', {}).get(tid) or {}
        if registro.get('commits') or registro.get('inicio'):
            continue
        pedidas = P.classes_de_teste(t)
        if pedidas and any(casa_classe(pc, c) for pc in pedidas for c in classes):
            eo['tarefas'].setdefault(tid, {'commits': []})['inicio'] = inicio


def _causa_sem_contagem(cfg, saida):
    """Causa provável de o runner sair sem relatório: em geral, spec que não compilou ou seleção que não casou
    spec — o gate recusa, e a mensagem diz por quê."""
    if re.search(r'(não gravou o JUnit|did not (write|produce).*(junit|report))', saida or '', re.IGNORECASE):
        return 'o runner avisou que não gravou o relatório (spec que não compilou?) — veja o fim do log'
    if cfg.get('relatorios'):
        return ('spec não compilou ou a seleção não casou nenhum spec — o relatório %s não foi gerado; veja o fim do log'
                % cfg['relatorios'])
    return 'spec não compilou ou a seleção não casou nenhum spec — o runner não imprimiu a contagem; veja o fim do log'


def classes_falhando(e):
    """Classes com falha ou erro numa execução (como o relatório as nomeia)."""
    return sorted(c for c, v in (e.get('por_classe') or {}).items() if v.get('falhas') or v.get('erros'))


def so_falhas_de_teste(e):
    """A execução falhou só porque teste falhou (exit ≠ 0 e falhas/erros contados por classe): sem relatório
    ausente, sem seleção errada, sem código mudado durante a execução."""
    if e.get('ok') or e.get('tipo') != 'teste' or not classes_falhando(e):
        return False
    return all(p.startswith('exit ') or 'falha(s)' in p for p in (e.get('problemas') or []))


def suite_inteira_aceita(estado, e):
    """A suíte inteira `e` falhou, mas só em classes que o usuário já aceitou como preexistentes do repo."""
    if not e.get('suite_inteira') or not so_falhas_de_teste(e):
        return False
    pre = (estado.get('falhas_preexistentes') or {}).get(e['repo'])
    return bool(pre) and set(classes_falhando(e)) <= set(pre['classes'])


def evidencia(pasta, args):
    """Registra evidência manual (roteiro de tela, print, planilha) amarrada ao código atual."""
    estado = C.carregar_estado(pasta)
    cfg = C.repo_cfg(estado, args.repo)
    arq = args.arquivo if os.path.isabs(args.arquivo) else os.path.join(pasta, args.arquivo)
    arq = os.path.abspath(arq)
    if not os.path.exists(arq):
        raise SystemExit('arquivo de evidência não existe: %s' % arq)
    if not arq.startswith(os.path.abspath(pasta) + os.sep):
        raise SystemExit('a evidência tem de estar dentro da pasta do projeto: %s' % arq)
    if not arq.endswith('.md') or not os.path.isfile(arq):
        raise SystemExit('o roteiro é um .md com a tabela de passos (Esperado | Obtido | Evidência)')
    texto = C.ler(arq)
    erro = conferir_roteiro(texto, pasta=pasta)
    if erro:
        raise SystemExit('roteiro recusado: ' + erro)
    fp = C.fingerprint(cfg['caminho'])
    declarado = re.search(r'C[óo]digo:\**\s*`?([0-9a-f]{6,40})`?', texto)
    if not declarado:
        raise SystemExit('roteiro recusado: sem a linha "Código: <assinatura>" no cabeçalho. Rode '
                         '`estado fingerprint --repo %s` antes de executar o roteiro e copie a linha: '
                         'é ela que prova sobre qual código ele rodou' % args.repo)
    if declarado.group(1) != fp['assinatura']:
        raise SystemExit('roteiro recusado: ele declara o código %s, e o código atual de %s é %s — o '
                         'roteiro rodou sobre outro código. Execute-o de novo, num arquivo novo'
                         % (declarado.group(1), args.repo, fp['assinatura']))
    sha = C.sha1_arquivo(arq)
    repetida = [e['id'] for e in estado['execucoes'] if e.get('sha1') == sha]
    if repetida:
        raise SystemExit('roteiro recusado: este mesmo arquivo já foi registrado (%s). Execução nova é '
                         'arquivo novo, com o Código atual no cabeçalho' % ', '.join(repetida))
    eid = C.proximo_id(estado, 'E')
    reg = {'id': eid, 'tipo': args.tipo, 'repo': args.repo,
           'onda': args.onda or C.onda_ativa(estado), 'arquivo': os.path.relpath(arq, pasta),
           'arquivo_abs': arq,
           'sha1': sha, 'descricao': args.descricao or '', 'inicio': C.agora(), 'fim': C.agora(),
           'exit': 0, 'fingerprint': fp, 'ok': True, 'problemas': []}
    # os aceites que o roteiro diz provar e as evidências que ele cita, seladas: o fechamento confere a
    # cobertura e `vigente` perde o roteiro se um desses arquivos mudar depois
    reg['aceites'], reg['evidencias'] = dados_do_roteiro(texto, pasta)
    estado['execucoes'].append(reg)
    C.salvar_estado(pasta, estado)
    print('%s registrada: %s %s (%s), fingerprint %s'
          % (eid, args.tipo, reg['arquivo'], args.repo, reg['fingerprint']['assinatura']))
    return 0


# "Obtido" que não diz o que se obteve: vale para qualquer passo, e o roteiro estrito o recusa.
OBTIDO_TRIVIAL = {'ok', 'okay', 'passou', 'sim', 'certo', 'correto', 'conforme', 'funcionou', 'feito', 'igual',
                  'confere', 'bateu', 'de acordo'}
RE_ARQUIVO_EVIDENCIA = re.compile(r'[\w./-]+\.(?:png|jpe?g|gif|webp|log|md|txt|json|csv|pdf|html|xlsx|har)\b', re.IGNORECASE)


def _tabelas_do_roteiro(texto):
    """[(cabeçalho normalizado, [(nº da linha, [células])])] de cada tabela que tem a coluna Obtido."""
    linhas_md = texto.splitlines()
    saida = []
    for i, ln in enumerate(linhas_md):
        s = ln.strip()
        if not s.startswith('|') or i + 1 >= len(linhas_md) or not re.match(r'^\|[\s:|-]+\|$', linhas_md[i + 1].strip()):
            continue
        cab = [C.chave(c) for c in s.strip('|').split('|')]
        if 'obtido' not in cab:
            continue
        passos = []
        for j in range(i + 2, len(linhas_md)):
            corpo = linhas_md[j].strip()
            if not corpo.startswith('|'):
                break
            passos.append((j + 1, [c.strip() for c in corpo.strip('|').split('|')]))
        saida.append((cab, passos))
    return saida


def _arquivos_da_evidencia(celula, pasta):
    """Os arquivos que a célula Evidência cita, como caminho absoluto dentro de `evidencias/` do projeto."""
    base = os.path.join(os.path.abspath(pasta), 'evidencias') + os.sep
    return [os.path.normpath(os.path.join(pasta, m.group(0))) for m in RE_ARQUIVO_EVIDENCIA.finditer(celula)], base


def conferir_roteiro(texto, pasta=None):
    """Roteiro vale como evidência se cada passo diz o que se obteve. Esperado sem obtido é
    plano de teste, não teste. A tabela tem passos, o Obtido diz algo além de "ok",
    a coluna Evidência cita arquivo que existe em `evidencias/` do projeto e a coluna Aceite diz qual
    aceite o passo prova (o fechamento confere que todo aceite com gate roteiro tem passo)."""
    tabelas = _tabelas_do_roteiro(texto)
    if not tabelas:
        return 'nenhuma tabela com a coluna "Obtido"'
    for cab, passos in tabelas:
        if not passos:
            return 'a tabela do roteiro não tem nenhum passo — cabeçalho sem linhas não é execução'
        col = cab.index('obtido')
        esperado = cab.index('esperado') if 'esperado' in cab else None
        faltam = [n for n in ('evidencia', 'aceite') if n not in cab]
        if faltam:
            return ('roteiro: faltam as colunas %s (| Passo | Esperado | Obtido | Evidência | Aceite |)'
                    % ', '.join('"%s"' % {'evidencia': 'Evidência', 'aceite': 'Aceite'}[n] for n in faltam))
        for num, cel in passos:
            valor = cel[col] if col < len(cel) else ''
            if not valor or valor in ('-', '—', '…', '...') or re.match(r'^<.*>$', valor):
                return 'linha %d sem Obtido preenchido' % num
            if re.match(r'^(pendente|a fazer|a executar|todo|tbd|\?+|nao executado|n/?a)\b', C.chave(valor.strip('*_ '))):
                # "pendente" não é o que se obteve
                return 'linha %d com Obtido %r — passo não executado' % (num, valor)
            obtido = C.chave(valor.strip('*_ .!'))
            if obtido in OBTIDO_TRIVIAL or (esperado is not None and esperado < len(cel)
                                            and obtido and obtido == C.chave(cel[esperado].strip('*_ .!'))):
                return ('linha %d com Obtido %r — diga o que se obteve (valor, mensagem, tela), não que "passou" '
                        'nem o próprio Esperado copiado' % (num, valor))
            aceites = C.RE_ACEITE.findall(cel[cab.index('aceite')] if cab.index('aceite') < len(cel) else '')
            if not aceites:
                return 'linha %d sem Aceite: diga qual aceite (A<onda>.<k>) o passo prova' % num
            arquivos, base = _arquivos_da_evidencia(cel[cab.index('evidencia')] if cab.index('evidencia') < len(cel) else '',
                                                    pasta or '.')
            if not arquivos:
                return 'linha %d sem Evidência: cite o arquivo (captura, log, resposta) em evidencias/' % num
            for arq in arquivos:
                if not arq.startswith(base) or not os.path.isfile(arq):
                    return 'linha %d: a evidência %s não existe em evidencias/ do projeto' % (num, os.path.relpath(arq, pasta or '.'))
    return None


def dados_do_roteiro(texto, pasta):
    """(aceites provados, {arquivo de evidência: sha1}) de um roteiro estrito já conferido."""
    aceites, evidencias = set(), {}
    for cab, passos in _tabelas_do_roteiro(texto):
        for _, cel in passos:
            if 'aceite' in cab and cab.index('aceite') < len(cel):
                aceites.update(m.group(0) for m in C.RE_ACEITE.finditer(cel[cab.index('aceite')]))
            if 'evidencia' in cab and cab.index('evidencia') < len(cel):
                for arq in _arquivos_da_evidencia(cel[cab.index('evidencia')], pasta)[0]:
                    if os.path.isfile(arq):
                        evidencias[arq] = C.sha1_arquivo(arq)
    return sorted(aceites), evidencias


# ------------------------------------------------------------------------------ consultas

def vigente(e):
    """Execução que conta: não anulada e, se for roteiro, com o arquivo ainda igual ao registrado
    (antes nada reconferia o arquivo depois do registro)."""
    if e.get('anulada'):
        return False
    if e.get('tipo') == 'roteiro' and e.get('arquivo_abs') and e.get('sha1'):
        try:
            if os.path.isdir(e['arquivo_abs']) or C.sha1_arquivo(e['arquivo_abs']) != e['sha1']:
                return False
            for arq, sha in (e.get('evidencias') or {}).items():
                if os.path.isdir(arq) or C.sha1_arquivo(arq) != sha:
                    return False
        except OSError:
            return False
    return True


def execucoes_frescas(estado, repo, fp_atual, tipo=None):
    """Execuções OK, vigentes, cujo fingerprint é o atual do repositório."""
    return [e for e in estado['execucoes']
            if e['repo'] == repo and e.get('ok') and vigente(e) and C.mesmo_fp(e.get('fingerprint'), fp_atual)
            and (tipo is None or e['tipo'] == tipo)]


def anular(pasta, args):
    """Anula uma execução registrada por engano. Nunca apaga: ela fica, marcada, com a decisão."""
    import decisoes as DC
    estado = C.carregar_estado(pasta)
    e = next((x for x in estado['execucoes'] if x['id'].lower() == args.id.lower()), None)
    if not e:
        raise SystemExit('execução %s não existe' % args.id)
    if e.get('anulada'):
        raise SystemExit('%s já foi anulada (%s)' % (e['id'], e['anulada']['decisao']))
    if len((args.motivo or '').strip()) < 15:
        raise SystemExit('motivo curto demais: diga por que a execução não vale')
    erro_d = DC.exigir(estado, args.decisao, para='anular', alvo=e['id'])
    if erro_d:
        raise SystemExit('recusado: anular evidência é decisão do usuário — %s' % erro_d)
    e['anulada'] = {'decisao': args.decisao, 'motivo': args.motivo.strip(), 'em': C.agora()}
    C.salvar_estado(pasta, estado)
    print('%s anulada (%s): %s' % (e['id'], args.decisao, args.motivo.strip()))
    return 0


def classes_executadas(execucoes):
    """Só o que o relatório diz que rodou. A seleção pedida não conta: `-Dtest=FooTest,BarTest`
    com `failIfNoTests=false` roda FooTest e fica quieto se BarTest não existir."""
    nomes = set()
    for e in execucoes:
        nomes.update(e.get('por_classe', {}).keys())
    return nomes
