"""Personal-only audio fallback. Temporary audio is removed after transcription."""
import os
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse, parse_qs

_lock = threading.Lock()
_model = None


def canonical_url(value):
    value = value.strip()
    if re.fullmatch(r'BV[0-9A-Za-z]{10}', value):
        return 'https://www.bilibili.com/video/' + value + '/?p=1'
    u = urlparse(value)
    match = re.fullmatch(r'/video/(BV[0-9A-Za-z]{10})/?', u.path)
    if u.scheme != 'https' or u.hostname not in ('www.bilibili.com', 'bilibili.com') or u.username or u.password or not match:
        raise ValueError('请使用完整的 B 站 HTTPS 视频链接或 BV 号，短链接请先展开。')
    try:
        page = int(parse_qs(u.query).get('p', ['1'])[0])
        if page < 1:
            raise ValueError()
    except ValueError:
        raise ValueError('分 P 编号必须为正整数。')
    return f'https://www.bilibili.com/video/{match[1]}/?p={page}'


def extract(app, value, progress=lambda message: None):
    url = canonical_url(value)
    progress('正在读取视频字幕…')
    try:
        result = app.import_bilibili(url)
        result['source'] = 'subtitle'
        return result
    except app.AppError:
        pass
    # Serialize heavy inference. Never run audio extraction on the hosted multi-user API.
    if not _lock.acquire(blocking=False):
        raise app.AppError('另一段视频正在转写，请等它完成后再试。')
    try:
        try:
            import yt_dlp
            from faster_whisper import WhisperModel
        except ImportError:
            raise app.AppError('自动转写组件尚未安装，请运行「安装视频提取组件.bat」后重启 App。')
        progress('字幕不可用，正在获取音频信息…')
        class Quiet:
            def debug(self, *args): pass
            def warning(self, *args): pass
            def error(self, *args): pass
        with tempfile.TemporaryDirectory(prefix='zhizhen-audio-') as folder:
            def hook(info):
                if info.get('status') == 'downloading':
                    size = info.get('total_bytes') or info.get('total_bytes_estimate')
                    if size and size > 200_000_000:
                        raise app.AppError('音频超过 200 MB，请选择更短的视频。')
                    if info.get('downloaded_bytes', 0) > 200_000_000:
                        raise app.AppError('音频超过 200 MB，请选择更短的视频。')
                    progress('正在下载音频' + (f" · {min(100, int(info.get('downloaded_bytes', 0) * 100 / size))}%" if size else '…'))
            options = dict(format='bestaudio', outtmpl=str(Path(folder)/'audio.%(ext)s'),
                           noplaylist=True, socket_timeout=30, retries=2, quiet=True,
                           logger=Quiet(), progress_hooks=[hook], max_filesize=200_000_000)
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info or info.get('_type') in ('playlist', 'multi_video'):
                    raise app.AppError('请使用单个视频分 P 的完整链接。')
                if info.get('is_live') or (info.get('duration') or 0) > 7200:
                    raise app.AppError('暂不支持直播或超过两小时的视频，请分段学习。')
                ydl.process_info(info)
                files = [p for p in Path(folder).iterdir() if p.suffix not in ('.part', '.ytdl') and p.is_file()]
                if len(files) != 1:
                    raise app.AppError('未得到可转写音频，视频可能需要登录或受访问限制。')
            global _model
            if _model is None:
                progress('正在加载语音模型；首次需下载 multilingual base 模型，可能耗时较长…')
                cache = Path(os.getenv('LOCALAPPDATA', Path.home()))/'BiliStudy'/'models'
                _model = WhisperModel('base', device='cpu', compute_type='int8', download_root=str(cache), cpu_threads=4)
            progress('正在本机转写音频，长视频可能需要数分钟…')
            chunks, metadata = _model.transcribe(str(files[0]), beam_size=3)
            segments = []
            total = 0
            for chunk in chunks:
                text = chunk.text.strip()
                if not text:
                    continue
                total += len(text)
                if total > 55000:
                    raise app.AppError('转写超过 55,000 字符，请选择更短的分段；未静默截断。')
                segments.append(dict(id=f'S{len(segments)+1}', text=text, start=app.stamp(chunk.start), end=app.stamp(chunk.end)))
                progress(f'正在转写 · 已处理至 {app.stamp(chunk.end)}')
            if not segments:
                raise app.AppError('没有识别到语音，请确认视频包含清晰人声。')
            return dict(title=info.get('title') or '视频学习', url=url, segments=segments,
                        subtitle='本机语音转写（可能有识别错误，未分析画面）', source='asr')
    except app.AppError:
        raise
    except Exception:
        raise app.AppError('音频提取或转写失败：可能是 B 站访问限制、网络问题或语音模型下载失败。可重试或导入字幕；已有学习记录未修改。')
    finally:
        _lock.release()


jobs = {}
jobs_lock = threading.Lock()


def start_job(app, value):
    import time
    import secrets
    url = canonical_url(value)
    with jobs_lock:
        now = time.time()
        for key in list(jobs):
            if jobs[key]['state'] != 'running' and now-jobs[key]['created'] > 3600:
                del jobs[key]
        if any(j['state'] == 'running' for j in jobs.values()):
            raise app.AppError('已有视频正在提取，请等待完成。')
        jid = secrets.token_hex(16)
        jobs[jid] = dict(id=jid, created=now, state='running', message='正在准备…')
    def progress(message):
        with jobs_lock:
            jobs[jid]['message'] = message
    def run():
        try:
            result = extract(app, url, progress)
            with jobs_lock:
                jobs[jid].update(state='done', message='内容已提取', result=result)
        except Exception as exc:
            with jobs_lock:
                jobs[jid].update(state='error', error=str(exc) if isinstance(exc, app.AppError) else '视频提取失败，请重试。')
    threading.Thread(target=run, daemon=True).start()
    return dict(id=jid)


def get_job(app, jid):
    with jobs_lock:
        if jid not in jobs:
            raise app.AppError('提取任务不存在或已过期，请重试。')
        return dict(jobs[jid])
