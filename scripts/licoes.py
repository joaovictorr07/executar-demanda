#!/usr/bin/env python3
"""Lições entre projetos — adaptado do `lessons.py` do tlc-spec-driven
(Felipe Rodrigues, github.com/felipfr, CC-BY-4.0).

O modelo dá o julgamento (que falha aconteceu, como dizer a regra geral, onde ela está
ancorada); o script faz a contabilidade (IDs, recorrência, promoção, poda, quarentena).

O que muda em relação ao original:

- **a loja é global**, em `~/.codex/executar-demanda/licoes/` — as demandas mudam, os repositórios não. Uma
  lição sobre o `repositorio-api` vale para o próximo projeto que o tocar;
- **o escopo é um repositório**: `--escopo` é o apelido de um repositório configurado no projeto
  (`api`, `ui`), gravado também pelo nome da pasta dele (`repositorio-api`), que é o que
  identifica a lição entre projetos. Lição sobre o método ("skill", ferramenta do harness) não tem
  repositório e é recusada — no tlc, isso é decisão de quem mantém a skill, não lição;
- **a recorrência conta ocorrências distintas (projeto, onda)** no mesmo repositório — o análogo
  das features do tlc. Contar "2 projetos" não confirmaria quase nada;
- **armadilha de um repositório nasce confirmada**: esperando ocorrências, quase toda armadilha
  ficaria candidata e não chegaria ao `iniciar-onda`. Os outros sinais seguem pedindo 2;
- sinais de qualidade e processo, incluindo `armadilha` — as "Armadilhas desta rodada" das consolidações.

Sem âncora (`--fonte`) não há lição: é opinião, e o script recusa.
"""

import datetime as _dt
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum as C  # noqa: E402

DIR = os.path.normpath(os.path.expanduser(
    os.environ.get('EXEC_DEMANDA_LICOES', os.path.join(os.environ.get('CODEX_HOME', os.path.expanduser('~/.codex')), 'executar-demanda', 'licoes'))))
SINAIS = {'mutante_sobrevivente', 'aceite_sem_evidencia', 'teste_removido_ou_ignorado',
          'gate_falhou', 'desvio_do_plano', 'armadilha'}
PADRAO = {'limiar_promocao': 2, 'janela_dias': 180, 'limiar_quarentena': 2}


def _agora():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds')


def _carregar():
    arq = os.path.join(DIR, 'licoes.json')
    if not os.path.exists(arq):
        return dict(PADRAO, proximo=1, licoes=[], criterio='ocorrencias')
    with open(arq, encoding='utf-8') as fh:
        dados = json.load(fh)
    if dados.get('criterio') != 'ocorrencias':
        _migrar(dados)
    return dados


def _salvar(dados):
    os.makedirs(DIR, exist_ok=True)
    C.gravar_json_atomico(os.path.join(DIR, 'licoes.json'), dados)
    _renderizar(dados)


def _norm(texto):
    t = unicodedata.normalize('NFD', texto.casefold())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    t = ''.join(c if (c.isalnum() or c.isspace()) else ' ' for c in t)
    return re.sub(r'\s+', ' ', t).strip()


# Semelhança para achar a mesma lição dita com outras palavras. Não decide nada: o `licao add`
# mostra as parecidas e o modelo escolhe `--mesma L-NNN` ou `--nova`. Calibrada nas candidatas
# registradas: duas lições com a mesma regra ficam perto de 0,2, e o limiar fica abaixo disso.
LIMIAR_PARECIDA = 0.15
STOPWORDS = set('a o e de da do das dos em no na nos nas um uma uns umas que para por com sem se nao '
                'ao aos as os ou mais so ja ele ela isso esse essa este esta pelo pela como quando tem '
                'ter sao ser foi vai cada todo toda'.split())
ATIVAS = ('candidate', 'confirmed')


def _palavras(texto):
    return {w for w in _norm(texto).split() if len(w) > 2 and w not in STOPWORDS}


def _semelhanca(a, b):
    pa, pb = _palavras(a), _palavras(b)
    return len(pa & pb) / len(pa | pb) if pa | pb else 0.0


def _parecidas(dados, repo, texto, limiar=LIMIAR_PARECIDA, ignorar=None):
    saida = []
    for l in dados['licoes']:
        if l['status'] in ATIVAS and l.get('repo') == repo and l['id'] != ignorar:
            s = _semelhanca(texto, l['text'])
            if s >= limiar:
                saida.append((s, l))
    return sorted(saida, key=lambda x: -x[0])


def _somar(dados, l, projeto, ocorrencia, fonte):
    """Soma uma ocorrência à lição e promove pela regra. Devolve True se promoveu."""
    if projeto not in l['projetos']:
        l['projetos'].append(projeto)
    if fonte and fonte not in l['fontes']:
        l['fontes'].append(fonte)
    l.setdefault('ocorrencias', []).append(ocorrencia)
    l['ultima_vez'] = _agora()
    promovida = l['status'] == 'candidate' and len(_ocorrencias(l)) >= dados['limiar_promocao']
    if promovida:
        l['status'] = 'confirmed'
    return promovida


def _chave(sinal, texto, repo=''):
    return sinal + '::' + (repo or '') + '::' + _norm(texto)


RE_ONDA_FONTE = re.compile(r'(?i)onda[- ](\d+[a-z]?)\b')


def _ocorrencias(l):
    """(projeto, onda) distintos em que a lição apareceu. Lição gravada antes do campo
    `ocorrencias` é reconstituída das fontes (`revisao-onda-10.RV1.md` → onda 10)."""
    if 'ocorrencias' in l:
        return {(o['projeto'], o.get('onda') or '?') for o in l['ocorrencias']}
    saida = set()
    projeto = l['projetos'][0] if len(l['projetos']) == 1 else None
    for f in l.get('fontes', []):
        for m in RE_ONDA_FONTE.finditer(f):
            saida.add((projeto or '?', m.group(1).lower()))
    if not saida:
        saida = {(p, '?') for p in l['projetos']}
    return saida


def _repo_do_apelido(projeto, apelido):
    """Pasta do repositório que o apelido nomeia no projeto; '' se não dá para saber."""
    try:
        cfg = C.carregar_estado(C.resolver(projeto))['repos'].get(apelido or '')
    except (SystemExit, Exception):
        return ''
    return os.path.basename(os.path.normpath(cfg['caminho'])) if cfg else ''


def _migrar(dados):
    """Formato novo sem perder nada: chave com o repositório e ocorrências por (projeto, onda)."""
    for l in dados['licoes']:
        if 'ocorrencias' not in l:
            l['ocorrencias'] = [{'projeto': p, 'onda': o, 'fonte': None} for p, o in sorted(_ocorrencias(l))]
        if not l.get('repo'):
            l['repo'] = _repo_do_apelido(l['projetos'][0] if l.get('projetos') else None, l.get('scope'))
        l['key'] = _chave(l['signal'], l['text'], l.get('repo'))
    dados['criterio'] = 'ocorrencias'


def _podar(dados):
    agora = _dt.datetime.now(_dt.timezone.utc)
    mantidas, podadas = [], []
    for l in dados['licoes']:
        if l['status'] == 'candidate':
            idade = (agora - _dt.datetime.fromisoformat(l['ultima_vez'])).days
            if idade > dados['janela_dias']:
                podadas.append(l['id'])
                continue
        mantidas.append(l)
    dados['licoes'] = mantidas
    return podadas


def _renderizar(dados):
    nomes = {'confirmed': 'Confirmadas (carregar ao planejar e ao iniciar onda)',
             'candidate': 'Candidatas (em observação — não usar como regra ainda)',
             'quarantined': 'Em quarentena (falharam quando aplicadas — ignorar)',
             'discarded': 'Descartadas (sobre o método, não sobre um repositório — fora do playbook)',
             'merged': 'Fundidas (a mesma lição de outra, com outras palavras — ver a de destino)'}
    out = ['# Lições — mantido por licoes.py', '',
           '> Gerado. Não edite à mão: `demanda.py licao add|penalize`.',
           '> armadilha de um repositório nasce confirmada; os outros sinais, com %(limiar_promocao)d ocorrências '
           'distintas (projeto, onda) no mesmo repositório · poda de candidata após %(janela_dias)d dias' % dados, '']
    for status, titulo in nomes.items():
        out += ['## ' + titulo, '']
        itens = [l for l in dados['licoes'] if l['status'] == status]
        if not itens:
            out += ['_nenhuma_', '']
        for l in sorted(itens, key=lambda x: x['id']):
            out += ['### %s — %s' % (l['id'], l['text']),
                    '- sinal: `%s` · repositório: `%s` · ocorrências: %s · falhou ao aplicar: %d'
                    % (l['signal'], l.get('repo') or l.get('scope') or '—',
                       ', '.join('%s/onda %s' % po for po in sorted(_ocorrencias(l))), l.get('harmful', 0)),
                    '- fonte: %s' % '; '.join(l['fontes'][:3])]
            if l.get('fundida'):
                out.append('- fundida em %s: %s' % (l['fundida']['em'], l['fundida']['motivo']))
            out.append('')
    with open(os.path.join(DIR, 'LICOES.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out).rstrip() + '\n')


def listar(status='confirmed', escopos=None, busca=None):
    dados = _carregar()
    saida = []
    for l in dados['licoes']:
        if status != 'all' and l['status'] != status:
            continue
        alvos = [x.lower() for x in (l.get('scope'), l.get('repo')) if x]
        if escopos and alvos and not any(e.lower() in alvos for e in escopos):
            continue
        if busca and busca.lower() not in l['text'].lower():
            continue
        saida.append(l)
    return sorted(saida, key=lambda x: x['id'])


def cmd(args):
    # A loja é compartilhada entre as sessões de todos os projetos: um comando por vez.
    os.makedirs(DIR, exist_ok=True)
    with C.trava(os.path.join(DIR, 'licoes.json')):
        return _cmd(args)


def _cmd(args):
    if args.acao == 'add':
        if args.sinal not in SINAIS:
            raise SystemExit('--sinal tem de ser um de: %s' % ', '.join(sorted(SINAIS)))
        if not (args.fonte or '').strip():
            raise SystemExit('--fonte é obrigatória (repo:arquivo:linha, M12, A2.3, seção da consolidação). '
                             'Lição sem âncora é opinião — recusada.')
        if len((args.texto or '').strip()) < 12:
            raise SystemExit('--texto curto demais: a regra geral, numa frase')
        pasta = C.resolver(args.projeto)
        projeto = os.path.basename(pasta)
        estado = C.carregar_estado(pasta)
        cfg = estado['repos'].get((args.escopo or '').strip())
        if not cfg:
            raise SystemExit('--escopo tem de ser um repositório configurado no projeto (%s). Lição sobre '
                             'o método ou a ferramenta não é lição de execução: leve a quem mantém a skill'
                             % (', '.join(sorted(estado['repos'])) or 'nenhum configurado'))
        repo = os.path.basename(os.path.normpath(cfg['caminho']))
        onda = (args.onda or C.onda_ativa(estado) or '').strip() or None
        dados = _carregar()
        _podar(dados)
        k = _chave(args.sinal, args.texto, repo)
        existente = next((l for l in dados['licoes'] if l['key'] == k), None)
        ocorrencia = {'projeto': projeto, 'onda': onda, 'fonte': args.fonte}
        if getattr(args, 'mesma', None):
            existente = next((l for l in dados['licoes'] if l['id'].lower() == args.mesma.lower()), None)
            if not existente:
                raise SystemExit('lição %s não existe' % args.mesma)
            if existente['status'] not in ATIVAS or existente.get('repo') != repo:
                raise SystemExit('recusado: %s é de outro repositório (%s) ou não está ativa (%s)'
                                 % (existente['id'], existente.get('repo') or '—', existente['status']))
        elif not existente and not getattr(args, 'nova', False):
            parecidas = _parecidas(dados, repo, args.texto)
            if parecidas:
                linhas = '\n'.join('  %s (%.0f%%): %s' % (l['id'], 100 * s_, l['text'][:150]) for s_, l in parecidas[:3])
                raise SystemExit('há lição parecida em %s — é a mesma lição com outras palavras? '
                                 '`--mesma L-NNN` soma a ocorrência a ela; `--nova` cria outra:\n%s' % (repo, linhas))
        if existente:
            promovida = _somar(dados, existente, projeto, ocorrencia, args.fonte)
            n = len(_ocorrencias(existente))
            _salvar(dados)
            print('%s atualizada (%d ocorrência(s) distinta(s), %s)%s' % (existente['id'], n, existente['status'],
                                                                         ' — PROMOVIDA' if promovida else ''))
            return 0
        lid = 'L-%03d' % dados['proximo']
        dados['proximo'] += 1
        # Armadilha com escopo de repositório nasce confirmada: esperando 2 ocorrências distintas, quase
        # toda lição ficaria candidata e nunca seria lida. Armadilha é fato observado num repositório,
        # não hipótese a corroborar; os outros sinais seguem pedindo 2.
        status_inicial = 'confirmed' if args.sinal == 'armadilha' and repo else 'candidate'
        dados['licoes'].append({'id': lid, 'key': k, 'text': args.texto.strip(), 'signal': args.sinal,
                                'scope': args.escopo.strip(), 'repo': repo, 'status': status_inicial,
                                'projetos': [projeto], 'fontes': [args.fonte], 'ocorrencias': [ocorrencia],
                                'harmful': 0, 'criada': _agora(), 'ultima_vez': _agora()})
        _salvar(dados)
        print('%s registrada (%s, %s)' % (lid, 'confirmada: armadilha do repositório' if status_inicial == 'confirmed'
                                           else 'candidata', repo))
        return 0
    if args.acao == 'parecidas':
        dados = _carregar()
        ativas = [l for l in dados['licoes'] if l['status'] in ATIVAS
                  and (not args.escopo or args.escopo.lower() in ((l.get('repo') or '').lower(), (l.get('scope') or '').lower()))]
        pares = []
        for i, a in enumerate(ativas):
            for b in ativas[i + 1:]:
                if a.get('repo') == b.get('repo'):
                    s_ = _semelhanca(a['text'], b['text'])
                    if s_ >= args.limiar:
                        pares.append((s_, a, b))
        if not pares:
            print('(nenhum par acima de %.2f)' % args.limiar)
        for s_, a, b in sorted(pares, key=lambda x: -x[0]):
            print('%.2f  %s ~ %s  [%s]\n      %s\n      %s' % (s_, a['id'], b['id'], a.get('repo') or '—',
                                                         a['text'][:140], b['text'][:140]))
        return 0
    if args.acao == 'fundir':
        if len((args.motivo or '').strip()) < 12:
            raise SystemExit('--motivo curto demais: por que as duas são a mesma lição')
        dados = _carregar()
        achar = lambda i: next((l for l in dados['licoes'] if l['id'].lower() == i.lower()), None)
        origem, destino = achar(args.id), achar(args.em)
        if not origem or not destino or origem is destino:
            raise SystemExit('informe duas lições existentes e diferentes')
        if origem['status'] not in ATIVAS or destino['status'] not in ATIVAS:
            raise SystemExit('recusado: só lições ativas (candidata ou confirmada) se fundem')
        if origem.get('repo') != destino.get('repo'):
            raise SystemExit('recusado: %s e %s são de repositórios diferentes' % (origem['id'], destino['id']))
        promovida = False
        for o_ in origem.get('ocorrencias', []) or [{'projeto': p_, 'onda': o2, 'fonte': None}
                                                     for p_, o2 in sorted(_ocorrencias(origem))]:
            promovida = _somar(dados, destino, o_['projeto'], dict(o_), o_.get('fonte')) or promovida
        for f_ in origem['fontes']:
            if f_ not in destino['fontes']:
                destino['fontes'].append(f_)
        origem['status'] = 'merged'
        origem['fundida'] = {'em': destino['id'], 'motivo': args.motivo.strip(), 'quando': _agora()}
        _salvar(dados)
        print('%s fundida em %s (%d ocorrência(s) distinta(s), %s)%s'
              % (origem['id'], destino['id'], len(_ocorrencias(destino)), destino['status'],
                 ' — PROMOVIDA' if promovida else ''))
        return 0
    if args.acao == 'confirmar':
        # Promoção manual de candidata, com o ok do usuário (ex.: armadilha que ficou candidata pela
        # regra antiga, revista uma a uma).
        if len((args.motivo or '').strip()) < 12:
            raise SystemExit('--motivo curto demais: quem confirmou e por quê')
        dados = _carregar()
        alvo = next((l for l in dados['licoes'] if l['id'].lower() == args.id.lower()), None)
        if not alvo:
            raise SystemExit('lição %s não existe' % args.id)
        if alvo['status'] != 'candidate':
            raise SystemExit('%s não é candidata (%s)' % (alvo['id'], alvo['status']))
        alvo['status'] = 'confirmed'
        alvo['confirmada'] = {'motivo': args.motivo.strip(), 'em': _agora()}
        _salvar(dados)
        print('%s confirmada: %s' % (alvo['id'], args.motivo.strip()))
        return 0
    if args.acao == 'descartar':
        if len((args.motivo or '').strip()) < 12:
            raise SystemExit('--motivo curto demais: por que a lição sai')
        dados = _carregar()
        alvo = next((l for l in dados['licoes'] if l['id'].lower() == args.id.lower()), None)
        if not alvo:
            raise SystemExit('lição %s não existe' % args.id)
        alvo['status'] = 'discarded'
        alvo['descartada'] = {'motivo': args.motivo.strip(), 'em': _agora()}
        _salvar(dados)
        print('%s descartada: %s' % (alvo['id'], args.motivo.strip()))
        return 0
    if args.acao == 'list':
        itens = listar(args.status, [args.escopo] if args.escopo else None, args.busca)
        if not itens:
            print('(nenhuma lição %s)' % args.status)
        for l in itens:
            print('%s (%s, %d ocorrência(s))%s: %s' % (l['id'], l['status'], len(_ocorrencias(l)),
                                                       ' [%s]' % (l.get('repo') or l.get('scope')) if (l.get('repo') or l.get('scope')) else '',
                                                       l['text']))
        return 0
    if args.acao == 'penalize':
        dados = _carregar()
        alvo = next((l for l in dados['licoes'] if l['id'].lower() == args.id.lower()), None)
        if not alvo:
            raise SystemExit('lição %s não existe' % args.id)
        alvo['harmful'] = alvo.get('harmful', 0) + 1
        if alvo['harmful'] >= dados['limiar_quarentena']:
            alvo['status'] = 'quarantined'
        _salvar(dados)
        print('%s penalizada (%d, %s)' % (alvo['id'], alvo['harmful'], alvo['status']))
        return 0
    if args.acao == 'status':
        dados = _carregar()
        c = {}
        for l in dados['licoes']:
            c[l['status']] = c.get(l['status'], 0) + 1
        print('lições: %d · confirmadas %d · candidatas %d · quarentena %d · descartadas %d · fundidas %d · loja %s'
              % (len(dados['licoes']), c.get('confirmed', 0), c.get('candidate', 0), c.get('quarantined', 0),
                 c.get('discarded', 0), c.get('merged', 0), DIR))
        return 0
    raise SystemExit('ação desconhecida')
