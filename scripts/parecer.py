#!/usr/bin/env python3
"""Parecer de liberação: esqueleto no molde dos pareceres do 34/2026 e validação.

O que muda em relação aos pareceres escritos à mão: o **vocabulário é fechado** (veredito GO,
GO COM CONDIÇÕES ou NO-GO; estado de achado Corrigido, Não procede, Fora do escopo, Aceito ou
Pendente), as seções factuais (o que mudou por repositório, validação executada) são geradas do
git e do `.execucao.json`, e um GO não sai se alguma onda estiver aberta, se a evidência não for
do código atual ou se houver achado pendente.
"""

import datetime as dt
import glob
import os
import re

import comum as C
import decisoes as DC
import mutantes as M
import plano as P
import testes as T

VEREDITOS = {'go': 'GO', 'go com condicoes': 'GO COM CONDIÇÕES', 'no-go': 'NO-GO', 'no go': 'NO-GO'}
ESTADOS_ACHADO = ('corrigido', 'nao procede', 'fora do escopo', 'aceito', 'pendente')


def _pareceres(pasta):
    return sorted(glob.glob(os.path.join(pasta, 'PARECER-LIBERACAO-*.md')))


def _base_por_repo(estado, p):
    """Commit de partida de cada repo: o baseline da primeira onda (na ordem do plano) que o tocou."""
    base = {}
    for o in p.ondas:
        for repo, b in estado['ondas'].get(o['id'], {}).get('baseline', {}).items():
            base.setdefault(repo, b['head'])
    return base


def bloco_alteracoes(estado, p):
    partes = []
    for repo, base in sorted(_base_por_repo(estado, p).items()):
        real = estado['repos'][repo]['caminho']
        head = C.git(real, 'rev-parse', 'HEAD')
        stat = C.git(real, 'diff', '--shortstat', base) or 'sem diferença'
        log = C.git(real, 'log', '--format=- `%h` %s', '%s..HEAD' % base)
        sujo = C.git(real, 'status', '--porcelain')
        partes.append('### `%s` — `%s..%s`\n\n%s\n\n%s%s' % (
            repo, base[:9], head[:9], stat, log or '_nenhum commit_',
            '\n\n**Não commitado:** %d arquivo(s)' % len(sujo.splitlines()) if sujo else ''))
    return '\n\n'.join(partes) or '_nenhuma onda iniciada_'


def bloco_validacao(estado, p, fps):
    linhas = ['| Onda | Estado | Revisão | Mutantes (mortos/válidos) |', '|---|---|---|---|']
    for o in p.ondas:
        eo = estado['ondas'].get(o['id'], {})
        revs = [r for r in estado['revisoes'] if r['onda'] == o['id']]
        validos = M.mutantes_validos(estado, o['id'], fps)
        linhas.append('| %s | %s | %s | %d/%d |' % (
            o['id'], eo.get('estado', 'não iniciada'), revs[-1]['id'] if revs else '—',
            len([m for m in validos if m['resultado'] == 'morto']), len(validos)))
    linhas += ['', '| Execução | Repo | Tipo | Resultado |', '|---|---|---|---|']
    for repo in sorted(_base_por_repo(estado, p)):
        for e in T.execucoes_frescas(estado, repo, fps.get(repo)):
            res = ('%(run)d testes, %(falhas)d falhas, %(erros)d erros, %(pulados)d pulados' % e['totais']
                   if e.get('totais') else 'exit %d' % e['exit'] if e['tipo'] != 'roteiro' else e.get('arquivo', ''))
            linhas.append('| %s | `%s` | %s | %s |' % (e['id'], repo, e['tipo'], res))
    return '\n'.join(linhas)


def bloco_engenharia(estado):
    """As decisões que o modelo tomou com a autorização de engenharia do usuário, para ele rever em lote."""
    rs = DC.rulings(estado)
    if not rs:
        return '_nenhuma decisão de engenharia_'
    linhas = ['| Decisão | Para | Alvo | Justificativa | Autorizada por | Situação |', '|---|---|---|---|---|---|']
    for d in rs:
        if d.get('revogada_por'):
            sit = 'revogada por %s%s' % (d['revogada_por'], ' depois do uso' if d.get('usada_em') else '')
        else:
            sit = 'usada' if d.get('usada_em') else 'não usada'
        linhas.append('| %s | %s | %s | %s | %s | %s |' % (d['id'], d.get('para'), d.get('alvo') or '—',
                                                         d['texto'].replace('|', '\\|'), d.get('autorizada_por'), sit))
    return '\n'.join(linhas)


def bloco_propostos(estado):
    """Valor esperado que só aparece na pergunta que o modelo escreveu (o usuário respondeu a ela), por onda,
    da última revisão validada de cada uma."""
    linhas = ['| Onda | Revisão | Aceite | Decisão | Valor |', '|---|---|---|---|---|']
    ultimas = {}
    for rv in estado.get('revisoes', []):
        if rv.get('validada_em'):
            ultimas[rv['onda']] = rv
    for onda, rv in sorted(ultimas.items()):
        for x in rv.get('esperados_propostos') or []:
            linhas.append('| %s | %s | %s | %s | `%s` |' % (onda, rv['id'], x['aceite'], x['decisao'], x['literal']))
    return '\n'.join(linhas) if len(linhas) > 2 else '_nenhum valor esperado só na pergunta do modelo_'


ESQUELETO = """# Parecer de liberação — {rotulo}

> Documento de decisão. Emitido em **{data}**.{sucede}

## Veredito

**<GO | GO COM CONDIÇÕES | NO-GO>**

<quantos achados, quantos bloqueantes, quantos corrigidos, improcedentes e fora do escopo>

## 1. Estado dos achados

| # | Achado | Onde | Estado |
|---|---|---|---|

## 2. O que foi alterado, por repositório

{alteracoes}

## 3. Validação executada

{validacao}

## 4. Condições para a subida

## 5. Limites deste parecer

<o que este parecer não cobre>

## 6. Decisões do modelo

Decisões de engenharia (com a autorização do usuário): o usuário as revê aqui, e revoga a que não aceita.

{engenharia}

Valores esperados propostos pelo agente: o literal só aparece na pergunta que o modelo escreveu, e o usuário
respondeu a ela. Vale como esperado; o usuário confere aqui se é o valor que ele quis.

{propostos}
"""


def iniciar(pasta, args):
    estado = C.carregar_estado(pasta)
    p = P.Plano(C.arquivo_plano(pasta))
    fps = C.fingerprints(estado)
    hoje = dt.date.today().isoformat()
    arq = os.path.join(pasta, 'PARECER-LIBERACAO-%s.md' % hoje)
    n = 2
    while os.path.exists(arq):
        arq = os.path.join(pasta, 'PARECER-LIBERACAO-%s-%d.md' % (hoje, n))
        n += 1
    anteriores = _pareceres(pasta)
    sucede = ''
    if anteriores:
        ant = os.path.basename(anteriores[-1])
        sucede = ' Sucede o [parecer anterior](%s), cujos vereditos seguem valendo salvo onde este documento diz o contrário.' % ant
    C.gravar(arq, ESQUELETO.format(
        rotulo=C.rotulo(pasta), data=hoje, sucede=sucede,
        alteracoes=C.bloco('alteracoes', bloco_alteracoes(estado, p)),
        validacao=C.bloco('validacao', bloco_validacao(estado, p, fps)),
        engenharia=C.bloco('engenharia', bloco_engenharia(estado)),
        propostos=C.bloco('propostos', bloco_propostos(estado))))
    estado['pareceres'].append({'arquivo': os.path.basename(arq), 'iniciado_em': C.agora(), 'fingerprints': fps})
    C.salvar_estado(pasta, estado)
    print('parecer iniciado: %s' % arq)
    return 0


def validar(pasta, args):
    estado = C.carregar_estado(pasta)
    p = P.Plano(C.arquivo_plano(pasta))
    arq = args.arquivo and os.path.join(pasta, args.arquivo) or (_pareceres(pasta) or [None])[-1]
    rel = C.Relatorio('parecer validar %s' % (os.path.basename(arq) if arq else '—'))
    if not arq or not os.path.exists(arq):
        rel.erro('nenhum parecer (`parecer iniciar`)')
        return rel.imprimir()
    reg = [x for x in estado['pareceres'] if x['arquivo'] == os.path.basename(arq)]
    if not reg:
        rel.erro('%s não foi criado por `parecer iniciar` — sem o registro, não há como saber '
                 'sobre que código ele foi escrito' % os.path.basename(arq))
    fps = C.fingerprints(estado)
    texto = C.ler(arq)
    for nome, conteudo in (('alteracoes', bloco_alteracoes(estado, p)),
                           ('validacao', bloco_validacao(estado, p, fps)),
                           ('engenharia', bloco_engenharia(estado)),
                           ('propostos', bloco_propostos(estado))):
        texto, achou = C.trocar_bloco(texto, nome, conteudo)
        if nome == 'engenharia' and not achou and DC.rulings(estado):
            rel.erro('o parecer não tem o bloco gerado das decisões de engenharia (%s) — o usuário as revê no '
                     'parecer: acrescente `## 6. Decisões do modelo` com `<!-- gerado:engenharia:inicio -->…'
                     '<!-- gerado:engenharia:fim -->`' % ', '.join(d['id'] for d in DC.rulings(estado)))
    C.gravar(arq, texto)

    corpo = C.secao(texto, r'^veredito') or ''
    m = re.search(r'\*\*([^*]+)\*\*', corpo)
    veredito = VEREDITOS.get(C.chave(m.group(1)) if m else '', None)
    if not veredito:
        rel.erro('veredito tem de ser **GO**, **GO COM CONDIÇÕES** ou **NO-GO**')
    for nome, rx in (('1. Estado dos achados', r'estado dos achados'), ('2. O que foi alterado', r'(o que foi )?alterado'),
                     ('3. Validação executada', r'valida'), ('4. Condições para a subida', r'condi'),
                     ('5. Limites deste parecer', r'limites')):
        if C.secao(texto, r'^\d*\.?\s*' + rx) is None:
            rel.erro('seção ausente: ## %s' % nome)
    limites = C.secao(texto, r'^\d*\.?\s*limites')
    if limites is not None and not C.tem_conteudo(limites):
        rel.erro('"Limites deste parecer" vazio — todo parecer tem limite')

    pendentes = bloqueantes = 0
    ids = set()
    for cel in C.linhas_de_tabela(C.secao(texto, r'^\d*\.?\s*estado dos achados')):
        if not cel or not cel[0].strip('*'):
            continue
        aid = cel[0].strip('*` ')
        if not re.fullmatch(r'A\d+', aid):
            rel.erro('achado %r fora do padrão A<n>' % aid)
        if aid in ids:
            rel.erro('achado %s duplicado' % aid)
        ids.add(aid)
        estado_cel = C.chave(re.sub(r'[*~]', '', cel[-1]))
        tipo = next((e for e in ESTADOS_ACHADO if estado_cel.startswith(e)), None)
        if not tipo:
            rel.erro('%s: estado %r fora do vocabulário (Corrigido, Não procede, Fora do escopo, '
                     'Aceito, Pendente)' % (aid, cel[-1]))
        elif tipo == 'corrigido':
            hashes = re.findall(r'`([0-9a-f]{7,40})`', cel[-1])
            if not hashes:
                rel.erro('%s: Corrigido sem o commit entre crases' % aid)
            for h in hashes:
                if not any(C.commit_existe(cfg['caminho'], h) for cfg in estado['repos'].values()):
                    rel.erro('%s: commit %s não existe em nenhum repositório configurado' % (aid, h))
        elif tipo in ('aceito', 'fora do escopo'):
            # aceitar risco ou tirar do escopo é do usuário: a decisão tem de estar no livro
            ds = re.findall(r'\bD\d+\b', cel[-1])
            if not ds:
                rel.erro('%s: %s sem a decisão do usuário (D<n>)' % (aid, tipo.capitalize()))
            for d in ds:
                erro_d = DC.exigir(estado, d)
                if erro_d:
                    rel.erro('%s: %s' % (aid, erro_d))
        elif tipo == 'nao procede':
            if '§' not in cel[-1] and not re.search(r'\bse[çc][aã]o\b', cel[-1], re.IGNORECASE):
                rel.erro('%s: Não procede sem a seção (§) que explica por quê' % aid)
        elif tipo == 'pendente':
            pendentes += 1
            if 'bloqueante' in estado_cel:
                bloqueantes += 1
    condicoes = re.findall(r'\bC\d+\b', C.sem_riscado(C.secao(texto, r'^\d*\.?\s*condi') or ''))

    if veredito in ('GO', 'GO COM CONDIÇÕES'):
        erro_ap = DC.conferir_aprovacao(pasta, estado)
        if erro_ap:
            rel.erro(erro_ap)
        if bloqueantes:
            rel.erro('%s com %d achado(s) pendente(s) bloqueante(s)' % (veredito, bloqueantes))
        if veredito == 'GO' and pendentes:
            rel.erro('GO com %d achado(s) pendente(s) — é GO COM CONDIÇÕES ou NO-GO' % pendentes)
        if veredito == 'GO COM CONDIÇÕES' and not condicoes:
            rel.erro('GO COM CONDIÇÕES sem condição C<n> em aberto na seção 4')
        if not ids and not re.search(r'nenhum achado', C.chave(C.secao(texto, r'^\d*\.?\s*estado dos achados') or '')):
            rel.erro('%s sem nenhum achado na tabela — se a revisão não achou nada, diga "nenhum achado" '
                     'na seção 1 (tabela vazia não distingue revisão limpa de revisão não feita)' % veredito)
        import onda as OND
        citado = (C.secao(texto, r'^\d*\.?\s*estado dos achados') or '') + (C.secao(texto, r'^\d*\.?\s*condi') or '')
        for o in p.ondas:
            eo = estado['ondas'].get(o['id'], {})
            if eo.get('estado') in ('replanejada', 'abandonada'):
                if eo['estado'] == 'abandonada' and not re.search(r'\bOnda %s\b' % re.escape(o['id']), citado):
                    rel.erro('onda %s abandonada (%s) e o parecer não diz o que ficou de fora (cite "Onda %s" '
                             'num achado ou condição)' % (o['id'], eo['abandonada']['decisao'], o['id']))
                continue
            if eo.get('estado') != 'fechada':
                rel.erro('onda %s não está fechada' % o['id'])
                continue
            md = eo.get('mutante_dispensado') or {}
            for item in md.get('aceites', []):
                if not re.search(r'\b%s\b' % re.escape(item), citado):
                    rel.erro('onda %s fechou com o aceite %s sem mutante (%s) e o parecer não o cita em achado '
                             'ou condição' % (o['id'], item, md.get('decisao')))
            pa = eo.get('pendencias_aceitas') or {}
            for item in pa.get('aceites', []) + pa.get('mutantes', []):
                if not re.search(r'\b%s\b' % re.escape(item), citado):
                    rel.erro('onda %s fechou com a pendência %s (%s) e o parecer não a cita em achado ou condição'
                             % (o['id'], item, pa['decisao']))
            # A regra de mutantes de hoje vale também para a onda que fechou antes dela: reconfere
            # os mutantes que valiam no fechamento, sobre o código do fechamento. Onda histórica (de antes
            # da 0.4.0) fechou por outra regra: o que não satisfaz a de hoje aparece, como aviso.
            fps_f = eo.get('fingerprints_no_fechamento') or {}
            rel_o = C.Relatorio()
            OND.conferir_mutantes(rel_o, estado, o, eo, o['id'], fps_f,
                                  ate={r: fp.get('head') for r, fp in fps_f.items()})
            for e in rel_o.erros:
                if C.historica(eo):
                    rel.aviso('onda %s (histórica, %s) não satisfaz o critério atual: %s'
                              % (o['id'], C.rotulo_regras(eo), e))
                else:
                    rel.erro('onda %s, reconferida pelas regras atuais: %s' % (o['id'], e))
        # Pendência que nenhuma onda assumiu não some no parecer. Alta sem onda é erro; baixa sem onda tem de
        # estar citada (P<n>) num achado ou condição. Pendência histórica sem severidade: aviso.
        for x in OND.pendencias_sem_onda(estado, p):
            if not x.get('severidade') and C.historica(estado['ondas'].get(x['onda'])):
                rel.aviso('pendência histórica %s (onda %s) sem severidade e sem onda: %s'
                          % (x['id'], x['onda'], x['texto'][:80]))
                continue
            if OND.severidade(x) == 'alta':
                rel.erro('pendência alta %s (onda %s, %s) sem onda que a tenha na Origem: %s — leve para uma onda, '
                         'ou o usuário a descarta (`pendencia descartar`)' % (x['id'], x['onda'], x['origem'], x['texto'][:80]))
            elif not re.search(r'\b%s\b' % re.escape(x['id']), citado):
                rel.erro('pendência baixa %s (onda %s) sem onda e o parecer não a cita em achado ou condição: %s'
                         % (x['id'], x['onda'], x['texto'][:80]))
        for repo in sorted(_base_por_repo(estado, p)):
            cfg = estado['repos'][repo]
            if repo not in fps:
                rel.erro('%s: o caminho %s não existe — sem o repositório não há o que conferir'
                         % (repo, cfg['caminho']))
                continue
            frescas = T.execucoes_frescas(estado, repo, fps[repo])
            tipo = ('build', 'teste') if cfg.get('sem_testes_automatizados') else ('teste',)
            if not [e for e in frescas if e['tipo'] in tipo]:
                rel.erro('%s: nenhuma execução OK de %s sobre o código atual' % (repo, '/'.join(tipo)))
            # o fingerprint gravado no `parecer iniciar` é o do conteúdo: se o código mudou
            # depois, o parecer fala de outro código (sem depender de relógio)
            if reg and not C.mesmo_fp(reg[-1]['fingerprints'].get(repo), fps[repo]):
                rel.erro('%s: o código mudou depois do `parecer iniciar` — inicie outro parecer' % repo)
        for o in p.ondas:
            for m_ in M.mutantes_validos(estado, o['id'], fps):
                if m_['resultado'] == 'sobrevivente' and not m_.get('equivalente'):
                    rel.erro('mutante %s sobrevivente (onda %s)' % (m_['id'], o['id']))
    rel.nota('veredito: %s · achados: %d (pendentes %d, bloqueantes %d) · condições: %s'
             % (veredito or '—', len(ids), pendentes, bloqueantes, ', '.join(condicoes) or '—'))
    return rel.imprimir()
