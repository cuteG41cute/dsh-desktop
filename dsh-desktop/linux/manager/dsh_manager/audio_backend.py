# -*- coding: utf-8 -*-
"""audio.cpp 后端（通用 TTS 引擎）的下载、配置与启停。

audio.cpp 是一个 ggml 原生的多模型音频推理引擎（143 个模型族），
对外提供 OpenAI 兼容接口：/v1/models、/v1/audio/speech、/v1/audio/voices。

这里负责把它「按需装到用户目录」并跑起来：
  <data>/dsh-manager/services/audiocpp/bin/     -> 预编译发行包解压出来的内容
  <data>/dsh-manager/services/audiocpp/models/  -> 各个 GGUF 模型
  <data>/dsh-manager/services/audiocpp/server.json -> 按当前选中的模型生成
"""
import io
import json
import os
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile

PORT = 8092

GH = 'https://github.com/0xShug0/audio.cpp/releases/download/v0.9.5/'
MIRROR = 'https://gh-proxy.com/'
MS = 'https://modelscope.cn/models/audio-cpp/audio.cpp-gguf/resolve/master/'

# 平台对应的发行包（管理器按需下载）
BUNDLE = {
    'linux': 'audio-v0.9.5-bin-ubuntu-x64-cpu-portable.tar.gz',
    'win32': 'audio-v0.9.5-bin-windows-x64-cpu-portable.zip',
}

# 目前接入的模型（都是 audio.cpp 官方 ModelScope 仓库里的 GGUF）
MODELS = [
    {
        'id': 'kokoro',
        'label': 'Kokoro-82M（快、54 音色）',
        'family': 'kokoro_tts',
        'file': 'kokoro-82m-q8_0.gguf',
        'remote': 'Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf',
        'size': 189_550_976,
        'default_voice': 'af_heart',
        'clone': False,
    },
    {
        'id': 'moss-nano',
        'label': 'MOSS-TTS-Nano 100M（极小、快）',
        'family': 'moss_tts_nano',
        'file': 'moss-tts-nano-100m-q8_0.gguf',
        'remote': 'MOSS-TTS-Nano-100M-GGUF/moss-tts-nano-100m-q8_0.gguf',
        'size': 193_343_328,
        'default_voice': '',
        'clone': True,
    },
    {
        'id': 'omnivoice',
        'label': 'OmniVoice（646 语言、克隆/设计）',
        'family': 'omnivoice',
        'file': 'omnivoice-q8_0.gguf',
        'remote': 'OmniVoice-GGUF/omnivoice-q8_0.gguf',
        'size': 1_350_296_096,
        'default_voice': '',
        'clone': True,
    },
    {
        'id': 'irodori-anime',
        'label': 'Irodori-TTS v4.1 动漫（日系）',
        'family': 'irodori_tts',
        'file': 'irodori-tts-v4.1-anime-q8_0.gguf',
        'remote': 'Irodori-TTS-v4-Small-GGUF/irodori-tts-v4.1-anime-q8_0.gguf',
        'size': 1_112_550_112,
        'default_voice': '',
        'clone': True,
    },
    {
        'id': 'qwen3-tts',
        'label': 'Qwen3-TTS 0.6B（可克隆音色）',
        'family': 'qwen3_tts',
        'file': 'qwen3-tts-0.6b-base-q8_0.gguf',
        'remote': 'Qwen3-TTS-12Hz-0.6B-Base-GGUF/qwen3-tts-12hz-0.6b-base-q8_0.gguf',
        'size': 1_991_217_728,
        'default_voice': '',
        'clone': True,
    },
    {
        'id': 'cosyvoice3',
        'label': 'CosyVoice3（中文克隆/设计）',
        'family': 'cosyvoice3',
        'file': 'cosyvoice3-q8_0.gguf',
        'remote': 'CosyVoice3-GGUF/cosyvoice3-q8_0.gguf',
        'size': 2_257_658_336,
        'default_voice': '',
        'clone': True,
    },
    {
        'id': 'chatterbox',
        'label': 'Chatterbox（英文表现力强）',
        'family': 'chatterbox',
        'file': 'chatterbox-q8_0.gguf',
        'remote': 'Chatterbox-GGUF/chatterbox-q8_0.gguf',
        'size': 2_088_399_204,
        'default_voice': '',
        'clone': True,
    },
    {
        'id': 'index-tts2',
        'label': 'IndexTTS2.5（中文克隆最强档，3.3 GB）',
        'family': 'index_tts2',
        'file': 'index-tts2_5-q8_0.gguf',
        'remote': 'IndexTTS2.5-GGUF/index-tts2_5-q8_0.gguf',
        'size': 3_502_960_096,
        'default_voice': '',
        'clone': True,
    },
]


def data_root():
    env = os.environ.get('DSH_AUDIOCPP_DIR')
    if env:
        return os.path.expanduser(env)
    base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'dsh-manager', 'services', 'audiocpp')


def paths():
    root = data_root()
    return {
        'root': root,
        'bin': os.path.join(root, 'bin'),
        'models': os.path.join(root, 'models'),
        'voices': os.path.join(root, 'voices'),
        'logs': os.path.join(root, 'logs'),
        'config': os.path.join(root, 'server.json'),
    }


SYSTEM_DIR = '/usr/lib/dsh-manager/audio-cpp'


def server_exe():
    """优先用用户目录里下载/释放的运行时，其次用 deb 里自带的（带静态 eSpeak）。"""
    name = 'audiocpp_server.exe' if os.name == 'nt' else 'audiocpp_server'
    user = os.path.join(paths()['bin'], name)
    if os.path.isfile(user):
        return user
    system = os.path.join(SYSTEM_DIR, name)
    if os.path.isfile(system):
        return system
    return user


def ready():
    return os.path.isfile(server_exe())


def model_path(model):
    return os.path.join(paths()['models'], model['file'])


def model_ready(model):
    p = model_path(model)
    return os.path.isfile(p) and os.path.getsize(p) >= model['size'] * 0.9


def _active_file():
    return os.path.join(paths()['root'], 'active.json')




KOKORO_VOICES = [
    'af_heart', 'af_alloy', 'af_aoede', 'af_bella', 'af_jessica', 'af_kore', 'af_nicole',
    'af_nova', 'af_river', 'af_sarah', 'af_sky',
    'am_adam', 'am_echo', 'am_eric', 'am_fenrir', 'am_liam', 'am_michael', 'am_onyx',
    'am_puck', 'am_santa',
    'bf_alice', 'bf_emma', 'bf_isabella', 'bf_lily',
    'bm_daniel', 'bm_fable', 'bm_george', 'bm_lewis',
    'ef_dora', 'em_alex', 'ff_siwis',
    'hf_alpha', 'hf_beta', 'hm_omega', 'hm_psi',
    'if_sara', 'im_nicola',
    'jf_alpha', 'jf_gongitsune', 'jf_nezumi', 'jf_tebukuro', 'jm_kumo',
    'pf_dora', 'pm_alex', 'pm_santa',
    'zf_xiaobei', 'zf_xiaoni', 'zf_xiaoxiao', 'zf_xiaoyi',
    'zm_yunjian', 'zm_yunxi', 'zm_yunxia', 'zm_yunyang',
]


def preset_voices(mid):
    return list(KOKORO_VOICES) if mid == 'kokoro' else []



def _voice_file():
    return os.path.join(paths()['root'], 'voice.json')


def active_voice():
    try:
        with open(_voice_file(), 'r', encoding='utf-8') as fh:
            return (json.load(fh) or {}).get('voice') or ''
    except (OSError, ValueError):
        return ''


def set_active_voice(name):
    os.makedirs(paths()['root'], exist_ok=True)
    with open(_voice_file(), 'w', encoding='utf-8') as fh:
        json.dump({'voice': name}, fh)


def add_voice(name, wav_path, ref_text=''):
    """把一个参考音频登记成 audio.cpp 的音色：voices/<name>.wav + prompt_text 里 name|文本。"""
    p = paths()
    os.makedirs(p['voices'], exist_ok=True)
    dest = os.path.join(p['voices'], name + '.wav')
    shutil.copyfile(wav_path, dest)
    prompt = os.path.join(p['voices'], 'prompt_text')
    lines = []
    if os.path.isfile(prompt):
        for line in io.open(prompt, encoding='utf-8', errors='replace'):
            line = line.rstrip('\n')
            if not line.strip():
                continue
            if line.split('|')[0].strip().lower() == name.lower():
                continue
            lines.append(line)
    lines.append('%s|%s' % (name, (ref_text or '').strip()))
    with io.open(prompt, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return True, '音色已创建：%s' % name


def active_model():
    """当前选中的模型 id（没设置或模型被删了就回退到第一个已安装的）。"""
    try:
        with open(_active_file(), 'r', encoding='utf-8') as fh:
            mid = (json.load(fh) or {}).get('id') or ''
    except (OSError, ValueError):
        mid = ''
    installed = [m['id'] for m in installed_models()]
    if mid in installed:
        return mid
    return installed[0] if installed else ''


def set_active_model(mid):
    os.makedirs(paths()['root'], exist_ok=True)
    with open(_active_file(), 'w', encoding='utf-8') as fh:
        json.dump({'id': mid}, fh)



def installed_models():
    return [m for m in MODELS if model_ready(m)]


def port_open(port=PORT, timeout=0.3):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(('127.0.0.1', port)) == 0
    finally:
        s.close()


def running():
    return port_open()


def _download(urls, dest, progress=None, label='', cancel=None):
    """依次尝试多个 URL 下载到 dest（带 .part 续传）。返回 (ok, err)。"""
    part = dest + '.part'
    have = os.path.getsize(part) if os.path.exists(part) else 0
    last = None
    for url in urls:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'dsh-manager/3.2.3',
            'Accept': '*/*',
        })
        if have:
            req.add_header('Range', 'bytes=%d-' % have)
        try:
            resp = urllib.request.urlopen(req, timeout=60)
        except Exception as exc:
            last = exc
            continue
        total = have + int(resp.headers.get('Content-Length') or 0)
        mode = 'ab' if have and resp.status == 206 else 'wb'
        if mode == 'wb':
            have = 0
        try:
            with open(part, mode) as fh:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise DownloadCancelled()
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    have += len(chunk)
                    if progress:
                        progress(have, total, label)
        except Exception as exc:
            last = exc
            return False, '下载中断：%s' % exc
        finally:
            try:
                resp.close()
            except Exception:
                pass
        os.replace(part, dest)
        return True, ''
    return False, '下载失败：%s' % last


class DownloadCancelled(Exception):
    pass


def download_bundle(progress=None, cancel=None):
    """下载并解压 audio.cpp 预编译发行包到 bin/。"""
    if ready():
        return True, '已安装'
    import platform
    key = 'win32' if os.name == 'nt' else 'linux'
    name = BUNDLE[key]
    # 优先用我们自编译的「带静态 eSpeak」发行包（官方包没有 eSpeak，英文音色会失败）
    ours = ('https://github.com/cuteG41cute/dsh-desktop/releases/download/'
            'audio-cpp-espeak-v1/audio-cpp-espeak-linux-x64.tar.gz')
    urls = [ours, MIRROR + GH + name, GH + name]
    p = paths()
    os.makedirs(p['bin'], exist_ok=True)
    tmp = os.path.join(tempfile.gettempdir(), name)
    ok, err = _download(urls, tmp, progress, name, cancel)
    if not ok:
        return False, err
    try:
        if name.endswith('.zip'):
            with zipfile.ZipFile(tmp) as zf:
                zf.extractall(p['bin'])
        else:
            with tarfile.open(tmp) as tf:
                tf.extractall(p['bin'])
    except Exception as exc:
        return False, '解压失败：%s' % exc
    # 发行包可能带一层目录
    exe = server_exe()
    if not os.path.isfile(exe):
        for root, _dirs, files in os.walk(p['bin']):
            if 'audiocpp_server' in files or 'audiocpp_server.exe' in files:
                for f in files:
                    shutil.move(os.path.join(root, f), os.path.join(p['bin'], f))
                break
    if not os.path.isfile(exe):
        return False, '发行包里没有 audiocpp_server'
    try:
        os.chmod(exe, 0o755)
    except OSError:
        pass
    return True, 'audio.cpp 已安装'


def download_model(model, progress=None, cancel=None):
    p = paths()
    os.makedirs(p['models'], exist_ok=True)
    dest = model_path(model)
    if model_ready(model):
        return True, '已存在'
    urls = [MS + model['remote']]
    try:
        return _download(urls, dest, progress, model['file'], cancel)
    except DownloadCancelled:
        return False, '已取消'


def write_config(active_ids):
    """按选中的模型生成 server.json。"""
    p = paths()
    os.makedirs(p['voices'], exist_ok=True)
    models = []
    for m in MODELS:
        if m['id'] not in active_ids or not model_ready(m):
            continue
        entry = {
            'id': m['id'],
            'family': m['family'],
            'path': model_path(m),
            'task': 'tts',
            'mode': 'offline',
        }
        if m.get('default_voice'):
            entry['default_voice_preset'] = {'voice_id': m['default_voice']}
        models.append(entry)
    cfg = {
        'host': '127.0.0.1',
        'port': PORT,
        'backend': 'cpu',
        'threads': max(2, (os.cpu_count() or 4) - 1),
        'lazy_load': True,
        'max_loaded_models': 1,
        'ui': False,
        'voice_dir': p['voices'],
        'models': models,
    }
    os.makedirs(p['root'], exist_ok=True)
    with open(p['config'], 'w', encoding='utf-8') as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    return cfg


def start(active_ids):
    if running():
        return True, 'audio.cpp 已在运行'
    if not ready():
        return False, '还没下载 audio.cpp 运行时'
    cfg = write_config(active_ids)
    if not cfg['models']:
        return False, '没有可用的模型（先下载至少一个）'
    p = paths()
    os.makedirs(p['logs'], exist_ok=True)
    log = open(os.path.join(p['logs'], 'server.log'), 'ab')
    cmd = [server_exe(), '--config', p['config']]
    try:
        subprocess.Popen(cmd, cwd=os.path.dirname(server_exe()), stdout=log, stderr=log,
                         start_new_session=(os.name != 'nt'))
    except OSError as exc:
        return False, '启动失败：%s' % exc
    for _ in range(120):
        if running():
            return True, 'audio.cpp 已启动（端口 %d）' % PORT
        time.sleep(0.5)
    return False, '启动超时，看日志：' + os.path.join(p['logs'], 'server.log')


def stop():
    if not running():
        return True, 'audio.cpp 已停止'
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/IM', 'audiocpp_server.exe'],
                           capture_output=True)
        else:
            subprocess.run(['pkill', '-f', 'audiocpp_server'], capture_output=True)
    except OSError:
        pass
    for _ in range(40):
        if not running():
            return True, 'audio.cpp 已停止'
        time.sleep(0.25)
    return False, '停止失败：端口 %d 仍被占用' % PORT


def _get(path, timeout=10):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d%s' % (PORT, path), timeout=timeout) as r:
            return r.status, r.read()
    except Exception as exc:
        return 0, str(exc).encode()


def models():
    st, body = _get('/v1/models')
    if st != 200:
        return False, body[:200].decode('utf-8', 'replace'), []
    try:
        data = json.loads(body.decode('utf-8'))
    except ValueError:
        return False, '返回不是 JSON', []
    return True, '', [m.get('id') for m in data.get('data') or []]


def voices():
    st, body = _get('/v1/audio/voices')
    if st != 200:
        return []
    try:
        return json.loads(body.decode('utf-8')).get('voices') or []
    except ValueError:
        return []


def synthesize(text, model_id, voice='', timeout=900):
    payload = {'model': model_id, 'input': text, 'response_format': 'wav'}
    if voice:
        payload['voice'] = voice
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:%d/v1/audio/speech' % PORT, data=data,
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except Exception as exc:
        return False, str(exc), '', 0.0, 0.0
    out = os.path.join(tempfile.gettempdir(), 'acpp-%d.wav' % int(time.time() * 1000))
    with open(out, 'wb') as fh:
        fh.write(body)
    secs = max(0.0, (len(body) - 44) / 48000.0)
    return True, '', out, secs, time.time() - t0
