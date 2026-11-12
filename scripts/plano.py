#!/usr/bin/env python3
"""Leitura e validação do `PLANO-NN-AAAA.md`.

O plano é documento seu; este módulo só o lê. O formato (ver referencias/formatos.md) é o de um
plano em ondas com duas coisas que o tornam conferível por máquina: aceite com ID (`A2.1`) e
tarefas (`#### T2.1 — …`) com campos fixos.

Duas regras vêm da `levantar-analise` e são o que este validador tem de mais duro:

- **Não existe seção de premissas.** Premissa é decisão tomada por quem não responde por ela. O
  que não foi perguntado vai como `[A VERIFICAR]`, e isso bloqueia a onda (ver onda.py).
- **Ponto em aberto da análise não some.** Cada linha de `## Pontos em aberto` da
  `analise-NN-AAAA.md` tem de aparecer em `## Pontos em aberto da análise` do plano, com a
  situação num vocabulário fechado (`Aberto`, `Respondido — D<n>`, `Fora desta entrega — D<n>`).
  Onda cuja origem é um assunto com ponto ainda aberto não começa.

E uma terceira, desta revisão: **nada no plano é inventado.** Aceite cita de onde vem o valor
(`(análise: ASSUNTO)`, `ER x.y`, `D<n>`); Origem é o assunto com a grafia exata da análise; toda
`D<n>` citada existe no livro de decisões (decisoes.py); assunto da análise sem onda só sai do
plano por decisão registrada em `## Fora do escopo`.

E uma quarta, que fecha o buraco entre o assunto e o item: **cada item do `**Funcional**` da
análise é coberto por um aceite ou sai do escopo por decisão do usuário.** O aceite aponta o item
pela posição, sem ID novo: `(análise: DESCONTO #2)` é o 2º item de primeiro nível do Funcional do
assunto DESCONTO (`#1-3` e `#1,3` valem). Os itens de `## Mudanças de comportamento` da análise
(quando são lista) respondem igual, como `(análise: Mudanças de comportamento #1)`. Num plano ainda
não aprovado a lacuna é erro; num já aprovado, aviso — não quebra o projeto em curso.
"""

import os
import re

import comum as C

CAMPOS_TAREFA = ['Repo', 'Onde', 'Aceite', 'Teste', 'Gate', 'Depende de', 'Commits']
GATES = {'rapido', 'completo', 'build', 'roteiro'}
RE_CAMPO = re.compile(r'^\s*[-*]?\s*\*\*(%s)\s*:?\s*\*\*\s*:?\s*(.*)$' % '|'.join(CAMPOS_TAREFA),
                      re.IGNORECASE)
RE_ONDA_TITULO = re.compile(r'^##\s+Onda\s+(%s)\s*[—–-]\s*(.+?)\s*$' % C.RE_ONDA, re.IGNORECASE)
RE_TAREFA_TITULO = re.compile(r'^####\s+(T(%s)\.(\d+))\s*[—–-]\s*(.+?)\s*$' % C.RE_ONDA)
RE_CHECK = re.compile(r'^\s*[-*]\s*\[( |x|X)\]\s*(.*)$')
RE_PREMISSA = re.compile(r'premissa|assumid|assumption', re.IGNORECASE)
A_VERIFICAR = '[A VERIFICAR]'
RE_A_VERIFICAR = re.compile(r'\[\s*a\s+verificar\s*\]', re.IGNORECASE)
# Premissa em texto corrido: a frase que assume em vez de perguntar.
RE_SUPOSICAO = re.compile(r'\b(sup[õo]e-se|supondo que|supomos|assumimos|assumindo que|presume-se|'
                          r'presumimos|parte-se do princ[íi]pio)\b', re.IGNORECASE)


class Plano(object):
    def __init__(self, caminho):
        self.caminho = caminho
        self.texto = C.ler(caminho) if os.path.exists(caminho) else ''
        self.titulo = ''
        self.decisoes_a_mao = []    # linhas D<n> fora do bloco gerado
        self.tem_bloco_decisoes = False
        self.fora_do_escopo = ''
        self.riscos = []
        self.matriz = {}            # repo -> [linhas]
        self.pontos = []            # [{assunto, pergunta, situacao}]
        self.ondas = []             # lista ordenada de dicts
        self.premissas = []         # linhas que denunciam seção/linha de premissa
        self.a_verificar_fora = 0
        self.secoes = set()
        if self.texto:
            self._ler()

    # -------------------------------------------------------------------- leitura
    def _ler(self):
        linhas = self.texto.splitlines()
        em_codigo = False
        for i, ln in enumerate(linhas):
            if ln.lstrip().startswith('```'):
                em_codigo = not em_codigo
                continue
            if em_codigo:
                continue
            if RE_SUPOSICAO.search(C.sem_riscado(re.sub(r'`[^`]*`', '', ln))):
                self.premissas.append('L%d: %s' % (i + 1, ln.strip()[:80]))
            m = re.match(r'^(#{1,4})\s+(.*)$', ln)
            if m:
                titulo = m.group(2).strip()
                if len(m.group(1)) == 1 and not self.titulo:
                    self.titulo = titulo
                if len(m.group(1)) == 2:
                    self.secoes.add(C.chave(titulo))
                if RE_PREMISSA.search(titulo):
                    self.premissas.append('L%d: %s' % (i + 1, ln.strip()))
            elif re.match(r'^\s*\*\*[^*]*(premissa|assumid)', ln, re.IGNORECASE):
                self.premissas.append('L%d: %s' % (i + 1, ln.strip()[:80]))

        # Decisões: só o bloco gerado pelo livro (`decisao add`). Linha D<n> fora dele é
        # decisão escrita à mão, sem prova de origem.
        corpo_dec = C.secao(self.texto, r'^decis') or ''
        self.tem_bloco_decisoes = '<!-- gerado:decisoes:inicio -->' in corpo_dec
        fora_bloco = C.RE_BLOCO_DECISOES.sub('', corpo_dec)
        for cel in C.linhas_de_tabela(fora_bloco):
            if cel and re.match(r'^~*D\d+', cel[0]):
                self.decisoes_a_mao.append(cel[0])
        self.fora_do_escopo = C.secao(self.texto, r'^fora d[oe] escopo') or ''
        for cel in C.linhas_de_tabela(C.secao(self.texto, r'^riscos')):
            if cel and re.match(r'^R\d+$', cel[0]):
                self.riscos.append((cel[0], ' | '.join(cel[1:])))
        for cel in C.linhas_de_tabela(C.secao(self.texto, r'^matriz de gate')):
            if cel and cel[0]:
                self.matriz.setdefault(cel[0].strip('`').strip(), []).append(cel[1:])
        for cel in C.linhas_de_tabela(C.secao(self.texto, r'^pontos em aberto')):
            if len(cel) >= 3:
                self.pontos.append({'assunto': cel[0], 'pergunta': cel[1], 'situacao': cel[2]})

        self._ler_ondas(linhas)

    def _ler_ondas(self, linhas):
        atual = None
        tarefa = None
        em_aceite = False
        fora = []
        for i, ln in enumerate(linhas):
            m = RE_ONDA_TITULO.match(ln)
            if m:
                atual = {'id': m.group(1), 'titulo': m.group(2), 'linha': i + 1,
                         'origem': '', 'risco': '', 'so_testes': False, 'tamanho': '', 'aceites': {}, 'ordem_aceites': [],
                         'tarefas': {}, 'ordem_tarefas': [], 'a_verificar': 0, 'texto': []}
                self.ondas.append(atual)
                tarefa = None
                em_aceite = False
                continue
            if atual is not None and re.match(r'^#{1,2} ', ln):
                atual = None  # saiu da onda (outra seção ## ou # )
                tarefa = None
            if atual is None:
                fora.append(ln)
                continue
            atual['texto'].append(ln)
            if RE_A_VERIFICAR.search(C.sem_riscado(ln)):
                atual['a_verificar'] += len(RE_A_VERIFICAR.findall(C.sem_riscado(ln)))
            mo = re.match(r'^\s*\*\*Origem:?\*\*:?\s*(.*)$', ln, re.IGNORECASE)
            if mo:
                atual['origem'] = mo.group(1).strip()
                continue
            mt = re.match(r'^\s*\*\*Tamanho:?\*\*:?\s*(.*)$', ln, re.IGNORECASE)
            if mt:
                atual['tamanho'] = mt.group(1).strip()
                continue
            ms = re.match(r'^\s*\*\*S[óo] testes:?\*\*:?\s*(.*)$', ln, re.IGNORECASE)
            if ms:
                atual['so_testes'] = C.chave(ms.group(1)).startswith('sim')
                continue
            mr = re.match(r'^\s*\*\*Risco:?\*\*:?\s*(.*)$', ln, re.IGNORECASE)
            if mr:
                atual['risco'] = C.chave(mr.group(1)).split(' ')[0] if mr.group(1).strip() else ''
                continue
            if re.match(r'^\s*\*\*Aceite\b', ln, re.IGNORECASE):
                em_aceite = True
                continue
            mt = RE_TAREFA_TITULO.match(ln)
            if mt:
                em_aceite = False
                tarefa = {'id': mt.group(1), 'onda': mt.group(2), 'titulo': mt.group(4),
                          'linha': i + 1, 'campos': {}}
                atual['tarefas'].setdefault(mt.group(1), tarefa)
                atual['ordem_tarefas'].append(mt.group(1))
                continue
            if re.match(r'^###\s', ln):
                em_aceite = False
                tarefa = None
                continue
            if tarefa is not None:
                mc = RE_CAMPO.match(ln)
                if mc:
                    nome = [c for c in CAMPOS_TAREFA if c.lower() == mc.group(1).lower()][0]
                    tarefa['campos'][nome] = mc.group(2).strip()
                continue
            mk = RE_CHECK.match(ln)
            if mk and em_aceite:
                corpo = mk.group(2)
                ma = re.match(r'^(~~)?\s*(A(%s)\.(\d+))\b' % C.RE_ONDA, corpo)
                if ma:
                    # Reclassificado = riscado **e** com a decisão do usuário (D<n>) fora do
                    # riscado. Riscar sem decisão é o modelo tirando um aceite sozinho.
                    reclass = bool(ma.group(1)) and bool(
                        re.search(r'\bD\d+\b', re.sub(r'~~.*?~~', '', corpo)))
                    atual['aceites'][ma.group(2)] = {
                        'texto': corpo, 'marcado': mk.group(1).lower() == 'x',
                        'riscado': bool(ma.group(1)), 'reclassificado': reclass,
                        'linha': i + 1, 'onda_id': ma.group(3)}
                    atual['ordem_aceites'].append(ma.group(2))
                else:
                    atual.setdefault('aceites_sem_id', []).append(i + 1)
        # O bloco gerado de decisoes e registro do livro (texto e citacao do usuario), nao pendencia do plano:
        # uma resposta como 'Fica [A VERIFICAR]' bloquearia todas as ondas para sempre.
        fora = C.RE_BLOCO_DECISOES.sub('', '\n'.join(fora)).splitlines()
        self.a_verificar_fora = sum(len(RE_A_VERIFICAR.findall(C.sem_riscado(l))) for l in fora)

    # -------------------------------------------------------------------- consultas
    def onda(self, oid):
        for o in self.ondas:
            if o['id'] == oid:
                return o
        return None

    def tarefa(self, tid):
        for o in self.ondas:
            if tid in o['tarefas']:
                return o['tarefas'][tid]
        return None

    def indice_onda(self, oid):
        for i, o in enumerate(self.ondas):
            if o['id'] == oid:
                return i
        return -1


# ------------------------------------------------------------------------ campos da tarefa

def lista_ids(texto, regex):
    return [m.group(0) for m in regex.finditer(texto or '')]


def onde_de(tarefa):
    bruto = tarefa['campos'].get('Onde', '')
    entre_crases = re.findall(r'`([^`]+)`', bruto)
    itens = entre_crases or [p.strip() for p in re.split(r'[,;]', bruto)]
    return [i for i in itens if i and i not in ('—', '-')]


def repo_de(tarefa):
    return tarefa['campos'].get('Repo', '').strip().strip('`').strip()


def gate_de(tarefa):
    g = C.chave(tarefa['campos'].get('Gate', '')).split(' ')
    return g[0] if g and g[0] else ''


def teste_de(tarefa):
    return tarefa['campos'].get('Teste', '').strip()


def teste_automatizado(tarefa):
    """Tarefa cujo teste é automatizado: não é `nenhum` nem `roteiro`."""
    t = C.chave(teste_de(tarefa))
    return bool(t) and not t.startswith('nenhum') and not t.startswith('roteiro') \
        and gate_de(tarefa) != 'roteiro'


def classes_de_teste(tarefa):
    """Classes (ou globs de classe) citadas entre crases no campo Teste."""
    return [c for c in re.findall(r'`([^`]+)`', teste_de(tarefa))
            if re.match(r'^[A-Za-z_][\w*]*$', c)]


def aceites_com_teste(onda):
    ids = set()
    for t in onda['tarefas'].values():
        if teste_automatizado(t):
            ids.update(lista_ids(t['campos'].get('Aceite', ''), C.RE_ACEITE))
    return ids


# ------------------------------------------------------------------------ análise

MUDANCAS = 'Mudanças de comportamento'
RE_BLOCO_ANALISE = re.compile(r'^\*\*([^*]+)\*\*')


def _itens_de_primeiro_nivel(linhas, bloco=None):
    """Itens `- ` sem indentação. Com `bloco`, só os do bloco `**<bloco>**` (o Funcional de um
    assunto); sem ele, todos. A posição nessa lista é o `#n` do aceite: sub-item indentado é
    desdobramento do item, não item."""
    itens, dentro = [], bloco is None
    for ln in linhas:
        if bloco is not None and not ln[:1].isspace():
            m = RE_BLOCO_ANALISE.match(ln.strip())
            if m:
                dentro = C.chave(m.group(1)) == C.chave(bloco)
                continue
        if dentro and ln.startswith(('- ', '* ')):
            itens.append(ln[2:].strip())
        elif dentro and bloco is not None and ln.strip() and not ln[:1].isspace():
            dentro = False                      # prosa na margem fecha o bloco
    return itens


def ler_analise(pasta):
    """Assuntos (### sob Requisitos por assunto), itens do Funcional de cada um, Mudanças de
    comportamento e Fora do escopo (itens de lista) e Pontos em aberto da análise, se ela existir."""
    arq = C.arquivo_analise(pasta)
    if not os.path.exists(arq):
        return None
    texto = C.ler(arq)
    corpo = C.secao(texto, r'^requisitos por assunto') or ''
    assuntos = [m.group(1).strip() for m in re.finditer(r'^###\s+(.+)$', corpo, re.MULTILINE)]
    funcional, atual = {}, None
    for ln in corpo.splitlines():
        m = re.match(r'^###\s+(.+)$', ln)
        if m:
            atual = m.group(1).strip()
            funcional[atual] = []
        elif atual is not None:
            funcional[atual].append(ln)
    funcional = {a: _itens_de_primeiro_nivel(ls, 'Funcional') for a, ls in funcional.items()}
    pontos = []
    for cel in C.linhas_de_tabela(C.secao(texto, r'^pontos em aberto')):
        if len(cel) >= 2 and cel[1]:
            pontos.append({'assunto': cel[0], 'pergunta': cel[1]})
    mudancas = _itens_de_primeiro_nivel((C.secao(texto, r'^mudan[cç]as de comportamento') or '').splitlines())
    fora = _itens_de_primeiro_nivel((C.secao(texto, r'^fora d[oe] escopo') or '').splitlines())
    return {'arquivo': arq, 'assuntos': assuntos, 'pontos': pontos, 'funcional': funcional,
            'mudancas': mudancas, 'fora': fora}


def itens_a_cobrir(analise):
    """{chave do assunto: (nome, [itens])} que o plano tem de cobrir: o Funcional de cada assunto e
    as Mudanças de comportamento (só quando são lista; "Nenhuma." em prosa não tem o que cobrir)."""
    cobrir = {C.chave(a): (a, itens) for a, itens in (analise.get('funcional') or {}).items() if itens}
    if analise.get('mudancas'):
        cobrir[C.chave(MUDANCAS)] = (MUDANCAS, analise['mudancas'])
    return cobrir


def _mesma_pergunta(a, b):
    """A pergunta é copiada da análise: casa pelo texto inteiro normalizado, não por prefixo
    (duas perguntas do 112 começam igual e só divergem no fim)."""
    return C.chave(re.sub(r'[`*]', '', a)) == C.chave(re.sub(r'[`*]', '', b))


RE_ER = re.compile(r'^ER\s+\d+(\.\d+)*(\s*[–-]\s*\d+(\.\d+)*)?$', re.IGNORECASE)
RE_ANCORA_ANALISE = re.compile(r'\(an[aá]lise:\s*([^)]+)\)', re.IGNORECASE)
RE_ITENS_ANCORA = re.compile(r'^(?P<assunto>.+?)\s+#(?P<itens>\d+(?:\s*[-–,]\s*#?\d+)*)\s*$')


def partir_ancora(texto):
    """`DESCONTO #2` -> ('DESCONTO', {2}); `DESCONTO #1-3` -> ('DESCONTO', {1, 2, 3});
    `DESCONTO` -> ('DESCONTO', None), que é o assunto inteiro (a âncora de antes dos itens)."""
    texto = texto.strip()
    m = RE_ITENS_ANCORA.match(texto)
    if not m:
        return texto, None
    itens = set()
    for parte in re.split(r'\s*,\s*', m.group('itens')):
        m2 = re.fullmatch(r'#?(\d+)\s*[-–]\s*#?(\d+)', parte.strip())
        if m2:
            itens.update(range(int(m2.group(1)), int(m2.group(2)) + 1))
        else:
            itens.add(int(parte.strip().lstrip('#')))
    return m.group('assunto').strip(), itens
RE_ANCORA_ER = re.compile(r'\bER\s+\d+(\.\d+)*', re.IGNORECASE)


def porte(onda):
    """Porte da onda: `leve` (até 4 tarefas e risco normal), `grande` (mais de 10 tarefas) ou
    `normal`. O rito acompanha o porte: a onda pequena não paga o preço da grande."""
    n = len(onda.get('ordem_tarefas') or [])
    if n <= 4 and onda.get('risco') == 'normal':
        return 'leve'
    return 'grande' if n > 10 else 'normal'


def origens(onda):
    """Partes da **Origem:**, separadas por `;`: assunto da análise, `ER x.y`, `D<n>` ou `P<n>`
    (pendência levada de uma onda anterior)."""
    return [x.strip().strip('`').strip() for x in (onda.get('origem') or '').split(';') if x.strip()]


def assuntos_de_origem(onda):
    return {C.chave(x) for x in origens(onda) if not RE_ER.match(x) and not re.fullmatch(r'[DP]\d+', x)}


def situacao_ponto(texto):
    """('respondido' | 'fora' | 'aberto' | None, [D<n>]) — vocabulário fechado da Situação."""
    t = C.chave(re.sub(r'[*~`]', '', texto or ''))
    ds = ['D' + n for n in decisoes_citadas(texto)]
    if t.startswith('aberto'):
        return 'aberto', ds
    if t.startswith('respondido') and ds:
        return 'respondido', ds
    if t.startswith('fora desta entrega') and ds:
        return 'fora', ds
    return None, ds


def decisoes_citadas(texto):
    return [m.group(1) for m in re.finditer(r'\bD(\d+)\b', C.sem_riscado(texto or ''))]


def decisoes_do_usuario(estado, texto):
    """As D<n> citadas no texto que são do usuário (fonte usuario) e vigentes. Tirar aceite,
    dispensar teste, tirar assunto do escopo e responder ponto em aberto são decisões dele; uma
    decisão tirada da análise ou da ER não autoriza nada disso."""
    livro = {d['id']: d for d in (estado or {}).get('decisoes', [])}
    return [n for n in decisoes_citadas(texto)
            if livro.get('D' + n, {}).get('fonte') == 'usuario' and not livro['D' + n].get('revogada_por')]


def pontos_abertos_da_onda(plano, analise, onda):
    """Pontos da análise que bloqueiam a onda: o assunto do ponto é origem da onda e a situação
    no plano não é `Respondido — D<n>` nem `Fora desta entrega — D<n>`."""
    if not analise:
        return []
    assuntos = assuntos_de_origem(onda)
    bloqueantes = []
    for p in analise['pontos']:
        if C.chave(p['assunto']) not in assuntos:
            continue
        tratado = [q for q in plano.pontos if _mesma_pergunta(q['pergunta'], p['pergunta'])]
        sit = situacao_ponto(tratado[0]['situacao'])[0] if tratado else None
        if sit not in ('respondido', 'fora'):
            bloqueantes.append(p['pergunta'])
    return bloqueantes


# ------------------------------------------------------------------------ validação

def _conferir_ds(rel, estado, texto, onde):
    """Toda D<n> citada tem de estar no livro e não estar revogada."""
    livro = {d['id']: d for d in (estado or {}).get('decisoes', [])}
    for n in decisoes_citadas(texto):
        d = livro.get('D' + n)
        if not d:
            rel.erro('%s cita D%s, que não está no livro de decisões (`decisao add`)' % (onde, n))
        elif d.get('revogada_por'):
            rel.erro('%s cita D%s, revogada por %s' % (onde, n, d['revogada_por']))


def validar(pasta, estado=None):
    if estado is None:
        estado = C.carregar_estado(pasta)
    arq = C.arquivo_plano(pasta)
    rel = C.Relatorio('validar-plano: %s' % os.path.basename(arq))
    if not os.path.exists(arq):
        rel.erro('plano não encontrado: %s' % arq)
        return rel, None
    p = Plano(arq)
    analise = ler_analise(pasta)
    assuntos_analise = {C.chave(a): a for a in (analise or {}).get('assuntos', [])}

    for nome, rx in (('Contexto', r'^contexto'), ('Decisões', r'^decis'),
                     ('Fora do escopo', r'^fora d[oe] escopo'), ('Matriz de gate', r'^matriz de gate')):
        if C.secao(p.texto, rx) is None:
            rel.erro('seção obrigatória ausente: ## %s' % nome)
    if C.secao(p.texto, r'^riscos') is None:
        rel.aviso('sem seção ## Riscos')

    for linha in p.premissas:
        rel.erro('premissa no plano (%s) — o que não foi perguntado vira [A VERIFICAR], '
                 'que bloqueia a onda; premissa é decisão tomada por quem não responde por ela' % linha)

    # decisões: só o livro
    if C.secao(p.texto, r'^decis') is not None and not p.tem_bloco_decisoes:
        rel.erro('## Decisões sem o bloco <!-- gerado:decisoes:inicio --> / <!-- gerado:decisoes:fim --> '
                 '— a tabela é gerada do livro (`decisao add`)')
    for d in p.decisoes_a_mao:
        rel.erro('decisão %s escrita à mão em ## Decisões — decisão só entra por `decisao add`, '
                 'com a fonte conferida' % d)
    _conferir_ds(rel, estado, C.RE_BLOCO_DECISOES.sub('', p.texto), 'o plano')
    _unicos(rel, [r[0] for r in p.riscos], 'risco')

    if not p.ondas:
        rel.erro('nenhuma onda: esperado "## Onda N — <assunto>"')
    _unicos(rel, [o['id'] for o in p.ondas], 'onda')

    repos_cfg = estado.get('repos', {})
    todas_tarefas = {}
    for o in p.ondas:
        for tid in o['ordem_tarefas']:
            if tid in todas_tarefas:
                rel.erro('tarefa %s duplicada' % tid)
            todas_tarefas[tid] = o['id']

    for idx, o in enumerate(p.ondas):
        pre = 'Onda %s: ' % o['id']
        if not o['origem']:
            rel.erro(pre + 'sem **Origem:** (assunto da análise, coordenada da ER ou D<n>)')
        for parte in origens(o):
            if RE_ER.match(parte) or re.fullmatch(r'D\d+', parte):
                continue
            if re.fullmatch(r'P\d+', parte):
                if not any(x['id'] == parte for x in (estado or {}).get('pendencias', [])):
                    rel.erro(pre + 'Origem %s: pendência inexistente (`pendencia list`)' % parte)
                continue
            if analise is None:
                rel.erro(pre + 'Origem %r: sem análise na pasta, a origem só pode ser ER x.y ou D<n>' % parte)
            elif C.chave(parte) not in assuntos_analise:
                rel.erro(pre + 'Origem %r não é assunto da análise (grafia exata do "### ASSUNTO"; '
                         'separe vários por ";")' % parte)
        if o['risco'] not in ('normal', 'alto'):
            rel.erro(pre + '**Risco:** tem de ser "normal" ou "alto" (é o que decide o mínimo de mutantes)')
        if not o['aceites']:
            rel.erro(pre + 'sem itens de aceite com ID ("- [ ] A%s.1 …")' % o['id'])
        for ln in o.get('aceites_sem_id', []):
            rel.erro(pre + 'item de aceite sem ID na linha %d' % ln)
        for aid, a in o['aceites'].items():
            if a['onda_id'] != o['id']:
                rel.erro(pre + 'aceite %s pertence a outra onda' % aid)
            _conferir_ancora(rel, pre, aid, a, assuntos_analise, analise)
            if a['riscado'] and not decisoes_do_usuario(estado, re.sub(r'~~.*?~~', '', a['texto'])):
                rel.erro(pre + 'aceite %s riscado sem a decisão do usuário que o tirou (D<n> depois '
                         'do riscado)' % aid)
        _unicos(rel, o['ordem_aceites'], 'aceite', pre)
        if not o['tarefas']:
            rel.erro(pre + 'sem tarefas ("#### T%s.1 — …")' % o['id'])
        elif len(o['ordem_tarefas']) > 10:
            # tlc: fase acima de ~10 tarefas é sinal de corte errado, e onda grande é revisão de muitas
            # rodadas. Acima de 15 é decisão do usuário; onda já fechada fica como está.
            fechada = (estado or {}).get('ondas', {}).get(o['id'], {}).get('estado') in C.TERMINAIS
            if len(o['ordem_tarefas']) > 15 and not fechada and not decisoes_do_usuario(estado, o.get('tamanho')):
                rel.erro(pre + '%d tarefas — acima de 15 é decisão do usuário: divida a onda num ponto real '
                         'de dependência, ou registre a decisão dele e escreva `**Tamanho:** D<n>` na onda'
                         % len(o['ordem_tarefas']))
            else:
                rel.aviso(pre + '%d tarefas — onda grande demais? Divida num ponto real de dependência '
                          '(revisão e mutantes cobrem a onda inteira de uma vez)%s'
                          % (len(o['ordem_tarefas']), ' (tamanho autorizado: %s)' % o['tamanho'] if o.get('tamanho') else ''))
        # Achado fora dos aceites, da 2ª revisão em diante, vai para a próxima onda: a onda que cresce
        # a cada rodada não converge.
        revs_onda = [r_ for r_ in (estado or {}).get('revisoes', []) if r_['onda'] == o['id']]
        eo_ = (estado or {}).get('ondas', {}).get(o['id'], {})
        if revs_onda and eo_.get('estado') in ('em_execucao', 'bloqueada'):
            import revisao as RVS
            iniciais = RVS.aceites_da_revisao(pasta, revs_onda[0])
            novos = [a_ for a_ in RVS.aceites_ativos(o) if iniciais is not None and a_ not in iniciais]
            t_iniciais = revs_onda[0].get('tarefas')
            t_novas = [t_ for t_ in o['ordem_tarefas'] if t_iniciais is not None and t_ not in t_iniciais]
            if novos or t_novas:
                # Escopo congela na 1ª revisão. Lacuna se corrige sob a tarefa dona do aceite
                # (`commit --correcao RV<k>`); requisito novo vira pendência (`pendencia add`) e entra
                # numa onda seguinte.
                rel.erro(pre + 'escopo congelado desde a 1ª revisão (%s): %s — correção de lacuna vai '
                         'sob a tarefa dona do aceite (`commit --correcao RV<k>`); o que é novo vira '
                         '`pendencia add` e outra onda' % (revs_onda[0]['id'], ', '.join(novos + t_novas)))
        cobertos = set()
        for tid in o['ordem_tarefas']:
            t = o['tarefas'][tid]
            pt = pre + tid + ': '
            if t['onda'] != o['id']:
                rel.erro(pt + 'ID não pertence à onda %s' % o['id'])
            for campo in ('Repo', 'Onde', 'Aceite', 'Teste', 'Gate'):
                if not t['campos'].get(campo):
                    rel.erro(pt + 'campo **%s:** ausente ou vazio' % campo)
            if o.get('so_testes'):
                # A marca afrouxa o gate de mutantes (linha anterior à onda conta, se um teste da onda
                # a pegou); por isso a onda não pode ter uma linha de produção sequer.
                import mutantes as M
                for arq in onde_de(t):
                    if not M._eh_teste(arq):
                        rel.erro(pt + 'a onda é **Só testes** e o Onde tem arquivo de produção: %s' % arq)
            repo = repo_de(t)
            if repo and p.matriz and repo not in p.matriz:
                rel.erro(pt + 'repo %r fora da Matriz de gate (%s)' % (repo, ', '.join(sorted(p.matriz))))
            if repo and repo not in repos_cfg:
                rel.aviso(pt + 'repo %r ainda não configurado (`demanda.py configurar`)' % repo)
            g = gate_de(t)
            if t['campos'].get('Gate') and g not in GATES:
                rel.erro(pt + 'Gate %r inválido — use rapido, completo, build ou roteiro' % g)
            aceites = lista_ids(t['campos'].get('Aceite', ''), C.RE_ACEITE)
            if t['campos'].get('Aceite') and not aceites:
                rel.erro(pt + 'campo Aceite sem ID (A%s.k)' % o['id'])
            for aid in aceites:
                if aid not in o['aceites']:
                    rel.erro(pt + 'aponta aceite inexistente nesta onda: %s' % aid)
                cobertos.add(aid)
            onde = onde_de(t)
            if len(onde) > 3:
                rel.aviso(pt + '%d itens em Onde — tarefa grande demais? (tlc: uma tarefa, um entregável)' % len(onde))
            if teste_automatizado(t) and not classes_de_teste(t):
                rel.aviso(pt + 'Teste automatizado sem classe entre crases — o fechamento não '
                               'consegue conferir que ela rodou')
            teste = C.chave(teste_de(t))
            cfg = repos_cfg.get(repo) or {}
            if teste.startswith('nenhum') and cfg and not cfg.get('sem_testes_automatizados') \
                    and not decisoes_do_usuario(estado, teste_de(t)):
                rel.erro(pt + '"Teste: nenhum" num repositório com suíte — cite a decisão do '
                               'usuário que dispensou o teste (D<n>)')
            for dep in lista_ids(t['campos'].get('Depende de', ''), C.RE_TAREFA):
                if dep not in todas_tarefas:
                    rel.erro(pt + 'depende de tarefa inexistente %s' % dep)
                elif p.indice_onda(todas_tarefas[dep]) > idx:
                    rel.erro(pt + 'depende de %s, de uma onda posterior' % dep)
        for aid in o['ordem_aceites']:
            a = o['aceites'][aid]
            if aid not in cobertos and not a['riscado']:
                rel.erro(pre + 'aceite %s sem tarefa que o entregue' % aid)
        if not o.get('so_testes'):
            # Aceite cujas tarefas só mexem em teste conta mutante em linha anterior à onda (se morreu
            # por asserção num teste da onda): afrouxa o mínimo, então o usuário vê isso ao aprovar.
            import onda as OND
            brandos = [aid for aid in o['ordem_aceites'] if OND.aceite_so_de_testes(o, aid)]
            if brandos:
                rel.aviso(pre + 'aceite(s) só de testes (%s): o mutante em linha anterior à onda conta '
                          'para eles, se morrer por asserção num teste da onda' % ', '.join(brandos))
        if o['a_verificar']:
            rel.aviso(pre + '%d [A VERIFICAR] — a onda não inicia enquanto houver' % o['a_verificar'])
    if p.a_verificar_fora:
        rel.aviso('%d [A VERIFICAR] fora das ondas — nenhuma onda inicia enquanto houver' % p.a_verificar_fora)

    # pontos em aberto: vocabulário fechado
    for q in p.pontos:
        sit, _ds = situacao_ponto(q['situacao'])
        if sit is None:
            rel.erro('ponto em aberto %r: Situação %r fora do vocabulário — "Aberto", '
                     '"Respondido — D<n>" ou "Fora desta entrega — D<n>"'
                     % (q['pergunta'][:60], q['situacao']))
        elif sit in ('respondido', 'fora') and not decisoes_do_usuario(estado, q['situacao']):
            rel.erro('ponto em aberto %r: %s sem decisão do usuário — a D<n> citada tem de ter fonte '
                     'usuario (resposta dele, com citação)' % (q['pergunta'][:60], q['situacao']))

    if analise is None:
        # Sem análise nem ER, todo esperado acaba ancorado só em decisões e nenhum ponto em aberto
        # bloqueia nada: é seguir sem o documento que o método pressupõe, e isso é do usuário.
        sem_doc = not C.arquivos_er(pasta)
        import decisoes as DC
        sa = estado.get('sem_analise')
        base = C.arquivo_plano_base(pasta, estado)
        autorizado = isinstance(sa, dict) and base and not DC.exigir(estado, sa.get('decisao'))
        if sem_doc and not autorizado:
            rel.erro('sem %s e sem documento de requisitos — pontos em aberto e origens não têm contra o que ser conferidos. '
                     'Forneça a análise (%s ou requisitos) ou registre a decisão do usuário de seguir '
                     'com o plano base: `validar-plano --sem-analise D<n> --plano-base <arquivo>`'
                     % (os.path.basename(C.arquivo_analise(pasta)), os.path.basename(C.arquivo_analise(pasta))))
        else:
            rel.aviso('sem %s — rastreabilidade com a análise não conferida%s'
                      % (os.path.basename(C.arquivo_analise(pasta)),
                         ' (seguindo com o plano base %s, por %s)' % (sa['plano_base'], sa['decisao'])
                         if sem_doc else ''))
    else:
        cobertos_por_onda = set()
        for o in p.ondas:
            cobertos_por_onda |= assuntos_de_origem(o)
        for assunto in analise['assuntos']:
            if C.chave(assunto) in cobertos_por_onda:
                continue
            linha = [ln for ln in p.fora_do_escopo.splitlines() if C.chave(assunto) in C.chave(ln)]
            if not linha or not decisoes_do_usuario(estado, ' '.join(linha)):
                rel.erro('assunto da análise sem onda: %s — ou uma onda o cobre (Origem), ou ele vai '
                         'para ## Fora do escopo com a decisão do usuário (D<n>)' % assunto)
        conferir_cobertura_dos_itens(rel, p, estado, analise)
        for ponto in analise['pontos']:
            tratado = [q for q in p.pontos if _mesma_pergunta(q['pergunta'], ponto['pergunta'])]
            if not tratado:
                rel.erro('ponto em aberto da análise ausente de "## Pontos em aberto da análise" '
                         '(copie a pergunta literal): %s' % ponto['pergunta'][:90])
                continue
            sit = situacao_ponto(tratado[0]['situacao'])[0]
            if sit != 'fora' and C.chave(ponto['assunto']) not in cobertos_por_onda:
                rel.erro('ponto em aberto de %r, assunto que nenhuma onda tem na Origem, e não está '
                         '"Fora desta entrega — D<n>": %s' % (ponto['assunto'], ponto['pergunta'][:70]))
        for o in p.ondas:
            for perg in pontos_abertos_da_onda(p, analise, o):
                rel.aviso('Onda %s: ponto em aberto ainda sem resposta — %s' % (o['id'], perg[:90]))
    cobertas = {x for o in p.ondas for x in origens(o) if re.fullmatch(r'P\d+', x)}
    for pend in (estado or {}).get('pendencias', []):
        if pend['id'] not in cobertas and not pend.get('descartada'):
            rel.aviso('pendência %s (da onda %s, %s) sem onda que a tenha na Origem: %s'
                      % (pend['id'], pend['onda'], pend['origem'], pend['texto'][:80]))
    # Onda encerrada é histórico: a seção dela não muda depois de aprovada (marcar [x] e **Commits:** não conta).
    import decisoes as DC
    aprovadas = DC.ondas_aprovadas(estado or {})
    _comum, ondas_agora = C.selo_por_onda(p.texto)
    for o in p.ondas:
        eo_ = (estado or {}).get('ondas', {}).get(o['id']) or {}
        if eo_.get('estado') in C.TERMINAIS and aprovadas.get(o['id']) and ondas_agora.get(o['id']) != aprovadas[o['id']]:
            rel.erro('Onda %s: a seção mudou depois da aprovação e a onda já está %s — o histórico não muda; o que '
                     'falta vai para uma onda nova' % (o['id'], eo_['estado']))
    return rel, p


def _conferir_ancora(rel, pre, aid, a, assuntos_analise, analise):
    """Aceite sem origem é critério inventado: tem de citar a análise, a ER ou uma decisão."""
    texto = C.sem_riscado(a['texto'])
    ancoras = RE_ANCORA_ANALISE.findall(texto)
    if not ancoras and not RE_ANCORA_ER.search(texto) and not decisoes_citadas(texto):
        if not a['riscado']:
            rel.erro(pre + 'aceite %s sem origem — cite "(análise: <ASSUNTO> #n)", "ER x.y" ou a decisão D<n> '
                     'de onde vem o valor' % aid)
        return
    cobrir = itens_a_cobrir(analise) if analise else {}
    for ancora in ancoras:
        assunto, itens = partir_ancora(ancora)
        chave = C.chave(assunto)
        if analise is None or (chave not in assuntos_analise and chave not in cobrir):
            rel.erro(pre + 'aceite %s cita "(análise: %s)", que não é assunto da análise' % (aid, ancora.strip()))
        elif itens and chave in cobrir:
            total = len(cobrir[chave][1])
            for n in sorted(itens):
                if not 1 <= n <= total:
                    rel.erro(pre + 'aceite %s cita "(análise: %s)", mas %s tem %d item(ns) em %s'
                             % (aid, ancora.strip(), cobrir[chave][0], total,
                                'Mudanças de comportamento' if chave == C.chave(MUDANCAS)
                                else '**Funcional**'))
        elif itens:
            rel.erro(pre + 'aceite %s cita "(análise: %s)", mas %r não tem itens em **Funcional** '
                     'para numerar' % (aid, ancora.strip(), assunto))


def _itens_citados(p):
    """{chave do assunto: {n}} que os aceites não riscados citam como `(análise: ASSUNTO #n)`."""
    citados = {}
    for o in p.ondas:
        for a in o['aceites'].values():
            if a['riscado']:
                continue
            for ancora in RE_ANCORA_ANALISE.findall(C.sem_riscado(a['texto'])):
                assunto, itens = partir_ancora(ancora)
                if itens:
                    citados.setdefault(C.chave(assunto), set()).update(itens)
    return citados


def _item_fora_do_escopo(p, estado, chave, n):
    """O item `n` do assunto está em `## Fora do escopo` do plano com decisão do usuário? A linha
    nomeia o assunto; sem `#n` ela tira o assunto inteiro, com `#n` só os itens que cita."""
    for ln in p.fora_do_escopo.splitlines():
        if chave not in C.chave(ln) or not decisoes_do_usuario(estado, ln):
            continue
        refs = {int(x) for x in re.findall(r'#(\d+)', ln)}
        if not refs or n in refs:
            return True
    return False


def conferir_cobertura_dos_itens(rel, p, estado, analise):
    """Cada item do Funcional (e das Mudanças de comportamento) da análise é citado por um aceite
    ou sai do escopo por decisão do usuário. Num plano já aprovado vira aviso: o gate não derruba um
    plano que o usuário já aprovou."""
    registrar = rel.aviso if (estado or {}).get('aprovacoes_plano') else rel.erro
    citados = _itens_citados(p)
    for chave, (nome, itens) in itens_a_cobrir(analise).items():
        faltam = [n for n in range(1, len(itens) + 1)
                  if n not in citados.get(chave, set()) and not _item_fora_do_escopo(p, estado, chave, n)]
        for n in faltam:
            registrar('item #%d de %s sem aceite — %s: ou um aceite o cita "(análise: %s #%d)", ou ele '
                      'vai para ## Fora do escopo ("%s #%d") com a decisão do usuário (D<n>)'
                      % (n, nome, itens[n - 1][:70], nome, n, nome, n))
    # O que a análise já deixou fora do escopo não pode sumir do plano.
    for item in analise.get('fora') or []:
        cabeca = C.chave(item.split(':', 1)[0])
        if cabeca and cabeca not in C.chave(p.fora_do_escopo):
            rel.aviso('item de "Fora do escopo" da análise ausente do plano — %s' % item[:80])


def _unicos(rel, ids, nome, pre=''):
    vistos = set()
    for i in ids:
        if i in vistos:
            rel.erro('%s%s %s duplicado(a)' % (pre, nome, i))
        vistos.add(i)


# ------------------------------------------------------------------------ escrita pontual

def registrar_commits(pasta, tid, hashes):
    """Escreve (ou reescreve) a linha `- **Commits:**` da tarefa no plano. Uma das duas escritas
    do script no plano; a outra é o bloco gerado de decisões (decisoes.renderizar)."""
    arq = C.arquivo_plano(pasta)
    linhas = C.ler(arq).splitlines()
    inicio = None
    for i, ln in enumerate(linhas):
        m = RE_TAREFA_TITULO.match(ln)
        if m and m.group(1) == tid:
            inicio = i
            break
    if inicio is None:
        return False
    fim = len(linhas)
    for j in range(inicio + 1, len(linhas)):
        if re.match(r'^#{1,4}\s', linhas[j]):
            fim = j
            break
    valor = '- **Commits:** ' + ', '.join('`%s`' % h for h in hashes)
    ultimo_campo = inicio
    for j in range(inicio + 1, fim):
        mc = RE_CAMPO.match(linhas[j])
        if mc and mc.group(1).lower() == 'commits':
            linhas[j] = valor
            break
        if mc:
            ultimo_campo = j
    else:
        linhas.insert(ultimo_campo + 1, valor)
    C.gravar(arq, '\n'.join(linhas) + '\n')
    return True
