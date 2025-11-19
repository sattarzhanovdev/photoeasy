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


def add_watermark_to_bytes(data: bytes, text: str = "photoeasy") -> bytes:
    """
    Создаёт копию изображения с водяным знаком «PHOTOEASY» сеткой по диагонали.
    - Сжимает изображение по ширине до 1000 px, если оно больше.
    - Область лица вырезается КРУГОМ из слоя с водяным знаком.
    Возвращает bytes JPEG.
    """
    # 1. Загружаем и нормализуем изображение
    img = _load_image_safely(data)
    width, height = img.size

    # 2. Сжатие до ширины 1000 px (если нужно)
    max_width = 1000
    if width > max_width:
        ratio = max_width / float(width)
        new_height = int(height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)
        width, height = img.size

    # 3. Подготовка шрифта
    draw_dummy = ImageDraw.Draw(img)
    font = None
    try:
        font_path = getattr(settings, "WATERMARK_FONT_PATH", None)
        if font_path:
            font = ImageFont.truetype(
                font_path,
                size=int(min(width, height) * 0.06),  # размер от размеров фото
            )
    except Exception:
        font = None

    if font is None:
        font = ImageFont.load_default()

    watermark_text = "PHOTOEASY"

    # Размер текста
    bbox = draw_dummy.textbbox((0, 0), watermark_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # 4. Большой квадратный слой (чтобы при повороте не было дыр)
    diag = int(math.hypot(width, height))
    overlay_size = diag + max(width, height)
    overlay = Image.new("RGBA", (overlay_size, overlay_size), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Шаги по сетке
    step_x = int(text_width * 3)
    step_y = int(text_height * 3)

    alpha = 160  # прозрачность (0-255)
    fill = (255, 255, 255, alpha)

    # 5. Заполняем текстом по всей площади overlay
    for y in range(0, overlay_size, step_y):
        for x in range(0, overlay_size, step_x):
            overlay_draw.text((x, y), watermark_text, font=font, fill=fill)

    # 6. Поворачиваем слой с текстом для диагонального эффекта
    rotated = overlay.rotate(-30, expand=True)
    rw, rh = rotated.size

    # Вырезаем центр под размер исходного изображения
    left = (rw - width) // 2
    top = (rh - height) // 2
    rotated = rotated.crop((left, top, left + width, top + height))

    # 7. Находим лицо и вырезаем *круг* из слоя водяного знака
    face_boxes = []
    try:
        _ensure_face_libs_loaded()
        arr = np.array(img, dtype=np.uint8)
        arr = np.ascontiguousarray(arr)
        locations = face_recognition.face_locations(
            arr,
            number_of_times_to_upsample=1,
            model="hog",
        )
        for (top_f, right_f, bottom_f, left_f) in locations:
            margin = int((bottom_f - top_f) * 0.25)
            lx = max(left_f - margin, 0)
            ty = max(top_f - margin, 0)
            rx = min(right_f + margin, width)
            by = min(bottom_f + margin, height)
            face_boxes.append((lx, ty, rx, by))
    except Exception:
        face_boxes = []

    if face_boxes:
        cut_draw = ImageDraw.Draw(rotated)
        for (lx, ty, rx, by) in face_boxes:
            # вместо прямоугольника — круг (эллипс в bounding box)
            cut_draw.ellipse((lx, ty, rx, by), fill=(0, 0, 0, 0))

    # 8. Склеиваем исходное изображение и водяной знак
    img_rgba = img.convert("RGBA")
    watermarked = Image.alpha_composite(img_rgba, rotated)

    # 9. Сохраняем в JPEG и возвращаем
    buf = io.BytesIO()
    watermarked.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()
