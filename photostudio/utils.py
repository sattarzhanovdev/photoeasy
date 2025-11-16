import io
import math
from typing import Optional, List

from PIL import Image, ImageOps, UnidentifiedImageError

# Пытаемся подтянуть numpy и face_recognition, но НЕ падаем, если их нет/они кривые
try:
    import numpy as np
except Exception:
    np = None

try:
    import face_recognition
except Exception:
    face_recognition = None


def _load_image_safely(file_bytes: bytes):
    """
    Пробуем привести картинку к нормальному RGB.
    Если нет Pillow/face_recognition/numpy или файл битый – кидаем понятное исключение.
    """
    img = Image.open(io.BytesIO(file_bytes))

    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    img = img.convert("RGB")
    return img


def extract_face_encoding_from_file(file) -> Optional[List[float]]:
    """
    Основная функция, которую дергает твой код.
    Если нет face_recognition / numpy или что-то ломается – возвращаем None.
    """
    # если на сервере не установлен face_recognition или numpy – просто выходим
    if face_recognition is None or np is None:
        return None

    try:
        data = file.read()
        img = _load_image_safely(data)

        # конвертируем в numpy-массив
        arr = np.array(img, dtype=np.uint8)
        arr = np.ascontiguousarray(arr)

        # ищем лицо
        locations = face_recognition.face_locations(
            arr,
            number_of_times_to_upsample=1,
            model="hog",
        )
        if not locations:
            return None

        encodings = face_recognition.face_encodings(
            arr,
            known_face_locations=locations,
            num_jitters=1,
            model="small",
        )
        if not encodings:
            return None

        return encodings[0].tolist()
    except UnidentifiedImageError:
        # не удалось распознать файл как изображение
        return None
    except Exception:
        # любая другая ошибка – не роняем проект, просто нет encoding
        return None


def face_distance(enc1: List[float], enc2: List[float]) -> float:
    """
    Евклидово расстояние между двумя embedding'ами.
    Работает даже без numpy (чистый Python).
    """
    if np is not None:
        a = np.array(enc1)
        b = np.array(enc2)
        return float(np.linalg.norm(a - b))

    # Fallback без numpy
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(enc1, enc2)))
