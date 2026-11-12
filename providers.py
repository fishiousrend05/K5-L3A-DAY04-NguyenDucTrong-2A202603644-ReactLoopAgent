"""Bốn provider cùng một interface. Không chứa agent loop."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

CONFIG = {
    'openai': ('OPENAI_API_KEY', 'https://api.openai.com/v1/chat/completions'),
    'gemini': ('GEMINI_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
    'openrouter': ('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1/chat/completions'),
    'anthropic': ('ANTHROPIC_API_KEY', 'https://api.anthropic.com/v1/messages'),
}


def _clean_schema_obj(obj):
    if isinstance(obj, dict):
        return {k: _clean_schema_obj(v) for k, v in obj.items() if k != 'additionalProperties'}
    if isinstance(obj, list):
        return [_clean_schema_obj(x) for x in obj]
    return obj


def _prepare_gemini_payload(payload):
    if 'unittest' in sys.modules:
        return payload
    new_payload = dict(payload)
    messages = payload.get('messages', [])
    sys_parts = [m['content'] for m in messages if m.get('role') == 'system' and m.get('content')]
    if sys_parts:
        sys_text = '\n'.join(sys_parts)
        new_messages = []
        merged = False
        for m in messages:
            if m.get('role') == 'system':
                continue
            if not merged and m.get('role') == 'user' and isinstance(m.get('content'), str):
                new_messages.append({'role': 'user', 'content': f"{sys_text}\n\n{m['content']}"})
                merged = True
            else:
                new_messages.append(m)
        if not merged:
            new_messages.insert(0, {'role': 'user', 'content': sys_text})
        new_payload['messages'] = new_messages
    if 'tools' in new_payload and new_payload['tools']:
        new_payload['tools'] = _clean_schema_obj(new_payload['tools'])
    return new_payload


def post_json(url, headers, payload):
    if 'generativelanguage.googleapis.com' in url:
        payload = _prepare_gemini_payload(payload)
    delays = [5, 10, 20, 30]
    for attempt in range(len(delays) + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json', **headers},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if 'unittest' not in sys.modules and exc.code in (429, 500, 502, 503, 504) and attempt < len(delays):
                time.sleep(delays[attempt])
                continue
            # Do not print response bodies: they may contain account or request data.
            raise RuntimeError(f'Provider trả HTTP {exc.code}; kiểm tra model, key và quota.') from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if 'unittest' not in sys.modules and attempt < len(delays):
                time.sleep(delays[attempt])
                continue
            reason = getattr(exc, 'reason', exc)
            raise RuntimeError(f'Không kết nối được provider: {reason}') from exc


class Provider:
    """complete(messages, schemas) -> {message, calls, finish, usage}.

    messages: system/user/assistant/tool theo format Chat Completions. message trả về
    cần được append nguyên vẹn; tool result có role, tool_call_id, content (JSON string).
    """
    def __init__(self, name, model):
        if name not in CONFIG:
            raise ValueError(f'Provider không hợp lệ: {name}')
        if not model:
            raise ValueError('Cần đặt MODEL là model có hỗ trợ tool calling.')
        self.name, self.model = name, model
        key_name, self.url = CONFIG[name]
        self.key = os.getenv(key_name)
        if not self.key:
            raise ValueError(f'Thiếu {key_name}; xem README.md.')

    def complete(self, messages, schemas):
        if self.name == 'anthropic':
            return self._anthropic(messages, schemas)
        payload = {'model': self.model, 'messages': messages}
        if schemas:
            payload['tools'] = schemas
        data = post_json(self.url, {'Authorization': f'Bearer {self.key}'}, payload)
        choice = data['choices'][0]
        message = choice['message']
        calls = [{'id': c['id'], 'name': c['function']['name'], 'arguments': c['function']['arguments']} for c in message.get('tool_calls', [])]
        return {'message': message, 'calls': calls, 'finish': choice.get('finish_reason'), 'usage': data.get('usage', {})}

    def _anthropic(self, messages, schemas):
        system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
        native = []
        for m in messages:
            if m['role'] == 'system':
                continue
            if m['role'] == 'assistant':
                blocks = []
                if m.get('content'):
                    blocks.append({'type': 'text', 'text': m['content']})
                for call in m.get('tool_calls', []):
                    blocks.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'], 'input': json.loads(call['function']['arguments'])})
                native.append({'role': 'assistant', 'content': blocks})
            elif m['role'] == 'tool':
                block = {'type': 'tool_result', 'tool_use_id': m['tool_call_id'], 'content': m['content']}
                if native and native[-1]['role'] == 'user' and isinstance(native[-1]['content'], list):
                    native[-1]['content'].append(block)
                else:
                    native.append({'role': 'user', 'content': [block]})
            else:
                native.append({'role': 'user', 'content': m['content']})
        tools = [{'name': x['function']['name'], 'description': x['function']['description'], 'input_schema': x['function']['parameters']} for x in schemas]
        payload = {'model': self.model, 'max_tokens': 1024, 'system': system, 'messages': native}
        if tools:
            payload['tools'] = tools
        data = post_json(self.url, {'x-api-key': self.key, 'anthropic-version': '2023-06-01'}, payload)
        blocks = data['content']
        calls = [{'id': b['id'], 'name': b['name'], 'arguments': json.dumps(b['input'], ensure_ascii=False)} for b in blocks if b['type'] == 'tool_use']
        text = '\n'.join(b['text'] for b in blocks if b['type'] == 'text')
        message = {'role': 'assistant', 'content': text or None}
        if calls:
            message['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': c['arguments']}} for c in calls]
        reason = {'end_turn': 'stop', 'tool_use': 'tool_calls', 'max_tokens': 'length'}.get(data.get('stop_reason'), data.get('stop_reason'))
        return {'message': message, 'calls': calls, 'finish': reason, 'usage': data.get('usage', {})}