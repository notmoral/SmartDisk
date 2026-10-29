import webview
import json
import threading
import os
import smartdisk_core
from core.scanner import find_empty_folders, get_all_drives, find_large_files_py

class Api:
    def __init__(self):
        self._window = None
        self.is_maximized = False

    def set_window(self, window):
        self._window = window

    def choose_folder(self):
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result and len(result) > 0 else None

    def delete_file(self, path):
        try:
            if os.path.exists(path):
                os.remove(path)
                return {"status": "success"}
            return {"status": "error", "message": "Файл не найден"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_folder(self, path):
        try:
            if os.path.exists(path) and os.path.isdir(path):
                os.rmdir(path)
                return {"status": "success"}
            return {"status": "error", "message": "Папка не пуста"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def open_folder(self, path):
        try:
            target = path if os.path.isdir(path) else os.path.dirname(path)
            os.startfile(target)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def minimize(self):
        self._window.minimize()

    def toggle_maximize(self):
        if self.is_maximized:
            self._window.restore()
            self.is_maximized = False
        else:
            self._window.maximize()
            self.is_maximized = True

    def close(self):
        self._window.destroy()

    def start_scan(self, path):
        if not path:
            return {"error": "Путь не выбран"}

        def scan_task():
            try:
                targets = get_all_drives() if path == "PC" else [path]
                target_str = targets[0] if not path == "PC" else "C:\\"
                
                def rust_progress_cb(progress, text):
                    self._send_to_js({"type": "progress", "progress": progress, "current_file": text})

                self._send_to_js({"type": "status", "text": "Запуск сканера...", "progress": 0.01})
                
                res = smartdisk_core.scan_and_find_duplicates(target_str, rust_progress_cb)
                
                self._send_to_js({"type": "status", "text": "Поиск пустых папок...", "progress": 0.97})
                empty_folders = find_empty_folders(targets)

                total_files = res["total_files"]
                raw_duplicates = res["duplicates"]
                stats_ext = res["stats_ext"]
                
                total_groups = len(raw_duplicates)
                wasted = 0
                dups_data = []
                
                for group in raw_duplicates:
                    if not group: continue
                    group_size = group[0]["size_bytes"]
                    wasted += group_size * (len(group) - 1)
                    
                    if len(dups_data) < 200:
                        display_files = group[:10] 
                        
                        dups_data.append({
                            "size_bytes": group_size,
                            "size_str": f"{group_size / 1024:.1f} КБ",
                            "ext": os.path.splitext(group[0]["path"])[1].lower().replace('.', '') or "нет",
                            "count": len(group),
                            "files": display_files,
                            "hidden_count": len(group) - len(display_files) # Сколько файлов скрыто
                        })

                large_files = find_large_files_py([f["path"] for g in raw_duplicates for f in g])

                self._send_to_js({
                    "status": "success",
                    "total_files": total_files,
                    "total_groups": total_groups,
                    "wasted_mb": round(wasted / (1024 * 1024), 2),
                    "stats_ext": stats_ext, 
                    "duplicates": dups_data,
                    "large_files": large_files,
                    "empty_folders": empty_folders[:200]
                })
                self._send_to_js({"type": "status", "text": "Готово", "progress": 1.0})

            except Exception as e:
                self._send_to_js({"status": "error", "message": str(e)})

        threading.Thread(target=scan_task, daemon=True).start()
        return {"status": "started"}

    def _send_to_js(self, data):
        if self._window:
            self._window.evaluate_js(f"window.updateUI({json.dumps(data)})")

if __name__ == '__main__':
    api = Api()
    window = webview.create_window(
        'SmartDisk', 
        'ui/index.html', 
        js_api=api, 
        width=1280, 
        height=850, 
        background_color='#e4e4e7',
        frameless=True,
        easy_drag=True
    )
    api.set_window(window)
    webview.start()