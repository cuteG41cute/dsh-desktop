# -*- coding: utf-8 -*-
"""本地语音服务（Qwen3-TTS）的 Linux 侧封装。

与 Windows 版 dsh-manager-win/Services/TtsService.cs 对齐：
- 服务脚本与模型放在 ~/.local/share/dsh-manager/services/tts（可用环境变量覆盖）
- 端口 8098，OpenAI 兼容 /v1/audio/speech、/v1/audio/voices
- 提供 启停 / 列出音色 / 克隆音色 / 改名 / 删除 / 合成 六个动作
- 合成结果落到临时目录，播放交给 ffplay/paplay/aplay
"""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

PORT = 8098


def service_root():
    """服务目录：~/.local/share/dsh-manager/services/tts（可用 DSH_TTS_DIR 覆盖）。"""
    env = os.environ.get('DSH_TTS_DIR')
    if env:
        return os.path.expanduser(env)
    base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'dsh-manager', 'services', 'tts')


def paths():
    root = service_root()
    return {
        'root': root,
        'run': os.path.join(root, 'run'),
        'models': os.path.join(root, 'models'),
        'voices': os.path.join(root, 'voices'),
        'logs': os.path.join(root, 'logs'),
        'samples': os.path.join(root, 'samples'),
    }


def _server_exe():
    return os.path.join(paths()['run'], 'tts-server')


def binaries_ready():
    return os.access(_server_exe(), os.X_OK)


def models_ready():
    d = paths()['models']
    if not os.path.isdir(d):
        return False
    names = os.listdir(d)
    return any(n.endswith('.gguf') and 'codec' in n for n in names) and \
        any(n.endswith('.gguf') and 'tts' in n for n in names)


def models_bytes():
    d = paths()['models']
    if not os.path.isdir(d):
        return 0
    total = 0
    for n in os.listdir(d):
        try:
            total += os.path.getsize(os.path.join(d, n))
        except OSError:
            pass
    return total


def port_open(port=PORT, timeout=0.25):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(('127.0.0.1', port)) == 0
    finally:
        s.close()


def running():
    return port_open()


def _find_backbone():
    d = paths()['models']
    if not os.path.isdir(d):
        return None
    for n in sorted(os.listdir(d)):
        if n.endswith('.gguf') and 'qwen' in n.lower():
            return os.path.join(d, n)
    return None


def _find_codec():
    d = paths()['models']
    if not os.path.isdir(d):
        return None
    for n in sorted(os.listdir(d)):
        if n.endswith('.gguf') and 'codec' in n.lower():
            return os.path.join(d, n)
    return None


def start():
    """拉起服务；返回 (ok, message)。"""
    if running():
        return True, '本地语音已在运行'
    if not binaries_ready():
        return False, '缺少 run/tts-server（把编译好的程序放进去）'
    backbone = _find_backbone()
    codec = _find_codec()
    if not backbone or not codec:
        return False, 'models/ 里缺少模型（需要 qwen3-tts*.gguf + codec*.gguf）'
    p = paths()
    os.makedirs(p['logs'], exist_ok=True)
    os.makedirs(p['voices'], exist_ok=True)
    os.makedirs(p['samples'], exist_ok=True)
    log_path = os.path.join(p['logs'], 'server.log')
    cmd = [_server_exe(),
           '--backbone', backbone,
           '--model', codec,
           '--voice-dir', p['voices'],
           '--allow-voice-create',
           '--n-threads', str(max(2, (os.cpu_count() or 4) - 1)),
           '--port', str(PORT)]
    try:
        with open(log_path, 'ab') as log:
            subprocess.Popen(cmd, cwd=p['run'], stdout=log, stderr=log,
                             start_new_session=True)
    except OSError as exc:
        return False, '启动失败：%s' % exc
    for _ in range(40):
        if running():
            return True, '本地语音已启动（端口 %d）' % PORT
        time.sleep(0.25)
    return False, '启动超时，查看日志：%s' % log_path


def stop():
    """按端口杀服务，返回 (ok, message)。"""
    if not running():
        return True, '本地语音已停止'
    try:
        # ss/lsof 任选其一；找不到就用 fuser
        for cmd in (['fuser', '-k', '%d/tcp' % PORT],
                    ['bash', '-lc', "ss -ltnp 2>/dev/null | grep ':%d ' | grep -o 'pid=[0-9]*' | cut -d= -f2 | xargs -r kill" % PORT]):
            if shutil.which(cmd[0] if cmd[0] != 'bash' else 'bash'):
                subprocess.run(cmd, capture_output=True)
                break
    except OSError:
        pass
    for _ in range(20):
        if not running():
            return True, '本地语音已停止'
        time.sleep(0.2)
    return False, '停止失败：端口 %d 仍被占用' % PORT


def _request(path, method='GET', data=None, headers=None, timeout=600):
    url = 'http://127.0.0.1:%d%s' % (PORT, path)
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        return 0, str(exc).encode()


def list_voices():
    """返回 (ok, error, [{'id':..,'name':..}, ...])"""
    if not running():
        return False, '服务没在运行', []
    status, body = _request('/v1/audio/voices', timeout=10)
    if status != 200:
        return False, body[:200].decode('utf-8', 'replace'), []
    try:
        data = json.loads(body.decode('utf-8'))
    except ValueError:
        return False, '返回不是 JSON', []
    out = []
    for v in data.get('custom') or []:
        out.append({'id': v.get('id', ''), 'name': v.get('name', '')})
    return True, '', out


def _multipart(fields, files):
    boundary = '----dshmanager' + uuid.uuid4().hex
    lines = []
    for k, v in fields.items():
        lines.append('--' + boundary)
        lines.append('Content-Disposition: form-data; name="%s"' % k)
        lines.append('')
        lines.append(v)
    for k, (filename, content, ctype) in files.items():
        lines.append('--' + boundary)
        lines.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (k, filename))
        lines.append('Content-Type: %s' % ctype)
        lines.append('')
    body = ('\r\n'.join(lines) + '\r\n').encode('utf-8')
    for k, (filename, content, ctype) in files.items():
        body += content + b'\r\n'
    body += ('--' + boundary + '--\r\n').encode('utf-8')
    return body, 'multipart/form-data; boundary=' + boundary


def create_voice(name, wav_path):
    if not running():
        return False, '服务没在运行'
    try:
        with open(wav_path, 'rb') as fh:
            content = fh.read()
    except OSError as exc:
        return False, '读取音频失败：%s' % exc
    body, ctype = _multipart({'name': name},
                             {'audio_sample': (os.path.basename(wav_path), content, 'audio/wav')})
    status, resp = _request('/v1/audio/voices', 'POST', body, {'Content-Type': ctype})
    if status == 200:
        return True, '已创建音色：%s' % name
    return False, resp[:300].decode('utf-8', 'replace')


def rename_voice(voice_id, name):
    if not running():
        return False, '服务没在运行'
    body = json.dumps({'name': name}).encode('utf-8')
    status, resp = _request('/v1/audio/voices/' + urllib.request.quote(voice_id, safe=''),
                            'PATCH', body, {'Content-Type': 'application/json'})
    if status == 200:
        return True, '已改名为 %s' % name
    return False, resp[:300].decode('utf-8', 'replace')


def delete_voice(voice_id):
    if not running():
        return False, '服务没在运行'
    status, resp = _request('/v1/audio/voices/' + urllib.request.quote(voice_id, safe=''), 'DELETE')
    if status == 200:
        return True, '已删除'
    return False, resp[:300].decode('utf-8', 'replace')


def synthesize(text, voice='', timeout=900):
    """合成到临时 wav；返回 (ok, error, path, 音频秒数)。"""
    if not running():
        return False, '服务没在运行', '', 0
    payload = {'model': 'codec-q8_0', 'input': text, 'response_format': 'wav'}
    if voice:
        payload['voice'] = voice
    status, body = _request('/v1/audio/speech', 'POST', json.dumps(payload).encode('utf-8'),
                            {'Content-Type': 'application/json'}, timeout=timeout)
    if status != 200:
        return False, body[:300].decode('utf-8', 'replace'), '', 0
    out = os.path.join(tempfile.gettempdir(), 'dsh-tts-%s.wav' % uuid.uuid4().hex[:8])
    with open(out, 'wb') as fh:
        fh.write(body)
    secs = max(0.0, (len(body) - 44) / 48000.0)   # 24k 单声道 16bit
    return True, '', out, secs


def ffmpeg():
    for name in ('ffmpeg',):
        hit = shutil.which(name)
        if hit:
            return hit
    return None


def transcode_to_wav(src, out_dir=None):
    """把任意音频转成 24k 单声道 PCM16 wav；失败返回 (None, error)。"""
    ff = ffmpeg()
    if not ff:
        return None, '找不到 ffmpeg（apt install ffmpeg）'
    dst = os.path.join(out_dir or tempfile.gettempdir(), 'dsh-tts-in-%s.wav' % uuid.uuid4().hex[:8])
    proc = subprocess.run([ff, '-y', '-i', src, '-ac', '1', '-ar', '24000',
                           '-c:a', 'pcm_s16le', dst], capture_output=True)
    if proc.returncode != 0 or not os.path.exists(dst):
        return None, (proc.stderr or b'')[-300:].decode('utf-8', 'replace')
    return dst, ''


def apply_speed(wav_path, speed):
    """变速（atempo），失败原样返回。"""
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        return wav_path
    if abs(speed - 1.0) < 0.01:
        return wav_path
    ff = ffmpeg()
    if not ff:
        return wav_path
    dst = os.path.join(tempfile.gettempdir(), 'dsh-tts-speed-%s.wav' % uuid.uuid4().hex[:8])
    proc = subprocess.run([ff, '-y', '-i', wav_path, '-filter:a', 'atempo=%s' % speed, dst],
                          capture_output=True)
    if proc.returncode == 0 and os.path.exists(dst):
        return dst
    return wav_path


def play(wav_path):
    """优先 ffplay，其次 paplay/aplay；返回 (ok, message)。"""
    for cmd in (['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', wav_path],
                ['paplay', wav_path],
                ['aplay', '-q', wav_path]):
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, ''
            except OSError:
                continue
    return False, '找不到播放器（ffplay/paplay/aplay 都没有）'
