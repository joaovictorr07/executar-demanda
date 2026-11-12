"""Modelo do grafo de rastreabilidade do projeto — análise, ER, ET, esboços, plano, ondas, tarefas, aceites e a
execução (commits, testes, mutantes, revisões, pendências, decisões) — e as lacunas entre eles.

Só leitura: lê os arquivos do projeto e não grava nada. `montar` devolve `{nodes, edges, lacunas, ...}` com o
layout em fluxo já calculado; `compactar` o deixa no formato que a página embute. A página (o painel, aba Grafo)
é `estado.painel_html`; o subcomando `grafo` só atalha para ela."""
import json
import os
import re
import webbrowser

import comum as C
import plano as P
import testes as T

# Nós que o desenho recolhe por padrão: há centenas num projeto real e escondem a estrutura.
RECOLHIDOS = ('mutante', 'execucao', 'commit', 'er_req', 'et_req')
RE_COORD = re.compile(r'<!--\s*(\d+(?:\.\d+)*)(?:\s+#([A-Za-z0-9][A-Za-z0-9_-]*))?\s*-->\s*$')
RE_PRINT = re.compile(r'^\[\[PRINT:\s*(.+?)\s*\]\]$')
RE_COORD_ER = re.compile(r'\d+(?:\.\d+)*')
PROFUNDIDADE_MAX = 3      # X.Y.Z; abaixo disso é desdobramento do requisito, não nó


class Modelo(object):
    def __init__(self):
        self.nos = {}
        self.arestas = []
        self.lacunas = []
        self._vistas = set()

    def no(self, nid, tipo, rotulo, detalhe='', arquivo=''):
        if nid not in self.nos:
            self.nos[nid] = {'id': nid, 'tipo': tipo, 'rotulo': rotulo, 'detalhe': detalhe or '',
                             'arquivo': arquivo, 'lacunas': []}
        return nid

    def liga(self, de, para, rotulo):
        if de in self.nos and para in self.nos and de != para and (de, para, rotulo) not in self._vistas:
            self._vistas.add((de, para, rotulo))
            self.arestas.append({'de': de, 'para': para, 'rotulo': rotulo})

    def lacuna(self, nid, msg, nivel='lacuna'):
        """`lacuna` é falta de amarração; `aviso` é heurística (casamento por nome), que pode errar."""
        self.lacunas.append({'no': nid, 'msg': msg, 'nivel': nivel})
        if nid in self.nos:
            self.nos[nid]['lacunas'].append(msg)

    def como_dict(self):
        contagem = {}
        for n in self.nos.values():
            contagem[n['tipo']] = contagem.get(n['tipo'], 0) + 1
        return {'nodes': list(self.nos.values()), 'edges': self.arestas, 'lacunas': self.lacunas,
                'contagem': contagem, 'recolhidos': list(RECOLHIDOS)}


def _curto(texto, n=110):
    """Texto limpo (sem comentário HTML, `*` nem crase); `n=None` não corta — a página mostra o texto inteiro."""
    texto = re.sub(r'<!--.*?-->', '', texto or '')
    texto = re.sub(r'\s+', ' ', re.sub(r'[*`]', '', texto)).strip()
    return texto if n is None or len(texto) <= n else texto[:n - 1] + '…'


# ------------------------------------------------------------------------ ER e ET

def ler_arvore(caminho):
    """[{coord, rotulo, texto, nivel, titulo, prints}] das linhas anotadas `<!-- 2.1.1 #slug -->` de um ER.md ou
    ET.md; `titulo` marca o `####` (o assunto). `[[PRINT: x.png]]` vai para o requisito anterior."""
    if not os.path.isfile(caminho):
        return None
    nos, ultimo = [], None
    for ln in C.ler(caminho).splitlines():
        mp = RE_PRINT.match(ln.strip())
        if mp and ultimo is not None:
            ultimo['prints'].append(mp.group(1))
            continue
        m = RE_COORD.search(ln)
        if not m:
            continue
        corpo = ln[:m.start()].strip()
        titulo = corpo.startswith('#')
        texto = re.sub(r'^(#+|[-*])\s*', '', corpo)
        ultimo = {'coord': m.group(1), 'rotulo': m.group(2) or '', 'texto': texto, 'titulo': titulo,
                  'nivel': m.group(1).count('.') + 1, 'prints': []}
        nos.append(ultimo)
    return nos


def _nos_da_arvore(g, arvore, tipo, arquivo):
    """O título (`####`, `###`) é `er`/`et`; o requisito (item de lista) é `er_req`/`et_req`, recolhido, preso ao pai
    pela coordenada (`2.1.1` sob `2.1`)."""
    ids = {}
    for n in arvore:
        if n['nivel'] > PROFUNDIDADE_MAX:
            continue
        t = tipo if n['titulo'] else tipo + '_req'
        rot = n['coord'] + ' ' + _curto(n['texto'], 70)
        ids[n['coord']] = g.no('%s:%s' % (t, n['coord']), t, rot, n['texto'], arquivo)
    for c, nid in ids.items():
        pai = c.rsplit('.', 1)[0] if '.' in c else None
        if pai in ids:
            g.liga(ids[pai], nid, 'contém')
    return ids


# ------------------------------------------------------------------------ montagem

def montar(pasta):
    g = Modelo()
    estado = C.carregar_estado(pasta)
    p = P.Plano(C.arquivo_plano(pasta))
    analise = P.ler_analise(pasta)
    fonte = os.path.join(pasta, 'docx-fonte')
    arq_er, arq_et = os.path.join(fonte, 'ER.md'), os.path.join(fonte, 'ET.md')

    # ---- análise
    raiz = g.no('analise', 'analise', 'Análise ' + C.rotulo(pasta), '', os.path.basename(C.arquivo_analise(pasta)))
    assunto_id, item_id, cobrir = {}, {}, {}
    if analise:
        cobrir = P.itens_a_cobrir(analise)
        for nome in analise['assuntos']:
            assunto_id[C.chave(nome)] = g.no('assunto:' + C.chave(nome), 'assunto', nome, '', g.nos[raiz]['arquivo'])
            g.liga(raiz, assunto_id[C.chave(nome)], 'tem')
        if analise.get('mudancas'):
            k = C.chave(P.MUDANCAS)
            assunto_id[k] = g.no('assunto:' + k, 'assunto', P.MUDANCAS, '', g.nos[raiz]['arquivo'])
            g.liga(raiz, assunto_id[k], 'tem')
        for k, (nome, itens) in cobrir.items():
            for i, texto in enumerate(itens, 1):
                item_id[(k, i)] = g.no('item:%s#%d' % (k, i), 'item', '%s #%d' % (nome, i), texto, g.nos[raiz]['arquivo'])
                g.liga(assunto_id[k], item_id[(k, i)], 'item')
        for i, pt in enumerate(analise['pontos'], 1):
            pid = g.no('ponto:%d' % i, 'ponto', 'Ponto em aberto %d' % i, pt['assunto'] + ' — ' + pt['pergunta'],
                       g.nos[raiz]['arquivo'])
            k = C.chave(pt['assunto'])
            g.liga(assunto_id.get(k, raiz), pid, 'pergunta')
    elif estado.get('sem_analise'):
        g.nos[raiz]['detalhe'] = 'sem análise: plano base ' + estado['sem_analise'].get('plano_base', '')

    # ---- ER e ET
    er, et = ler_arvore(arq_er), ler_arvore(arq_et)
    er_id = _nos_da_arvore(g, er, 'er', 'docx-fonte/ER.md') if er else {}
    et_id = _nos_da_arvore(g, et, 'et', 'docx-fonte/ET.md') if et else {}
    for c, nid in er_id.items():
        if c in et_id:
            g.liga(nid, et_id[c], 'espelho')
    por_titulo_er = {C.chave(x['texto']): er_id[x['coord']] for x in (er or [])
                     if x['titulo'] and x['nivel'] == 2 and x['coord'] in er_id}
    por_titulo_et = {C.chave(x['texto']): et_id[x['coord']] for x in (et or [])
                     if x['titulo'] and x['nivel'] == 2 and x['coord'] in et_id}
    if analise:
        for nome in analise['assuntos']:
            k = C.chave(nome)
            for tabela, rotulo, doc in ((por_titulo_er, 'ER', er), (por_titulo_et, 'ET', et)):
                if k in tabela:
                    g.liga(assunto_id[k], tabela[k], 'vira')
                elif doc is not None:
                    g.lacuna(assunto_id[k], 'sem #### de mesmo nome na %s (grafia diferente?)' % rotulo, 'aviso')
    if er and et:
        for x in er:
            if x['coord'].startswith('2.') and x['nivel'] <= PROFUNDIDADE_MAX and x['coord'] not in et_id:
                g.lacuna(er_id[x['coord']], 'requisito da ER sem par na ET', 'aviso')
    prints_er, prints_et = set(), set()
    for arvore, ids, doc in ((er, er_id, prints_er), (et, et_id, prints_et)):
        for x in (arvore or []):
            for img in x['prints']:
                nome = os.path.basename(img)
                eid = g.no('esboco:' + nome, 'esboco', nome, '', 'docx-fonte/prints/' + nome)
                doc.add(nome)
                if x['coord'] in ids:
                    g.liga(ids[x['coord']], eid, 'mostra')
                titulo = '.'.join(x['coord'].split('.')[:2])
                if titulo in ids and titulo != x['coord']:
                    g.liga(ids[titulo], eid, 'mostra')
    pasta_prints = os.path.join(fonte, 'prints')
    if os.path.isdir(pasta_prints):
        for nome in sorted(os.listdir(pasta_prints)):
            if not nome.lower().endswith('.png'):
                continue
            eid = g.no('esboco:' + nome, 'esboco', nome, '', 'docx-fonte/prints/' + nome)
            if et is not None and nome not in prints_et:     # a ET é que carrega a sequência de prints
                g.lacuna(eid, 'esboço só na ER; a ET carrega a sequência de prints' if nome in prints_er
                         else 'esboço sem [[PRINT]] na ET', 'aviso')
    pasta_sql = os.path.join(pasta, 'scripts')
    if os.path.isdir(pasta_sql):
        for nome in sorted(os.listdir(pasta_sql)):
            if re.match(r'(script|erwin)-.*\.sql$', nome):
                g.liga(raiz, g.no('sql:' + nome, 'sql', nome, '', 'scripts/' + nome), 'banco')

    # ---- plano
    decisoes = {d['id']: d for d in estado.get('decisoes', [])}

    def no_decisao(num):
        did = 'D' + num
        if did in decisoes:
            return g.no('decisao:' + did, 'decisao', did, decisoes[did].get('texto', ''), '.execucao.json')
        return None

    def liga_decisoes(origem, texto):
        for num in P.decisoes_citadas(texto):
            d = no_decisao(num)
            if d:
                g.liga(origem, d, 'decisão')

    def liga_er(origem, texto):
        for m in re.finditer(r'\bER\s+(\d+(?:\.\d+)*)(?:\s*[–-]\s*(\d+(?:\.\d+)*))?', texto or '', re.IGNORECASE):
            for c in filter(None, m.groups()):
                if c in er_id:
                    g.liga(origem, er_id[c], 'ER')
                elif er is not None:
                    g.lacuna(origem, 'cita ER %s, que não existe na ER' % c)

    sem_aceite_de_tarefa = set()
    aceites_de_tarefa = {}
    cobertos = set()
    for o in p.ondas:
        oid = g.no('onda:' + o['id'], 'onda', 'Onda %s' % o['id'], o['titulo'], os.path.basename(C.arquivo_plano(pasta)))
        eo = (estado.get('ondas') or {}).get(o['id']) or {}
        g.nos[oid]['detalhe'] = '%s — %s' % (o['titulo'], eo.get('estado') or 'planejada')
        assuntos = set()
        for parte in P.origens(o):
            if P.RE_ER.match(parte):
                liga_er(oid, parte)
            elif re.fullmatch(r'D\d+', parte):
                d = no_decisao(parte[1:])
                if d:
                    g.liga(oid, d, 'origem')
            elif re.fullmatch(r'P\d+', parte):
                pass                    # a pendência liga depois, quando o nó existir
            else:
                k = C.chave(parte)
                assuntos.add(k)
                if k in assunto_id:
                    g.liga(oid, assunto_id[k], 'origem')
        for aid in o['ordem_aceites']:
            ac = o['aceites'][aid]
            nid = g.no('aceite:' + aid, 'aceite', aid, _curto(ac['texto'], None), os.path.basename(C.arquivo_plano(pasta)))
            g.liga(oid, nid, 'aceite')
            liga_decisoes(nid, ac['texto'])
            liga_er(nid, ac['texto'])
            for ancora in P.RE_ANCORA_ANALISE.findall(ac['texto']):
                for trecho in ancora.split(';'):
                    if P.RE_ANCORA_ER.search(trecho):
                        continue
                    nome, itens = P.partir_ancora(trecho)
                    k = C.chave(nome)
                    if itens:
                        for i in sorted(itens):
                            if (k, i) in item_id:
                                g.liga(nid, item_id[(k, i)], 'cobre')
                                cobertos.add((k, i))
                    elif k in assunto_id:
                        g.liga(nid, assunto_id[k], 'cobre')
                        cobertos.update((k, i) for i in range(1, len(cobrir.get(k, ('', []))[1]) + 1))
        for tid in o['ordem_tarefas']:
            t = o['tarefas'][tid]
            nid = g.no('tarefa:' + tid, 'tarefa', tid, t['titulo'], os.path.basename(C.arquivo_plano(pasta)))
            g.liga(oid, nid, 'tarefa')
            for aid in P.lista_ids(t['campos'].get('Aceite', ''), C.RE_ACEITE):
                aceites_de_tarefa.setdefault(aid, []).append(tid)
                g.liga(nid, 'aceite:' + aid, 'cobre')
            for dep in P.lista_ids(t['campos'].get('Depende de', ''), C.RE_TAREFA):
                g.liga(nid, 'tarefa:' + dep, 'depende')
            if not P.gate_de(t) or not P.teste_de(t):
                g.lacuna(nid, 'tarefa sem Gate ou sem Teste')
            for c in estado.get('ondas', {}).get(o['id'], {}).get('tarefas', {}).get(tid, {}).get('commits', []):
                cid = g.no('commit:' + c['hash'][:10], 'commit', c['hash'][:7], c.get('assunto', ''), c.get('repo', ''))
                g.liga(nid, cid, 'commit')

    # ---- lacunas do plano contra a análise
    if p.ondas and analise:
        usados = set()
        for o in p.ondas:
            usados |= P.assuntos_de_origem(o)
        fora = C.chave(p.fora_do_escopo)
        for nome in analise['assuntos']:
            k = C.chave(nome)
            if k not in usados and k not in fora:
                g.lacuna(assunto_id[k], 'assunto sem onda e fora do "Fora do escopo"')
        for (k, i), nid in item_id.items():
            if (k, i) not in cobertos:
                g.lacuna(nid, 'item sem aceite (nem "Fora do escopo")')
        for pt in p.pontos:
            sit, _ds = P.situacao_ponto(pt['situacao'])
            if sit == 'aberto':
                g.lacuna(raiz, 'ponto em aberto sem resposta: %s' % _curto(pt['pergunta'], 70), 'lacuna')
    for o in p.ondas:
        for aid in o['ordem_aceites']:
            ac = o['aceites'][aid]
            if not ac['riscado'] and aid not in aceites_de_tarefa:
                g.lacuna('aceite:' + aid, 'aceite sem tarefa')

    # ---- execução
    for e in estado.get('execucoes', []):
        eid = g.no('execucao:' + e['id'], 'execucao', e['id'], '%s %s %s' % (e.get('tipo', ''), e.get('repo', ''),
                   'ok' if e.get('ok') else 'falhou'), e.get('log') or '')
        for aid in e.get('aceites') or []:
            g.liga(eid, 'aceite:' + aid, 'prova')
        o = p.onda(str(e.get('onda'))) if e.get('onda') is not None else None
        for tid in (o['ordem_tarefas'] if o else []):
            classes = P.classes_de_teste(o['tarefas'][tid])
            if any(T.casa_classe(c, x) for c in classes for x in e.get('classes') or []):
                g.liga(eid, 'tarefa:' + tid, 'testa')
    mutante_de = {}
    for s in estado.get('sessoes_mutacao', []):
        for m in s.get('mutantes', []):
            mid = g.no('mutante:' + m['id'], 'mutante', m['id'], '%s — %s (%s)' % (
                m.get('arquivo', ''), m.get('descricao', ''), m.get('resultado', '')), m.get('arquivo', ''))
            mutante_de.setdefault(m.get('aceite'), []).append(mid)
            g.liga(mid, 'aceite:' + str(m.get('aceite')), 'mira')
            for campo in ('reaplica', 'reconfirma'):
                if m.get(campo):
                    g.liga(mid, 'mutante:' + str(m[campo]), campo)
            if m.get('revisao'):
                g.liga(mid, 'revisao:' + m['revisao'], 'sessão')
    provados = set()
    for r in estado.get('revisoes', []):
        rid = g.no('revisao:' + r['id'], 'revisao', r['id'], '%s — %s' % (r.get('veredito') or 'sem veredito',
                   ('onda %s' % r.get('onda'))), 'revisao-onda-%s.md' % r.get('onda'))
        g.liga('onda:' + str(r.get('onda')), rid, 'revisão')
        for aid in r.get('aceites') or []:
            g.liga(rid, 'aceite:' + aid, 'revisa')
            if (r.get('resultados') or {}).get(aid) == 'OK':
                provados.add(aid)
    for pe in estado.get('pendencias', []):
        pid = g.no('pendencia:' + pe['id'], 'pendencia', pe['id'], pe.get('texto', ''), '.execucao.json')
        if pe.get('origem'):
            g.liga(pid, 'revisao:' + pe['origem'], 'veio de')
        if pe.get('descartada'):
            liga = no_decisao(pe['descartada'][1:])
            if liga:
                g.liga(pid, liga, 'descartada')
        for o in p.ondas:
            if pe['id'] in P.origens(o):
                g.liga('onda:' + o['id'], pid, 'assume')
    for i, pa in enumerate(estado.get('pareceres', []), 1):
        if isinstance(pa, dict):
            g.no('parecer:%d' % i, 'parecer', 'Parecer %d' % i, str(pa.get('veredito') or ''), pa.get('arquivo') or '')
    for d in decisoes.values():
        did = 'decisao:' + d['id']
        if did in g.nos:
            alvo = str(d.get('alvo') or '')
            for pref, tipo in (('T', 'tarefa'), ('M', 'mutante'), ('E', 'execucao'), ('P', 'pendencia')):
                if re.fullmatch(pref + r'\d+(\.\d+)?', alvo) and '%s:%s' % (tipo, alvo) in g.nos:
                    g.liga(did, '%s:%s' % (tipo, alvo), 'alvo')
            if d.get('revogada_por'):
                g.liga(did, 'decisao:' + d['revogada_por'], 'revogada por')
    # aceite de onda já iniciada sem nenhuma prova (mutante, revisão OK ou roteiro) é aviso
    for o in p.ondas:
        if o['id'] not in (estado.get('ondas') or {}):
            continue
        for aid in o['ordem_aceites']:
            if o['aceites'][aid]['riscado'] or aid in provados or aid in mutante_de:
                continue
            if any(aid in (e.get('aceites') or []) for e in estado.get('execucoes', [])):
                continue
            g.lacuna('aceite:' + aid, 'aceite de onda iniciada sem mutante, revisão OK nem roteiro', 'aviso')
    if not any(raiz in (e['de'], e['para']) for e in g.arestas) and not g.nos[raiz]['lacunas']:
        del g.nos[raiz]                 # projeto sem análise: o nó solto só distorceria o enquadramento
    modelo = g.como_dict()
    layout_fluxo(modelo)
    return modelo




# ------------------------------------------------------------------------ layout em fluxo

# tipo -> (coluna, faixa). Faixa 0 é o fio principal (análise → plano → execução); 1, a especificação (ER, ET,
# esboço, banco); 2, as decisões e o parecer. A coluna é o que importa para ler da esquerda para a direita.
COLUNAS = {'analise': (0, 0), 'assunto': (1, 0), 'ponto': (1, 0), 'onda': (2, 0), 'item': (3, 0), 'aceite': (4, 0),
           'tarefa': (5, 0), 'commit': (7, 0), 'execucao': (8, 0), 'mutante': (9, 0), 'revisao': (10, 0),
           'pendencia': (11, 0), 'er': (2, 1), 'et': (3, 1), 'er_req': (4, 1), 'et_req': (5, 1), 'esboco': (6, 1),
           'sql': (6, 1), 'decisao': (4, 2), 'parecer': (10, 2)}
LARGURA = {7: 90, 8: 90, 9: 90}      # as demais colunas levam o rótulo ao lado do nó
LARGURA_PADRAO = 230
LINHA = 26                           # altura de cada nó na coluna
MAX_LINHAS = 48                      # coluna mais alta que isto quebra em subcolunas
FOLGA_FAIXA = 44                     # entre as faixas (a página recalcula pelo que está visível)


def layout_fluxo(modelo):
    """Dá a cada nó `c` (coluna), `s` (subcoluna, quando a coluna quebra) e `y`, e põe `colunas` no modelo:
    `[{c, tipos, w, n}]` só das colunas que existem, para o desenho não ter buraco. Dentro da coluna a ordem é a
    de inserção no modelo, que segue o plano e os documentos (T6.1 antes de T6.4, A1.x antes de A2.x, 2.1 antes
    de 2.10): quem lê acha o item onde espera, mesmo que cruze mais linhas."""
    nos = {n['id']: n for n in modelo['nodes']}
    grupos = {}
    for n in modelo['nodes']:
        c, f = COLUNAS.get(n['tipo'], (5, 0))
        n['c'], n['f'] = c, f
        grupos.setdefault((c, f), []).append(n['id'])

    altura = {}
    for (c, f), ids in grupos.items():
        altura[f] = max(altura.get(f, 0), min(len(ids), MAX_LINHAS) * LINHA)
    deslocamento, acumulado = {}, 0
    for f in sorted(altura):
        deslocamento[f] = acumulado
        acumulado += altura[f] + FOLGA_FAIXA
    subs = {}
    for (c, f), ids in grupos.items():
        n_ = len(ids)
        for i, nid in enumerate(ids):
            nos[nid]['s'] = i // MAX_LINHAS
            if n_ > MAX_LINHAS:                  # coluna que quebra: empacotada
                y = (i % MAX_LINHAS) * LINHA
            else:                                # coluna curta: espalhada na altura da faixa, ao lado das longas
                y = (altura[f] - LINHA) / 2 if n_ == 1 else i * (altura[f] - LINHA) / (n_ - 1)
            nos[nid]['y'] = deslocamento[f] + round(y, 1)
        subs[c] = max(subs.get(c, 1), (len(ids) + MAX_LINHAS - 1) // MAX_LINHAS)
    colunas = []
    presentes = {n['tipo'] for n in modelo['nodes']}
    for c in sorted(subs):
        tipos = sorted({t for t, (cc, _f) in COLUNAS.items() if cc == c and t in presentes})
        faixas = {}                          # título por faixa: a coluna 4 tem aceite (faixa 0) e decisão (faixa 2)
        for t in tipos:
            faixas.setdefault(str(COLUNAS[t][1]), []).append(t)
        colunas.append({'c': c, 'tipos': tipos, 'faixas': faixas, 'w': LARGURA.get(c, LARGURA_PADRAO), 'n': subs[c]})
    modelo['colunas'] = colunas
    return modelo


# ------------------------------------------------------------------------ formato da página

def compactar(modelo):
    """O que a página embute: nós e arestas como listas (sem repetir chave) e uma tabela de rótulos de aresta.
    Nunca leva fala nem citação do usuário: só o que o modelo já tem (texto de aceite, tarefa, decisão, pendência)."""
    indice = {n['id']: i for i, n in enumerate(modelo['nodes'])}
    rotulos, idx = [], {}
    arestas = []
    for e in modelo['edges']:
        r = idx.setdefault(e['rotulo'], len(idx))
        if r == len(rotulos):
            rotulos.append(e['rotulo'])
        arestas.append([indice[e['de']], indice[e['para']], r])
    return {'nos': [[n['id'], n['tipo'], n['rotulo'], n['detalhe'], n['arquivo'], n['lacunas'], n['c'], n['s'], n['y'], n['f']]
                    for n in modelo['nodes']],
            'arestas': arestas, 'rotulos': rotulos, 'colunas': modelo['colunas'],
            'lacunas': [[l['no'], l['msg'], l['nivel']] for l in modelo['lacunas']],
            'contagem': modelo['contagem'], 'recolhidos': modelo['recolhidos'],
            'linha': LINHA}


def grafo(pasta, args):
    """Atalho: o grafo é uma aba do painel. `--json` imprime o modelo; sem ele grava o `PAINEL-NN-AAAA.html`."""
    modelo = montar(pasta)
    if args.json:
        print(json.dumps(modelo, ensure_ascii=False, indent=2))
        return 0
    import estado as E
    caminho = E.painel_html(pasta, grafo=modelo)
    rel = C.Relatorio()
    rel.nota('painel (aba Grafo): %s' % caminho)
    rel.nota('%d nó(s), %d aresta(s), %d lacuna(s)' % (len(modelo['nodes']), len(modelo['edges']), len(modelo['lacunas'])))
    for l in modelo['lacunas']:
        (rel.aviso if l['nivel'] == 'aviso' else rel.nota)('%s — %s' % (l['no'], l['msg']))
    if getattr(args, 'abrir', False):
        webbrowser.open('file://' + os.path.abspath(caminho) + '#grafo')
    return rel.imprimir()
