"""Модуль поиска дубликатов через хэширование."""
import hashlib
from pathlib import Path


CHUNK_SIZE = 64 * 1024  # 64 КБ


def compute_hash(path: Path, algorithm: str = "md5") -> str | None:
    """Считает хэш файла. Возвращает None при ошибке доступа."""
    try:
        h = hashlib.new(algorithm)
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def find_duplicates(files: list[Path], progress_callback=None) -> dict[str, list[Path]]:
    """
    Находит дубликаты.

    Алгоритм оптимизации:
    1. Группируем файлы по размеру (файлы разного размера — не дубли).
    2. Хэшируем только файлы с одинаковым размером.
    3. Группируем по хэшу — группы больше 1 — это дубликаты.

    :return: словарь {хэш: [список путей]}
    """
    # Шаг 1: группировка по размеру
    by_size: dict[int, list[Path]] = {}
    for f in files:
        try:
            size = f.stat().st_size
        except (OSError, PermissionError):
            continue
        if size == 0:  # пустые файлы не считаем дублями
            continue
        by_size.setdefault(size, []).append(f)

    # Шаг 2: хэшируем только кандидатов (размер > 1 файла)
    candidates = [f for group in by_size.values() if len(group) > 1 for f in group]
    total = len(candidates)

    by_hash: dict[str, list[Path]] = {}
    for i, f in enumerate(candidates, 1):
        h = compute_hash(f)
        if h:
            by_hash.setdefault(h, []).append(f)
        if progress_callback:
            progress_callback(i, total)

    # Шаг 3: оставляем только настоящие дубли
    return {h: paths for h, paths in by_hash.items() if len(paths) > 1}