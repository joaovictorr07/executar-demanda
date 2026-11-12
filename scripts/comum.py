#!/usr/bin/env python3
"""Peças que todos os comandos do `demanda.py` usam.

O desenho é o do `lessons.py` do tlc e do `validar.py` do skills-documentacao: **o modelo julga, o
script contabiliza**. Todo estado mecânico da execução de uma demanda — repositórios e comandos,
ondas, tarefas e seus commits, execuções de teste, mutantes, revisões — vive num arquivo só,
`<pasta do projeto>/.execucao.json`, que só os scripts escrevem. Os `.md` continuam sendo
documentos de gente; o que neles é fato (tabela de commits, linha de testes, painel) é gerado
daqui, entre marcadores `<!-- gerado:NOME:inicio -->` / `<!-- gerado:NOME:fim -->`.

**Fingerprint** é o que torna uma evidência datável: por repositório, a identidade do **conteúdo**
do estado de trabalho — a árvore (modo, blob, caminho) que o git veria se tudo fosse commitado
agora, menos os caminhos excluídos (`.playwright-mcp/` e os do `ignorar_no_codigo`). Toda evidência
grava o fingerprint do momento em que foi produzida; um gate só a aceita se ele ainda for o atual.
Mexeu no código depois do teste, o teste venceu; **commitar sem mudar conteúdo não vence nada**.

A identidade antiga incluía o HEAD, e commitar a documentação depois do teste vencia o teste. A
assinatura antiga continua calculada (`assinatura_v1`) para comparar evidência gravada com ela:
`mesmo_fp` usa o conteúdo quando os dois lados o têm, e a antiga quando um deles é velho.
"""

import os
import time
import contextlib
import datetime as _dt
if os.name == 'nt':
    import msvcrt
else:
    import fcntl
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

# A raiz dos projetos pode ser trocada por variável de ambiente — é o que o autoteste usa para
# trabalhar numa pasta temporária sem encostar em ~/projetos.
RAIZ = os.path.normpath(os.path.expanduser(os.environ.get('EXEC_DEMANDA_RAIZ', os.path.join(os.environ.get('CODEX_HOME', os.path.expanduser('~/.codex')), 'executar-demanda', 'demandas'))))
ARQUIVO_ESTADO = '.execucao.json'
VERSAO_ESTADO = 1

# "34 - 2026", "108 - 2025". O resto de ~/projetos não é projeto.
PADRAO_PASTA = re.compile(r'^(?P<numero>\d+)\s*-\s*(?P<ano>\d{4})$')

# Identificadores. Os namespaces são fechados de propósito: o mesmo prefixo não pode servir a
# decisão numa onda e a defeito noutra, nem a numeração de achados recomeçar entre rodadas do
# parecer. Onda: "2", "4b", "10".
RE_ONDA = r'\d+[a-z]?'
RE_TAREFA = re.compile(r'\bT(%s)\.(\d+)\b' % RE_ONDA)
RE_ACEITE = re.compile(r'\bA(%s)\.(\d+)\b' % RE_ONDA)


# ------------------------------------------------------------------------------ ambiente

def configurar_saida():
    """Força UTF-8 em stdout/stderr (mesmo motivo do ambiente.py do skills-documentacao)."""
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, 'reconfigure'):
            try:
                fluxo.reconfigure(encoding='utf-8')
            except (ValueError, OSError):
                pass


def chave(texto):
    """Forma comparável: sem acento, sem caixa, espaços colapsados."""
    t = unicodedata.normalize('NFKD', texto or '')
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return ' '.join(t.casefold().split())


def agora():
    return _dt.datetime.now().astimezone().isoformat(timespec='seconds')


def hoje_br():
    return _dt.date.today().strftime('%d/%m/%Y')


def sha1_bytes(dados):
    return hashlib.sha1(dados).hexdigest()


def sha1_arquivo(caminho):
    h = hashlib.sha1()
    with open(caminho, 'rb') as fh:
        for bloco in iter(lambda: fh.read(1 << 16), b''):
            h.update(bloco)
    return h.hexdigest()


def dir_scratch():
    """Onde ficam as worktrees de mutação. Fora de qualquer repositório e de ~/projetos."""
    base = os.environ.get('EXEC_DEMANDA_SCRATCH') or os.path.join(
        tempfile.gettempdir(), 'executar-demanda')
    os.makedirs(base, exist_ok=True)
    return base


# ------------------------------------------------------------------------------ relatório

class Relatorio(object):
    """ERRO impede seguir; AVISO é para o usuário decidir. Mesmo contrato do validar.py."""

    def __init__(self, titulo=None):
        self.titulo = titulo
        self.erros = []
        self.avisos = []
        self.notas = []

    def erro(self, msg):
        self.erros.append(msg)

    def aviso(self, msg):
        self.avisos.append(msg)

    def nota(self, msg):
        self.notas.append(msg)

    def absorver(self, outro, prefixo=''):
        self.erros += [prefixo + e for e in outro.erros]
        self.avisos += [prefixo + a for a in outro.avisos]

    def imprimir(self):
        if self.titulo:
            print(self.titulo)
        for n in self.notas:
            print('  %s' % n)
        for a in self.avisos:
            print('  aviso: %s' % a)
        for e in self.erros:
            print('  ERRO:  %s' % e)
        if not self.erros and not self.avisos:
            print('  sem apontamentos')
        print()
        print('resultado: %d erro(s), %d aviso(s)' % (len(self.erros), len(self.avisos)))
        return 1 if self.erros else 0


# ------------------------------------------------------------------------------ projeto

def resolver(referencia):
    """Aceita "34 - 2026", "34/2026" ou um caminho. Só o número não: o ano é do usuário dizer
    (há "112 - 2024" e "112 - 2026" lado a lado em ~/projetos)."""
    if os.path.isdir(referencia):
        return os.path.abspath(referencia)
    if not os.environ.get('EXEC_DEMANDA_AUTOTESTE'):
        raise SystemExit('informe o caminho de uma pasta existente escolhida para a demanda: %r' % referencia)
    ref = referencia.strip()
    candidatos = []
    if os.path.isdir(RAIZ):
        for nome in sorted(os.listdir(RAIZ)):
            m = PADRAO_PASTA.match(nome)
            if m and os.path.isdir(os.path.join(RAIZ, nome)):
                candidatos.append((int(m.group('numero')), int(m.group('ano')), nome))
    m = re.match(r'^(\d+)\s*[-/／]\s*(\d{4})$', ref)
    if m:
        achados = [c for c in candidatos if c[0] == int(m.group(1)) and c[1] == int(m.group(2))]
    elif ref.isdigit():
        raise SystemExit('informe número e ano ("%s - AAAA"): o projeto é do usuário dizer, '
                         'não se deduz pelo número' % ref)
    else:
        achados = [c for c in candidatos if c[2] == ref]
    if not achados:
        raise SystemExit('projeto não encontrado em %s: %r' % (RAIZ, referencia))
    if len(achados) > 1:
        raise SystemExit('referência ambígua %r — candidatos: %s'
                         % (referencia, ', '.join(c[2] for c in achados)))
    return os.path.join(RAIZ, achados[0][2])


def numero_ano(pasta):
    m = PADRAO_PASTA.match(os.path.basename(os.path.normpath(pasta)))
    if not m:
        raise SystemExit('pasta de projeto fora do padrão "NN - AAAA": %s' % pasta)
    return int(m.group('numero')), int(m.group('ano'))


def arquivo_plano(pasta):
    if not PADRAO_PASTA.match(os.path.basename(os.path.normpath(pasta))):
        return os.path.join(pasta, 'PLANO.md')
    n, a = numero_ano(pasta)
    return os.path.join(pasta, 'PLANO-%d-%d.md' % (n, a))


def arquivo_analise(pasta):
    if not PADRAO_PASTA.match(os.path.basename(os.path.normpath(pasta))):
        return os.path.join(pasta, 'analise.md')
    n, a = numero_ano(pasta)
    return os.path.join(pasta, 'analise-%d-%d.md' % (n, a))


def arquivo_painel_html(pasta):
    if not PADRAO_PASTA.match(os.path.basename(os.path.normpath(pasta))):
        return os.path.join(pasta, 'PAINEL.html')
    n, a = numero_ano(pasta)
    return os.path.join(pasta, 'PAINEL-%d-%d.html' % (n, a))


def arquivo_estado_md(pasta):
    if not PADRAO_PASTA.match(os.path.basename(os.path.normpath(pasta))):
        return os.path.join(pasta, 'ESTADO-ATUAL.md')
    n, a = numero_ano(pasta)
    return os.path.join(pasta, 'ESTADO-ATUAL-%d-%d.md' % (n, a))


def arquivo_consolidacao(pasta, onda):
    return os.path.join(pasta, 'ONDA-%s-consolidacao.md' % onda)


def arquivo_revisao(pasta, onda):
    return os.path.join(pasta, 'revisao-onda-%s.md' % onda)


def arquivo_autoconferencia(pasta, onda):
    return os.path.join(pasta, 'autoconferencia-onda-%s.md' % onda)


def rotulo(pasta):
    if not PADRAO_PASTA.match(os.path.basename(os.path.normpath(pasta))):
        return os.path.basename(os.path.normpath(pasta))
    n, a = numero_ano(pasta)
    return '%d/%d' % (n, a)


# ------------------------------------------------------------------------------ estado

def estado_vazio():
    return {
        'versao': VERSAO_ESTADO,
        'repos': {},
        'ondas': {},
        'execucoes': [],
        'sessoes_mutacao': [],
        'revisoes': [],
        'autoconferencias': [],
        'pareceres': [],
        'contadores': {},
    }


# Concorrência. O revisor roda em background enquanto o orquestrador registra decisões, e as
# sessões de projetos diferentes compartilham a loja de lições: duas escritas sobre o mesmo JSON não
# podem se perder. Dois mecanismos:
# - `trava(arquivo)`: lock exclusivo (flock) num `.lock` ao lado, reentrante no mesmo processo. O
#   `demanda.py` segura a do projeto durante todo comando rápido; os longos (`testar`, `mutante
#   preparar/aplicar`) usam `transacao` só nos trechos que gravam, e rodam o resto fora dela.
# - guarda otimista: `carregar_estado` anota o sha1 do que leu; `salvar_estado` recusa se o arquivo
#   mudou desde então — pega o caminho que gravasse sobre uma leitura velha.
_TRAVAS = {}
_LIDO = {}  # id(estado) -> sha1 do arquivo de onde aquele objeto foi lido
_PASTA = {}  # id(estado) -> pasta do projeto de onde ele foi lido (o estado não guarda a própria pasta)


@contextlib.contextmanager
def trava(arquivo):
    """Lock exclusivo e reentrante sobre `<arquivo>.lock`."""
    chave = os.path.normcase(os.path.abspath(arquivo))
    if chave in _TRAVAS:
        _TRAVAS[chave][1] += 1
        try:
            yield
        finally:
            _TRAVAS[chave][1] -= 1
        return
    os.makedirs(os.path.dirname(chave), exist_ok=True)
    fh = open(chave + '.lock', 'a+b')
    try:
        if os.name == 'nt':
            fh.seek(0, 2)
            if fh.tell() == 0:
                fh.write(b'0'); fh.flush()
            while True:
                fh.seek(0)
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (13, 11, 36):
                        raise
                    time.sleep(0.05)
        else:
            fcntl.flock(fh, fcntl.LOCK_EX)
        _TRAVAS[chave] = [fh, 1]
        try:
            yield
        finally:
            del _TRAVAS[chave]
            if os.name == 'nt':
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fh, fcntl.LOCK_UN)
    finally:
        fh.close()


def trava_projeto(pasta):
    return trava(os.path.join(pasta, ARQUIVO_ESTADO))


@contextlib.contextmanager
def transacao(pasta):
    """Lê o estado sob lock, entrega para alteração e grava ao sair sem exceção."""
    with trava_projeto(pasta):
        estado = carregar_estado(pasta)
        yield estado
        salvar_estado(pasta, estado)


def atualizar(pasta, fn):
    """Aplica `fn(estado)` numa transação curta e devolve o que ela devolver."""
    with transacao(pasta) as estado:
        return fn(estado)


def _sha_arquivo_ou_nada(arq):
    return sha1_arquivo(arq) if os.path.exists(arq) else None


def gravar_json_atomico(arq, dados):
    """Temporário de nome único na mesma pasta + rename: nem Ctrl+C nem dois escritores deixam
    JSON pela metade."""
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(arq) + '.', suffix='.tmp',
                               dir=os.path.dirname(os.path.abspath(arq)))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(dados, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write('\n')
        os.replace(tmp, arq)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def carregar_estado(pasta):
    arq = os.path.join(pasta, ARQUIVO_ESTADO)
    if not os.path.exists(arq):
        base = estado_vazio()
        _LIDO[id(base)] = None
        _PASTA[id(base)] = pasta
        return base
    with open(arq, 'rb') as fh:
        bruto = fh.read()
    dados = json.loads(bruto.decode('utf-8'))
    base = estado_vazio()
    base.update(dados)
    _LIDO[id(base)] = sha1_bytes(bruto)
    _PASTA[id(base)] = pasta
    registrar_exclusoes(base)
    return base


def pasta_de(estado):
    """Pasta do projeto de onde `estado` foi lido (None se não veio de `carregar_estado`)."""
    return _PASTA.get(id(estado))


def salvar_estado(pasta, estado):
    arq = os.path.join(pasta, ARQUIVO_ESTADO)
    with trava(arq):
        if id(estado) in _LIDO and _sha_arquivo_ou_nada(arq) != _LIDO[id(estado)]:
            raise SystemExit('o %s mudou depois que este comando o leu (outra sessão ou o revisor '
                             'gravou nele). Nada foi gravado: rode o comando de novo.' % ARQUIVO_ESTADO)
        gravar_json_atomico(arq, estado)
        _LIDO[id(estado)] = sha1_arquivo(arq)
    return arq


def proximo_id(estado, prefixo):
    c = estado.setdefault('contadores', {})
    c[prefixo] = c.get(prefixo, 0) + 1
    return '%s%d' % (prefixo, c[prefixo])


def repo_cfg(estado, nome):
    cfg = estado['repos'].get(nome)
    if not cfg:
        raise SystemExit('repositório %r não configurado — rode `demanda.py configurar`. '
                         'Configurados: %s' % (nome, ', '.join(sorted(estado['repos'])) or 'nenhum'))
    return cfg


# Uma regra só. A onda iniciada a partir da 0.4.0 grava `consolidada` e segue as regras deste
# documento; as de antes (rótulo `regras` 1–3) são históricas — só leitura: painel, métricas e
# parecer. Onda histórica que não esteja encerrada não anda mais (`exigir_onda_consolidada`).
SKILL_DIR = os.environ.get('EXEC_DEMANDA_SKILL_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Onda que não volta mais a andar. `replanejada` e `abandonada` vêm do `onda desbloquear`.
TERMINAIS = ('fechada', 'replanejada', 'abandonada')


def blobs_alterados(repo, base):
    """{caminho: blob} dos arquivos que diferem de `base` no estado de trabalho (mais os não
    rastreados). É o retrato que a revisão grava para a rodada seguinte saber o que mudou."""
    nomes = [n for n in git(repo, 'diff', '--name-only', '--no-renames', base).splitlines() if n]
    nomes += nao_rastreados(repo)
    existentes = [n for n in dict.fromkeys(nomes) if os.path.isfile(os.path.join(repo, n))]
    if not existentes:
        return {}
    saida = git(repo, 'hash-object', '--stdin-paths',
                entrada=('\n'.join(existentes) + '\n').encode('utf-8', 'surrogateescape')).split()
    return dict(zip(existentes, saida))


def historica(eo):
    """Onda de antes da 0.4.0: sem o campo `consolidada`."""
    return not (eo or {}).get('consolidada')


def rotulo_regras(eo):
    """Rótulo para painel e métricas: `r1`, `r2`, `r3` (históricas) ou `atual`. Não decide gate."""
    return 'r%d' % (eo or {}).get('regras', 1) if historica(eo) else 'atual'


def exigir_onda_consolidada(estado, oid):
    """Onda histórica não encerrada não anda com esta versão da skill."""
    eo = (estado.get('ondas') or {}).get(oid)
    if eo and historica(eo) and eo.get('estado') not in TERMINAIS:
        raise SystemExit('recusado: a onda %s é de antes da 0.4.0 (regras %s) e não está encerrada — feche-a com '
                         'a versão 0.3.1 da skill, ou decida com o usuário replanejá-la numa onda nova'
                         % (oid, eo.get('regras', 1)))


def versao_skill():
    """Último commit que tocou a pasta da skill e se há alteração não commitada nela (o que roda é o working tree).
    A skill vive num repositório com outras skills: o `HEAD` do repositório mudaria por commit alheio e
    congelaria a onda à toa, então vale o último commit que mexe nesta pasta. Sem commit nela (pasta ainda não
    versionada, ou repositório só com commits vazios), cai no `HEAD`."""
    if not git_ok(SKILL_DIR, 'rev-parse', '--git-dir'):
        return {'commit': None, 'sujo': None, 'conteudo': _conteudo_skill()}
    commit = git(SKILL_DIR, 'log', '-1', '--format=%H', '--', '.', checar=False) \
        or git(SKILL_DIR, 'rev-parse', 'HEAD', checar=False)
    return {'commit': commit or None,
            'sujo': bool(git(SKILL_DIR, 'status', '--porcelain', '--', '.', checar=False)),
            'conteudo': _conteudo_skill()}


def _conteudo_skill():
    """sha1 do conteúdo dos arquivos da pasta da skill (rastreados e novos, fora do .gitignore) como estão
    agora: o que roda é o working tree. O commit sozinho não vê edição sem commit, e a skill pode ser uma pasta independente ou estar versionada."""
    if git_ok(SKILL_DIR, 'rev-parse', '--git-dir'):
        nomes = git(SKILL_DIR, 'ls-files', '-co', '--exclude-standard', '-z', '--', '.', bruto=True, checar=False)
    else:
        arquivos = []
        for base, dirs, files in os.walk(SKILL_DIR):
            dirs[:] = sorted(d for d in dirs if d not in ('.git', '__pycache__'))
            arquivos.extend(os.path.relpath(os.path.join(base, f), SKILL_DIR).replace(os.sep, '/').encode('utf-8')
                            for f in files if not f.endswith(('.pyc', '.lock')))
        nomes = b'\0'.join(arquivos)
    h = hashlib.sha1()
    for nome in sorted(n for n in nomes.split(b'\0') if n):
        try:
            with open(os.path.join(SKILL_DIR, nome.decode('utf-8', 'surrogateescape')), 'rb') as fh:
                h.update(nome + b'\0' + hashlib.sha1(fh.read()).digest())
        except OSError:
            continue
    return h.hexdigest()


def skill_mudou(eo):
    """Texto do que mudou na skill desde o início da onda, ou None."""
    inicio = (eo or {}).get('skill')
    if not inicio:
        return None
    agora_ = versao_skill()
    if inicio.get('commit') and agora_['commit'] and agora_['commit'] != inicio['commit']:
        return 'a skill mudou desde o início da onda (commit %s → %s)' % (inicio['commit'][:9], agora_['commit'][:9])
    if inicio.get('conteudo') and agora_.get('conteudo') and agora_['conteudo'] != inicio['conteudo']:
        return ('a skill mudou desde o início da onda (conteúdo da pasta, inclusive alteração sem commit: %s → %s)'
                % (inicio['conteudo'][:9], agora_['conteudo'][:9]))
    return None


def analise_mudou(pasta, estado, eo=None):
    """Texto do que mudou na análise desde que o plano foi aprovado (ou desde que o usuário aceitou
    a mudança ao iniciar a onda), ou None.

    O plano é selado na aprovação; a análise, que é de onde ele sai, não era: o analista corrigia
    uma resposta e o plano seguia sobre a versão antiga sem que ninguém visse. Aprovação anterior
    ao selo (sem `analise_sha1`) não tem o que comparar e não acusa nada. O `hash_plano` não inclui
    a análise, de propósito: mudar uma vírgula nela não pode invalidar as revisões do plano."""
    ref = ((eo or {}).get('analise_aceita') or {}).get('sha1')
    aprovacoes = (estado or {}).get('aprovacoes_plano') or []
    if not ref and aprovacoes:
        ref = aprovacoes[-1].get('analise_sha1')
    if not ref:
        return None
    arq = arquivo_analise(pasta)
    atual = sha1_arquivo(arq) if os.path.exists(arq) else None
    if atual == ref:
        return None
    aid = aprovacoes[-1]['id'] if aprovacoes else 'do plano'
    if atual is None:
        return 'a análise %s não existe mais; o plano foi aprovado (%s) sobre ela' % (os.path.basename(arq), aid)
    return ('a análise %s mudou depois da aprovação %s — o plano pode estar sobre respostas antigas'
            % (os.path.basename(arq), aid))


def onda_ativa(estado):
    ativas = [k for k, v in estado['ondas'].items() if v.get('estado') == 'em_execucao']
    return ativas[0] if len(ativas) == 1 else None


# ------------------------------------------------------------------------------ git

class ErroGit(Exception):
    pass


def git(repo, *args, entrada=None, bruto=False, checar=True):
    proc = subprocess.run(
        ['git', '-c', 'core.quotepath=false', '-C', repo] + list(args), input=entrada,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=None if entrada is not None else subprocess.DEVNULL)
    if checar and proc.returncode != 0:
        raise ErroGit('git %s: %s' % (' '.join(args), proc.stderr.decode('utf-8', 'replace').strip()))
    if bruto:
        return proc.stdout
    return proc.stdout.decode('utf-8', 'replace').strip()


def git_ok(repo, *args):
    return subprocess.run(['git', '-c', 'core.quotepath=false', '-C', repo] + list(args), stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).returncode == 0


def branch_atual(repo):
    return git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')


def nao_rastreados(repo, ignorar=()):
    """Arquivos fora do git e fora do .gitignore. `ignorar`: prefixos que a sessão de mutação
    linkou ou copiou no scratch (um symlink `node_modules` não casa com `node_modules/`)."""
    saida = git(repo, 'ls-files', '--others', '--exclude-standard', '-z', bruto=True)
    nomes = sorted(p.decode('utf-8', 'surrogateescape') for p in saida.split(b'\0') if p)
    prefixos = [i.strip('/') for i in ignorar if i]
    return [n for n in nomes if not any(n == p or n.startswith(p + '/') for p in prefixos)]


# Caminhos que não são código e não entram na identidade: o Playwright MCP grava
# `.playwright-mcp/` no cwd da sessão, que é o repositório (e venceria toda evidência a cada
# roteiro). Cada repo acrescenta os seus com `configurar --ignorar-no-codigo`.
EXCLUIR_PADRAO = ('.playwright-mcp',)
_EXCLUIR = {}  # caminho real do repo -> tupla de prefixos, registrado ao carregar o estado


def registrar_exclusoes(estado):
    for cfg in estado.get('repos', {}).values():
        extras = [p.strip().strip('/') for p in cfg.get('ignorar_no_codigo', []) if p.strip().strip('/')]
        _EXCLUIR[os.path.realpath(cfg['caminho'])] = tuple(sorted(set(EXCLUIR_PADRAO) | set(extras)))


def excluir_de(repo):
    return _EXCLUIR.get(os.path.realpath(repo), EXCLUIR_PADRAO)


def _excluido(caminho, excluir):
    return any(caminho == p or caminho.startswith(p + '/') for p in excluir)


def _indice_com_crlf(repo):
    """Caminhos rastreados cujo blob no índice tem CRLF (`i/crlf` ou `i/mixed`)."""
    crus = set()
    for reg in git(repo, 'ls-files', '--eol', '-z', bruto=True).split(b'\0'):
        if not reg or b'\t' not in reg:
            continue
        meta, caminho = reg.split(b'\t', 1)
        if meta.split()[0] in (b'i/crlf', b'i/mixed'):
            crus.add(caminho.decode('utf-8', 'surrogateescape'))
    return crus


def conteudo_arvore(repo, excluir=EXCLUIR_PADRAO):
    """sha1 da árvore virtual do estado de trabalho, sem escrever nada no `.git`.

    Parte do índice (`ls-files -s`: modo e blob de cada arquivo rastreado), troca o que difere do
    índice no working tree pelo blob calculado com `hash-object --stdin-paths` (sem `-w`), soma os
    não rastreados não ignorados e tira os caminhos excluídos. Arquivo apagado sai; submódulo vale
    pelo HEAD dele. O resultado não depende de HEAD nem do que está staged — só do conteúdo.

    Arquivo rastreado cujo blob no índice tem CRLF (`ls-files --eol`: `i/crlf` ou `i/mixed`) é
    calculado com `--no-filters`: o repositório o guarda cru, e com `core.autocrlf=input` o hash
    com filtros daria o blob em LF, que o commit (feito com `-c core.autocrlf=false`) não grava.
    """
    entradas = {}
    for reg in git(repo, 'ls-files', '-s', '-z', bruto=True).split(b'\0'):
        if not reg:
            continue
        meta, caminho = reg.split(b'\t', 1)
        modo, blob, _estagio = meta.decode().split()
        entradas[caminho.decode('utf-8', 'surrogateescape')] = (modo, blob)
    alterados = [p.decode('utf-8', 'surrogateescape') for p in
                 git(repo, 'diff', '--name-only', '-z', '--no-renames', bruto=True).split(b'\0') if p]
    calcular = []
    for rel in alterados + nao_rastreados(repo):
        absoluto = os.path.join(repo, rel)
        if os.path.islink(absoluto):
            entradas[rel] = ('120000', sha1_bytes(os.readlink(absoluto).encode('utf-8', 'surrogateescape')))
        elif os.path.isdir(absoluto):
            entradas[rel] = ('160000', git(absoluto, 'rev-parse', 'HEAD', checar=False))
        elif os.path.isfile(absoluto):
            calcular.append(rel)
        else:
            entradas.pop(rel, None)
    crus = _indice_com_crlf(repo) if calcular else set()
    for sem_filtro in (False, True):
        grupo = [rel for rel in calcular if (rel in crus) == sem_filtro]
        if not grupo:
            continue
        args = ['hash-object', '--stdin-paths'] + (['--no-filters'] if sem_filtro else [])
        saida = git(repo, *args, entrada=('\n'.join(grupo) + '\n').encode('utf-8', 'surrogateescape')).split()
        for rel, blob in zip(grupo, saida):
            modo = entradas.get(rel, ('100644', ''))[0] if os.name == 'nt' else ('100755' if os.access(os.path.join(repo, rel), os.X_OK) else '100644')
            entradas[rel] = (modo, blob)
    h = hashlib.sha1()
    for rel in sorted(entradas):
        if not _excluido(rel, excluir):
            modo, blob = entradas[rel]
            h.update(('%s %s %s\0' % (modo, blob, rel)).encode('utf-8', 'surrogateescape'))
    return h.hexdigest()


def _assinatura_v1(repo, ignorar=()):
    """A identidade antiga (HEAD + diff + não rastreados), só para comparar com evidência gravada
    com ela."""
    head = git(repo, 'rev-parse', 'HEAD')
    diff = git(repo, 'diff', 'HEAD', '--binary', bruto=True)
    h = hashlib.sha1()
    for rel in nao_rastreados(repo, ignorar):
        h.update(rel.encode('utf-8', 'surrogateescape') + b'\0')
        caminho = os.path.join(repo, rel)
        if os.path.isfile(caminho) and not os.path.islink(caminho):
            h.update(sha1_arquivo(caminho).encode())
    fp = {'head': head, 'diff': sha1_bytes(diff), 'nao_rastreados': h.hexdigest()}
    fp['assinatura_v1'] = sha1_bytes(('%(head)s|%(diff)s|%(nao_rastreados)s' % fp).encode())[:12]
    return fp


def fingerprint(repo, ignorar=(), excluir=None):
    """Identidade do código do repositório agora.

    `conteudo`/`assinatura`: o conteúdo (ver `conteudo_arvore`); é o que os gates comparam.
    `assinatura_v1`, `head`, `diff`, `nao_rastreados`: a identidade antiga, para evidência velha.
    `head` também é usado como "até onde" ao reler código fechado (parecer). `excluir`: os
    prefixos de fora; por padrão os do repositório registrado — a réplica de mutação passa os do
    repo real.
    """
    excluir = tuple(excluir) if excluir is not None else excluir_de(repo)
    fp = _assinatura_v1(repo, ignorar)
    # `ignorar` (o que a réplica linkou ou copiou) sai também do conteúdo; no repo real essas
    # pastas já estão no .gitignore. O hash de `excluir` fica só com a lista do repositório.
    fp['conteudo'] = conteudo_arvore(repo, excluir + tuple(i.strip('/') for i in ignorar if i))
    fp['assinatura'] = fp['conteudo'][:12]
    fp['excluir'] = sha1_bytes('|'.join(excluir).encode())[:8]
    return fp


def fingerprints(estado):
    """Fingerprint de cada repositório configurado que existe no disco. O que sumiu fica de fora, e
    quem consome aponta isso como erro em vez de quebrar com KeyError."""
    return {r: fingerprint(cfg['caminho']) for r, cfg in estado['repos'].items()
            if os.path.isdir(cfg['caminho'])}


def porcelain_sha1(repo):
    """Identidade do `git status`, sem os caminhos excluídos (a sessão de mutação confere com ele
    que o repositório real não mudou; `.playwright-mcp/` gravado no meio invalidaria a sessão)."""
    excluir = excluir_de(repo)
    bruto = git(repo, 'status', '--porcelain', '-z', '--untracked-files=all', '--no-renames', bruto=True)
    registros = [r for r in bruto.split(b'\0') if r]
    mantidos = [r for r in registros
                if not _excluido(r[3:].decode('utf-8', 'surrogateescape').rstrip('/'), excluir)]
    return sha1_bytes(b'\0'.join(mantidos))


def mesmo_fp(a, b):
    """Mesma identidade. Os dois com conteúdo (e a mesma lista de exclusão): compara o conteúdo.
    Um deles gravado com a identidade antiga: compara a assinatura antiga dos dois."""
    if not a or not b:
        return False
    if a.get('conteudo') and b.get('conteudo') and a.get('excluir') == b.get('excluir'):
        return a['conteudo'] == b['conteudo']
    va = a.get('assinatura_v1') or (None if a.get('conteudo') else a.get('assinatura'))
    vb = b.get('assinatura_v1') or (None if b.get('conteudo') else b.get('assinatura'))
    return bool(va) and va == vb


def commit_existe(repo, h):
    return git_ok(repo, 'cat-file', '-e', '%s^{commit}' % h)


def data_commit(repo, h):
    return git(repo, 'show', '-s', '--format=%cI', h)


def eh_ancestral(repo, a, b):
    return git_ok(repo, 'merge-base', '--is-ancestor', a, b)


# ------------------------------------------------------------------------------ comandos

def rodar(comando, cwd, log, timeout=3600, env_extra=None):
    """Roda um comando de shell, grava a saída inteira em `log` e devolve (exit, saída).

    Timeout vira exit 124, como o `timeout` do coreutils — o chamador decide o que isso significa
    (num mutante, laço infinito provocado conta como morto). O comando roda num grupo de processos
    próprio e, no timeout, o **grupo inteiro** é encerrado: matar só o shell deixava o `mvn` filho
    vivo, reescrevendo relatórios que a execução seguinte lia.
    """
    import signal
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    os.makedirs(os.path.dirname(log), exist_ok=True)
    inicio = agora()
    proc = subprocess.Popen(comando, shell=True, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=(os.name != 'nt'),
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
    nota = ''
    try:
        bruto, _ = proc.communicate(timeout=timeout)
        codigo = proc.returncode
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        else:
            for sinal, espera in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
                try:
                    os.killpg(proc.pid, sinal)
                except ProcessLookupError:
                    break
                try:
                    proc.wait(timeout=espera)
                    break
                except subprocess.TimeoutExpired:
                    continue
        try:
            bruto, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            bruto = b''
        nota = '\n[timeout de %ds: grupo de processos %d encerrado]\n' % (timeout, proc.pid)
        codigo = 124
    saida = (bruto or b'').decode('utf-8', 'replace') + nota
    with open(log, 'w', encoding='utf-8') as fh:
        fh.write('# comando: %s\n# cwd: %s\n# inicio: %s\n# fim: %s\n# exit: %d\n\n'
                 % (comando, cwd, inicio, agora(), codigo))
        fh.write(saida)
    return codigo, saida


# ------------------------------------------------------------------------------ markdown

def secao(texto, titulo_regex, nivel=2):
    """Corpo de uma seção `##` (ou outro nível) cujo título casa com a regex, sem o título."""
    linhas = texto.splitlines()
    marca = '#' * nivel + ' '
    inicio = None
    for i, ln in enumerate(linhas):
        if ln.startswith(marca) and re.search(titulo_regex, ln[len(marca):], re.IGNORECASE):
            inicio = i + 1
            continue
        if inicio is not None and re.match(r'^#{1,%d} ' % nivel, ln):
            return '\n'.join(linhas[inicio:i])
    if inicio is not None:
        return '\n'.join(linhas[inicio:])
    return None


def linhas_de_tabela(texto):
    """Linhas de tabela markdown como listas de células (sem cabeçalho nem separador)."""
    linhas = []
    cabecalho_visto = False
    for ln in (texto or '').splitlines():
        s = ln.strip()
        if not s.startswith('|'):
            cabecalho_visto = False
            continue
        celulas = [c.strip() for c in s.strip('|').split('|')]
        if all(re.match(r'^:?-{2,}:?$', c) for c in celulas if c):
            cabecalho_visto = True
            continue
        if not cabecalho_visto:
            continue  # linha de cabeçalho
        linhas.append(celulas)
    return linhas


def sem_riscado(texto):
    return re.sub(r'~~.*?~~', '', texto or '')


def tem_conteudo(texto):
    """Seção preenchida de verdade: alguma linha que não seja comentário, marcador vazio ou guia.
    O texto-guia do esqueleto (`<…>`) pode ocupar várias linhas."""
    texto = re.sub(r'(?ms)^[ \t]*[-*]?[ \t]*<[^<>]*>[ \t]*$', '', texto or '')
    for ln in texto.splitlines():
        s = re.sub(r'<!--.*?-->', '', ln).strip()
        if not s or s in ('-', '*', '...', '…') or re.match(r'^[-*]\s*$', s):
            continue
        if re.match(r'^[-*]?\s*<.*>$', s):  # texto-guia do esqueleto: "<o que foi ...>"
            continue
        return True
    return False


def marcadores(nome):
    return '<!-- gerado:%s:inicio -->' % nome, '<!-- gerado:%s:fim -->' % nome


def trocar_bloco(texto, nome, conteudo):
    """Substitui o conteúdo entre os marcadores do bloco `nome`. Devolve (texto, achou)."""
    ini, fim = marcadores(nome)
    padrao = re.compile(re.escape(ini) + r'.*?' + re.escape(fim), re.DOTALL)
    novo = '%s\n%s\n%s' % (ini, conteudo.rstrip('\n'), fim)
    if not padrao.search(texto):
        return texto, False
    return padrao.sub(lambda _m: novo, texto, count=1), True


def bloco(nome, conteudo):
    ini, fim = marcadores(nome)
    return '%s\n%s\n%s' % (ini, conteudo.rstrip('\n'), fim)


def ler(caminho):
    with open(caminho, encoding='utf-8') as fh:
        return fh.read()


def gravar(caminho, texto):
    with open(caminho, 'w', encoding='utf-8') as fh:
        fh.write(texto)


def _glob_regex(padrao):
    """Glob de caminho: `*` e `?` não atravessam `/`; `**` atravessa."""
    rx, i = '', 0
    while i < len(padrao):
        if padrao.startswith('**', i):
            rx += '.*'
            i += 2
        elif padrao[i] == '*':
            rx += '[^/]*'
            i += 1
        elif padrao[i] == '?':
            rx += '[^/]'
            i += 1
        else:
            rx += re.escape(padrao[i])
            i += 1
    return re.compile(rx + r'\Z')


def casa_padrao(caminho, padroes):
    """`caminho` (relativo à raiz do repositório) casa com algum padrão de `Onde`: o mesmo caminho,
    uma pasta que o contém (`src/app/`) ou um glob em que `*` fica dentro da pasta (`**` atravessa).
    Nome solto (`package.json`) é o arquivo da raiz, não "qualquer arquivo com esse nome": antes
    `Onde: index.ts` cobria todo index.ts do repositório."""
    caminho = caminho.replace('\\', '/')
    for p in padroes:
        p = p.strip().strip('`').replace('\\', '/')
        if p.startswith('./'):
            p = p[2:]
        p = p.rstrip('/')
        if not p:
            continue
        if caminho == p or caminho.startswith(p + '/'):
            return True
        if any(c in p for c in '*?') and _glob_regex(p).match(caminho):
            return True
    return False


# ------------------------------------------------------------------------------ fala do usuário
#
# O hook `~/.codex/skills/executar-demanda/hooks/registrar-fala-usuario.py` grava, a cada mensagem digitada e a cada
# resposta de request_user_input, uma linha JSON em `~/.codex/executar-demanda/falas-usuario/AAAA-MM.jsonl`. É a
# única prova, fora da conversa, de que uma decisão veio do usuário: toda decisão com fonte
# "usuario" e toda aprovação de plano citam um trecho literal que tem de estar lá.

def _pastas_falas_candidatas():
    pastas = []
    env = os.environ.get('EXEC_DEMANDA_FALAS')
    if env:
        pastas.append(os.path.normpath(os.path.expanduser(env)))
    # Gemini / Antigravity
    gemini_dir = os.path.normpath(os.path.expanduser('~/.gemini/falas-usuario'))
    pastas.append(gemini_dir)
    # Codex
    codex_home = os.environ.get('CODEX_HOME', os.path.expanduser('~/.codex'))
    pastas.append(os.path.normpath(os.path.join(codex_home, 'executar-demanda', 'falas-usuario')))
    # Claude Code
    pastas.append(os.path.normpath(os.path.expanduser('~/.claude/falas-usuario')))
    return [p for p in dict.fromkeys(pastas) if os.path.isdir(p)]


def _padrao_falas():
    env = os.environ.get('EXEC_DEMANDA_FALAS')
    if env:
        return os.path.normpath(os.path.expanduser(env))
    if os.path.isdir(os.path.expanduser('~/.gemini')):
        return os.path.normpath(os.path.expanduser('~/.gemini/falas-usuario'))
    codex_home = os.environ.get('CODEX_HOME', os.path.expanduser('~/.codex'))
    if os.path.isdir(codex_home):
        return os.path.normpath(os.path.join(codex_home, 'executar-demanda', 'falas-usuario'))
    return os.path.normpath(os.path.expanduser('~/.claude/falas-usuario'))


FALAS = _padrao_falas()
MIN_CITACAO = 12
# Prompts que o Claude Code injeta como se fossem do usuário (o hook já não os grava; o filtro
# aqui limpa o que entrou antes dele).
NAO_E_FALA = ('<task-notification', '<agent-message', '<local-command-stdout', '<local-command-stderr',
              '<system-reminder')


def falas():
    """Entradas do log, em ordem. Linha corrompida é ignorada (o hook nunca bloqueia)."""
    saida = []
    vistos = set()
    pastas = _pastas_falas_candidatas()
    if not pastas and os.path.isdir(FALAS):
        pastas = [FALAS]
    for pasta in pastas:
        for nome in sorted(os.listdir(pasta)):
            if not nome.endswith('.jsonl'):
                continue
            with open(os.path.join(pasta, nome), encoding='utf-8', errors='replace') as fh:
                for ln in fh:
                    try:
                        e = json.loads(ln)
                    except ValueError:
                        continue
                    if not isinstance(e, dict) or not e.get('texto'):
                        continue
                    if e.get('tipo') == 'prompt' and e['texto'].lstrip().startswith(NAO_E_FALA):
                        continue
                    chave_unica = (e.get('em'), e.get('texto'))
                    if chave_unica in vistos:
                        continue
                    vistos.add(chave_unica)
                    saida.append(e)
    saida.sort(key=lambda x: str(x.get('em') or ''))
    return saida


def chave_citacao(texto):
    """A `chave` sem crases e aspas: a citação as perde ao ser normalizada, e a fala tem de perdê-las
    igual, senão uma resposta com `código` nunca casa com a cópia literal dela."""
    return chave(re.sub(r'[`"“”]', '', texto or ''))


def _casa_citacao(cit, entrada):
    """A citação está na entrada. Numa resposta de request_user_input, o que prova é a resposta: o
    trecho cabe inteiro na resposta (e notas); ou, quando a resposta é curta demais para ser citada
    sozinha, o trecho contém a resposta inteira (e pode trazer o fim da pergunta). Citar só a
    pergunta, ou um prefixo da resposta ("…?: S" casando com "Sim" e com "Sem"), não prova nada."""
    if entrada.get('tipo') != 'resposta':
        return cit in chave_citacao(entrada['texto'])
    resposta = chave_citacao(entrada.get('resposta', ''))
    notas = chave_citacao(entrada.get('notas', ''))
    if cit in resposta or (notas and cit in notas) or (notas and cit in chave(resposta + ' ' + notas)):
        return True
    return bool(resposta) and resposta in cit and cit in chave_citacao(entrada['texto'])


def locais_do_projeto(pasta, estado):
    """Onde uma fala sobre este projeto pode ter sido dita: a pasta dele e os repositórios."""
    locais = [os.path.abspath(pasta)]
    for cfg in (estado or {}).get('repos', {}).values():
        if cfg.get('caminho'):
            locais.append(os.path.abspath(cfg['caminho']))
    return locais


def _dentro(cwd, locais):
    if not cwd:
        return False
    cwd = os.path.normcase(os.path.abspath(cwd))
    return any(cwd == os.path.normcase(l) or cwd.startswith(os.path.normcase(l) + os.sep) for l in locais)


def citacao_do_usuario(citacao, depois_de=None, locais=None):
    """(entrada, erro). `depois_de`: epoch; só valem falas posteriores. `locais`: só valem falas
    ditas numa sessão aberta num desses diretórios (a pasta do projeto ou um repositório dele) —
    uma fala dita noutro projeto não prova decisão deste."""
    cit = chave_citacao(citacao)
    if len(cit) < MIN_CITACAO:
        return None, ('citação com menos de %d caracteres — cite um trecho que só a fala do '
                      'usuário tem' % MIN_CITACAO)
    todas = falas()
    if not todas:
        return None, ('nenhuma fala do usuário registrada em %s — o hook registrar-fala-usuario '
                      'não está instalado. Sem ele não há como provar a decisão' % FALAS)
    achadas = [e for e in todas if _casa_citacao(cit, e)]
    if not achadas:
        return None, ('a citação não está em nenhuma fala do usuário: %r. Cite literalmente o que '
                      'ele digitou ou respondeu (numa resposta, a resposta — não a pergunta que você '
                      'escreveu); nunca o que você acha que ele quis dizer' % citacao)
    if locais is not None:
        no_projeto = [e for e in achadas if _dentro(e.get('cwd'), locais)]
        if not no_projeto:
            return None, ('a fala citada foi dita fora deste projeto (sessão em %s); vale só fala de '
                          'sessão aberta na pasta do projeto ou num repositório dele: %s'
                          % (achadas[-1].get('cwd') or 'diretório desconhecido', ', '.join(locais)))
        achadas = no_projeto
    if depois_de is not None:
        recentes = [e for e in achadas if epoch_iso(e.get('em')) > depois_de]
        if not recentes:
            return None, ('a fala citada é anterior à versão atual do plano (%s): o usuário aprovou '
                          'outra versão' % achadas[-1].get('em'))
        achadas = recentes
    return achadas[-1], None


def fala_por_momento(em, citacao=None):
    """A entrada do log gravada em `em` (o carimbo que a decisão guardou). As respostas de uma mesma
    chamada de request_user_input têm o mesmo carimbo: com `citacao`, vale a que a contém."""
    mesmas = [e for e in falas() if e.get('em') == em]
    if citacao:
        cit = chave_citacao(citacao)
        mesmas = [e for e in mesmas if _casa_citacao(cit, e)] or [e for e in mesmas if cit in chave_citacao(e['texto'])]
    return mesmas[0] if mesmas else None


def epoch_iso(texto):
    try:
        return _dt.datetime.fromisoformat(texto).timestamp()
    except (TypeError, ValueError):
        return 0.0


def agora_fino():
    return _dt.datetime.now().astimezone().isoformat(timespec='microseconds')


# ------------------------------------------------------------------------------ plano selado

RE_BLOCO_DECISOES = re.compile(r'<!-- gerado:decisoes:inicio -->.*?<!-- gerado:decisoes:fim -->', re.DOTALL)


def plano_normalizado(texto):
    """O plano sem o que o script escreve nele ou que muda sem decisão nova: linhas
    `**Commits:**`, marca `[x]` dos aceites e o bloco gerado de decisões (cada decisão tem prova
    própria). O resto — tarefa, aceite, Onde, Risco, Teste — é o que o usuário aprovou."""
    texto = RE_BLOCO_DECISOES.sub('<!-- gerado:decisoes -->', texto or '')
    linhas = []
    for ln in texto.splitlines():
        if re.match(r'^\s*[-*]?\s*\*\*Commits\s*:?\s*\*\*', ln, re.IGNORECASE):
            continue
        ln = re.sub(r'^(\s*[-*]\s*)\[[xX]\]', r'\1[ ]', ln)
        linhas.append(ln.rstrip())
    while linhas and not linhas[-1]:
        linhas.pop()
    return '\n'.join(linhas) + '\n'


def hash_plano(texto):
    return sha1_bytes(plano_normalizado(texto).encode('utf-8'))[:16]


RE_SECAO_ONDA = re.compile(r'^##\s+Onda\s+(%s)\s*[—–-]' % RE_ONDA, re.IGNORECASE)


def selo_por_onda(texto):
    """(hash da parte comum, {onda: hash da seção dela}), sobre o plano normalizado. A seção vai do `## Onda N —`
    até o próximo título `## `; o resto (contexto, decisões, fora do escopo…) é a parte comum. Mudar uma onda
    não toca o selo das outras."""
    comum, ondas, atual = [], {}, None
    for ln in plano_normalizado(texto).splitlines():
        m = RE_SECAO_ONDA.match(ln)
        if m:
            atual = m.group(1)
            ondas[atual] = []
        elif ln.startswith('## '):
            atual = None
        (ondas[atual] if atual else comum).append(ln)
    h = lambda ls: sha1_bytes(('\n'.join(ls).rstrip() + '\n').encode('utf-8'))[:16]
    return h(comum), {k: h(v) for k, v in ondas.items()}


def hash_da_onda(texto, onda):
    """Selo do que a onda depende: a parte comum mais a seção dela."""
    comum, ondas = selo_por_onda(texto)
    return '%s.%s' % (comum, ondas.get(onda, '-'))


# ------------------------------------------------------------------------------ documentos

def texto_docx(caminho):
    """Texto corrido de um .docx (stdlib): parágrafos de word/document.xml, sem marcação."""
    import html
    import zipfile
    with zipfile.ZipFile(caminho) as z:
        xml = z.read('word/document.xml').decode('utf-8', 'replace')
    xml = re.sub(r'</w:p>', '\n', xml)
    xml = re.sub(r'<w:tab/>', '\t', xml)
    return html.unescape(re.sub(r'<[^>]+>', '', xml))


def texto_documento(caminho):
    """Texto de um documento da pasta do projeto (.docx pelo XML; o resto como texto)."""
    if caminho.lower().endswith('.docx'):
        return texto_docx(caminho)
    return ler(caminho)


def arquivo_plano_base(pasta, estado):
    """O plano base que substitui a análise, quando o usuário decidiu seguir sem ela; senão None."""
    sa = (estado or {}).get('sem_analise')
    if not isinstance(sa, dict) or not sa.get('plano_base'):
        return None
    arq = os.path.join(pasta, sa['plano_base'])
    return arq if os.path.isfile(arq) else None


def arquivos_er(pasta):
    import glob
    return sorted(glob.glob(os.path.join(pasta, 'ER*.docx')))


def linhas_novas(antigo, novo):
    """Números de linha de `novo` (caminho de arquivo) acrescentados ou alterados em relação a `antigo`
    (caminho de arquivo, p.ex. a cópia guardada na revisão anterior). None se o diff falhar."""
    proc = subprocess.run(['git', 'diff', '--no-index', '--no-color', '-U0', '--', antigo, novo],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    if proc.returncode not in (0, 1):
        return None
    linhas = set()
    for m in re.finditer(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', proc.stdout.decode('utf-8', 'replace'),
                         re.MULTILINE):
        ini, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        linhas.update(range(ini, ini + n))
    return linhas


def linhas_alteradas(repo, base, rel):
    """Números de linha (no arquivo atual) acrescentados ou alterados desde `base`. Arquivo não
    rastreado: todas. None se o arquivo não existe."""
    caminho = os.path.join(repo, rel)
    if not os.path.isfile(caminho):
        return None
    if rel in nao_rastreados(repo):
        with open(caminho, 'rb') as fh:
            return set(range(1, fh.read().count(b'\n') + 2))
    diff = git(repo, 'diff', '-U0', '--no-color', base, '--', rel, checar=False)
    linhas = set()
    for m in re.finditer(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', diff, re.MULTILINE):
        ini, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        linhas.update(range(ini, ini + n))
    return linhas
