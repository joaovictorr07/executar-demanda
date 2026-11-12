#!/usr/bin/env python3
"""Registra eventos de usuário de Antigravity (Gemini), Codex e Claude Code.

Grava uma linha JSON por fala em ~/.gemini/falas-usuario/AAAA-MM.jsonl (ou ~/.codex/... ou ~/.claude/...):
    {"em": ..., "session_id": ..., "tipo": "prompt", "texto": "<o que ele digitou>"}
    {"em": ..., "session_id": ..., "tipo": "resposta", "pergunta": ..., "resposta": ...,
     "opcoes": [...], "recomendada": ..., "texto": "<pergunta>: <resposta>"}

A skill executar-demanda (`decisao add --fonte usuario`, `aprovar-plano`) só aceita citação
que esteja comprovada aqui.
"""
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import comum as C

def _determinar_dir_falas():
    env = os.environ.get('EXEC_DEMANDA_FALAS')
    if env:
        return os.path.normpath(os.path.expanduser(env))
    gemini_home = os.path.expanduser('~/.gemini')
    if os.path.isdir(gemini_home):
        return os.path.normpath(os.path.join(gemini_home, 'falas-usuario'))
    codex_home = os.environ.get('CODEX_HOME', os.path.expanduser('~/.codex'))
    if os.path.isdir(codex_home):
        return os.path.normpath(os.path.join(codex_home, 'executar-demanda', 'falas-usuario'))
    return os.path.normpath(os.path.expanduser('~/.claude/falas-usuario'))

DIR = _determinar_dir_falas()

NAO_E_FALA = ('<task-notification', '<agent-message', '<local-command-stdout',
              '<local-command-stderr', '<system-reminder', '<environment_context>',
              '<external_codex_apps_open_page>')
RECOMENDADA = ('(Recomendado)', '(Recomendada)', '(Recommended)')


def eh_fala(texto):
    return isinstance(texto, str) and bool(texto.strip()) and not texto.lstrip().startswith(NAO_E_FALA)


def registros(dados):
    if not isinstance(dados, dict):
        return []

    # Extrai metadados compatíveis com Antigravity (camelCase), Codex e Claude Code
    session_id = dados.get('session_id') or dados.get('conversationId')
    turn_id = dados.get('turn_id') or dados.get('stepIdx')
    cwd = dados.get('cwd')
    if not cwd and dados.get('workspacePaths'):
        cwd = dados['workspacePaths'][0]
    if not cwd:
        cwd = os.getcwd()

    if not session_id or not cwd:
        return []

    base = {
        'em': datetime.datetime.now().astimezone().isoformat(timespec='microseconds'),
        'session_id': str(session_id),
        'turn_id': str(turn_id) if turn_id is not None else None,
        'cwd': os.path.abspath(cwd)
    }

    evento = dados.get('hook_event_name') or dados.get('hookEventName')

    # 1. Prompt do usuário (Claude Code / Codex via UserPromptSubmit)
    if evento == 'UserPromptSubmit' and eh_fala(dados.get('prompt')):
        return [dict(base, tipo='prompt', texto=dados['prompt'])]

    # 2. Prompt do usuário no Antigravity / Gemini (PreInvocation via lastUserInput)
    if (evento == 'PreInvocation' or 'lastUserInput' in dados) and eh_fala(dados.get('lastUserInput')):
        return [dict(base, tipo='prompt', texto=dados['lastUserInput'])]

    # 3. Resposta de pergunta interativa (PostToolUse)
    # Suporta:
    # - Antigravity: ask_question
    # - Codex: request_user_input
    # - Claude Code: AskUserQuestion
    tool_name = dados.get('tool_name') or (dados.get('toolCall') or {}).get('name') or ''
    tool_suffix = tool_name.split('.')[-1]

    if evento not in ('PostToolUse', None) and not dados.get('toolCall'):
        return []

    if tool_suffix not in ('request_user_input', 'AskUserQuestion', 'ask_question'):
        return []

    entrada = dados.get('tool_input') or (dados.get('toolCall') or {}).get('args') or {}
    saida = dados.get('tool_response') or dados.get('toolResponse') or {}
    if isinstance(saida, str):
        try:
            saida = json.loads(saida)
        except ValueError:
            saida = {'content': saida}

    # Se saida não tem respostas estruturadas mas temos transcriptPath, tenta inspecionar o log do Antigravity
    if not isinstance(saida, dict):
        saida = {}

    respostas = saida.get('answers')
    linhas = []

    # Caso Codex: {answers: {question_id: {answers: ['...']}}}
    if isinstance(respostas, dict):
        for q in entrada.get('questions', []):
            if not isinstance(q, dict):
                continue
            qid = q.get('id') or q.get('question')
            resposta = respostas.get(qid)
            texto = ''
            if isinstance(resposta, dict):
                valores = resposta.get('answers') or []
                if isinstance(valores, list):
                    texto = '; '.join(str(v) for v in valores if str(v).strip())
            elif isinstance(resposta, str):
                texto = resposta.strip()

            if not texto:
                continue
            pergunta = q.get('question', '')
            opcoes = [o['label'] if isinstance(o, dict) else str(o) for o in q.get('options', [])]
            recomendada = next((o for o in opcoes if any(m in o for m in RECOMENDADA)), None)
            linhas.append(dict(base, tipo='resposta', pergunta=pergunta, resposta=texto, notas='',
                               opcoes=opcoes, recomendada=recomendada, texto=pergunta + ': ' + texto))

    # Caso Antigravity / Claude Code com formato direto de respostas
    elif isinstance(saida.get('content'), str) and saida.get('content').strip():
        # Conteúdo de texto do resultado da pergunta
        texto = saida['content'].strip()
        for q in entrada.get('questions', []):
            pergunta = q.get('question', '') if isinstance(q, dict) else str(q)
            opcoes = [o['label'] if isinstance(o, dict) else str(o) for o in (q.get('options', []) if isinstance(q, dict) else [])]
            recomendada = next((o for o in opcoes if any(m in o for m in RECOMENDADA)), None)
            linhas.append(dict(base, tipo='resposta', pergunta=pergunta, resposta=texto, notas='',
                               opcoes=opcoes, recomendada=recomendada, texto=pergunta + ': ' + texto))

    return linhas


def main():
    try:
        dados = json.load(sys.stdin)
    except Exception:
        return
    linhas = registros(dados)
    if not linhas:
        return
    os.makedirs(DIR, exist_ok=True)
    arq = os.path.join(DIR, datetime.date.today().strftime('%Y-%m') + '.jsonl')
    with C.trava(arq):
        with open(arq, 'a', encoding='utf-8') as fh:
            for linha in linhas:
                fh.write(json.dumps(linha, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('executar-demanda: falha no registro: ' + str(exc), file=sys.stderr)
