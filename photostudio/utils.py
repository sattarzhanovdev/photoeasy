import io
from typing import Optional, List, Tuple, Dict

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
import face_recognition


def _load_image_safely(file_bytes: bytes) -> np.ndarray:
    """
    Загружает картинку и ПЕРЕКОДИРУЕТ её в нормальный 8-bit JPEG RGB,
    чтобы избежать ошибок dlib/PIL.
    """
    img = Image.open(io.BytesIO(file_bytes))

    # Учитываем EXIF-ориентацию (айфоны и т.п.)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Приводим к RGB и 8-битам
    img = img.convert("RGB")

    # Перекодируем в JPEG в памяти (гарантированно 8-bit RGB)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    buf.seek(0)

    img2 = Image.open(buf).convert("RGB")
    arr = np.array(img2, dtype=np.uint8)
    arr = np.ascontiguousarray(arr)
    return arr


def _extract_encoding_with_info(arr: np.ndarray) -> Tuple[Optional[List[float]], Dict]:
    """
    Пытаемся найти лицо, возвращаем (encoding | None, debug_info).
    """
    h, w = arr.shape[:2]
    info: Dict = {"width": w, "height": h, "faces": 0}

    try:
        locations = face_recognition.face_locations(
            arr,
            number_of_times_to_upsample=2,
            model="hog",
        )
        info["faces"] = len(locations)

        if not locations:
            return None, info

        encodings = face_recognition.face_encodings(
            arr,
            known_face_locations=locations,
            num_jitters=1,
            model="small",
        )
        if not encodings:
            return None, info

        return encodings[0].tolist(), info
    except Exception as e:
        info["error"] = str(e)
        return None, info


def extract_face_encoding_and_info_from_bytes(data: bytes) -> Tuple[Optional[List[float]], Dict]:
    """
    bytes -> (encoding | None, debug_info).
    Без падений, даже если файл не картинка.
    """
    try:
        arr = _load_image_safely(data)
    except UnidentifiedImageError as e:
        # Вообще не получилось распознать как картинку
        return None, {
            "width": None,
            "height": None,
            "faces": 0,
            "error": str(e),
        }

    return _extract_encoding_with_info(arr)


def extract_face_encoding_and_info_from_file(file) -> Tuple[Optional[List[float]], Dict]:
    data = file.read()
    return extract_face_encoding_and_info_from_bytes(data)


def extract_face_encoding_from_file(file) -> Optional[List[float]]:
    """
    Обёртка для использования в админке/серилайзерах.
    Любая ошибка -> None, чтобы не ронять процесс.
    """
    try:
        enc, _ = extract_face_encoding_and_info_from_file(file)
        return enc
    except Exception:
        return None


def face_distance(enc1: List[float], enc2: List[float]) -> float:
    a = np.array(enc1)
    b = np.array(enc2)
    return float(np.linalg.norm(a - b))
