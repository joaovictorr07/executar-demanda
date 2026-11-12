#!/usr/bin/env python3
"""Registra eventos de usuário do Codex, sem converter perguntas em aprovações."""
import datetime
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import comum as C

DIR = os.path.expanduser(os.environ.get('EXEC_DEMANDA_FALAS', os.path.join(
    os.environ.get('CODEX_HOME', os.path.expanduser('~/.codex')), 'executar-demanda', 'falas-usuario')))
NAO_E_FALA = ('<task-notification', '<agent-message', '<local-command-stdout',
              '<local-command-stderr', '<system-reminder', '<environment_context>',
              '<external_codex_apps_open_page>')
RECOMENDADA = ('(Recomendado)', '(Recomendada)', '(Recommended)')

def eh_fala(texto):
    return isinstance(texto, str) and bool(texto.strip()) and not texto.lstrip().startswith(NAO_E_FALA)

def registros(dados):
    if not isinstance(dados, dict):
        return []
    base = {'em': datetime.datetime.now().astimezone().isoformat(timespec='microseconds'),
            'session_id': dados.get('session_id'), 'turn_id': dados.get('turn_id'), 'cwd': dados.get('cwd')}
    if not base['session_id'] or not base['cwd']:
        return []
    evento = dados.get('hook_event_name')
    if evento == 'UserPromptSubmit' and eh_fala(dados.get('prompt')):
        return [dict(base, tipo='prompt', texto=dados['prompt'])]
    if evento != 'PostToolUse' or dados.get('tool_name', '').split('.')[-1] != 'request_user_input':
        return []
    entrada = dados.get('tool_input') or {}
    saida = dados.get('tool_response') or {}
    if isinstance(saida, str):
        try:
            saida = json.loads(saida)
        except ValueError:
            return []
    if not isinstance(entrada, dict) or not isinstance(saida, dict):
        return []
    respostas = saida.get('answers')
    if not isinstance(respostas, dict):
        return []
    linhas = []
    for q in entrada.get('questions', []):
        if not isinstance(q, dict):
            continue
        resposta = respostas.get(q.get('id'))
        if not isinstance(resposta, dict):
            continue
        valores = resposta.get('answers')
        if not isinstance(valores, list) or not valores or not all(isinstance(v, str) for v in valores):
            continue
        texto = '; '.join(valores)
        if not texto.strip():
            continue
        pergunta = q.get('question', '')
        opcoes = [o['label'] for o in q.get('options', []) if isinstance(o, dict) and isinstance(o.get('label'), str)]
        recomendada = next((o for o in opcoes if any(m in o for m in RECOMENDADA)), None)
        linhas.append(dict(base, tipo='resposta', pergunta=pergunta, resposta=texto, notas='',
                           opcoes=opcoes, recomendada=recomendada, texto=pergunta + ': ' + texto))
    return linhas

def main():
    dados = json.load(sys.stdin)
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
        # Não bloqueia chats; os gates recusam aprovação sem registro.
        print('executar-demanda: falha no registro: ' + str(exc), file=sys.stderr)
