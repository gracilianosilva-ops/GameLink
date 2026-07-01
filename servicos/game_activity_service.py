import psutil
import threading
import time


class GameActivityService:
    def __init__(self, polling_interval: float = 2.0, installed_fallback: bool = False):
        self.polling_interval = polling_interval
        self.installed_fallback = installed_fallback
        self._thread = None
        self._stop_event = threading.Event()
        self._last_result = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._last_result = self.detect_activity([])
            except Exception:
                self._last_result = None
            self._stop_event.wait(self.polling_interval)

    def detect_activity(self, jogos):
        index = self._build_process_index(jogos)
        return self._detect_active_process(index)

    def _build_process_index(self, jogos):
        index = {}
        for j in jogos:
            if getattr(j, 'executavel', None):
                index[j.executavel.lower()] = j
            title_key = ''.join(e for e in j.titulo.lower() if e.isalnum())
            if title_key:
                index[title_key] = j
                # also add a variant without common leading articles (e.g., 'the')
                for prefix in ('the', 'a', 'an'):
                    if title_key.startswith(prefix) and len(title_key) > len(prefix):
                        stripped = title_key[len(prefix):]
                        index[stripped] = j
        return index

    def _detect_active_process(self, index):
        for proc in psutil.process_iter(['name', 'exe', 'pid', 'cmdline']):
            try:
                name = proc.info.get('name', '') or ''
                exe = proc.info.get('exe', '') or ''
                key = (name or exe).lower()
                key = ''.join(e for e in key if e.isalnum() or e in ['.', '\\', '/'])
                if key in index:
                    return {'status': 'ingame', 'jogo': index[key].titulo}
            except Exception:
                continue

        launcher_names = {
            'steam': 'Steam',
            'epicgameslauncher': 'Epic Games',
            'origin': 'Origin',
            'uplay': 'Uplay'
        }
        for proc in psutil.process_iter(['name']):
            try:
                name = (proc.info.get('name') or '').lower()
                for k, v in launcher_names.items():
                    if k in name:
                        return {'status': 'launcher', 'launcher': v}
            except Exception:
                continue

        return None
