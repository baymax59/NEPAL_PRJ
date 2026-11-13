"""A person's profile photo: what is accepted, and what is stored.

Whatever is sent is decoded and drawn again as a small square JPEG, so nothing the sender put into the file survives: not camera or location
tags (EXIF), not a second file hidden after the picture, not a script in an SVG. Only JPEG, PNG and WebP pictures are accepted.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # what a person may send
MAX_PIXELS = 24_000_000  # a picture of 6000 x 4000 is fine; a tiny file that unpacks into a gigantic one is not
SIDE = 256  # the stored picture is SIDE x SIDE
ALLOWED = {"JPEG", "PNG", "WEBP"}
CONTENT_TYPE = "image/jpeg"


def version(moment) -> int | None:
    """A number that changes whenever the photo does (None: no photo). The screens use it to fetch a new picture only when there is one."""
    return int(moment.timestamp()) if moment else None


class BadPhoto(ValueError):
    """The picture is refused; the message says why, in words the person can act on."""


def prepare_photo(raw: bytes) -> bytes:
    """The picture to store, from the bytes that were sent. Raises BadPhoto."""
    if not raw:
        raise BadPhoto("The file is empty")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise BadPhoto(f"The picture is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB: choose a smaller one")
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in ALLOWED:
            raise BadPhoto("Use a JPEG, PNG or WebP picture")
        if image.width * image.height > MAX_PIXELS:
            raise BadPhoto("The picture has too many pixels: choose a smaller one")
        image.load()  # decodes the whole picture: a damaged or disguised file fails here
    except BadPhoto:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise BadPhoto("This file is not a picture that can be read: use a JPEG, PNG or WebP picture") from None
    image = ImageOps.exif_transpose(image)  # a phone photo taken sideways is turned the right way up
    if image.mode in ("RGBA", "LA", "P"):  # transparent parts become white
        image = image.convert("RGBA")
        flat = Image.new("RGB", image.size, "white")
        flat.paste(image, mask=image.getchannel("A"))
        image = flat
    else:
        image = image.convert("RGB")
    image = ImageOps.fit(image, (SIDE, SIDE), method=Image.Resampling.LANCZOS)  # a square from the middle
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85, optimize=True)  # a new file: no metadata is carried over
    return out.getvalue()
