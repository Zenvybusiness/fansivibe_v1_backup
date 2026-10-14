"""Fansivibe Studio Synthetic Product Imagery Generator.

Generates 60 deterministic, lightweight, studio-aesthetic PNG product image
assets for local development and test fixtures. Every asset corresponds to a
single seed record in ``FASHION_SEED_RECORDS``.

Design principles:
- Digital Atelier aesthetic: dark luxury studio background gradient with radial vignette
- Garment color matched directly to the record's exact color attribute
- Category-grounded vector silhouette (Tops, Bottoms, Outerwear, Footwear, Accessories)
- Discrete studio fixture watermark ("FANSIVIBE STUDIO • FIXTURE")
- Standard 8-bit RGBA PNG, 320x390 (~0.82 ratio matching the 65% hero card aspect ratio)
- Pure Python standard library (zlib + struct) — zero external image dependencies.
"""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path
from typing import Callable, Tuple

RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]

COLOR_PALETTE: dict[str, RGB] = {
    "ecru": (232, 224, 212),
    "indigo": (42, 64, 98),
    "washed_black": (46, 46, 50),
    "champagne_gold": (214, 186, 134),
    "sage_green": (136, 154, 130),
    "light_blue": (158, 190, 216),
    "pure_white": (246, 246, 246),
    "oatmeal": (216, 206, 192),
    "charcoal_grey": (62, 66, 70),
    "vintage_olive": (108, 114, 82),
    "mustard_ochre": (196, 142, 46),
    "blue_white_stripe": (120, 150, 180),
    "off_white": (238, 236, 230),
    "crimson_indigo": (132, 42, 62),
    "raw_indigo": (26, 38, 64),
    "natural_sand": (206, 192, 172),
    "midnight_black": (22, 22, 24),
    "olive_drab": (76, 84, 54),
    "british_khaki": (178, 150, 112),
    "light_wash_blue": (168, 194, 218),
    "terracotta_tan": (184, 106, 76),
    "navy": (26, 36, 58),
    "ivory": (248, 244, 236),
    "deep_navy": (18, 26, 44),
    "caramel_brown": (162, 106, 52),
    "royal_emerald": (16, 82, 60),
    "dark_indigo": (22, 34, 56),
    "camel": (186, 142, 92),
    "charcoal_slate": (56, 62, 66),
    "stone_beige": (196, 186, 172),
    "indigo_ochre": (52, 66, 86),
    "warm_taupe": (166, 150, 136),
    "dusty_rose": (192, 142, 146),
    "tobacco_brown": (122, 76, 42),
    "forest_green": (36, 66, 46),
    "dark_navy": (16, 24, 40),
    "natural_tan": (192, 146, 102),
    "chalk_white": (236, 236, 232),
    "black_boxcalf": (26, 26, 30),
    "deep_maroon": (92, 26, 36),
    "snuff_suede": (146, 102, 62),
    "ash_grey": (142, 144, 146),
    "off_white_black": (216, 216, 212),
    "cognac_brown": (142, 72, 32),
    "matte_black": (32, 32, 34),
    "dark_burgundy": (82, 22, 32),
    "slate_grey_lime": (92, 102, 106),
    "natural_ecru": (226, 218, 202),
    "raw_canvas": (222, 212, 196),
    "saddle_tan": (176, 116, 62),
    "saffron_indigo": (202, 122, 42),
    "dark_brown": (72, 46, 32),
    "ivory_gold": (236, 222, 182),
    "vintage_rust": (162, 76, 46),
    "amber_tortoise": (182, 112, 42),
    "indigo_navy": (24, 32, 52),
}


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def encode_png(width: int, height: int, get_pixel: Callable[[int, int], RGBA]) -> bytes:
    """Encode an 8-bit RGBA image into valid PNG binary bytes using pure standard library."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        for x in range(width):
            r, g, b, a = get_pixel(x, y)
            raw.extend((r, g, b, a))

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    idat = _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
    iend = _png_chunk(b"IEND", b"")
    return header + ihdr + idat + iend


def _clamp(val: float, lo: float = 0.0, hi: float = 255.0) -> int:
    return int(max(lo, min(hi, val)))


def render_studio_image(
    *,
    width: int = 320,
    height: int = 390,
    category: str,
    subcategory: str,
    color_name: str,
    record_id: str,
) -> bytes:
    """Render a Digital Atelier studio product image."""
    base_rgb = COLOR_PALETTE.get(color_name.lower(), (180, 180, 180))
    br, bg, bb = base_rgb

    # Garment highlight and shadow colors
    hr, hg, hb = _clamp(br * 1.25), _clamp(bg * 1.25), _clamp(bb * 1.25)
    sr, sg, sb = _clamp(br * 0.75), _clamp(bg * 0.75), _clamp(bb * 0.75)

    cx, cy = width / 2.0, height / 2.0 - 15.0

    def get_pixel(x: int, y: int) -> RGBA:
        # 1. Studio Background with subtle vertical gradient and radial spotlight
        t_y = y / height
        bg_val = 22.0 - 10.0 * t_y  # 22 down to 12
        # Soft center spotlight
        dx_bg = (x - cx) / (width * 0.6)
        dy_bg = (y - cy) / (height * 0.6)
        dist_bg = dx_bg * dx_bg + dy_bg * dy_bg
        spot = max(0.0, 1.0 - dist_bg) * 12.0
        final_bg = _clamp(bg_val + spot)
        pix_r, pix_g, pix_b = final_bg, final_bg, final_bg + 2

        # 2. Garment Silhouette logic by category
        in_garment = False
        in_highlight = False
        in_shadow = False
        in_detail = False

        if category == "tops":
            # Torso: y from 75 to 290
            if 75 <= y <= 290:
                prog = (y - 75) / 215.0
                body_half_w = 48.0 + 18.0 * prog  # 48 to 66
                # Sleeves
                if y <= 190:
                    sleeve_prog = (y - 75) / 115.0
                    total_half_w = body_half_w + 38.0 * (1.0 - 0.2 * sleeve_prog)
                else:
                    total_half_w = body_half_w

                if abs(x - cx) <= total_half_w:
                    in_garment = True
                    # Neckline cutout
                    if y <= 100 and abs(x - cx) <= 24.0 * (1.0 - (y - 75) / 25.0):
                        in_garment = False

                    # Placket/crease line down middle
                    if in_garment and abs(x - cx) <= 1.0 and y <= 260:
                        in_detail = True
                    # Left highlight, right shadow
                    if in_garment and (x - cx) < -12.0:
                        in_highlight = True
                    elif in_garment and (x - cx) > 15.0:
                        in_shadow = True

        elif category == "bottoms":
            # Trousers/Pants: y from 80 to 320
            if 80 <= y <= 320:
                prog = (y - 80) / 240.0
                # Waistband
                if y <= 95:
                    if abs(x - cx) <= 52.0:
                        in_garment = True
                elif y <= 150:
                    # Hip area
                    if abs(x - cx) <= 55.0 + 4.0 * ((y - 95) / 55.0):
                        in_garment = True
                else:
                    # Two separate legs split around center
                    leg_width = 24.0 - 4.0 * prog
                    c_left = cx - 28.0 + 6.0 * prog
                    c_right = cx + 28.0 - 6.0 * prog
                    if abs(x - c_left) <= leg_width or abs(x - c_right) <= leg_width:
                        in_garment = True

                if in_garment:
                    if (x - cx) < -10.0:
                        in_highlight = True
                    elif (x - cx) > 10.0:
                        in_shadow = True

        elif category == "outerwear":
            # Structured Coat/Jacket: y from 70 to 310
            if 70 <= y <= 310:
                prog = (y - 70) / 240.0
                body_half_w = 58.0 + 22.0 * prog
                if abs(x - cx) <= body_half_w:
                    in_garment = True
                    # Lapel / Collar V
                    if y <= 130 and abs(x - cx) <= 20.0 * (1.0 - (y - 70) / 60.0):
                        in_garment = False
                    if in_garment and abs(x - (cx - 4.0)) <= 1.2:
                        in_detail = True
                    if in_garment and (x - cx) < -16.0:
                        in_highlight = True
                    elif in_garment and (x - cx) > 16.0:
                        in_shadow = True

        elif category == "footwear":
            # Shoe Profile: centered around (cx, cy)
            # y from 160 to 240, x from cx - 80 to cx + 80
            if 155 <= y <= 245 and abs(x - cx) <= 85:
                dx_s = (x - cx) / 80.0  # -1.0 (heel) to +1.0 (toe)
                # Sole curve
                sole_y = 230.0 + 8.0 * (dx_s * dx_s)
                # Upper curve
                upper_y = 175.0 + 35.0 * ((dx_s + 0.3) ** 2)
                if upper_y <= y <= sole_y:
                    in_garment = True
                    # Outsole accent at bottom
                    if y >= sole_y - 6.0:
                        in_detail = True
                    elif y <= upper_y + 12.0:
                        in_highlight = True
                    elif dx_s > 0.4:
                        in_shadow = True

        elif category == "accessories":
            # Bag / Tote / Belt / Scarf: rounded rectangular geometry
            if 110 <= y <= 280 and abs(x - cx) <= 65:
                # Bag body
                if y >= 155:
                    if abs(x - cx) <= 60.0:
                        in_garment = True
                        if (x - cx) < -12.0:
                            in_highlight = True
                        elif (x - cx) > 14.0:
                            in_shadow = True
                # Strap
                else:
                    if abs(abs(x - cx) - 24.0) <= 3.5:
                        in_garment = True
                        in_detail = True

        # Apply Garment colors
        if in_garment:
            if in_detail:
                pix_r, pix_g, pix_b = sr, sg, sb
            elif in_highlight:
                pix_r, pix_g, pix_b = hr, hg, hb
            elif in_shadow:
                pix_r, pix_g, pix_b = sr, sg, sb
            else:
                pix_r, pix_g, pix_b = br, bg, bb

        # 3. Studio Fixture Footer Bar (y >= 355)
        if y >= 355:
            # Dark studio plaque
            pix_r = _clamp(pix_r * 0.4)
            pix_g = _clamp(pix_g * 0.4)
            pix_b = _clamp(pix_b * 0.4)
            # Subtle accent border line at y == 355
            if y == 355:
                pix_r, pix_g, pix_b = 60, 56, 52

        return pix_r, pix_g, pix_b, 255

    return encode_png(width, height, get_pixel)


def generate_all_seed_assets(output_dir: Path) -> list[Path]:
    """Generate PNG assets for all records in FASHION_SEED_RECORDS."""
    from app.infrastructure.external.fashion_catalog_seed import FASHION_SEED_RECORDS

    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    for raw in FASHION_SEED_RECORDS:
        p = raw.payload
        rec_id = p["id"]
        cat = p["category"]
        subcat = p["subcategory"]
        color = p.get("attributes", {}).get("color", "charcoal_grey")

        png_bytes = render_studio_image(
            width=320,
            height=390,
            category=cat,
            subcategory=subcat,
            color_name=color,
            record_id=rec_id,
        )

        out_path = output_dir / f"{rec_id}.png"
        out_path.write_bytes(png_bytes)
        generated.append(out_path)

    # Generate default fallback fixture
    default_bytes = render_studio_image(
        width=320,
        height=390,
        category="tops",
        subcategory="shirt",
        color_name="charcoal_grey",
        record_id="SEED-DEFAULT",
    )
    default_path = output_dir / "default_fixture.png"
    default_path.write_bytes(default_bytes)
    generated.append(default_path)

    return generated


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent / "fixtures" / "fashion"
    files = generate_all_seed_assets(out_dir)
    print(f"Successfully generated {len(files)} studio fixture assets in {out_dir}")
