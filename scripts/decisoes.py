#!/usr/bin/env python3
"""Livro de decisões e aprovação do plano — onde a delegação deixa de ser só texto.

Decidir é do usuário (ou do documento que ele aprovou: a análise, a ER). O modelo redige, mas
não decide, e sobretudo não registra como do usuário o que o usuário não disse. Por isso:

- **toda decisão entra por `decisao add`**, com fonte conferida: `usuario` exige uma citação
  literal que esteja no log do hook `registrar-fala-usuario` (o que o usuário digitou ou
  respondeu); `analise` exige um assunto que exista na análise; `er` exige a ER na pasta. O
  script numera (`D<n>`) e escreve a tabela de `## Decisões` do plano num bloco gerado — linha
  `D<n>` escrita à mão fora dele é recusada pelo `validar-plano`;
- **todo relaxamento de gate aponta uma decisão** (`--decisao D<n>`): iniciar fora de ordem,
  tarefa sem commit, arquivo fora do Onde, mutante equivalente, achado aceito;
- **o plano é selado na aprovação** (`aprovar-plano --citacao`): o hash do plano normalizado
  (sem `**Commits:**`, sem a marca `[x]`, sem o bloco de decisões) fica gravado, e iniciar onda,
  commitar, revisar, fechar e dar GO recusam um plano que mudou depois disso. Tarefa nova,
  aceite reclassificado, Onde ampliado, risco rebaixado: tudo passa de novo pelo usuário.
"""

import difflib
import os
import re
import shutil

import comum as C

FONTES = ('usuario', 'analise', 'er')
RE_D = re.compile(r'\bD(\d+)\b')

# Para que uma decisão nova serve (`decisao add --para`). Uma frase real do usuário, reciclada, não
# serve de base para outro relaxamento: a decisão com `para` só vale para a finalidade (e o alvo) que ela diz.
FINALIDADES = ('sem-teste', 'sem-commit', 'sem-mutante', 'equivalente', 'fora-do-onde', 'skill-alterada',
               'analise-alterada', 'desbloquear', 'anular', 'base', 'oraculo', 'sem-padrao', 'sem-analise',
               'configurar', 'preexistentes', 'testar', 'fora-de-ordem', 'descartar-pendencia')
# Relaxamentos que o mesmo comando grava no estado: valem uma vez só. (Equivalente e sem-mutante ficam
# presos ao alvo, não ao uso: a conferência deles se repete no fechamento.)
USO_UNICO = ('sem-teste', 'sem-commit', 'desbloquear', 'anular', 'base')
# Decisões de engenharia: com a autorização do usuário no projeto (`decisao add --autoriza engenharia`), o
# modelo decide e registra (`decisao engenharia`), com justificativa, só nestas finalidades. Cada uma vale uma
# vez, nunca serve de valor esperado, e o parecer as lista para o usuário rever em lote.
FINALIDADES_ENGENHARIA = ('equivalente', 'fora-do-onde')
# Uma marca por processo: o mesmo comando pode usar a decisão mais de uma vez; outro comando, não.
_PROCESSO = '%d-%s' % (os.getpid(), os.urandom(4).hex())


# ------------------------------------------------------------------------------ livro

def livro(estado):
    return estado.setdefault('decisoes', [])


def achar(estado, did):
    for d in livro(estado):
        if d['id'] == did:
            return d
    return None


def exigir(estado, did, so_usuario=True, para=None, alvo=None, consumir=True, engenharia=False):
    """Mensagem de erro, ou None se `did` é uma decisão válida para relaxar um gate.

    Decisão nova (com `para`, de `decisao add --para`) só vale para a finalidade e o alvo que registrou,
    tem a fala conferida de novo no log do hook e, nos relaxamentos de `USO_UNICO`, vale uma vez. Decisão
    sem `para` não relaxa gate que pede finalidade (serve de registro e de âncora de valor). `consumir=False`: só confere
    (reconferência no fechamento), sem marcar o uso. Quem consome grava o estado em seguida. `engenharia`: o
    gate aceita também a decisão de engenharia do modelo, com a autorização do usuário vigente no uso."""
    did = (did or '').strip()
    if not re.fullmatch(r'D\d+', did):
        return 'informe a decisão como D<n> (decisão do usuário registrada com `decisao add`)'
    d = achar(estado, did)
    if not d:
        return '%s não está no livro de decisões — só `decisao add` cria decisão' % did
    if d.get('revogada_por'):
        return '%s foi revogada por %s' % (did, d['revogada_por'])
    if d['fonte'] == 'engenharia':
        if not engenharia:
            return ('%s é decisão de engenharia (do modelo, autorizada por %s); este gate é do usuário — '
                    'registre a dele com citação' % (did, d.get('autorizada_por')))
        if not autorizacao(estado, 'engenharia'):
            return ('%s é decisão de engenharia e a autorização do usuário (%s) não vale mais — o gate volta a '
                    'pedir a decisão dele' % (did, d.get('autorizada_por')))
        if d.get('para') != para:
            return '%s foi registrada para %r, não para %r' % (did, d.get('para'), para)
        if alvo and d.get('alvo') and d['alvo'] != alvo:
            return '%s foi registrada para o alvo %s, não para %s' % (did, d['alvo'], alvo)
        if consumir:
            if d.get('usada_em') and d['usada_em'] != _PROCESSO:
                return '%s (engenharia, %s) já foi usada — vale uma vez' % (did, d['para'])
            d['usada_em'] = _PROCESSO
        return None
    if so_usuario and d['fonte'] != 'usuario':
        return ('%s tem fonte %s; relaxar um gate é decisão do usuário (fonte usuario, com '
                'citação)' % (did, d['fonte']))
    if para and not d.get('para') and d['fonte'] == 'usuario':
        return ('%s foi registrada sem finalidade: relaxar um gate pede a decisão do usuário para este fim — '
                '`decisao add … --para %s`' % (did, para))
    if d.get('para'):
        if para and d['para'] != para:
            return ('%s foi registrada para %r (alvo %s), não para %r — cada decisão serve a um '
                    'relaxamento só; registre a do usuário para este (`decisao add --para %s`)'
                    % (did, d['para'], d.get('alvo') or 'qualquer', para, para))
        if alvo and d.get('alvo') and d['alvo'] != alvo:
            return '%s foi registrada para o alvo %s, não para %s' % (did, d['alvo'], alvo)
        if d['fonte'] == 'usuario' and d.get('fala') and not C.fala_por_momento(d['fala'].get('em'), d.get('citacao')):
            return ('a fala que sustenta %s não está mais no log do hook (%s): sem ela a decisão não se prova'
                    % (did, d['fala'].get('em')))
        if consumir and d['para'] in USO_UNICO:
            if d.get('usada_em') and d['usada_em'] != _PROCESSO:
                return '%s (%s) já foi usada em outro comando — relaxamento vale uma vez; registre outra decisão' \
                       % (did, d['para'])
            d['usada_em'] = _PROCESSO
    return None


def autorizacao(estado, o_que):
    """A D<n> vigente que autoriza `o_que` no projeto, ou None."""
    did = (estado.get('autorizacoes') or {}).get(o_que)
    return did if did and not exigir(estado, did) else None


def exigir_autorizacao_de_testes(estado, decisao):
    """Mensagem de erro, ou None. Rodar teste é do usuário: ou a autorização do projeto
    (`decisao add --autoriza testes`), ou uma decisão para esta vez (`--decisao D<n>`)."""
    if autorizacao(estado, 'testes'):
        return None
    if decisao:
        return exigir(estado, decisao, para='testar')
    return ('rodar testes é decisão do usuário e o projeto não tem autorização de testes — '
            'registre a dele com `decisao add --autoriza testes --fonte usuario --citacao …`, ou '
            'passe --decisao D<n> para esta execução')


def exigir_varias(estado, valores, para=None, alvo=None, engenharia=False):
    """(lista de D<n>, erro). `valores`: o que veio de `--decisao` repetido e/ou separado por
    vírgula. Todas têm de ser decisões vigentes do usuário."""
    ids = [x for v in (valores or []) for x in re.split(r'[,\s]+', v or '') if x]
    if not ids:
        return [], 'sem --decisao'
    for did in ids:
        erro = exigir(estado, did, para=para, alvo=alvo, engenharia=engenharia)
        if erro:
            return ids, erro
    return ids, None


def _fonte_legivel(d):
    if d['fonte'] == 'usuario':
        cit = d['citacao'] if len(d['citacao']) <= 90 else d['citacao'][:87] + '…'
        return 'usuário: “%s”' % cit.replace('|', '\\|')
    if d['fonte'] == 'analise':
        return 'análise: %s' % d['ref']
    if d['fonte'] == 'engenharia':
        return 'engenharia (%s, autorizada por %s)' % (d.get('para'), d.get('autorizada_por'))
    return 'ER %s' % d['ref']


def tabela(decisoes):
    linhas = ['| # | Decisão | Fonte | Data |', '|---|---|---|---|']
    for d in decisoes:
        texto = d['texto'].replace('|', '\\|').replace('\n', ' ')
        data = d['registrada_em'][8:10] + '/' + d['registrada_em'][5:7] + '/' + d['registrada_em'][:4]
        if d.get('revogada_por'):
            linhas.append('| ~~%s~~ | ~~%s~~ **Revogada por %s** | %s | %s |'
                          % (d['id'], texto, d['revogada_por'], _fonte_legivel(d), data))
        else:
            linhas.append('| %s | %s | %s | %s |' % (d['id'], texto, _fonte_legivel(d), data))
    return '\n'.join(linhas) if len(linhas) > 2 else '_nenhuma decisão registrada_'


def renderizar(pasta, estado):
    """Reescreve o bloco gerado de decisões do plano, se o plano o tiver. Só grava se mudou."""
    arq = C.arquivo_plano(pasta)
    if not os.path.exists(arq):
        return False
    texto = C.ler(arq)
    novo, achou = C.trocar_bloco(texto, 'decisoes', tabela(livro(estado)))
    if achou and novo != texto:
        C.gravar(arq, novo)
    return achou


def add(pasta, args):
    estado = C.carregar_estado(pasta)
    texto = ' '.join((args.texto or '').split())
    if len(texto) < 10:
        raise SystemExit('texto da decisão curto demais')
    if args.fonte not in FONTES:
        raise SystemExit('fonte tem de ser usuario, analise ou er')
    reg = {'texto': texto, 'fonte': args.fonte, 'ref': '', 'citacao': '', 'fala': None,
           'registrada_em': C.agora(), 'onda': C.onda_ativa(estado), 'revogada_por': None}
    if args.fonte == 'usuario':
        entrada, erro = C.citacao_do_usuario(args.citacao, locais=C.locais_do_projeto(pasta, estado))
        if erro:
            raise SystemExit('recusado: ' + erro)
        reg['citacao'] = ' '.join(args.citacao.split())
        reg['fala'] = {k: entrada.get(k) for k in ('em', 'session_id', 'tipo')}
        if entrada.get('tipo') == 'resposta':
            # a resposta foi a opção que o modelo marcou como recomendada? (medido no painel)
            resp = entrada.get('resposta') or ''
            reg['fala']['recomendada'] = bool((entrada.get('recomendada') and resp == entrada['recomendada'])
                                              or re.search(r'\((Recomendad[oa]|Recommended)\)', resp))
        for doc in _lista_docs(getattr(args, 'doc', None)):
            reg.setdefault('docs', []).append(_congelar_doc(pasta, doc, entrada, None))
    elif getattr(args, 'doc', None):
        raise SystemExit('recusado: --doc é para decisão do usuário (o documento que ele confirmou)')
    elif args.fonte == 'analise':
        import plano as P
        analise = P.ler_analise(pasta)
        if not analise:
            raise SystemExit('recusado: não há %s' % os.path.basename(C.arquivo_analise(pasta)))
        if C.chave(args.ref) not in [C.chave(a) for a in analise['assuntos']]:
            raise SystemExit('recusado: assunto %r não existe na análise (assuntos: %s)'
                             % (args.ref, '; '.join(analise['assuntos'])))
        reg['ref'] = args.ref.strip()
    else:
        if not C.arquivos_er(pasta):
            raise SystemExit('recusado: nenhuma ER (ER*.docx) na pasta do projeto')
        if not re.fullmatch(r'\d+(\.\d+)*', (args.ref or '').strip()):
            raise SystemExit('recusado: --ref da ER é a coordenada do item, como 2.3.1')
        reg['ref'] = args.ref.strip()
    if getattr(args, 'autoriza', None):
        if args.fonte != 'usuario':
            raise SystemExit('recusado: autorizar %s é decisão do usuário (fonte usuario, com citação)' % args.autoriza)
        reg['autoriza'] = args.autoriza
    if getattr(args, 'para', None):
        if args.fonte != 'usuario':
            raise SystemExit('recusado: --para é da decisão do usuário (fonte usuario, com citação)')
        if args.para not in FINALIDADES:
            raise SystemExit('recusado: --para %r não existe (%s)' % (args.para, ', '.join(FINALIDADES)))
        reg['para'] = args.para
        reg['alvo'] = (getattr(args, 'alvo', None) or '').strip() or None
    elif getattr(args, 'alvo', None):
        raise SystemExit('recusado: --alvo vai com --para')
    reg['id'] = C.proximo_id(estado, 'D')
    for d in reg.get('docs', []):
        d['copia'] = _gravar_copia(pasta, reg['id'], d.pop('_origem'))
    livro(estado).append(reg)
    if reg.get('autoriza'):
        estado.setdefault('autorizacoes', {})[reg['autoriza']] = reg['id']
    C.salvar_estado(pasta, estado)
    no_plano = renderizar(pasta, estado)
    print('%s registrada (%s): %s' % (reg['id'], _fonte_legivel(reg), texto))
    if not no_plano:
        print('  aviso: o plano ainda não tem o bloco <!-- gerado:decisoes:inicio/fim --> em '
              '## Decisões — a tabela entra quando ele tiver')
    return 0


def _lista_docs(valor):
    return [x.strip() for x in (valor or '').split(',') if x.strip()]


def _congelar_doc(pasta, doc, fala, did):
    """Documento da pasta do projeto que a decisão do usuário cita. Só vale se o nome dele está na
    fala citada (na resposta, na pergunta que ele respondeu ou no que ele digitou): é a prova de
    que ele viu aquele documento. O conteúdo é congelado numa cópia — o valor esperado é procurado
    no que ele confirmou, não numa versão editada depois."""
    arq = os.path.abspath(doc if os.path.isabs(doc) else os.path.join(pasta, doc))
    if not arq.startswith(os.path.abspath(pasta) + os.sep) or not os.path.isfile(arq):
        raise SystemExit('recusado: --doc tem de ser um arquivo da pasta do projeto: %s' % doc)
    nome = os.path.basename(arq)
    # O plano e o que a skill gera não são fonte: o aceite do plano não prova a si mesmo.
    if re.match(r'(?i)^(plano(?:-\d|\.md$)|onda-|revisao-onda-|autoconferencia-onda-|estado-atual(?:-|\.md$)|painel(?:-|\.html$)|parecer-liberacao-)', nome):
        raise SystemExit('recusado: %s é artefato da execução (plano, consolidação, revisão, estado), '
                         'não documento-fonte — o valor esperado não pode vir dele' % nome)
    texto_fala = C.chave(fala.get('texto', ''))
    if C.chave(nome) not in texto_fala and C.chave(os.path.splitext(nome)[0]) not in texto_fala:
        raise SystemExit('recusado: %s não aparece na fala citada — o usuário não confirmou esse documento. '
                         'Pergunte citando o nome do arquivo' % nome)
    reg = {'arquivo': os.path.relpath(arq, pasta), 'sha1': C.sha1_arquivo(arq), '_origem': arq}
    if did:
        reg['copia'] = _gravar_copia(pasta, did, arq)
        del reg['_origem']
    return reg


def _gravar_copia(pasta, did, origem):
    destino_dir = os.path.join(pasta, 'evidencias', 'decisoes')
    os.makedirs(destino_dir, exist_ok=True)
    destino = os.path.join(destino_dir, '%s-%s' % (did, os.path.basename(origem)))
    shutil.copy2(origem, destino)
    return os.path.relpath(destino, pasta)


def anexar(pasta, args):
    """Liga a uma decisão do usuário já registrada o documento que a fala dela cita."""
    estado = C.carregar_estado(pasta)
    d = achar(estado, args.id)
    if not d:
        raise SystemExit('%s não está no livro' % args.id)
    if d['fonte'] != 'usuario' or d.get('revogada_por'):
        raise SystemExit('recusado: só decisão vigente do usuário recebe documento')
    fala = C.fala_por_momento((d.get('fala') or {}).get('em'), d.get('citacao'))
    if not fala:
        raise SystemExit('recusado: a fala de %s não está no log — sem ela não há como provar que o '
                         'usuário viu o documento' % d['id'])
    for doc in _lista_docs(args.doc):
        reg = _congelar_doc(pasta, doc, fala, d['id'])
        d.setdefault('docs', []).append(reg)
        print('%s: %s anexado (cópia em %s)' % (d['id'], reg['arquivo'], reg['copia']))
    C.salvar_estado(pasta, estado)
    return 0


def engenharia(pasta, args):
    """`decisao engenharia`: o modelo decide, com a autorização do usuário vigente, um relaxamento de engenharia
    (mutante equivalente, arquivo vizinho fora do Onde) e o registra com a justificativa."""
    estado = C.carregar_estado(pasta)
    aut = autorizacao(estado, 'engenharia')
    if not aut:
        raise SystemExit('recusado: o projeto não tem autorização de engenharia do usuário — `decisao add --autoriza '
                         'engenharia --fonte usuario --citacao …`; sem ela, o gate pede a decisão dele')
    if args.para not in FINALIDADES_ENGENHARIA:
        raise SystemExit('recusado: decisão de engenharia é só para %s; %r é do usuário'
                         % (' ou '.join(FINALIDADES_ENGENHARIA), args.para))
    texto = ' '.join((args.texto or '').split())
    if len(texto) < 40:
        raise SystemExit('recusado: justificativa curta demais — diga por quê (o usuário a revê no parecer)')
    alvo = (getattr(args, 'alvo', None) or '').strip() or None
    if args.para == 'equivalente':
        import mutantes as M
        s_, m = M._mutante(estado, alvo)
        if not m or s_.get('tipo') == 'autor' or m['resultado'] != 'sobrevivente':
            raise SystemExit('recusado: --alvo de equivalente é um M<n> sobrevivente de sessão do revisor')
        alvo = m['id']
    reg = {'id': C.proximo_id(estado, 'D'), 'texto': texto, 'fonte': 'engenharia', 'ref': '', 'citacao': '',
           'fala': None, 'registrada_em': C.agora(), 'onda': C.onda_ativa(estado), 'revogada_por': None,
           'para': args.para, 'alvo': alvo, 'autorizada_por': aut}
    livro(estado).append(reg)
    C.salvar_estado(pasta, estado)
    renderizar(pasta, estado)
    print('%s registrada (engenharia, %s%s, autorizada por %s): %s'
          % (reg['id'], args.para, ' ' + alvo if alvo else '', aut, texto))
    return 0


def rulings(estado):
    """As decisões de engenharia, para o usuário rever em lote (fechamento e parecer)."""
    return [d for d in livro(estado) if d.get('fonte') == 'engenharia']


def revogar(pasta, args):
    estado = C.carregar_estado(pasta)
    d = achar(estado, args.id)
    if not d:
        raise SystemExit('%s não está no livro' % args.id)
    if d.get('revogada_por'):
        raise SystemExit('%s já foi revogada por %s' % (args.id, d['revogada_por']))
    # decisão do usuário só é revogada por outra do usuário: análise ou ER não desfazem o que ele disse
    erro = exigir(estado, args.por, so_usuario=d['fonte'] == 'usuario', consumir=False)
    if erro:
        raise SystemExit('recusado: ' + erro)
    if args.por == args.id:
        raise SystemExit('uma decisão não revoga a si mesma')
    d['revogada_por'] = args.por
    C.salvar_estado(pasta, estado)
    renderizar(pasta, estado)
    print('%s revogada por %s' % (args.id, args.por))
    return 0


def listar(pasta, args):
    estado = C.carregar_estado(pasta)
    print(tabela(livro(estado)))
    return 0


# ------------------------------------------------------------------------------ aprovação

def registrar_validacao(pasta, estado):
    """Chamado pelo `validar-plano` sem erro: grava que esta versão do plano foi validada (e,
    portanto, pode ser mostrada ao usuário). A aprovação precisa de uma fala posterior a isso."""
    h = C.hash_plano(C.ler(C.arquivo_plano(pasta)))
    ap = estado.get('plano_validado')
    if not ap or ap.get('hash') != h:
        estado['plano_validado'] = {'hash': h, 'em': C.agora_fino()}
        C.salvar_estado(pasta, estado)


def aprovar(pasta, args):
    import plano as P
    estado = C.carregar_estado(pasta)
    renderizar(pasta, estado)
    rel, _p = P.validar(pasta, estado)
    if rel.erros:
        rel.titulo = 'aprovar-plano: o plano não passa no validar-plano'
        return rel.imprimir()
    registrar_validacao(pasta, estado)
    arq = C.arquivo_plano(pasta)
    h = C.hash_plano(C.ler(arq))
    validado = estado['plano_validado']
    entrada, erro = C.citacao_do_usuario(args.citacao, depois_de=C.epoch_iso(validado['em']),
                                         locais=C.locais_do_projeto(pasta, estado))
    if erro:
        raise SystemExit('recusado: ' + erro)
    aprovacoes = estado.setdefault('aprovacoes_plano', [])
    arq_analise = C.arquivo_analise(pasta)
    selo = C.sha1_arquivo(arq_analise) if os.path.exists(arq_analise) else None
    # Mesmo plano e mesma análise (ou aprovação de antes do selo): nada a refazer. Mesmo plano com a
    # análise mudada é a reaprovação que o `iniciar-onda` pede, e sela a análise de novo.
    if aprovacoes and aprovacoes[-1]['hash'] == h and (
            'analise_sha1' not in aprovacoes[-1] or aprovacoes[-1]['analise_sha1'] == selo):
        print('o plano já está aprovado nesta versão (%s)' % aprovacoes[-1]['id'])
        return 0
    aid = 'AP%d' % (len(aprovacoes) + 1)
    pasta_copias = os.path.join(pasta, 'evidencias', 'plano-aprovado')
    os.makedirs(pasta_copias, exist_ok=True)
    copia = os.path.join(pasta_copias, '%s-%s' % (aid, os.path.basename(arq)))
    shutil.copy2(arq, copia)
    comum, ondas = C.selo_por_onda(C.ler(arq))
    vigentes = ondas_aprovadas(estado)
    novas = [o for o in ondas if vigentes.get(o) != ondas[o]]
    registro = {'id': aid, 'hash': h, 'hash_comum': comum, 'hash_ondas': ondas, 'ondas_aprovadas': novas,
                'em': C.agora(), 'citacao': ' '.join(args.citacao.split()),
                'fala': {k: entrada.get(k) for k in ('em', 'session_id', 'tipo')},
                'copia': os.path.relpath(copia, pasta), 'analise_sha1': selo}
    if selo:
        copia_analise = os.path.join(pasta_copias, '%s-%s' % (aid, os.path.basename(arq_analise)))
        shutil.copy2(arq_analise, copia_analise)
        registro['analise_copia'] = os.path.relpath(copia_analise, pasta)
    aprovacoes.append(registro)
    C.salvar_estado(pasta, estado)
    print('plano aprovado (%s, hash %s) — citação conferida na fala de %s' % (aid, h, entrada.get('em')))
    if novas:
        print('  esta aprovação cobre a(s) onda(s) nova(s) ou mudada(s): %s' % ', '.join(novas))
    return 0


def ondas_aprovadas(estado):
    """{onda: hash da seção} pelo AP mais recente que trouxe o selo de cada onda."""
    vigentes = {}
    for ap in estado.get('aprovacoes_plano') or []:
        vigentes.update(ap.get('hash_ondas') or {})
    return vigentes


def conferir_aprovacao(pasta, estado, onda=None):
    """Mensagem de erro, ou None. Sem `onda`: o plano atual é exatamente o último aprovado (parecer). Com `onda`:
    a parte comum é a da última aprovação e a seção da onda é a que o usuário aprovou por último — mudar outra
    onda (acrescentar a seguinte, por exemplo) não para esta."""
    aprovacoes = estado.get('aprovacoes_plano') or []
    if not aprovacoes:
        return ('plano não aprovado — mostre-o ao usuário e, com a resposta dele, '
                '`aprovar-plano --citacao "<o que ele disse>"`')
    arq = C.arquivo_plano(pasta)
    if not os.path.exists(arq):
        return 'plano não encontrado: %s' % arq
    if onda is not None and aprovacoes[-1].get('hash_comum'):
        comum, ondas = C.selo_por_onda(C.ler(arq))
        if comum != aprovacoes[-1]['hash_comum']:
            return ('a parte comum do plano (fora das seções de onda) mudou depois da aprovação %s — `plano diff` '
                    'mostra o quê; mostre ao usuário e aprove de novo' % aprovacoes[-1]['id'])
        aprovada = ondas_aprovadas(estado).get(onda)
        if aprovada is None:
            return ('a onda %s ainda não foi aprovada — mostre-a ao usuário e, com a resposta dele, '
                    '`aprovar-plano --citacao "<o que ele disse>"`' % onda)
        if ondas.get(onda) != aprovada:
            return ('a seção da onda %s mudou depois da aprovação — `plano diff` mostra o quê; mostre ao usuário '
                    'e aprove de novo' % onda)
        return None
    if C.hash_plano(C.ler(arq)) != aprovacoes[-1]['hash']:
        return ('o plano mudou depois da aprovação %s — `plano diff` mostra o quê; mostre ao '
                'usuário e aprove de novo' % aprovacoes[-1]['id'])
    return None


def diff(pasta, args):
    estado = C.carregar_estado(pasta)
    aprovacoes = estado.get('aprovacoes_plano') or []
    if not aprovacoes:
        raise SystemExit('nenhuma aprovação registrada')
    ult = aprovacoes[-1]
    antigo = C.plano_normalizado(C.ler(os.path.join(pasta, ult['copia']))).splitlines(True)
    novo = C.plano_normalizado(C.ler(C.arquivo_plano(pasta))).splitlines(True)
    linhas = list(difflib.unified_diff(antigo, novo, 'aprovado (%s)' % ult['id'], 'atual'))
    if not linhas:
        print('o plano atual é o aprovado em %s' % ult['id'])
        return 0
    print(''.join(linhas))
    return 1
