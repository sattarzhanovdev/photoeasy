import io
import math
from typing import Optional, List

from PIL import (
    Image,
    ImageOps,
    ImageDraw,
    ImageFont,
    UnidentifiedImageError,
)
from django.conf import settings

# Ленивая инициализация – сначала None,
# позже загрузим внутри функции.
np = None
face_recognition = None


def _load_image_safely(file_bytes: bytes) -> Image.Image:
    """
    Приводим картинку к нормальному RGB и учитываем EXIF-поворот.
    """
    img = Image.open(io.BytesIO(file_bytes))

    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    img = img.convert("RGB")
    return img


def _ensure_face_libs_loaded():
    """
    Ленивая загрузка numpy и face_recognition.
    Вызывается только в момент реального распознавания лица.
    """
    global np, face_recognition

    if np is not None and face_recognition is not None:
        return

    try:
        import numpy as _np
        import face_recognition as _fr
    except BaseException:
        # BaseException, чтобы словить даже sys.exit() внутри face_recognition
        raise RuntimeError(
            "Библиотеки 'face_recognition', 'face_recognition_models' и 'numpy' "
            "обязательны для работы распознавания по лицу. "
            "Установи их в виртуальное окружение."
        )

    np = _np
    face_recognition = _fr


def extract_face_encoding_from_file(file) -> Optional[List[float]]:
    """
    Основная функция распознавания:

    - Если нет нужных библиотек -> RuntimeError (так как это обязательный функционал).
    - Если лицо не найдено или файл битый -> возвращаем None.
    """
    # Ленивая загрузка библиотек
    _ensure_face_libs_loaded()

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

        encodings = face_recognition.face_encodings(arr, known_face_locations=locations)
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
    global np

    if np is None:
        try:
            import numpy as _np
            np = _np
        except BaseException:
            np = None

    if np is not None:
        a = np.array(enc1)
        b = np.array(enc2)
        return float(np.linalg.norm(a - b))

    # Fallback без numpy
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(enc1, enc2)))


def add_watermark_to_bytes(data: bytes, text: str = "WATERMARK") -> bytes:
    """
    Создаёт копию изображения с текстовым водяным знаком.
    Возвращает bytes JPEG.
    """
    img = _load_image_safely(data)
    width, height = img.size

    draw = ImageDraw.Draw(img)

    # Шрифт
    font = None
    try:
        font_path = getattr(settings, "WATERMARK_FONT_PATH", None)
        if font_path:
            font = ImageFont.truetype(
                font_path,
                size=int(min(width, height) * 0.05),
            )
    except Exception:
        pass

    if font is None:
        font = ImageFont.load_default()

    watermark_text = text or "WATERMARK"

    # ------ ВАЖНО: новая версия Pillow ------
    # textbbox = (x0, y0, x1, y1)
    bbox = draw.textbbox((0, 0), watermark_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    # ----------------------------------------

    # Правый нижний угол
    x = width - text_width - 20
    y = height - text_height - 20

    fill = (255, 255, 255)

    draw.text((x, y), watermark_text, font=font, fill=fill)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
