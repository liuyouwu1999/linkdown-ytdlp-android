"""
yt-dlp runner for yt-dlp-android (Chaquopy / Python 3.13).

Called from Java via Chaquopy's Java-Python bridge.
No curl_cffi / browser TLS impersonation in this build; sites that require a
browser-like TLS fingerprint need cookie-based auth or will return errors.
"""
import sys
import threading

import yt_dlp
from yt_dlp.utils import DownloadCancelled

# ---------------------------------------------------------------------------
# Cancellation (M3: per-run registry keyed by run_id)
# ---------------------------------------------------------------------------
_cancel_registry: dict[str, bool] = {}

# Serializes the stdout swap -> run -> restore of the --dump-single-json
# bridge: without it, two overlapping execute_debug calls would each capture
# the other's bridge as "the old stdout" and the first restore would leave
# sys.stdout pointing at a dead callback.
_STDOUT_LOCK = threading.Lock()


def request_cancel(run_id):
    _cancel_registry[run_id] = True


def _reset_cancel(run_id):
    _cancel_registry[run_id] = False


def _cancel_hook(run_id, d):
    if _cancel_registry.get(run_id):
        # Deterministic marker: host-side tests assert this line, not the exception class.
        print("[linkdown] cancelled")
        raise DownloadCancelled()


# ---------------------------------------------------------------------------
# Native lib dir passthrough (channel for the host's ffprobe fallback
# monkeypatch; harmless when unused)
# ---------------------------------------------------------------------------
_LIB_DIR = ""


def set_native_lib_dir(p: str):
    global _LIB_DIR
    _LIB_DIR = p


# ---------------------------------------------------------------------------
# CLI flag → YoutubeDL option mapping
# ---------------------------------------------------------------------------
_FLAG_MAP = {
    '-f':                    ('format',              True),
    '--format':              ('format',              True),
    '-o':                    ('outtmpl',             True),
    '--output':              ('outtmpl',             True),
    '--cookies':             ('cookiefile',           True),
    '--proxy':               ('proxy',               True),
    '--add-header':          ('_header',              True),
    '--user-agent':          ('_user_agent',          True),
    '--restrict-filenames':  ('restrictfilenames',    False),
    '--newline':             ('newline',              False),
    '--no-playlist':         ('noplaylist',           False),
    '-F':                    ('listformats',          False),
    '--dump-single-json':    ('dump_single_json',     False),
    '-x':                    ('_extract_audio',       False),
    '--extract-audio':       ('_extract_audio',       False),
    '--audio-format':        ('_audio_format',        True),
    '--audio-quality':       ('_audio_quality',       True),
    '--write-sub':           ('writesubtitles',       False),
    '--sub-lang':            ('subtitleslangs',       True),
    '--merge-output-format': ('merge_output_format',  True),
    '--ffmpeg-location':     ('ffmpeg_location',      True),
    '--write-thumbnail':     ('writethumbnail',       False),
    '--skip-download':       ('skip_download',        False),
    '--flat-playlist':       ('extract_flat',         False),
}


def _cli_to_opts(cli_flags):
    """Convert a list of CLI-style flag strings to a YoutubeDL opts dict."""
    opts = {}
    flags = list(cli_flags)
    i = 0
    while i < len(flags):
        flag = flags[i]
        mapping = _FLAG_MAP.get(flag)
        if mapping is None:
            i += 1
            continue
        key, needs_value = mapping
        if not needs_value:
            if key == '_extract_audio':
                opts.setdefault('postprocessors', []).append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                })
                opts['extractaudio'] = True
            else:
                opts[key] = True
            i += 1
        else:
            if i + 1 >= len(flags):
                i += 1
                continue
            val = flags[i + 1]
            if key == '_header':
                name, _, value = val.partition(':')
                opts.setdefault('http_headers', {})[name.strip()] = value.strip()
            elif key == '_user_agent':
                opts.setdefault('http_headers', {})['User-Agent'] = val
            elif key == '_audio_format':
                for pp in opts.get('postprocessors', []):
                    if pp.get('key') == 'FFmpegExtractAudio':
                        pp['preferredcodec'] = val
            elif key == '_audio_quality':
                for pp in opts.get('postprocessors', []):
                    if pp.get('key') == 'FFmpegExtractAudio':
                        pp['preferredquality'] = val
            else:
                opts[key] = val
            i += 2
    # --flat-playlist 值特判（批量枚举）：照内部脚本蓝本 batch_ytdlp.py 用
    # 'in_playlist'——只扁平化播放列表内的 entries；裸 True 会把单视频 URL 也 flatten
    # 成 url-only 条目（丢失全部元数据）。
    if opts.get('extract_flat'):
        opts['extract_flat'] = 'in_playlist'
    return opts


# ---------------------------------------------------------------------------
# Public API (called from Java via Chaquopy)
# ---------------------------------------------------------------------------

def execute(run_id, url, output_template, cli_flags, progress_callback=None):
    """
    Execute a yt-dlp download.

    Args:
        run_id: unique per-run identifier (keys the cancellation registry)
        url: video URL string
        output_template: yt-dlp output path template or None
        cli_flags: Java String[] / list of CLI flag strings (without URL)
        progress_callback: Java DownloadProgressCallback or None

    Returns:
        int exit code (0 = success)
    """
    return _run(run_id, url, output_template, cli_flags,
                progress_callback=progress_callback)


def execute_debug(run_id, url, output_template, cli_flags,
                  log_callback=None,
                  progress_callback=None):
    """
    Like execute but forwards ALL yt-dlp log lines to log_callback.
    Use for debugging integration issues.

    run_id keys the per-run cancellation registry (see request_cancel).
    """
    _reset_cancel(run_id)
    opts = _cli_to_opts(cli_flags or [])
    if output_template:
        opts['outtmpl'] = output_template
    want_stdout_bridge = False
    if log_callback is not None:
        class _Logger:
            def debug(self, msg):
                log_callback.onLog('DEBUG' if msg.startswith('[debug]') else 'INFO', msg)
            def warning(self, msg):
                log_callback.onLog('WARNING', msg)
            def error(self, msg):
                log_callback.onLog('ERROR', msg)
        opts['logger'] = _Logger()
        # --dump-single-json prints its metadata JSON via YoutubeDL.to_stdout(),
        # which writes to sys.stdout — NOT through the logger (only to_screen /
        # to_stderr are routed to the logger). In Chaquopy sys.stdout goes to
        # logcat, so without this bridge the Java side never sees the JSON.
        # Gated on the flag being present: ordinary downloads are untouched.
        if '--dump-single-json' in (cli_flags or []):
            class _StdoutToLog:
                def write(self, s):
                    if s.strip():
                        log_callback.onLog('INFO', s.rstrip('\n'))
                    return len(s)
                def flush(self):
                    pass
            want_stdout_bridge = True
    # CLI parity: `yt-dlp -J/--dump-single-json` implies simulate (the
    # any_getting -> simulate normalization lives in the CLI entrypoint,
    # yt_dlp/__init__.py, and never runs on this API path). Without it the
    # media would be fully downloaded after metadata extraction.
    if opts.get('dump_single_json') and opts.get('simulate') is None:
        opts['simulate'] = True
    # Cancel-check hook is ALWAYS registered: cancellation must work even when
    # no progress callback was supplied (previously it silently did nothing).
    opts['progress_hooks'] = [lambda d: _cancel_hook(run_id, d)]
    if progress_callback is not None:
        def _hook(d):
            if d['status'] == 'downloading':
                try:
                    pct = float(d.get('_percent_str', '0.0%').strip().replace('%', ''))
                    eta = int(d.get('eta') or 0)
                    line = d.get('_default_template', '')
                    progress_callback.onProgressUpdate(pct, eta, line)
                except Exception:
                    pass
        opts['progress_hooks'].append(_hook)
    if not want_stdout_bridge:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.download([url])
    # Swap -> run -> restore under one module-level lock: a concurrent
    # execute_debug must not swap stdout out from under us mid-download.
    with _STDOUT_LOCK:
        _old_stdout = sys.stdout
        sys.stdout = _StdoutToLog()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.download([url])
        finally:
            sys.stdout = _old_stdout


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------

def _run(run_id, url, output_template, cli_flags, progress_callback):
    _reset_cancel(run_id)
    opts = _cli_to_opts(cli_flags or [])

    if output_template:
        opts['outtmpl'] = output_template

    # Cancel-check hook is ALWAYS registered: cancellation must work even when
    # no progress callback was supplied (previously it silently did nothing).
    opts['progress_hooks'] = [lambda d: _cancel_hook(run_id, d)]
    if progress_callback is not None:
        def _hook(d):
            if d['status'] == 'downloading':
                try:
                    pct = float(
                        d.get('_percent_str', '0.0%').strip().replace('%', '')
                    )
                    eta = int(d.get('eta') or 0)
                    line = d.get('_default_template', '')
                    progress_callback.onProgressUpdate(pct, eta, line)
                except Exception:
                    pass
        opts['progress_hooks'].append(_hook)

    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.download([url])
