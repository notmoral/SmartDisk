"""Графический интерфейс SmartDisk."""
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.scanner import scan_directory
from core.hasher import find_duplicates


class SmartDiskApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SmartDisk — интеллектуальный организатор файлов")
        self.geometry("900x600")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.selected_folder = None

        self._build_ui()

    def _build_ui(self):
        # Верхняя панель
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=10)

        self.folder_label = ctk.CTkLabel(
            top, text="Папка не выбрана", anchor="w"
        )
        self.folder_label.pack(side="left", fill="x", expand=True, padx=10)

        ctk.CTkButton(
            top, text="Выбрать папку", command=self.choose_folder, width=140
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            top, text="Найти дубликаты", command=self.start_scan, width=160
        ).pack(side="left", padx=5)

        # Прогресс-бар
        self.progress = ctk.CTkProgressBar(self)
        self.progress.pack(fill="x", padx=10, pady=5)
        self.progress.set(0)

        # Статус
        self.status_label = ctk.CTkLabel(self, text="Готов к работе", anchor="w")
        self.status_label.pack(fill="x", padx=10)

        # Список результатов
        self.results_box = ctk.CTkTextbox(self, wrap="none")
        self.results_box.pack(fill="both", expand=True, padx=10, pady=10)

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку для анализа")
        if folder:
            self.selected_folder = folder
            self.folder_label.configure(text=folder)

    def start_scan(self):
        if not self.selected_folder:
            messagebox.showwarning("SmartDisk", "Сначала выберите папку")
            return

        self.results_box.delete("1.0", "end")
        self.progress.set(0)
        self.status_label.configure(text="Сканирование...")

        threading.Thread(target=self._run_scan, daemon=True).start()

    def _run_scan(self):
        try:
            files = scan_directory(self.selected_folder)
            self._update_status(f"Найдено файлов: {len(files)}. Хэширование...")

            def progress_cb(cur, total):
                if total:
                    self._set_progress(cur / total)

            duplicates = find_duplicates(files, progress_callback=progress_cb)
            self._show_results(duplicates)
        except Exception as e:
            self._update_status(f"Ошибка: {e}")
        finally:
            self._set_progress(1.0)

    def _show_results(self, duplicates: dict):
        if not duplicates:
            self._update_status("Дубликатов не найдено ✅")
            self.results_box.insert("end", "Дубликаты не найдены.\n")
            return

        total_groups = len(duplicates)
        total_files = sum(len(p) for p in duplicates.values())
        wasted = 0

        self.results_box.insert(
            "end", f"Найдено групп дубликатов: {total_groups}\n"
                   f"Всего файлов-дублей: {total_files}\n\n"
        )

        for i, (h, paths) in enumerate(duplicates.items(), 1):
            size = paths[0].stat().st_size
            wasted += size * (len(paths) - 1)
            self.results_box.insert("end", f"--- Группа {i} ({size} байт, {len(paths)} шт.) ---\n")
            for p in paths:
                self.results_box.insert("end", f"  {p}\n")
            self.results_box.insert("end", "\n")

        self.results_box.insert("end", f"Можно освободить: {wasted / 1024 / 1024:.2f} МБ\n")
        self._update_status(f"Готово. Групп: {total_groups}, файлов: {total_files}")

    def _update_status(self, text):
        self.status_label.configure(text=text)

    def _set_progress(self, value):
        self.progress.set(value)