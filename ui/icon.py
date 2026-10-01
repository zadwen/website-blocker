"""zadwen monogram icon, generated with Pillow (optional dependency)."""
from core.branding import COLORS as C
from ui.widgets import lerp


def make_image(size=256):
    from PIL import Image, ImageDraw
    grad = Image.new("RGBA", (size, size))
    px = grad.load()
    for y in range(size):
        for x in range(size):
            col = lerp(C["accent"], C["accent2"], (x + y) / (2 * size))
            px[x, y] = tuple(int(col[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 4, fill=255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    m, t = size * 0.27, max(size // 10, 2)
    top, bot = size * 0.28, size * 0.72
    d.line([(m, top), (size - m, top), (m, bot), (size - m, bot)], fill="white", width=t, joint="curve")
    return img
