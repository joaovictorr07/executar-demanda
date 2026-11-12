#!/usr/bin/env python3
"""Gate de padrão: o que o AGENTS.md pede e um script consegue conferir sobre o diff.

Quatro regras, só sobre as linhas ACRESCENTADAS (linha antiga fora do padrão não é da tarefa):

  eol         o arquivo mantém o fim de linha que já tinha; arquivo novo segue a maioria dos irmãos da
              pasta e extensão; arquivo com EOL misto pede decisão
  colunas     linha adicionada acima do limite (120)
  comentario  TODO/FIXME/HACK em comentário (erro); comentário sobre a própria mudança (aviso). XXX fica de
              fora: é máscara de documento em comentário (XXX.XXX.XXX-XX)
  import      import adicionado e sem uso no arquivo (aviso)

O campo `padrao` do repositório liga o gate (sem ele nada muda). `configurar --padrao <preset>` o
preenche; afrouxar ou desligar regra, e `--lint`, são decisão do usuário. A dispensa é por regra e por
commit: `--sem-padrao regra=D<n>` (também `lint=D<n>`).

Lê o diff em bytes: `C.git` faz strip/splitlines e perde o CR, que é justamente o que se confere.
"""
import copy
import os
import re
import shutil
import tempfile
from collections import Counter

import comum as C

REGRAS = ('eol', 'colunas', 'comentario', 'import')
# `lint` não se desliga por regra (tira-se o `--lint`, com decisão), mas se dispensa num commit.
DISPENSAVEIS = REGRAS + ('lint',)

# Os presets são o ponto de partida; o repositório pode afrouxar com decisão do usuário.
# `sem_colunas`: o AGENTS.md pede 120, mas o template HTML do legado passa disso em dezenas de linhas por
# página (medido no web-logus-gestor-loja: 25 a 51 por arquivo); a regra ali só geraria ruído.
PRESETS = {
    'maven': {
        'eol': 'preservar', 'colunas': 120, 'comentario': 'bloquear', 'import_sem_uso': 'avisar',
        'extensoes': ['.java', '.js', '.html', '.css'],
        'sem_colunas': ['.html'],
    },
    'angular': {
        'eol': 'preservar', 'colunas': 120, 'comentario': 'bloquear', 'import_sem_uso': 'avisar',
        'extensoes': ['.ts', '.js', '.html', '.scss', '.css'],
        'sem_colunas': ['.html'],
    },
}

# Código de terceiros e gerado não é do autor da tarefa.
RE_FORA = re.compile(r'(^|/)(node_modules|vendor|lib|dist|target)/|\.min\.(js|css)$')

RE_COMENTARIO_TODO = re.compile(r'(?:/\*|//|<!--|^\s*\*|^\s*#)[^\n]*?\b(TODO|FIXME|HACK)\b')
RE_COMENTARIO_MUDANCA = re.compile(
    r'(?:/\*|//|<!--|^\s*\*)[^\n]*?(?:'
    r'\b(?:criad[oa]|alterad[oa]|modificad[oa]|adicionad[oa]|inclu[ií]d[oa]|ajustad[oa])\s+(?:em|por|para|na|no)\b'
    r'|\b(?:ticket|chamado|demanda|projeto|T)\s*[-#:]?\s*\d{3,}\b)', re.IGNORECASE)
RE_IMPORT_JAVA = re.compile(r'^\s*import\s+(?:static\s+)?[\w.]+\.(\w+)\s*;')
RE_IMPORT_TS = re.compile(r'^\s*import\s+(?!type\b)(.+?)\s+from\s+[\'"]')
RE_HUNK = re.compile(rb'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')


# ------------------------------------------------------------------------------ configuração

def _limite(colunas):
    """Limite de colunas comparável: 0 (ou ausente) é "sem limite", o mais frouxo de todos."""
    return colunas if colunas and colunas > 0 else float('inf')


def afrouxa(atual, novo):
    """True se `novo` pede menos do que `atual` (regra desligada, limite maior, bloqueio que vira aviso)."""
    if not atual:
        return False
    if not novo:
        return True
    if novo.get('eol') != 'preservar' and atual.get('eol') == 'preservar':
        return True
    if _limite(novo.get('colunas')) > _limite(atual.get('colunas')):
        return True
    ordem = {'bloquear': 2, 'avisar': 1, 'desligado': 0}
    for campo in ('comentario', 'import_sem_uso'):
        if ordem.get(novo.get(campo), 0) < ordem.get(atual.get(campo), 0):
            return True
    return False


def configurar(atual, preset, desligar, colunas, lint):
    """Devolve (novo_padrao, exigem): `exigem` lista o que só o usuário decide (afrouxar, `--lint`)."""
    exigem = []
    novo = copy.deepcopy(atual) if atual else None
    if preset == 'nenhum':
        if atual:
            exigem.append('--padrao nenhum (desliga o gate de padrão do repositório)')
        novo = None
    elif preset:
        novo = copy.deepcopy(PRESETS[preset])
        novo['preset'] = preset
        if atual and atual.get('lint'):
            novo['lint'] = atual['lint']
        if afrouxa(atual, novo):
            exigem.append('--padrao %s afrouxa o padrão já configurado' % preset)
    if desligar or colunas is not None or lint is not None:
        if novo is None:
            raise SystemExit('--padrao-desligar, --padrao-colunas e --lint precisam de um padrão: '
                             'configure primeiro com --padrao maven|angular')
    if desligar:
        for regra in [r.strip() for r in desligar.split(',') if r.strip()]:
            if regra not in REGRAS:
                raise SystemExit('regra de padrão desconhecida: %s (%s)' % (regra, ', '.join(REGRAS)))
            if regra == 'eol':
                novo['eol'] = 'desligado'
            elif regra == 'colunas':
                novo['colunas'] = 0
            elif regra == 'comentario':
                novo['comentario'] = 'desligado'
            else:
                novo['import_sem_uso'] = 'desligado'
            exigem.append('--padrao-desligar %s' % regra)
    if colunas is not None:
        if colunas < 0:
            raise SystemExit('--padrao-colunas %d: o limite é um número positivo (0 desliga a regra, com decisão)' % colunas)
        if _limite(colunas) > _limite(novo.get('colunas')):
            exigem.append('--padrao-colunas %d %s' % (colunas, 'desliga o limite' if not colunas else 'acima do limite atual'))
        novo['colunas'] = colunas
    if lint is not None:
        if (lint or None) != novo.get('lint'):
            exigem.append('--lint (o comando decide o que "passa")')
        novo['lint'] = lint or None
    return novo, exigem


# ------------------------------------------------------------------------------ dispensa

def dispensas(estado, itens, rel):
    """['eol=D3', 'colunas=D3'] -> {'eol': 'D3', 'colunas': 'D3'}, conferindo regra e decisão."""
    import decisoes as DC
    saida = {}
    for item in itens or []:
        regra, _, did = (item or '').partition('=')
        regra, did = regra.strip(), did.strip()
        if regra not in DISPENSAVEIS or not did:
            rel.erro('--sem-padrao %r: use regra=D<n>, com regra em %s' % (item, ', '.join(DISPENSAVEIS)))
            continue
        erro_d = DC.exigir(estado, did, para='sem-padrao', alvo=regra)
        if erro_d:
            rel.erro('--sem-padrao %s: %s' % (regra, erro_d))
            continue
        saida[regra] = did
    return saida


def registrar(onda, tarefa, usadas, onde, repo=None):
    """Grava na onda a dispensa que foi de fato usada, com os arquivos em que valeu, para o fechamento e o
    parecer citarem. `usadas`: {regra: {'decisao', 'arquivos'}}, o que `conferir` devolve."""
    for regra, u in sorted(usadas.items()):
        onda.setdefault('padrao_dispensado', []).append(
            {'regra': regra, 'decisao': u['decisao'], 'arquivos': list(u.get('arquivos') or []), 'repo': repo,
             'tarefa': tarefa, 'em': C.agora(), 'onde': onde})


def dispensadas_da_onda(onda, extras=None, repo=None):
    """O que o fechamento dispensa no diff da onda: a regra **no arquivo** em que um commit a dispensou
    ({(regra, arquivo): D<n>}) — a dispensa de um commit não cobre o resto da onda. Registro anterior, sem
    `arquivos`, vale para a regra inteira; `extras` (o `--sem-padrao` do próprio fechamento) também."""
    d = {}
    for x in (onda or {}).get('padrao_dispensado', []):
        if repo and x.get('repo') and x['repo'] != repo:
            continue
        if x.get('arquivos') is None:
            d[x['regra']] = x['decisao']
        else:
            d.update({(x['regra'], f): x['decisao'] for f in x['arquivos']})
    d.update(extras or {})
    return d


# ------------------------------------------------------------------------------ leitura do diff

def ler_diff(bruto):
    """Lista de arquivos do diff: {path, antigo, novo, removido, binario, linhas[(n, bytes, sem_eol)]}."""
    arquivos = []
    atual = None
    em_hunk = False
    n = 0
    ultima = None  # tipo da última linha do trecho: o "\\ No newline" vale para ela, e só importa se foi `+`
    for ln in bruto.split(b'\n'):
        if ln.startswith(b'diff --git '):
            atual = {'path': None, 'antigo': None, 'novo': False, 'removido': False, 'binario': False,
                     'linhas': []}
            arquivos.append(atual)
            em_hunk = False
            ultima = None
            continue
        if atual is None:
            continue
        if not em_hunk:
            if ln.startswith(b'new file mode'):
                atual['novo'] = True
            elif ln.startswith(b'deleted file mode'):
                atual['removido'] = True
            elif ln.startswith(b'rename from '):
                atual['antigo'] = ln[12:].decode('utf-8', 'surrogateescape')
            elif ln.startswith(b'Binary files ') or ln.startswith(b'GIT binary patch'):
                atual['binario'] = True
            elif ln.startswith(b'--- a/') and atual['antigo'] is None:
                atual['antigo'] = ln[6:].split(b'\t')[0].decode('utf-8', 'surrogateescape')
            elif ln.startswith(b'+++ b/'):
                atual['path'] = ln[6:].split(b'\t')[0].decode('utf-8', 'surrogateescape')
            else:
                m = RE_HUNK.match(ln)
                if m:
                    em_hunk = True
                    n = int(m.group(1))
            if not em_hunk:
                continue
            if RE_HUNK.match(ln):
                continue
        m = RE_HUNK.match(ln)
        if m:
            n = int(m.group(1))
            ultima = None
        elif ln.startswith(b'+'):
            atual['linhas'].append((n, ln[1:], False))
            n += 1
            ultima = '+'
        elif ln.startswith(b'\\'):
            if ultima == '+':
                num, texto, _ = atual['linhas'][-1]
                atual['linhas'][-1] = (num, texto, True)
        elif ln.startswith(b' '):
            n += 1
            ultima = ' '
        elif ln.startswith(b'-'):
            ultima = '-'
    return [a for a in arquivos if a['path'] and a['linhas'] and not a['binario'] and not a['removido']]


def _blob(real, rev, path):
    """Conteúdo do arquivo na revisão (`rev` vazio é o índice). None se não existe lá."""
    spec = '%s:%s' % (rev, path)
    if not C.git_ok(real, 'cat-file', '-e', spec):
        return None
    return C.git(real, 'show', spec, bruto=True, checar=False)


def _eol_do_conteudo(conteudo):
    crlf = conteudo.count(b'\r\n')
    lf = conteudo.count(b'\n') - crlf
    if not crlf and not lf:
        return None
    if crlf and lf:
        return 'misto'
    return 'crlf' if crlf else 'lf'


def _eol_dos_irmaos(real, path, ignorar):
    """EOL da maioria dos arquivos rastreados na mesma pasta e extensão; None se não há maioria."""
    pasta, ext = os.path.dirname(path), os.path.splitext(path)[1]
    saida = C.git(real, 'ls-files', '--eol', '-z', '--', pasta or '.', bruto=True, checar=False)
    cont = Counter()
    for reg in saida.split(b'\0'):
        meta, _, cam = reg.partition(b'\t')
        cam = cam.decode('utf-8', 'surrogateescape')
        if not cam or cam in ignorar or os.path.dirname(cam) != pasta or os.path.splitext(cam)[1] != ext:
            continue
        estado = meta.split()[0] if meta.split() else b''
        if estado == b'i/crlf':
            cont['crlf'] += 1
        elif estado == b'i/lf':
            cont['lf'] += 1
    if cont['crlf'] == cont['lf']:
        return None
    return 'crlf' if cont['crlf'] > cont['lf'] else 'lf'


# ------------------------------------------------------------------------------ regras

def _texto(linha):
    return linha.rstrip(b'\r').decode('utf-8', 'replace')


def _nomes_importados_ts(spec):
    nomes = []
    spec = spec.strip()
    if spec.startswith('*'):
        m = re.match(r'\*\s+as\s+(\w+)', spec)
        return [m.group(1)] if m else []
    m = re.match(r'^(\w+)\s*,?\s*(.*)$', spec)
    if m and not spec.startswith('{'):
        nomes.append(m.group(1))
        spec = m.group(2)
    m = re.search(r'\{([^}]*)\}', spec)
    if m:
        for parte in m.group(1).split(','):
            parte = parte.strip()
            if not parte:
                continue
            nomes.append(re.split(r'\s+as\s+', parte)[-1].strip())
    return nomes


def _sem_imports(texto):
    return '\n'.join(l for l in texto.splitlines() if not re.match(r'^\s*(import|package)\b', l))


def conferir(real, diff, rev_base, rev_fim, padrao, dispensadas, rel, excluir=()):
    """Aplica as regras de `padrao` às linhas acrescentadas de `diff` (bytes).

    `rev_base`: onde está o conteúdo antes da mudança (None = tudo é arquivo novo); `rev_fim`: onde
    está o depois (vazio é o índice). Erros e avisos vão para `rel`. A regra dispensada vira aviso e
    volta em `usadas` ({regra: {'decisao', 'arquivos'}}) para o chamador registrar. `dispensadas` tem a regra
    inteira ({regra: D<n>}) ou a regra num arquivo ({(regra, arquivo): D<n>}).
    """
    usadas = {}
    if not padrao:
        return usadas
    extensoes = set(padrao.get('extensoes') or [])
    arquivos = ler_diff(diff)
    novos = {a['path'] for a in arquivos if a['novo'] or (rev_base and _blob(real, rev_base, a['antigo'] or a['path']) is None)}

    def falha(regra, msg, bloqueia=True):
        did = dispensadas.get((regra, path)) or dispensadas.get(regra)
        if did:
            u = usadas.setdefault(regra, {'decisao': did, 'arquivos': []})
            if path not in u['arquivos']:
                u['arquivos'].append(path)
            rel.aviso('padrão (%s) dispensado por %s: %s' % (regra, did, msg))
        elif bloqueia:
            rel.erro('padrão (%s): %s' % (regra, msg))
        else:
            rel.aviso('padrão (%s): %s' % (regra, msg))

    for a in arquivos:
        path = a['path']
        if C._excluido(path, tuple(excluir) + C.EXCLUIR_PADRAO) or RE_FORA.search(path):
            continue
        ext = os.path.splitext(path)[1]
        linhas = a['linhas']

        # --- fim de linha
        if padrao.get('eol') == 'preservar':
            esperado = None
            origem = ''
            base_conteudo = None if (a['novo'] or not rev_base) else _blob(real, rev_base, a['antigo'] or path)
            if base_conteudo is not None:
                esperado = _eol_do_conteudo(base_conteudo)
                origem = 'o arquivo já tem'
            if esperado is None and (a['novo'] or base_conteudo is None or not base_conteudo):
                esperado = _eol_dos_irmaos(real, path, novos)
                origem = 'a maioria dos arquivos %s da pasta tem' % (ext or 'sem extensão')
                if esperado is None:
                    rel.aviso('padrão (eol): %s é arquivo novo e a pasta não tem maioria de EOL — não conferido' % path)
            if esperado == 'misto':
                falha('eol', '%s tem EOL misto no repositório (CRLF e LF); mexer nele exige decisão do usuário '
                      '(`--sem-padrao eol=D<n>`)' % path)
            elif esperado:
                erradas = [num for num, texto, sem_eol in linhas
                           if not sem_eol and (texto.endswith(b'\r') != (esperado == 'crlf'))]
                if erradas:
                    dica = ''
                    if a['novo'] and esperado == 'crlf':
                        dica = (' — com core.autocrlf=input o `git add` de arquivo novo grava LF; para guardar CRLF: '
                                '`git -c core.autocrlf=false add %s`' % path)
                    falha('eol', '%s: %d linha(s) adicionada(s) com %s, e %s %s (linhas %s)%s'
                          % (path, len(erradas), 'LF' if esperado == 'crlf' else 'CRLF', origem, esperado.upper(),
                             ', '.join(str(n) for n in erradas[:5]) + ('…' if len(erradas) > 5 else ''), dica))

        if ext not in extensoes:
            continue

        # --- colunas
        limite = padrao.get('colunas') or 0
        if limite and ext not in (padrao.get('sem_colunas') or ()):
            longas = [(num, len(_texto(texto))) for num, texto, _ in linhas if len(_texto(texto)) > limite]
            if longas:
                falha('colunas', '%s: %d linha(s) adicionada(s) acima de %d colunas (linha %d tem %d%s)'
                      % (path, len(longas), limite, longas[0][0], longas[0][1],
                         '; outras: ' + ', '.join(str(n) for n, _ in longas[1:4]) if len(longas) > 1 else ''))

        # --- comentário
        if padrao.get('comentario') in ('bloquear', 'avisar'):
            for num, texto, _ in linhas:
                t = _texto(texto)
                m = RE_COMENTARIO_TODO.search(t)
                if m:
                    falha('comentario', '%s:%d %s em comentário: %s' % (path, num, m.group(1), t.strip()[:80]),
                          padrao.get('comentario') == 'bloquear')
                elif RE_COMENTARIO_MUDANCA.search(t):
                    falha('comentario', '%s:%d comentário sobre a própria mudança (AGENTS.md): %s'
                          % (path, num, t.strip()[:80]), False)

        # --- import sem uso
        if padrao.get('import_sem_uso') in ('avisar', 'bloquear'):
            conteudo = _blob(real, rev_fim, path)
            if conteudo is None:
                continue
            corpo = _sem_imports(conteudo.decode('utf-8', 'replace'))
            for num, texto, _ in linhas:
                t = _texto(texto)
                nomes = []
                if ext == '.java':
                    m = RE_IMPORT_JAVA.match(t)
                    nomes = [m.group(1)] if m else []
                elif ext in ('.ts', '.js'):
                    m = RE_IMPORT_TS.match(t)
                    nomes = _nomes_importados_ts(m.group(1)) if m else []
                for nome in nomes:
                    if not re.search(r'\b%s\b' % re.escape(nome), corpo):
                        falha('import', '%s:%d import sem uso: %s' % (path, num, nome),
                              padrao.get('import_sem_uso') == 'bloquear')
    return usadas


# ------------------------------------------------------------------------------ pontos de entrada

def _git_diff(real, *args):
    return C.git(real, '-c', 'core.quotepath=false', *args, bruto=True)


def do_indice(real, padrao, dispensadas, rel, excluir=()):
    """O que vai no commit: o índice contra o HEAD."""
    diff = _git_diff(real, 'diff', '--cached', '-U0', '--no-color', '-M')
    return conferir(real, diff, 'HEAD', '', padrao, dispensadas, rel, excluir)


def do_commit(real, h, padrao, dispensadas, rel, excluir=()):
    """Commit já feito (vincular)."""
    diff = _git_diff(real, 'show', '-U0', '--no-color', '-M', '--format=', h)
    pai = h + '^' if C.git_ok(real, 'rev-parse', '--verify', '-q', h + '^') else None
    return conferir(real, diff, pai, h, padrao, dispensadas, rel, excluir)


def da_onda(real, base, padrao, dispensadas, rel, excluir=()):
    """Tudo que a onda entregou: base..HEAD."""
    diff = _git_diff(real, 'diff', '-U0', '--no-color', '-M', base, 'HEAD')
    return conferir(real, diff, base, 'HEAD', padrao, dispensadas, rel, excluir)


def rodar_lint(padrao, real, rel, dispensadas=None, modo='fechamento', h=None):
    """`--lint` do repositório, quando há: exit diferente de zero é erro. Devolve a dispensa usada
    ({'lint': {...}}) ou {}.

    O lint roda no working tree, então só prova o que está nele: no `commit`, alteração fora do índice
    (o commit leva o índice) é erro; no `vincular`, só o HEAD com a árvore limpa é conferível. No
    fechamento o diff da onda já é o HEAD, e a alteração não commitada tem o aviso do fingerprint."""
    cmd = (padrao or {}).get('lint')
    if not cmd:
        return {}
    did = (dispensadas or {}).get('lint')
    if did:
        rel.aviso('lint (%s) dispensado por %s' % (cmd, did))
        return {'lint': {'decisao': did, 'arquivos': []}}
    if modo == 'commit':
        soltos = [f for f in C.git(real, 'diff', '--name-only').splitlines() if f] + C.nao_rastreados(real)
        if soltos:
            rel.erro('lint (%s): há alteração fora do índice (%s) — o lint vê o working tree e o commit leva o '
                     'índice; `git add`, `git stash -u --keep-index` ou desfaça antes (dispensa: `--sem-padrao '
                     'lint=D<n>`)' % (cmd, ', '.join(soltos[:5]) + ('…' if len(soltos) > 5 else '')))
            return {}
    elif modo == 'vinculo':
        if h != C.git(real, 'rev-parse', 'HEAD') or C.git(real, 'status', '--porcelain'):
            rel.erro('lint (%s): o commit %s não é o HEAD com a árvore limpa — o lint roda no working tree e não '
                     'confere esse commit (dispensa: `--sem-padrao lint=D<n>`, decisão do usuário)'
                     % (cmd, (h or '')[:9]))
            return {}
    pasta_log = tempfile.mkdtemp(prefix='lint-')
    log = os.path.join(pasta_log, 'lint.log')
    codigo, saida = C.rodar(cmd, real, log, timeout=900)
    if codigo != 0:
        cauda = ' | '.join(l.strip() for l in saida.strip().splitlines()[-5:])
        rel.erro('lint (%s) saiu com %d: %s (log %s)' % (cmd, codigo, cauda[:300], log))
    else:
        shutil.rmtree(pasta_log, ignore_errors=True)
    return {}
