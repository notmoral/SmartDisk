"""Модуль сканирования файловой системы."""
import os
from pathlib import Path


def scan_directory(root_path: str, progress_callback=None) -> list[Path]:
    """
    Рекурсивно обходит папку и возвращает список всех файлов.

    :param root_path: путь к папке для сканирования
    :param progress_callback: функция(текущий, всего) для обновления прогресса
    :return: список объектов Path
    """
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Папка не существует: {root_path}")

    files = []
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            files.append(Path(dirpath) / name)

    if progress_callback:
        progress_callback(len(files), len(files))

    return files


def get_file_size(path: Path) -> int:
    """Возвращает размер файла в байтах, 0 если недоступен."""
    try:
        return path.stat().st_size
    except (OSError, PermissionError):
        return 0