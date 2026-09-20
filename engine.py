import os
import re
import time
import html
import urllib.parse
import threading
import concurrent.futures
import requests

CHUNK_SIZE = 64 * 1024  # 64 KB read buffer

MIME_TO_EXT = {
    "video/x-matroska": ".mkv",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/flac": ".flac",
    "audio/wav": ".wav",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/x-rar-compressed": ".rar",
    "application/vnd.rar": ".rar",
    "application/x-7z-compressed": ".7z",
    "application/x-tar": ".tar",
    "application/gzip": ".tar.gz",
    "application/pdf": ".pdf",
    "application/x-msdownload": ".exe",
    "application/vnd.android.package-archive": ".apk",
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

def format_bytes(bytes_num):
    if bytes_num is None or bytes_num < 0:
        return "Unknown size"
    units = ["B", "KB", "MB", "GB", "TB"]
    val = float(bytes_num)
    i = 0
    while val >= 1024.0 and i < len(units) - 1:
        val /= 1024.0
        i += 1
    return f"{val:.1f} {units[i]}"

def format_duration(seconds):
    if seconds is None or seconds < 0:
        return "--"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m = s // 60
    s %= 60
    if m < 60:
        return f"{m}m {s:02d}s"
    h = m // 60
    m %= 60
    return f"{h}h {m:02d}m"

def sanitize_filename(name):
    if not name:
        return None
    name = html.unescape(name)
    invalid_chars = r'[\\/*?:"<>|]'
    name = re.sub(invalid_chars, "_", name)
    name = name.strip(" .\t\r\n")
    return name if name else None

def parse_content_disposition(header):
    if not header:
        return None
    # 1. Try filename*=UTF-8''... (RFC 5987 / RFC 6266)
    m_star = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')?([^;\r\n]+)", header, re.IGNORECASE)
    if m_star:
        val = m_star.group(1).strip("\"' ")
        try:
            val = urllib.parse.unquote(val)
        except Exception:
            pass
        clean = sanitize_filename(val)
        if clean:
            return clean

    # 2. Try filename="..." or filename=...
    m_plain = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;\r\n]+))', header, re.IGNORECASE)
    if m_plain:
        val = m_plain.group(1) or m_plain.group(2)
        val = val.strip("\"' ")
        try:
            val = urllib.parse.unquote(val)
        except Exception:
            pass
        clean = sanitize_filename(val)
        if clean:
            return clean
    return None

def resolve_url_info(url):
    """
    Actively inspects the download URL, following redirects and extracting the
    real file name and file size before or during download.
    """
    resolved_name = None
    total_bytes = -1
    accepts_ranges = False

    # 1. First probe via HEAD request with full redirect following
    try:
        r = requests.head(url, headers=DEFAULT_HEADERS, allow_redirects=True, timeout=8)
        if r.status_code < 400:
            resolved_name = parse_content_disposition(r.headers.get("Content-Disposition", ""))
            if not resolved_name:
                final_path = urllib.parse.urlparse(r.url).path
                base = os.path.basename(final_path)
                if "." in base and not base.endswith(".php") and not base.endswith(".html"):
                    resolved_name = sanitize_filename(urllib.parse.unquote(base))

            cl = r.headers.get("Content-Length")
            if cl and cl.isdigit():
                total_bytes = int(cl)
            accepts_ranges = "bytes" in r.headers.get("Accept-Ranges", "").lower()
    except Exception:
        pass

    # 2. If HEAD failed or gave no disposition/name, probe via GET Range 0-0
    if not resolved_name or total_bytes <= 0:
        try:
            probe_headers = {**DEFAULT_HEADERS, "Range": "bytes=0-0"}
            with requests.get(url, headers=probe_headers, stream=True, allow_redirects=True, timeout=8) as r:
                cd = r.headers.get("Content-Disposition", "")
                if cd:
                    parsed = parse_content_disposition(cd)
                    if parsed:
                        resolved_name = parsed

                if not resolved_name:
                    final_path = urllib.parse.urlparse(r.url).path
                    base = os.path.basename(final_path)
                    if "." in base and not base.endswith(".php") and not base.endswith(".html"):
                        resolved_name = sanitize_filename(urllib.parse.unquote(base))

                if "Content-Range" in r.headers:
                    cr = r.headers["Content-Range"]
                    if "/" in cr:
                        tot = cr.split("/")[1]
                        if tot.isdigit():
                            total_bytes = int(tot)
                            accepts_ranges = True
                elif total_bytes <= 0:
                    cl = r.headers.get("Content-Length")
                    if cl and cl.isdigit():
                        total_bytes = int(cl)

                # Check Content-Type extension fallback if no dot in name
                ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if resolved_name and "." not in resolved_name:
                    ext = MIME_TO_EXT.get(ctype)
                    if ext:
                        resolved_name += ext
        except Exception:
            pass

    # 3. Last fallback: parse URL path
    if not resolved_name:
        raw_last = urllib.parse.urlparse(url).path.split("/")[-1]
        raw_last = urllib.parse.unquote(raw_last).split("?")[0]
        resolved_name = sanitize_filename(raw_last) or f"download_{int(time.time())}.bin"

    return resolved_name, total_bytes, accepts_ranges


class DownloadTask:
    def __init__(self, item, on_progress=None, on_complete=None, on_error=None, on_name_resolved=None):
        self.item = item
        self.id = item["id"]
        self.url = item["url"]
        self.file_name = item["file_name"]
        self.folder = item["folder"]
        self.connections = item.get("connections", 8)
        self.total_bytes = item.get("total_bytes", -1)
        self.downloaded_bytes = item.get("downloaded_bytes", 0)

        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.on_name_resolved = on_name_resolved

        self.is_paused = threading.Event()
        self.is_canceled = threading.Event()
        self.worker_thread = None
        self._part_files = []

    def start(self):
        self.is_paused.clear()
        self.is_canceled.clear()
        self.worker_thread = threading.Thread(target=self._run, daemon=True)
        self.worker_thread.start()

    def pause(self):
        self.is_paused.set()

    def cancel(self):
        self.is_canceled.set()

    def _run(self):
        try:
            real_name, total, accepts_ranges = resolve_url_info(self.url)
            if real_name and real_name != self.file_name:
                self.file_name = real_name
                self.item["file_name"] = real_name
                if self.on_name_resolved:
                    self.on_name_resolved(self.id, real_name)

            if total > 0:
                self.total_bytes = total
                self.item["total_bytes"] = total

            os.makedirs(self.folder, exist_ok=True)
            target_path = os.path.join(self.folder, self.file_name)

            if accepts_ranges and total > 0 and self.connections > 1:
                self._download_multithreaded(target_path, total)
            else:
                self._download_single(target_path)

            if not self.is_paused.is_set() and not self.is_canceled.is_set():
                if self.on_complete:
                    self.on_complete(self.id)
        except Exception as e:
            if not self.is_paused.is_set() and not self.is_canceled.is_set():
                if self.on_error:
                    self.on_error(self.id, str(e))

    def _download_single(self, target_path):
        headers = {**DEFAULT_HEADERS}
        temp_file = target_path + ".f2l.part"
        resume_pos = 0
        if os.path.exists(temp_file):
            resume_pos = os.path.getsize(temp_file)
            if resume_pos > 0:
                headers["Range"] = f"bytes={resume_pos}-"

        mode = "ab" if resume_pos > 0 else "wb"
        with requests.get(self.url, headers=headers, stream=True, allow_redirects=True, timeout=15) as r:
            r.raise_for_status()

            # Check if disposition was sent on the GET stream response
            cd = r.headers.get("Content-Disposition", "")
            if cd:
                real_name = parse_content_disposition(cd)
                if real_name and real_name != self.file_name:
                    self.file_name = real_name
                    self.item["file_name"] = real_name
                    target_path = os.path.join(self.folder, self.file_name)
                    if self.on_name_resolved:
                        self.on_name_resolved(self.id, real_name)

            downloaded = resume_pos
            last_time = time.time()
            last_downloaded = downloaded

            with open(temp_file, mode) as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if self.is_canceled.is_set():
                        f.close()
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                        return
                    if self.is_paused.is_set():
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        dt = now - last_time
                        if dt >= 0.5:
                            speed = int((downloaded - last_downloaded) / dt)
                            eta = int((self.total_bytes - downloaded) / speed) if speed > 0 and self.total_bytes > downloaded else -1
                            last_time = now
                            last_downloaded = downloaded
                            self.downloaded_bytes = downloaded
                            if self.on_progress:
                                self.on_progress(self.id, downloaded, self.total_bytes, speed, eta)

        # Download complete
        if os.path.exists(target_path):
            try: os.remove(target_path)
            except: pass
        os.rename(temp_file, target_path)
        self.downloaded_bytes = self.total_bytes if self.total_bytes > 0 else downloaded
        if self.on_progress:
            self.on_progress(self.id, self.downloaded_bytes, self.total_bytes, 0, 0)

    def _download_multithreaded(self, target_path, total):
        num_parts = self.connections
        part_size = total // num_parts
        ranges = []
        for i in range(num_parts):
            start = i * part_size
            end = total - 1 if i == num_parts - 1 else (i + 1) * part_size - 1
            ranges.append((start, end))

        self._part_files = [f"{target_path}.f2l.part{i}" for i in range(num_parts)]
        part_progress = [0] * num_parts

        for i, pf in enumerate(self._part_files):
            if os.path.exists(pf):
                part_progress[i] = os.path.getsize(pf)

        lock = threading.Lock()
        last_time = [time.time()]
        last_total = [sum(part_progress)]

        def worker(part_idx):
            start, end = ranges[part_idx]
            current_done = part_progress[part_idx]
            curr_start = start + current_done
            if curr_start > end:
                return

            pf = self._part_files[part_idx]
            headers = {
                **DEFAULT_HEADERS,
                "Range": f"bytes={curr_start}-{end}"
            }

            mode = "ab" if current_done > 0 else "wb"
            with requests.get(self.url, headers=headers, stream=True, allow_redirects=True, timeout=15) as r:
                r.raise_for_status()
                with open(pf, mode) as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if self.is_canceled.is_set() or self.is_paused.is_set():
                            return
                        if chunk:
                            f.write(chunk)
                            with lock:
                                part_progress[part_idx] += len(chunk)
                                cur_total = sum(part_progress)
                                now = time.time()
                                dt = now - last_time[0]
                                if dt >= 0.5:
                                    speed = int((cur_total - last_total[0]) / dt)
                                    eta = int((total - cur_total) / speed) if speed > 0 and total > cur_total else -1
                                    last_time[0] = now
                                    last_total[0] = cur_total
                                    self.downloaded_bytes = cur_total
                                    if self.on_progress:
                                        self.on_progress(self.id, cur_total, total, speed, eta)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_parts) as executor:
            futures = [executor.submit(worker, i) for i in range(num_parts)]
            concurrent.futures.wait(futures)

        if self.is_canceled.is_set():
            for pf in self._part_files:
                if os.path.exists(pf):
                    try: os.remove(pf)
                    except: pass
            return

        if self.is_paused.is_set():
            return

        all_done = sum(part_progress) >= total
        if all_done:
            with open(target_path, "wb") as outfile:
                for pf in self._part_files:
                    if os.path.exists(pf):
                        with open(pf, "rb") as infile:
                            while True:
                                data = infile.read(CHUNK_SIZE)
                                if not data:
                                    break
                                outfile.write(data)
                        try: os.remove(pf)
                        except: pass
            self.downloaded_bytes = total
            if self.on_progress:
                self.on_progress(self.id, total, total, 0, 0)
        else:
            raise Exception("Incomplete download segments")


class DownloadEngine:
    def __init__(self):
        self.tasks = {}

    def start(self, item, on_progress=None, on_complete=None, on_error=None, on_name_resolved=None):
        task_id = item["id"]
        if task_id in self.tasks:
            self.tasks[task_id].cancel()
        task = DownloadTask(item, on_progress, on_complete, on_error, on_name_resolved)
        self.tasks[task_id] = task
        task.start()
        return task

    def pause(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id].pause()

    def cancel(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id].cancel()
            del self.tasks[task_id]
