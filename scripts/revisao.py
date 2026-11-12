#!/usr/bin/env python3
"""Revisão independente de uma onda: esqueleto e validação do `revisao-onda-N.md`.

Quem escreve a revisão é um subagente novo (referencias/revisor.md) — autor ≠ revisor. O script
não tem como provar quem escreveu, mas prova o que dá para provar:

- o código **não mudou** desde o `revisao iniciar` (fingerprint gravado nele, pelo conteúdo:
  arquivo mudado depois do início vence a revisão; commit sem mudança de conteúdo, não). Antes
  era uma comparação de datas com resolução de segundo, que falhava quando o commit e o início
  caíam no mesmo segundo;
- o **plano não mudou** desde o início da revisão (o revisor não edita plano) e é o aprovado;
- **o esperado vem do documento, não do código**: a coluna Esperado cita a âncora (análise, ER
  x.y ou D<n>) e o valor literal entre crases, e o script confere que o literal está lá. Valor
  que nenhum documento define é LACUNA — e pergunta ao usuário;
- **evidência ou zero**: cada aceite tem linha; cada referência `repo:caminho:linha` resolve para
  um arquivo que existe, e o trecho citado entre crases **está** naquela linha (ou nas três
  seguintes) — referência que não bate com o código não prova nada;
- aceite com teste automatizado tem de apontar para arquivo de **teste** (a asserção), não para
  o código de produção;
- houve mutante válido para a onda, e as seções de asserção rasa e limites foram preenchidas.
"""

import os
import re

import comum as C
import decisoes as DC
import mutantes as M
import plano as P

VEREDITOS = ('APROVADA', 'REPROVADA')
# Cada lacuna ranqueada começa por uma classe. Alimenta o painel e decide se a rodada seguinte pode ser
# mecânica (`revisao confirmar`); o veredito segue APROVADA/REPROVADA.
CLASSES_LACUNA = ('teste-fraco', 'especificacao', 'defeito', 'pendencia-nao-bloqueante', 'equivalente-candidato')
RE_ITEM_LACUNA = re.compile(r'^\s*(?:\d+[.)]|[-*])\s+(.*)$')
RESULTADOS = ('OK', 'FALHA', 'LACUNA')
RE_REF = re.compile(r'(?P<repo>[\w.-]+):(?P<caminho>[^\s:`|;]+):(?P<linha>\d+)')
RE_EVID = re.compile(r'evidencia:(?P<caminho>[^\s`|;]+)')


def _revisoes(estado, oid):
    return [r for r in estado['revisoes'] if r['onda'] == oid]


def testes_sem_aceite(corpo):
    """[(nº da linha, match de repo:caminho:linha ou None, destino)] das linhas de dado da tabela de
    "Testes sem aceite". Cabeçalho (primeira célula "Teste…") e separador não contam; texto fora da
    tabela ("nenhum: …") também não."""
    linhas = [(i, ln.strip()) for i, ln in enumerate((corpo or '').splitlines(), 1)
              if ln.strip().startswith('|') and ln.strip().endswith('|')
              and not re.fullmatch(r'\|[\s:|-]+\|', ln.strip())]
    achados = []
    for i, ln in linhas:
        cel = [c.strip() for c in ln.strip('|').split('|')]
        if cel and C.chave(cel[0]).startswith('teste'):
            continue                                # o cabeçalho (`| Teste | … |`)
        achados.append((i, RE_REF.search(cel[0]) if cel else None, cel[-1] if len(cel) >= 3 else ''))
    return achados


def classes_das_lacunas(corpo):
    """[(n, classe ou None, texto)] dos itens da seção "Lacunas ranqueadas". A classe é a primeira palavra do
    item (aceita crases, negrito e colchetes em volta). "nenhuma" não é item; o modelo `<…>` por preencher, também não."""
    itens = []
    for ln in (corpo or '').splitlines():
        m = RE_ITEM_LACUNA.match(ln)
        if not m:
            continue
        texto = m.group(1).strip()
        sem = re.sub(r'^[\s*`\[(_]+', '', texto)
        if not sem or sem.startswith('<') or C.chave(sem).startswith(('nenhum', 'nada')):
            continue
        palavra = re.match(r'[A-Za-zÀ-ÿ-]+', sem)
        classe = C.chave(palavra.group(0)) if palavra else None
        itens.append((len(itens) + 1, classe if classe in CLASSES_LACUNA else None, texto))
    return itens


def nao_preenchida(pasta, onda):
    """Id (RV<k>) da revisão cujo arquivo ainda está com o modelo (`**<APROVADA | REPROVADA>**`), ou None. O
    esqueleto fica no disco se o revisor não terminou — e a onda parece ter revisão."""
    arq = C.arquivo_revisao(pasta, onda)
    if not os.path.exists(arq):
        return None
    texto = C.ler(arq)
    if '**<APROVADA | REPROVADA>**' not in texto:
        return None
    m = re.search(r'\|\s*Revis[aã]o\s*\|\s*(RV\d+)', texto[:1500])
    return m.group(1) if m else 'RV?'


def aceites_ativos(o):
    """Aceites da onda que não foram reclassificados (riscados com decisão)."""
    return [aid for aid in o['ordem_aceites'] if not o['aceites'][aid]['reclassificado']]


def aceites_da_revisao(pasta, reg):
    """Os aceites ativos quando a revisão começou: gravados no registro; nas revisões anteriores a
    esse campo, os IDs da tabela "Aceite a aceite" do arquivo dela."""
    if reg.get('aceites') is not None:
        return list(reg['aceites'])
    base = C.arquivo_revisao(pasta, reg['onda'])
    cabecalho = re.compile(r'\|\s*Revis[aã]o\s*\|\s*%s\b' % re.escape(reg['id']))
    for arq in (base.replace('.md', '.%s.md' % reg['id']), base):
        if os.path.exists(arq):
            texto = C.ler(arq)
            if cabecalho.search(texto[:1500]):
                ids = []
                for cel in C.linhas_de_tabela(C.secao(texto, r'^aceite a aceite')):
                    aid = cel[0].strip('*` ') if cel else ''
                    if C.RE_ACEITE.fullmatch(aid) and aid not in ids:
                        ids.append(aid)
                return ids
    return None


def _autoconferencias(estado, oid):
    return [r for r in estado.get('autoconferencias', []) if r['onda'] == oid]


ESQUELETO_AUTO = """# Autoconferência da Onda {onda} — {titulo} ({rotulo})

| | |
|---|---|
| Autoconferência | {acid}, iniciada em {inicio} |
| Código conferido | {fps} |

Quem implementou confere, antes de chamar o revisor, o que ele já pode ver sozinho: cada aceite
com a asserção que o prova e o valor esperado na fonte, e as asserções rasas. Não
conta para o fechamento — serve para a revisão não reprovar pelo que o autor já podia ter pego.

## Aceite a aceite

Mesmo formato da revisão. Resultado: OK, FALHA ou LACUNA — a autoconferência só passa com todo
aceite OK; o que não está OK vira teste (ou pergunta ao usuário) antes da revisão.

| Aceite | Evidência | Trecho | Esperado (análise/ER) | Resultado |
|---|---|---|---|---|
{linhas_aceite}

## Asserções rasas

<para cada classe de teste da onda: verify sem conferir estado, any() onde o valor importa, só assertNotNull, só o caminho feliz — passaria com uma implementação errada plausível?>
"""


def _linhas_aceite(o, onda):
    return '\n'.join('| %s | | | %s | |' % (aid, re.sub(r'^A%s\.\d+\s*' % re.escape(onda), '',
                                                         C.sem_riscado(o['aceites'][aid]['texto'])).strip()[:120])
                     for aid in o['ordem_aceites'] if not o['aceites'][aid]['reclassificado'])


def iniciar_autoconferencia(pasta, args):
    estado = C.carregar_estado(pasta)
    p = P.Plano(C.arquivo_plano(pasta))
    o = p.onda(args.onda)
    eo = estado['ondas'].get(args.onda)
    if not o or not eo or eo.get('estado') != 'em_execucao':
        raise SystemExit('onda %s não está em execução%s' % (args.onda, ' (bloqueada: `onda desbloquear`)'
                                                             if (eo or {}).get('estado') == 'bloqueada' else ''))
    erro_ap = DC.conferir_aprovacao(pasta, estado, args.onda)
    if erro_ap:
        raise SystemExit('recusado: ' + erro_ap)
    arq = C.arquivo_autoconferencia(pasta, args.onda)
    if os.path.exists(arq):
        # Nunca sobrescreve uma autoconferência preenchida: vai para o histórico, como a revisão.
        acs = [a for a in estado.get('autoconferencias', []) if a['onda'] == args.onda]
        rotulo_ant = acs[-1]['id'] if acs else 'antiga'
        historico = arq.replace('.md', '.%s.md' % rotulo_ant)
        n = 2
        while os.path.exists(historico):
            historico = arq.replace('.md', '.%s-%d.md' % (rotulo_ant, n))
            n += 1
        os.replace(arq, historico)
        print('autoconferência anterior preservada em %s' % os.path.basename(historico))
    acid = C.proximo_id(estado, 'AC')
    repos = sorted(eo['baseline'])
    fps = {r: C.fingerprint(estado['repos'][r]['caminho']) for r in repos}
    reg = {'id': acid, 'onda': args.onda, 'iniciada_em': C.agora(), 'fingerprints': fps,
           'hash_plano': C.hash_plano(C.ler(C.arquivo_plano(pasta))),
           'hash_onda': C.hash_da_onda(C.ler(C.arquivo_plano(pasta)), args.onda)}
    estado.setdefault('autoconferencias', []).append(reg)
    C.salvar_estado(pasta, estado)
    C.gravar(arq, ESQUELETO_AUTO.format(
        onda=args.onda, titulo=o['titulo'], rotulo=C.rotulo(pasta), acid=acid, inicio=reg['iniciada_em'],
        fps='; '.join('`%s` %s' % (r, fps[r]['assinatura']) for r in repos),
        linhas_aceite=_linhas_aceite(o, args.onda)))
    print('%s iniciada: %s' % (acid, arq))
    return 0


def cmd_validar_autoconferencia(pasta, args):
    rel, _ = validar(pasta, args.onda, modo='autoconferencia')
    if not rel.erros:
        # O instante em que passou: com o `iniciada_em`, mede o tempo de conferência do autor (só métrica).
        def _gravar(estado):
            regs = _autoconferencias(estado, args.onda)
            if regs:
                regs[-1]['validada_em'] = C.agora()
        C.atualizar(pasta, _gravar)
    return rel.imprimir()


def fontes_do_esperado(pasta, estado):
    """Textos normalizados onde o valor esperado pode estar: análise, ER (.docx) e decisões.

    O valor de uma decisão é procurado **na fonte dela**, não no `texto` que o modelo redigiu ao
    registrá-la: decisão do usuário → a fala citada inteira (numa resposta, pergunta + resposta +
    notas: ele leu a pergunta e respondeu a ela); decisão da análise ou da ER → o documento. Uma
    decisão do usuário cuja fala não está mais no log fica sem fonte (None)."""
    analise = C.arquivo_analise(pasta)
    er = ' '.join(C.texto_docx(a) for a in C.arquivos_er(pasta))
    base = C.arquivo_plano_base(pasta, estado)
    fontes = {
        'analise': C.chave(C.ler(analise)) if os.path.exists(analise) else None,
        'er': C.chave(er) if er.strip() else None,
        'plano_base': C.chave(C.texto_documento(base)) if base else None,
        'decisoes': {},
        # o que o usuário escreveu ou escolheu (resposta, notas, documento que ele confirmou), sem a pergunta:
        # o valor que só está na pergunta foi o modelo quem escreveu, e o parecer o mostra como proposto
        'respostas': {},
    }
    for d in estado.get('decisoes', []):
        if d.get('revogada_por'):
            continue
        if d.get('fonte') == 'usuario':
            fala = C.fala_por_momento((d.get('fala') or {}).get('em'), d.get('citacao'))
            if not fala:
                fontes['decisoes'][d['id']] = None
                continue
            partes = [fala['texto']]
            proprias = [fala['texto']] if fala.get('tipo') != 'resposta' else \
                [fala.get('resposta') or '', fala.get('notas') or '']
            for doc in d.get('docs', []):
                copia = os.path.join(pasta, doc.get('copia') or '')
                if os.path.isfile(copia):
                    partes.append(C.texto_documento(copia))
                    proprias.append(partes[-1])
            fontes['decisoes'][d['id']] = C.chave(' '.join(partes))
            fontes['respostas'][d['id']] = C.chave(' '.join(proprias))
        elif d.get('fonte') == 'analise':
            fontes['decisoes'][d['id']] = fontes['analise']
        elif d.get('fonte') == 'er':
            fontes['decisoes'][d['id']] = fontes['er']
        # decisão de engenharia nunca é fonte de valor esperado
    return fontes


def conferir_esperado(celula, fontes, propostos=None):
    """Mensagem de erro, ou None. A célula cita a âncora e o valor literal entre crases. `propostos` (lista):
    recebe (D<n>, literal) do valor que só aparece na pergunta que o modelo escreveu — aceito, e marcado."""
    literais = [C.chave(x) for x in re.findall(r'`([^`]+)`', celula) if x.strip()]
    # A análise é citada como "análise: `…`" ou "(análise: …)". A palavra solta, dentro do literal
    # de uma decisão ("as 6 análises") ou de um nome de classe, não é âncora.
    fora_das_crases = re.sub(r'`[^`]*`', ' ', celula)
    ancora_analise = re.search(r'\ban[aá]lise\s*:', fora_das_crases, re.IGNORECASE)
    ancora_er = re.search(r'\bER\s+\d+(\.\d+)*', celula)
    ancora_pb = re.search(r'\bplano[- ]base\s*:', fora_das_crases, re.IGNORECASE)
    ds = re.findall(r'\bD\d+\b', celula)
    if not (ancora_analise or ancora_er or ancora_pb or ds):
        return 'Esperado sem âncora (análise, ER x.y, plano base ou D<n>) — de onde veio o valor?'
    if not literais:
        return 'Esperado sem o valor literal entre crases, copiado do documento'
    textos = []
    if ancora_analise:
        if fontes['analise'] is None:
            return 'Esperado cita a análise, e não há análise na pasta'
        textos.append(fontes['analise'])
    if ancora_pb:
        if not fontes.get('plano_base'):
            return ('Esperado cita o plano base, e o projeto não segue com plano base '
                    '(`validar-plano --sem-analise D<n> --plano-base <arquivo>`)')
        textos.append(fontes['plano_base'])
    if ancora_er:
        if fontes['er'] is None:
            return 'Esperado cita a ER, e não há ER*.docx na pasta'
        textos.append(fontes['er'])
    for d in ds:
        if d not in fontes['decisoes']:
            return 'Esperado cita %s, que não é decisão vigente do livro' % d
        if fontes['decisoes'][d] is None:
            return ('Esperado cita %s, cuja fonte (a fala do usuário ou o documento) não está '
                    'disponível — o valor não tem como ser conferido' % d)
        textos.append(fontes['decisoes'][d])
    for lit in literais:
        if not any(lit in t for t in textos):
            return ('o valor `%s` não está no documento citado — o esperado vem da análise, da ER ou '
                    'da fala do usuário por trás da decisão (não do texto que registrou a decisão, '
                    'nem do código); sem valor definido, o resultado é LACUNA' % lit)
    if propostos is not None and ds:
        docs = [fontes[k] for k, a in (('analise', ancora_analise), ('plano_base', ancora_pb), ('er', ancora_er))
                if a and fontes.get(k)]
        respostas = fontes.get('respostas') or {}
        for lit in literais:
            if any(lit in t for t in docs):
                continue
            if not any(lit in (respostas.get(d, fontes['decisoes'][d]) or '') for d in ds):
                propostos.append((', '.join(ds), lit))
    return None


ESQUELETO = """# Revisão da Onda {onda} — {titulo} ({rotulo})

| | |
|---|---|
| Revisão | {rid}, iniciada em {inicio} |
| Commits da onda | {commits} |
| Código revisado | {fps} |

## Veredito

**<APROVADA | REPROVADA>**

<uma frase: por quê>

## Aceite a aceite

Evidência: `repo:caminho:linha` (da asserção, para aceite com teste automatizado) ou
`evidencia:<arquivo na pasta do projeto>` (roteiro, print). Trecho: o texto literal da linha,
entre crases. Resultado: OK, FALHA ou LACUNA.

| Aceite | Evidência | Trecho | Esperado (análise/ER) | Resultado |
|---|---|---|---|---|
{linhas_aceite}

## Asserções rasas

<classes lidas e o que foi achado: verify() sem conferir estado, só assertNotNull, any() onde o
valor importa, teste que passaria com implementação errada — ou "nenhuma", dizendo o que foi lido>

## Testes sem aceite

<mapeamento reverso: para cada método de teste das classes da onda que nenhum aceite da tabela acima cita, uma linha `| repo:caminho:linha | o que o teste verifica | destino |` — destino: o aceite que ele passa a provar, ou "remover" porque nenhuma regra pedida o exige; sem nenhum, escreva "nenhum" e diga as classes lidas>

## Qualidade e riscos fora dos aceites

<o que o diff faz além dos aceites e pode dar errado — concorrência, transação, estado pela metade, escopo além do pedido, padrão do AGENTS.md — com repo:arquivo:linha; ou "nada achado", dizendo o que foi lido>

## Mutantes

{mutantes}

## Lacunas ranqueadas

<1. classe — lacuna — aceite — repo:arquivo:linha. Classe, nesta ordem de palavras: teste-fraco | especificacao | defeito | pendencia-nao-bloqueante | equivalente-candidato. Cada lacuna é corrigida sob a tarefa dona (--correcao RV<k>), vira pendência P<n> ou é proposta ao usuário como equivalente>

## Limites desta revisão

<o que esta revisão não cobre>
"""


def _abrir_revisao(pasta, estado, o, eo, onda, anteriores, tipo=None):
    """Grava o registro da revisão nova (fingerprints, hash do plano, aceites, retrato dos arquivos e os
    blobs de produção) e preserva o arquivo da anterior no histórico. Devolve (reg, arq, commits, fps, repos)."""
    arq = C.arquivo_revisao(pasta, onda)
    if os.path.exists(arq):
        historico = arq.replace('.md', '.%s.md' % (anteriores[-1]['id'] if anteriores else 'antiga'))
        n = 2
        while os.path.exists(historico):  # nunca sobrescreve um histórico anterior
            historico = arq.replace('.md', '.%s-%d.md' % (anteriores[-1]['id'] if anteriores else 'antiga', n))
            n += 1
        os.replace(arq, historico)
        print('revisão anterior preservada em %s' % os.path.basename(historico))
    rid = C.proximo_id(estado, 'RV')
    repos = sorted(eo['baseline'])
    fps = {r: C.fingerprint(estado['repos'][r]['caminho']) for r in repos}
    commits = []
    for r in repos:
        base = eo['baseline'][r]['head']
        head = C.git(estado['repos'][r]['caminho'], 'rev-parse', 'HEAD')
        commits.append('`%s`: `%s..%s`' % (r, base[:9], head[:9]))
    reg = {'id': rid, 'onda': onda, 'tipo': tipo or 'subagente', 'iniciada_em': C.agora(), 'fingerprints': fps,
           'hash_plano': C.hash_plano(C.ler(C.arquivo_plano(pasta))),
           'hash_onda': C.hash_da_onda(C.ler(C.arquivo_plano(pasta)), onda),
           'aceites': aceites_ativos(o), 'tarefas': list(o['ordem_tarefas']),
           # o que cada arquivo da onda era no início desta revisão: a rodada seguinte só muta o que mudou
           'arquivos': {r: C.blobs_alterados(estado['repos'][r]['caminho'], eo['baseline'][r]['head'])
                        for r in repos}}
    # O conteúdo dos arquivos de produção da onda, como estão agora: a rodada seguinte compara por linha.
    for r, retrato in reg['arquivos'].items():
        for rel_, sha in retrato.items():
            if not M._eh_teste(rel_):
                M.guardar_blob(pasta, os.path.join(estado['repos'][r]['caminho'], rel_), sha)
    estado['revisoes'].append(reg)
    C.salvar_estado(pasta, estado)
    return reg, arq, commits, fps, repos


def iniciar(pasta, args):
    estado = C.carregar_estado(pasta)
    p = P.Plano(C.arquivo_plano(pasta))
    o = p.onda(args.onda)
    eo = estado['ondas'].get(args.onda)
    if not o or not eo or eo.get('estado') != 'em_execucao':
        raise SystemExit('onda %s não está em execução%s' % (args.onda, ' (bloqueada: `onda desbloquear`)'
                                                             if (eo or {}).get('estado') == 'bloqueada' else ''))
    erro_ap = DC.conferir_aprovacao(pasta, estado, args.onda)
    if erro_ap:
        raise SystemExit('recusado: ' + erro_ap)
    anteriores = _revisoes(estado, args.onda)
    if len(anteriores) >= 3:
        # Teto duro: a 3ª reprovada bloqueia a onda; o caminho é escolha do usuário, nunca uma 4ª igual.
        raise SystemExit('recusado: a onda %s já teve %d revisões (%s) — o teto é 3. Leve ao usuário os '
                         'caminhos de `onda desbloquear`: fechar com as pendências da última revisão, '
                         'replanejar o que falta numa onda nova, ou abandonar'
                         % (args.onda, len(anteriores), ', '.join(r['id'] for r in anteriores)))
    # O autor confere antes de chamar o revisor (tlc-spec-driven: revisão de adequação por tarefa).
    # Onda leve dispensa. A autoconferência é só antes da 1ª revisão; da 2ª em diante, no lugar dela, o
    # autor reaplica e mata cada sobrevivente das revisões anteriores sobre o código de agora.
    leve = P.porte(o) == 'leve'
    if anteriores:
        fps_agora = C.fingerprints(estado)
        faltam = [m for m in M.sobreviventes_pendentes(estado, args.onda)
                  if not M.reaplicado_e_morto(estado, args.onda, m['id'], fps_agora, True)]
        if faltam:
            raise SystemExit(
                'recusado: esta seria a %dª revisão da onda %s e há sobrevivente de revisão anterior que o autor '
                'não reaplicou e matou sobre o código atual: %s. Da 2ª revisão em diante não há autoconferência '
                'completa; no lugar dela: `mutante preparar --autor`, `mutante reaplicar`, `mutante limpar` '
                '(mutante novo é do revisor; equivalente é decisão do usuário)'
                % (len(anteriores) + 1, args.onda,
                   '; '.join('%s (%s:%d, %s)' % (m['id'], m['arquivo'], m['linha'], m['aceite']) for m in faltam)))
        rel_ac = C.Relatorio()
    else:
        rel_ac, _ = (C.Relatorio(), None) if leve else validar(pasta, args.onda, estado=estado, plano=p, modo='autoconferencia')
    if rel_ac.erros:
        rel_ac.titulo = 'revisao iniciar: a autoconferência da onda %s não passa' % args.onda
        rel_ac.imprimir()
        raise SystemExit('recusado: sem autoconferência válida sobre o código atual não há revisão '
                         '(`autoconferencia iniciar`, preencha a tabela de aceites e as asserções rasas, '
                         '`autoconferencia validar`)')
    reg, arq, commits, fps, repos = _abrir_revisao(pasta, estado, o, eo, args.onda, anteriores)
    rid = reg['id']
    linhas = _linhas_aceite(o, args.onda)
    C.gravar(arq, ESQUELETO.format(
        onda=args.onda, titulo=o['titulo'], rotulo=C.rotulo(pasta), rid=rid, inicio=reg['iniciada_em'],
        commits='; '.join(commits), fps='; '.join('`%s` %s' % (r, fps[r]['assinatura']) for r in repos),
        linhas_aceite=linhas, mutantes=C.bloco('mutantes', '_rode os mutantes; este bloco é gerado_')))
    print('%s iniciada: %s' % (rid, arq))
    return 0


def _trecho_na_linha(caminho, linha, trecho):
    try:
        with open(caminho, encoding='utf-8', errors='replace') as fh:
            linhas = fh.read().splitlines()
    except OSError:
        return None
    if not 1 <= linha <= len(linhas):
        return None
    janela = ' '.join(linhas[linha - 1:linha + 3])
    norm = lambda s: ' '.join(s.split())
    return norm(trecho) in norm(janela)


# Asserção que passa com qualquer implementação: citá-la como prova do aceite é prova nenhuma. Só o que é
# inequívoco — calibrado contra linhas OK de revisões aprovadas, sem nenhum acerto falso.
# A ligação lexical Esperado↔Trecho foi medida e descartada: boa parte das linhas aprovadas não a satisfaz.
RE_TAUTOLOGIA = (
    re.compile(r'assert(?:True|That)\(\s*true\s*\)(?:\.isTrue\(\))?', re.IGNORECASE),
    re.compile(r'assertFalse\(\s*false\s*\)', re.IGNORECASE),
    re.compile(r'assertEquals\(\s*([\w."\']+)\s*,\s*\1\s*\)'),
    re.compile(r'assertNotNull\(\s*(?:"[^"]*"|\'[^\']*\'|\d+|true|false)\s*\)'),
    re.compile(r'\bassert\s+(?:True|1\s*==\s*1)\b'),
    re.compile(r'expect\(\s*(true|false|\d+|"[^"]*"|\'[^\']*\')\s*\)\s*\.\s*(?:toBe|toEqual|toStrictEqual)\(\s*\1\s*\)'),
)


def trecho_tautologico(trecho):
    """O trecho é uma asserção tautológica (`assertTrue(true)`, `assertEquals(1, 1)`, `expect(true).toBe(true)`)?"""
    return any(rx.search(trecho or '') for rx in RE_TAUTOLOGIA)


def _onde_esta(caminho, trecho, linha):
    """Texto para a recusa do trecho: o que há nas linhas citadas e onde o trecho de fato está."""
    try:
        with open(caminho, encoding='utf-8', errors='replace') as fh:
            linhas = fh.read().splitlines()
    except OSError:
        return ''
    norm = lambda s: ' '.join(s.split())
    alvo = norm(trecho)
    achadas = [i for i, ln in enumerate(linhas, 1) if alvo and alvo in norm(ln)]
    vistas = '; '.join('%d: %s' % (i, norm(linhas[i - 1])[:100])
                       for i in range(linha, min(linha + 4, len(linhas) + 1)))
    onde = ('o trecho está na(s) linha(s) %s' % ', '.join(map(str, achadas[:5]))) if achadas \
        else 'o trecho não aparece no arquivo (nem numa linha só)'
    return ' — %s. Nas linhas citadas há: %s' % (onde, vistas or '(fora do arquivo)')


def validar(pasta, oid, estado=None, plano=None, fps=None, modo='revisao'):
    """(Relatorio, veredito). Atualiza só o bloco gerado de mutantes antes de conferir.
    `modo='autoconferencia'` confere o `autoconferencia-onda-N.md` do autor com as mesmas regras de
    evidência e esperado, sem veredito: passa só com todo aceite OK e nenhum mutante do autor vivo."""
    auto = modo == 'autoconferencia'
    estado = estado or C.carregar_estado(pasta)
    plano = plano or P.Plano(C.arquivo_plano(pasta))
    rel = C.Relatorio('%s validar %s' % (modo, oid))
    o = plano.onda(oid)
    arq = C.arquivo_autoconferencia(pasta, oid) if auto else C.arquivo_revisao(pasta, oid)
    regs = _autoconferencias(estado, oid) if auto else _revisoes(estado, oid)
    if not os.path.exists(arq) or not regs or not o:
        rel.erro('sem %s iniciada para a onda %s (`%s iniciar`)'
                 % ('autoconferência' if auto else 'revisão', oid, modo))
        return rel, None
    reg = regs[-1]
    if fps is None:
        fps = C.fingerprints(estado)
    texto = C.ler(arq)
    # A autoconferência não tem mutantes: o autor confere a tabela de aceites; quem muta é o revisor.
    validos = [] if auto else [m for m in M.mutantes_validos(estado, oid, fps) if m['aceite'] in o['aceites']]
    if not auto:
        texto, achou = C.trocar_bloco(texto, 'mutantes', M.tabela_mutantes(validos))
        if achou:
            C.gravar(arq, texto)

    # veredito (a autoconferência não tem: ela passa ou não passa)
    veredito = None
    if not auto:
        corpo = C.secao(texto, r'^veredito') or ''
        m = re.search(r'\*\*([^*]+)\*\*', corpo)
        veredito = m.group(1).strip().upper() if m else None
        if veredito not in VEREDITOS:
            rel.erro('veredito tem de ser **APROVADA** ou **REPROVADA** (achado: %r)' % veredito)

    # independência no código e no plano: conteúdo mudado depois do início vence a revisão —
    # sem depender de relógio
    if (reg['hash_onda'] != C.hash_da_onda(plano.texto, oid)) if reg.get('hash_onda') else \
            (reg.get('hash_plano') and reg['hash_plano'] != C.hash_plano(plano.texto)):
        rel.erro('o plano da onda mudou depois que %s começou — revisão vencida (o revisor não edita '
                 'plano; plano novo pede aprovação e revisão novas)' % reg['id'])
    for repo, fp in reg['fingerprints'].items():
        if not C.mesmo_fp(fp, fps.get(repo)):
            rel.erro('%s: o código mudou depois que %s começou — revisão vencida, inicie outra'
                     % (repo, reg['id']))

    # aceite a aceite
    linhas = {}
    for cel in C.linhas_de_tabela(C.secao(texto, r'^aceite a aceite')):
        if cel and C.RE_ACEITE.fullmatch(cel[0].strip('*` ')):
            linhas[cel[0].strip('*` ')] = cel
    com_teste = P.aceites_com_teste(o)
    fontes = fontes_do_esperado(pasta, estado)
    rel.resultados = {}
    rel.propostos = []
    for aid in o['ordem_aceites']:
        a = o['aceites'][aid]
        if a['reclassificado']:
            continue
        cel = linhas.get(aid)
        if not cel or len(cel) < 5:
            rel.erro('%s sem linha completa em "Aceite a aceite"' % aid)
            continue
        evid, trecho_cel, esperado = cel[1], cel[2], cel[3]
        resultado = re.sub(r'[*`]', '', cel[4]).strip().upper()
        rel.resultados[aid] = resultado
        if resultado not in RESULTADOS:
            rel.erro('%s: Resultado %r fora do vocabulário (OK, FALHA ou LACUNA — sem meio-termo)' % (aid, cel[4]))
        if veredito == 'APROVADA' and resultado != 'OK':
            rel.erro('%s com resultado %r numa revisão APROVADA' % (aid, cel[4]))
        if auto and resultado in ('FALHA', 'LACUNA'):
            rel.erro('%s com resultado %s — a autoconferência só passa com todo aceite OK: o que falta '
                     'vira teste (ou pergunta ao usuário) antes da revisão' % (aid, resultado))
        if resultado in ('OK', 'FALHA'):
            props = []
            erro_esp = conferir_esperado(esperado, fontes, props)
            if erro_esp:
                rel.erro('%s: %s' % (aid, erro_esp))
            for d_, lit in props:
                rel.propostos.append({'aceite': aid, 'decisao': d_, 'literal': lit})
                rel.aviso('%s: o valor `%s` só aparece na pergunta que o modelo escreveu (%s) — o usuário '
                          'respondeu a ela; o parecer o mostra como valor proposto pelo agente' % (aid, lit, d_))
        refs = list(RE_REF.finditer(evid))
        evids = list(RE_EVID.finditer(evid))
        if not refs and not evids:
            rel.erro('%s sem evidência (repo:caminho:linha ou evidencia:arquivo) — sem evidência, zero' % aid)
            continue
        trechos = re.findall(r'`([^`]+)`', trecho_cel)
        aponta_teste = False
        for i, r in enumerate(refs):
            repo, caminho, linha = r.group('repo'), r.group('caminho'), int(r.group('linha'))
            cfg = estado['repos'].get(repo)
            if not cfg:
                rel.erro('%s: repo %r da evidência não configurado' % (aid, repo))
                continue
            absoluto = os.path.join(cfg['caminho'], caminho)
            if not os.path.isfile(absoluto):
                rel.erro('%s: %s não existe em %s' % (aid, caminho, repo))
                continue
            if M._eh_teste(caminho):
                aponta_teste = True
            candidatos = [trechos[i]] if i < len(trechos) else trechos
            if not candidatos:
                rel.erro('%s: evidência %s sem trecho citado entre crases' % (aid, r.group(0)))
                continue
            achou = [t for t in candidatos if _trecho_na_linha(absoluto, linha, t)]
            if not achou:
                rel.erro('%s: o trecho citado não está em %s (nem nas 3 linhas seguintes)%s'
                         % (aid, r.group(0), _onde_esta(absoluto, candidatos[0], linha)))
            for t_ in achou:
                if M._eh_teste(caminho) and trecho_tautologico(t_):
                    rel.erro('%s: o trecho de %s é uma asserção tautológica (%s) — passa com qualquer implementação, '
                             'não prova o aceite' % (aid, r.group(0), ' '.join(t_.split())[:60]))
        for e in evids:
            if not os.path.exists(os.path.join(pasta, e.group('caminho'))):
                rel.erro('%s: evidência %s não existe na pasta do projeto' % (aid, e.group('caminho')))
        if aid in com_teste and not aponta_teste:
            rel.erro('%s tem teste automatizado: a evidência tem de apontar a asserção num arquivo de teste' % aid)

    secoes = [('Asserções rasas', r'^asser')]
    if not auto:
        secoes += [('Qualidade e riscos fora dos aceites', r'^qualidade'), ('Limites desta revisão', r'^limites')]
    for nome, rx in secoes:
        c = C.secao(texto, rx)
        if c is None or not C.tem_conteudo(c):
            rel.erro('seção "%s" ausente ou vazia' % nome)
    # Mapeamento reverso (o Check C da TLC): teste sem regra que o peça é código a mais, ou aceite que
    # ninguém escreveu. Só a revisão, e só se o relatório tem a seção (a rodada mecânica não a tem).
    sem_aceite = C.secao(texto, r'^testes sem aceite')
    if not auto and sem_aceite is not None:
        if not C.tem_conteudo(sem_aceite):
            rel.erro('seção "Testes sem aceite" vazia — liste os testes que nenhum aceite cita, ou escreva '
                     '"nenhum" dizendo as classes de teste lidas')
        for n, ref, dest in testes_sem_aceite(sem_aceite):
            if not ref:
                rel.erro('Testes sem aceite, linha %d: a primeira coluna tem de ser repo:caminho:linha do teste' % n)
                continue
            cfg = estado['repos'].get(ref.group('repo'))
            if not cfg:
                rel.erro('Testes sem aceite: repo %r não configurado' % ref.group('repo'))
            elif not os.path.isfile(os.path.join(cfg['caminho'], ref.group('caminho'))):
                rel.erro('Testes sem aceite: %s não existe em %s' % (ref.group('caminho'), ref.group('repo')))
            elif not M._eh_teste(ref.group('caminho')):
                rel.erro('Testes sem aceite: %s não é arquivo de teste' % ref.group('caminho'))
            if not dest.strip():
                rel.erro('Testes sem aceite, %s: sem destino — a que aceite ele passa a servir, ou "remover"'
                         % ref.group(0))
    if veredito == 'REPROVADA':
        c = C.secao(texto, r'^lacunas')
        if c is None or not C.tem_conteudo(c):
            rel.erro('REPROVADA sem lacunas ranqueadas')
    rel.classes_lacunas = None
    if not auto:
        itens = classes_das_lacunas(C.secao(texto, r'^lacunas'))
        for n, classe, t in itens:
            if classe is None:
                rel.erro('lacuna %d sem classe — o item começa por uma de: %s (achado: %r)'
                         % (n, ' | '.join(CLASSES_LACUNA), t[:60]))
        rel.classes_lacunas = [classe for _n, classe, _t in itens]
    if not auto and com_teste and not validos:
        rel.erro('nenhum mutante válido registrado para a onda %s' % oid)
    if not auto:
        # O sobrevivente de uma revisão anterior só sai da conta reaplicado e morto sobre o código atual
        # (na autoconferência ou nesta revisão), ou equivalente por decisão do usuário. Sem isto, a onda
        # leve (sem autoconferência) deixaria o sobrevivente cair no esquecimento.
        for pend in M.sobreviventes_pendentes(estado, oid):
            if pend.get('revisao') == reg['id']:
                continue
            if not M.reaplicado_e_morto(estado, oid, pend['id'], fps, True):
                rel.erro('%s, sobrevivente da %s (%s:%d, %s), não foi reaplicado e morto sobre o código atual '
                         '— `mutante reconfirmar` nesta revisão' % (pend['id'], pend.get('revisao') or 'revisão anterior',
                                                                   pend['arquivo'], pend['linha'], pend['aceite']))
    if not auto:
        # Herança relaxada vale com a amostra de alarme feita **nesta** revisão (`mutante reconfirmar`):
        # sem ela, mutante morto contra um código que já mudou entraria na conta sem nunca ser reaplicado.
        relaxados = [m for m in validos if m.get('heranca') == 'relaxada']
        if relaxados:
            ids_relaxados = {m['id'] for m in relaxados}
            reaplicados = amostra_reaplicada(estado, validos, relaxados)
            exigidos = min(M.AMOSTRA_RELAXADA, len(relaxados))
            if len(reaplicados) < exigidos:
                rel.erro('%d mutante(s) herdado(s) por herança relaxada (%s) e só %d reaplicado(s) nesta revisão '
                         '— a amostra de alarme pede %d: `mutante reconfirmar` na sessão desta revisão'
                         % (len(relaxados), ', '.join(sorted(ids_relaxados)[:5]), len(reaplicados), exigidos))
    return rel, veredito


def amostra_reaplicada(estado, validos, relaxados):
    """As origens dos relaxados que foram reaplicadas e mortas nesta revisão (os válidos sem
    `herdado_de`). Conta pela origem: o relaxado que já é reaplicação de outro (o morto da RV2 que
    reconfirma o da RV1) é a mesma mutação que o `reconfirmar` reaplica a partir do original."""
    origens_relaxadas = {M.origem_do_mutante(estado, m) for m in relaxados}
    return {M.origem_do_mutante(estado, m) for m in validos
            if (m.get('reconfirma') or m.get('reaplica')) and m['resultado'] == 'morto'
            and not m.get('herdado_de')} & origens_relaxadas


def cmd_validar(pasta, args):
    rel, veredito = validar(pasta, args.onda)
    rel.nota('veredito: %s' % (veredito or '—'))
    if not rel.erros and veredito in VEREDITOS:
        # A revisão válida grava o veredito; a 3ª reprovada bloqueia a onda.
        def _gravar(estado):
            regs = _revisoes(estado, args.onda)
            eo = estado['ondas'].get(args.onda, {})
            if not regs:
                return None
            regs[-1]['veredito'] = veredito
            regs[-1]['validada_em'] = C.agora()
            if getattr(rel, 'classes_lacunas', None) is not None:
                regs[-1]['classes_lacunas'] = rel.classes_lacunas
            # o que a rodada mecânica confere: o registro, não o arquivo (que se edita depois de validado)
            regs[-1]['resultados'] = getattr(rel, 'resultados', None)
            regs[-1]['esperados_propostos'] = getattr(rel, 'propostos', [])
            if veredito == 'REPROVADA' and len(regs) >= 3 and eo.get('estado') == 'em_execucao':
                eo['estado'] = 'bloqueada'
                eo['bloqueada_por'] = regs[-1]['id']
                eo['bloqueada_em'] = C.agora()
                return regs[-1]['id']
            return None
        bloqueou = C.atualizar(pasta, _gravar)
        if bloqueou:
            rel.nota('onda %s BLOQUEADA: %s foi a 3ª revisão e reprovou. Leve ao usuário os caminhos — '
                     'fechar com pendências, replanejar ou abandonar — e registre a escolha dele: '
                     '`onda desbloquear --caminho … --decisao D<n>`' % (args.onda, bloqueou))
    return rel.imprimir()


# ------------------------------------------------------------------------------ rodada mecânica

# Lacunas que a rodada seguinte confirma sem ler código: o teste fraco se prova pela reaplicação do
# sobrevivente, o equivalente pela decisão registrada e a pendência pelo registro dela.
CLASSES_MECANICAS = ('teste-fraco', 'equivalente-candidato', 'pendencia-nao-bloqueante')


def _ocorrencias(caminho, trecho):
    """Linhas onde o trecho começa (a janela de 4 linhas a partir dela o contém e a seguinte não)."""
    try:
        with open(caminho, encoding='utf-8', errors='replace') as fh:
            linhas = fh.read().splitlines()
    except OSError:
        return []
    norm = lambda s: ' '.join(s.split())
    alvo = norm(trecho)
    return [i for i in range(1, len(linhas) + 1)
            if alvo in norm(' '.join(linhas[i - 1:i + 3])) and alvo not in norm(' '.join(linhas[i:i + 4]))]


def elegibilidade_mecanica(pasta, estado, o, eo, onda):
    """(motivos, revisão anterior, {aceite: linha da tabela com a evidência relocalizada}). Sem motivos, a
    rodada seguinte pode ser mecânica: a anterior reprovou só por teste fraco, equivalente ou pendência, com
    todo aceite OK, e desde ela só arquivo de teste mudou."""
    anteriores = _revisoes(estado, onda)
    if not anteriores:
        return ['a onda %s ainda não teve revisão' % onda], None, {}
    prev, motivos = anteriores[-1], []
    if len(anteriores) >= 3:
        motivos.append('a onda já teve 3 revisões (o teto)')
    if prev.get('veredito') != 'REPROVADA' or not prev.get('validada_em'):
        motivos.append('%s não é uma revisão REPROVADA e validada' % prev['id'])
    arq = C.arquivo_revisao(pasta, onda)
    texto = C.ler(arq) if os.path.exists(arq) else ''
    if not re.search(r'\|\s*Revis[aã]o\s*\|\s*%s\b' % re.escape(prev['id']), texto[:1500]):
        return motivos + ['%s não é o arquivo da %s' % (os.path.basename(arq), prev['id'])], prev, {}
    linhas = {}
    for cel in C.linhas_de_tabela(C.secao(texto, r'^aceite a aceite')):
        aid = cel[0].strip('*` ') if cel else ''
        if C.RE_ACEITE.fullmatch(aid):
            linhas[aid] = cel
    ativos = aceites_ativos(o)
    if sorted(linhas) != sorted(ativos):
        motivos.append('os aceites da tabela da %s (%s) não são os ativos da onda (%s)'
                       % (prev['id'], ', '.join(sorted(linhas)) or 'nenhum', ', '.join(ativos)))
    # Resultados e classes vêm do registro da validação: o arquivo pode ter sido editado depois dela.
    resultados = prev.get('resultados') or {}
    nao_ok = [aid for aid in ativos if resultados.get(aid) != 'OK']
    if nao_ok:
        motivos.append('aceite sem OK na %s: %s — LACUNA ou FALHA pede o revisor' % (prev['id'], ', '.join(nao_ok)))
    classes = prev.get('classes_lacunas') or []
    fora = sorted({c or 'sem classe' for c in classes if c not in CLASSES_MECANICAS})
    if fora:
        motivos.append('lacuna de classe %s na %s — pede leitura de código' % (', '.join(fora), prev['id']))
    n_pend = len([c for c in classes if c == 'pendencia-nao-bloqueante'])
    registradas = len([x for x in estado.get('pendencias', []) if x.get('origem') == prev['id']])
    if registradas < n_pend:
        motivos.append('%d lacuna(s) pendencia-nao-bloqueante na %s e %d pendência(s) com essa origem — '
                       '`pendencia add --origem %s` antes' % (n_pend, prev['id'], registradas, prev['id']))
    if prev.get('hash_onda') != C.hash_da_onda(C.ler(C.arquivo_plano(pasta)), onda):
        motivos.append('o plano da onda mudou desde a %s' % prev['id'])
    for r in sorted(eo['baseline']):
        antes = (prev.get('arquivos') or {}).get(r) or {}
        agora = C.blobs_alterados(estado['repos'][r]['caminho'], eo['baseline'][r]['head'])
        producao = sorted(k for k in set(antes) | set(agora) if antes.get(k) != agora.get(k) and not M._eh_teste(k))
        if producao:
            motivos.append('%s: código de produção mudou desde a %s (%s)' % (r, prev['id'], ', '.join(producao[:5])))
    # A evidência aponta para a linha do teste, e a correção desloca as linhas: o trecho citado tem de
    # aparecer uma vez só no arquivo de agora, e a linha passa a ser a dele.
    novas = {}
    for aid in ativos:
        cel = linhas.get(aid)
        if not cel or len(cel) < 5:
            continue
        evid, trechos = cel[1], re.findall(r'`([^`]+)`', cel[2])
        for i, ref in enumerate(list(RE_REF.finditer(cel[1]))):
            cfg = estado['repos'].get(ref.group('repo'))
            candidatos = [trechos[i]] if i < len(trechos) else trechos
            absoluto = os.path.join(cfg['caminho'], ref.group('caminho')) if cfg else ''
            pos = sorted({n for t in candidatos for n in _ocorrencias(absoluto, t)})
            if len(pos) != 1:
                motivos.append('%s: o trecho de %s aparece %d vez(es) no arquivo de agora' % (aid, ref.group(0), len(pos)))
                continue
            evid = evid.replace(ref.group(0), '%s:%s:%d' % (ref.group('repo'), ref.group('caminho'), pos[0]), 1)
        novas[aid] = '| %s |' % ' | '.join([cel[0], evid] + list(cel[2:5]))
    return motivos, prev, novas


MECANICA = """# Revisão da Onda {onda} — {titulo} ({rotulo})

| | |
|---|---|
| Revisão | {rid}, iniciada em {inicio} — rodada mecânica (`revisao confirmar`) |
| Commits da onda | {commits} |
| Código revisado | {fps} |

## Veredito

**{veredito}**

{porque}

## Aceite a aceite

Tabela da {anterior}, com a evidência relocalizada no código de agora (desde ela só mudou arquivo de teste).

| Aceite | Evidência | Trecho | Esperado (análise/ER) | Resultado |
|---|---|---|---|---|
{linhas_aceite}

## Asserções rasas

Rodada mecânica: as classes de teste foram lidas na {anterior}; aqui só se reaplicam os mutantes dela.

## Qualidade e riscos fora dos aceites

Rodada mecânica: o código de produção é o mesmo da {anterior}; vale o que ela registrou.

## Mutantes

{mutantes}

## Lacunas ranqueadas

{lacunas}

## Limites desta revisão

Sem leitura de código nem mutante novo: confirma, por reaplicação, os sobreviventes da {anterior}, os mortos
que perderam a herança e a amostra de alarme da herança relaxada.
"""


def confirmar(pasta, args):
    """Rodada de confirmação sem subagente: quando a revisão anterior reprovou só pelo que a reaplicação prova
    (teste fraco, equivalente decidido, pendência registrada) e desde ela só arquivo de teste mudou, o script
    abre a revisão, reaplica o que a anterior pediu (`mutante reconfirmar`), escreve o relatório e o valida. Os
    mutantes continuam sendo os que o revisor escolheu. Conta para o teto de 3 como qualquer revisão."""
    import argparse
    estado = C.carregar_estado(pasta)
    p = P.Plano(C.arquivo_plano(pasta))
    o = p.onda(args.onda)
    eo = estado['ondas'].get(args.onda)
    if not o or not eo or eo.get('estado') != 'em_execucao':
        raise SystemExit('onda %s não está em execução' % args.onda)
    erro_ap = DC.conferir_aprovacao(pasta, estado, args.onda)
    if erro_ap:
        raise SystemExit('recusado: ' + erro_ap)
    motivos, prev, novas = elegibilidade_mecanica(pasta, estado, o, eo, args.onda)
    if motivos:
        raise SystemExit('recusado: a rodada não pode ser mecânica — %s. Lance a revisão com subagente '
                         '(`revisao iniciar` e o prompt de referencias/revisor.md)' % '; '.join(motivos))
    anteriores = _revisoes(estado, args.onda)
    reg, arq, commits, fps, repos = _abrir_revisao(pasta, estado, o, eo, args.onda, anteriores, tipo='mecanica')
    cabecalho = dict(onda=args.onda, titulo=o['titulo'], rotulo=C.rotulo(pasta), rid=reg['id'],
                     inicio=reg['iniciada_em'], commits='; '.join(commits), anterior=prev['id'],
                     fps='; '.join('`%s` %s' % (r, fps[r]['assinatura']) for r in repos),
                     linhas_aceite='\n'.join(novas[a] for a in aceites_ativos(o)),
                     mutantes=C.bloco('mutantes', '_gerado_'))
    C.gravar(arq, MECANICA.format(veredito='<APROVADA | REPROVADA>', porque='<em andamento>',
                                  lacunas='<em andamento>', **cabecalho))
    print('%s iniciada (mecânica): %s' % (reg['id'], arq))
    com_mutante = sorted({s_['repo'] for s_ in estado['sessoes_mutacao']
                          if s_['onda'] == args.onda and s_.get('tipo') != 'autor'})
    for repo in com_mutante:
        M.preparar(pasta, argparse.Namespace(repo=repo, onda=args.onda, autor=False,
                                             decisao=getattr(args, 'decisao', None)))
        estado = C.carregar_estado(pasta)
        sid = [s_ for s_ in estado['sessoes_mutacao'] if s_.get('revisao') == reg['id'] and s_['repo'] == repo][-1]['id']

        def _marcar(e, sid=sid):
            M._por_id(e, sid)['mecanica'] = True
        C.atualizar(pasta, _marcar)
        M.reconfirmar(pasta, argparse.Namespace(sessao=sid, repo=None, timeout=getattr(args, 'timeout', None)))
        M.limpar(pasta, argparse.Namespace(sessao=sid, repo=None))
    estado = C.carregar_estado(pasta)
    vivos = [m for s_ in estado['sessoes_mutacao'] if s_.get('revisao') == reg['id']
             for m in s_.get('mutantes', []) if m['resultado'] == 'sobrevivente' and not m.get('equivalente')]
    if vivos:
        veredito = 'REPROVADA'
        porque = 'Reaplicado sobre o código de agora, %d mutante(s) sobreviveu(ram) de novo.' % len(vivos)
        lacunas = '\n'.join('%d. teste-fraco — %s sobreviveu de novo (`%s` → `%s`) — %s — %s:%s:%d'
                            % (i, m['id'], m['de'], m['para'], m['aceite'], m['repo'], m['arquivo'], m['linha'])
                            for i, m in enumerate(vivos, 1))
    else:
        veredito = 'APROVADA'
        porque = 'Tudo o que a %s pediu foi reaplicado e morreu sobre o código de agora.' % prev['id']
        lacunas = '1. nenhuma'
    C.gravar(arq, MECANICA.format(veredito=veredito, porque=porque, lacunas=lacunas, **cabecalho))
    return cmd_validar(pasta, argparse.Namespace(onda=args.onda))
