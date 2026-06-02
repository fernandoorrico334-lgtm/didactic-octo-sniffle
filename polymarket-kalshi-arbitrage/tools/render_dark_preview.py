from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "print-cliente-dark-original.png"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts") / name,
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


REG = font("segoeui.ttf", 13)
SMALL = font("segoeui.ttf", 11)
TINY = font("segoeui.ttf", 10)
BOLD = font("segoeuib.ttf", 13)
BOLD_SMALL = font("segoeuib.ttf", 11)
BOLD_TINY = font("segoeuib.ttf", 10)
TITLE = font("segoeuib.ttf", 22)


COLORS = {
    "bg": (0, 0, 0),
    "panel": (5, 5, 5),
    "panel_soft": (10, 10, 10),
    "head": (16, 16, 16),
    "line": (48, 58, 54),
    "line_bright": (42, 112, 84),
    "glow_soft": (4, 24, 18),
    "glow": (8, 48, 36),
    "ink": (255, 255, 255),
    "muted": (210, 215, 212),
    "green": (49, 242, 176),
    "green_soft": (10, 55, 40),
    "amber": (255, 209, 92),
    "red": (255, 107, 107),
    "input": (0, 0, 0),
}


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, fill: str = "ink", fnt=REG) -> None:
    draw.text(xy, value, fill=COLORS[fill], font=fnt)


def rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: str | tuple[int, int, int],
    outline: str = "line_bright",
    width: int = 1,
    glow: bool = False,
    strong: bool = False,
) -> None:
    fill_color = COLORS[fill] if isinstance(fill, str) else fill
    outline_color = COLORS[outline]
    if glow:
        x1, y1, x2, y2 = box
        glow_steps = ((7, "glow_soft"), (3, "glow")) if strong else ((5, "glow_soft"),)
        for inflate, color in glow_steps:
            draw.rounded_rectangle(
                (x1 - inflate, y1 - inflate, x2 + inflate, y2 + inflate),
                radius=radius + inflate,
                outline=COLORS[color],
                width=1,
            )
    draw.rounded_rectangle(box, radius=radius, fill=fill_color, outline=outline_color, width=width)


def wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, width: int, fill: str = "muted", fnt=SMALL, line_gap: int = 2) -> int:
    avg = max(5, int(draw.textlength("abcdefghijklmnopqrstuvwxyz", font=fnt) / 26))
    chars = max(10, width // avg)
    y = xy[1]
    for line in wrap(value, width=chars):
        draw.text((xy[0], y), line, fill=COLORS[fill], font=fnt)
        y += fnt.size + line_gap
    return y


def underline_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, fnt=BOLD_SMALL) -> None:
    draw.text(xy, value, fill=COLORS["green"], font=fnt)
    w = draw.textlength(value, font=fnt)
    y = xy[1] + fnt.size + 2
    draw.line((xy[0], y, xy[0] + w, y), fill=COLORS["green"], width=1)


def input_box(draw: ImageDraw.ImageDraw, xy: tuple[int, int], w: int, value: str) -> None:
    x, y = xy
    rounded(draw, (x, y, x + w, y + 27), radius=5, fill="input", outline="line_bright")
    text(draw, (x + 8, y + 7), value, "ink", BOLD_SMALL)


def tab_icon(draw: ImageDraw.ImageDraw, key: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    if key == "all":
        for i, knob in enumerate([13, 5, 10]):
            yy = y + 4 + i * 7
            draw.line((x + 3, yy, x + 19, yy), fill=color, width=1)
            draw.ellipse((x + knob - 2, yy - 2, x + knob + 2, yy + 2), fill=color)
    elif key == "politica":
        draw.polygon([(x + 11, y + 2), (x + 2, y + 8), (x + 20, y + 8)], outline=color)
        draw.line((x + 4, y + 18, x + 18, y + 18), fill=color, width=1)
        for xx in (6, 11, 16):
            draw.line((x + xx, y + 9, x + xx, y + 17), fill=color, width=1)
    elif key == "economia":
        draw.line((x + 3, y + 17, x + 3, y + 5), fill=color, width=1)
        draw.line((x + 3, y + 17, x + 18, y + 17), fill=color, width=1)
        draw.line((x + 5, y + 14, x + 9, y + 10, x + 12, y + 12, x + 18, y + 5), fill=color, width=2)
        draw.line((x + 15, y + 5, x + 18, y + 5, x + 18, y + 8), fill=color, width=1)
    elif key == "esportes":
        draw.ellipse((x + 3, y + 3, x + 19, y + 19), outline=color, width=1)
        draw.line((x + 11, y + 3, x + 11, y + 19), fill=color, width=1)
        draw.arc((x + 7, y + 3, x + 15, y + 19), 80, 280, fill=color, width=1)
        draw.line((x + 4, y + 11, x + 18, y + 11), fill=color, width=1)
    elif key == "cripto":
        draw.ellipse((x + 3, y + 3, x + 19, y + 19), outline=color, width=1)
        draw.line((x + 9, y + 6, x + 9, y + 16), fill=color, width=1)
        draw.line((x + 13, y + 6, x + 13, y + 16), fill=color, width=1)
        draw.text((x + 8, y + 4), "B", fill=color, font=BOLD_TINY)
    elif key == "clima":
        draw.arc((x + 3, y + 9, x + 13, y + 18), 180, 360, fill=color, width=2)
        draw.arc((x + 9, y + 5, x + 20, y + 17), 190, 350, fill=color, width=2)
        draw.line((x + 4, y + 17, x + 19, y + 17), fill=color, width=2)


def pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, active: bool = False, count: str | None = None, key: str = "all") -> int:
    x, y = xy
    label_w = int(draw.textlength(value, font=BOLD_TINY))
    w = max(110, label_w + (74 if count is not None else 42))
    fill = COLORS["green"] if active else COLORS["panel_soft"]
    outline = COLORS["green"] if active else COLORS["line"]
    fg = (3, 18, 12) if active else COLORS["muted"]
    rounded(draw, (x, y, x + w, y + 42), radius=8, fill=fill, outline="green" if active else "line_bright", glow=True, strong=active)
    tab_icon(draw, key, x + 14, y + 11, fg)
    draw.text((x + 42, y + 15), value, fill=fg, font=BOLD_TINY)
    if count is not None:
        cx = x + w - 27
        draw.rounded_rectangle((cx, y + 12, cx + 19, y + 31), radius=9, fill=COLORS["bg"])
        draw.text((cx + 7, y + 16), count, fill=COLORS["ink"] if not active else COLORS["green"], font=BOLD_TINY)
    return w


def calc(draw: ImageDraw.ImageDraw, x: int, y: int, total: str, yes: str, no: str, contracts: str, profit: str, roi: str, limit: str) -> None:
    labels = [("Stake total", total), ("SIM", yes), ("NÃO", no)]
    for i, (label, value) in enumerate(labels):
        lx = x + i * 72
        text(draw, (lx, y), label, "muted", BOLD_TINY)
        input_box(draw, (lx, y + 14), 64, value)
    sy = y + 49
    draw.line((x, sy - 7, x + 214, sy - 7), fill=COLORS["glow"], width=1)
    rows = [("Contratos", contracts, "ink"), ("Lucro", profit, "green"), ("Porcentagem", roi, "green")]
    for i, (label, value, color) in enumerate(rows):
        text(draw, (x, sy + i * 15), label, "muted", BOLD_TINY)
        text(draw, (x + 86, sy + i * 15), value, color, BOLD_TINY)


def draw_title_icon(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.ellipse((x, y, x + 34, y + 34), outline=COLORS["green"], width=2)
    draw.ellipse((x + 8, y + 8, x + 26, y + 26), outline=COLORS["green"], width=1)
    draw.line((x + 29, y + 6, x + 34, y + 1), fill=COLORS["green"], width=2)
    draw.ellipse((x + 15, y + 15, x + 19, y + 19), fill=COLORS["green"])


def draw_info_icon(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.ellipse((x, y, x + 23, y + 23), outline=COLORS["green"], width=1)
    text(draw, (x + 9, y + 5), "i", "green", BOLD_TINY)


def main() -> None:
    img = Image.new("RGB", (1280, 720), COLORS["bg"])
    draw = ImageDraw.Draw(img)

    panel = (10, 8, 1270, 712)
    rounded(draw, panel, radius=8, fill="panel", outline="line_bright", glow=True, strong=True)

    note_box = (23, 23, 1255, 88)
    rounded(draw, note_box, radius=8, fill=(3, 3, 3), outline="line_bright", glow=True)
    draw_info_icon(draw, 40, 44)
    note1 = "AQUI A ARBITRAGEM ACONTECE QUANDO O CUSTO DO SIM + NÃO FICA ABAIXO DE $1.00."
    note2 = "EXEMPLO: SIM $0.49 + NÃO $0.47 = $0.96. VOCÊ PAGA $0.96 PARA RECEBER $1.00 NO FINAL. LUCRO BRUTO: $0.04 POR UNIDADE."
    text(draw, (76, 41), note1, "ink", BOLD_TINY)
    text(draw, (76, 65), note2, "ink", BOLD_TINY)

    x = 42
    y = 164
    for key, label, count, active in [
        ("all", "TODOS", "3", True),
        ("politica", "POLÍTICA", "0", False),
        ("economia", "ECONOMIA", "1", False),
        ("esportes", "ESPORTES", "0", False),
        ("cripto", "CRIPTO", "1", False),
        ("clima", "CLIMA", "1", False),
    ]:
        w = pill(draw, (x, y), label, active, count, key)
        x += w + 12
    text(draw, (970, 158), "Porcentagem mín. (%)", "muted", BOLD_TINY)
    input_box(draw, (970, 176), 125, "0")
    text(draw, (1118, 158), "Liquidez mín. ($)", "muted", BOLD_TINY)
    input_box(draw, (1118, 176), 124, "0")

    cols = [
        ("Mercado", 240),
        ("SIM", 154),
        ("NÃO", 162),
        ("Porcentagem", 126),
        ("Tamanho", 94),
        ("Lucro est.", 88),
        ("Confiança", 92),
        ("Calculadora", 246),
    ]
    table_x = 23
    table_y = 224
    table_w = 1232
    rounded(draw, (table_x, table_y, table_x + table_w, table_y + 35), radius=7, fill="head", outline="line_bright", glow=True)
    cx = table_x
    for label, w in cols:
        text(draw, (cx + 24, table_y + 12), label.upper(), "ink", BOLD_TINY)
        cx += w

    rows = [
        {
            "market": "Fed cuts rates by June 2026?",
            "against": "POLYMARKET SIM contra KALSHI NÃO",
            "yes": ("POLYMARKET SIM", "$0.490", "2.04x", "19"),
            "no": ("KALSHI NÃO", "$0.470", "2.13x", "19"),
            "edge": "4.00%",
            "gross": "bruto 4.00%",
            "size": "19",
            "max": "$18.24 max",
            "profit": "$0.76",
            "conf": "88.33%",
            "calc": ("18.24", "9.31", "8.93", "19", "$0.76", "4.17%", "$18.24"),
        },
        {
            "market": "CPI inflation above forecast?",
            "against": "POLYMARKET SIM contra KALSHI NÃO",
            "yes": ("POLYMARKET SIM", "$0.310", "3.23x", "12"),
            "no": ("KALSHI NÃO", "$0.650", "1.54x", "12"),
            "edge": "4.00%",
            "gross": "bruto 4.00%",
            "size": "12",
            "max": "$11.52 max",
            "profit": "$0.48",
            "conf": "80.00%",
            "calc": ("11.52", "3.72", "7.80", "12", "$0.48", "4.17%", "$11.52"),
            "warn": True,
        },
        {
            "market": "Bitcoin closes above $100k this month?",
            "against": "KALSHI SIM contra POLYMARKET NÃO",
            "yes": ("KALSHI SIM", "$0.600", "1.67x", "22"),
            "no": ("POLYMARKET NÃO", "$0.380", "2.63x", "22"),
            "edge": "2.00%",
            "gross": "bruto 2.00%",
            "size": "22",
            "max": "$21.56 max",
            "profit": "$0.44",
            "conf": "98.00%",
            "calc": ("21.56", "13.20", "8.36", "22", "$0.44", "2.04%", "$21.56"),
        },
    ]

    row_h = 128
    y = table_y + 40
    for row in rows:
        rounded(draw, (table_x, y, table_x + table_w, y + row_h), radius=8, fill=(3, 3, 3), outline="line_bright", glow=True)
        cx = table_x
        text(draw, (cx + 24, y + 17), row["market"], "ink", BOLD_SMALL)
        wrapped(draw, (cx + 24, y + 42), row["against"], 205, "muted", SMALL)
        cx += cols[0][1]

        for side in ("yes", "no"):
            label, px, odd, liq = row[side]
            underline_text(draw, (cx + 10, y + 17), label)
            text(draw, (cx + 10, y + 40), f"Preço {px} | Odd", "muted", SMALL)
            text(draw, (cx + 10, y + 58), odd, "muted", SMALL)
            text(draw, (cx + 10, y + 78), f"Liquidez {liq}", "muted", SMALL)
            cx += cols[1][1] if side == "yes" else cols[2][1]

        text(draw, (cx + 14, y + 17), row["edge"], "green", font("arialbd.ttf", 18))
        text(draw, (cx + 14, y + 43), row["gross"], "muted", SMALL)
        cx += cols[3][1]
        text(draw, (cx + 10, y + 17), row["size"], "ink", BOLD)
        text(draw, (cx + 10, y + 43), row["max"], "muted", SMALL)
        cx += cols[4][1]
        text(draw, (cx + 10, y + 17), row["profit"], "ink", REG)
        cx += cols[5][1]
        text(draw, (cx + 10, y + 17), row["conf"], "amber" if row.get("warn") else "ink", REG)
        cx += cols[6][1]
        rounded(draw, (cx + 6, y + 8, table_x + table_w - 10, y + row_h - 8), radius=7, fill=(6, 6, 6), outline="line_bright", glow=True)
        calc(draw, cx + 18, y + 11, *row["calc"])
        y += row_h + 7

    img.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
