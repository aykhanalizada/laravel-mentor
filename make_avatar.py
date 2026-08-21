"""Laravel Mentor bot avatarı yaradır."""
from PIL import Image, ImageDraw, ImageFont
import math

SIZE = 512
img = Image.new("RGB", (SIZE, SIZE))
draw = ImageDraw.Draw(img)

cx, cy = SIZE // 2, SIZE // 2

# ── Arxa fon: diagonal gradient (tünd göy → tünd bənövşəyi) ──────────────────
pixels = img.load()
for y in range(SIZE):
    for x in range(SIZE):
        t = (x + y) / (SIZE * 2)
        r = int(10  + t * 25)
        g = int(8   + t * 10)
        b = int(40  + t * 60)
        pixels[x, y] = (r, g, b)

# ── Altıbucaqlı panel (hex badge) ─────────────────────────────────────────────
def hex_points(cx, cy, r):
    pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return pts

# Kölgə qatı
draw.polygon(hex_points(cx+5, cy+5, 210), fill=(0, 0, 0, 80))
# Xarici haşiyə — parlaq narıncı-qırmızı
draw.polygon(hex_points(cx, cy, 218), fill=(220, 50, 50))
# Daxili gradient panel — tünd
draw.polygon(hex_points(cx, cy, 200), fill=(28, 14, 50))
# İkinci daxili haşiyə
draw.polygon(hex_points(cx, cy, 195), outline=(180, 60, 220), width=3)

# ── Parıltı — yuxarı sol küncdə ───────────────────────────────────────────────
for r in range(120, 0, -4):
    alpha = int(18 * (1 - r/120))
    c = (255, 180, 80, alpha)
    tmp = Image.new("RGBA", (SIZE, SIZE), (0,0,0,0))
    ImageDraw.Draw(tmp).ellipse([cx-180-r, cy-200-r, cx-180+r, cy-200+r], fill=c)
    img = Image.alpha_composite(img.convert("RGBA"), tmp).convert("RGB")
    draw = ImageDraw.Draw(img)

# ── Şriftlər ──────────────────────────────────────────────────────────────────
def try_font(size):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

font_l    = try_font(195)
font_code = try_font(68)
font_sub  = try_font(44)

# ── "<L>" kod dizaynı ─────────────────────────────────────────────────────────
# Soldakı "<" — solğun bənövşəyi
draw.text((cx - 68, cy - 70), "<", font=font_l, fill=(130, 60, 190), anchor="mm")
# Sağdakı ">" — solğun bənövşəyi
draw.text((cx + 68, cy - 70), ">", font=font_l, fill=(130, 60, 190), anchor="mm")

# Mərkəzdə "L" — ağ, kölgəli
draw.text((cx + 3, cy - 67), "L", font=font_l, fill=(60, 20, 90), anchor="mm")  # kölgə
draw.text((cx, cy - 70), "L",     font=font_l, fill=(255, 255, 255), anchor="mm")

# Alt bölmə ayırıcı xətt
lw = 160
draw.line([(cx - lw, cy + 80), (cx + lw, cy + 80)], fill=(180, 60, 220), width=2)

# "LARAVEL" yazısı
draw.text((cx, cy + 108), "LARAVEL", font=font_sub, fill=(200, 140, 255), anchor="mm")
# "MENTOR" yazısı — daha kiçik, solğun
draw.text((cx, cy + 154), "M E N T O R", font=try_font(30), fill=(120, 80, 170), anchor="mm")

# ── Künc dekorları (hex nöqtələri) ───────────────────────────────────────────
for i, pt in enumerate(hex_points(cx, cy, 218)):
    dot_r = 7 if i % 2 == 0 else 4
    col   = (255, 120, 50) if i % 2 == 0 else (180, 60, 220)
    draw.ellipse([pt[0]-dot_r, pt[1]-dot_r, pt[0]+dot_r, pt[1]+dot_r], fill=col)

out = "/home/ayxan/laravel-mentor/bot_avatar.png"
img.save(out, "PNG")
print(f"Avatar yaradıldı: {out}")
