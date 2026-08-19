from pyscript import document, window, when
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import base64, calendar

W, H = 1200, 1780
PHOTO_W = W - 100
PHOTO_H = 900
PHOTO_X = 50
PHOTO_Y = 38
CAL_TOP = 995

def get_font(size, bold=False):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()

FONT_TITLE = get_font(88, True)
FONT_WEEK = get_font(56, True)
FONT_DAY = get_font(54, True)

# PC一括ダウンロード用：直近に生成した12か月分のJPEG bytes
GENERATED_JPEGS = {}

async def js_file_to_image(file_obj):
    data_url = str(await window.readFileDataURL(file_obj))
    raw = base64.b64decode(data_url.split(",", 1)[1])
    img = Image.open(BytesIO(raw))
    return ImageOps.exif_transpose(img).convert("RGB")

def crop_with_adjustment(img, target_w, target_h, x_adj=0, y_adj=0, zoom=100):
    """
    写真をフレームへ配置する。
    x_adj / y_adj : -200..200（0が中央）
    zoom          : 50..200（100が従来の「全面を埋める」基準）

    50〜99%では写真全体をより多く見せられる代わりに余白が出る場合がある。
    大きく上下左右へ動かした場合も同様。
    """
    iw, ih = img.size

    # 100% = フレームを完全に埋める cover 基準
    cover_scale = max(target_w / iw, target_h / ih)
    scale = cover_scale * (zoom / 100.0)

    nw = max(1, int(round(iw * scale)))
    nh = max(1, int(round(ih * scale)))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS).convert("RGBA")

    # フレーム本体。縮小・大移動時に出る余白はカレンダー背景色に合わせる。
    frame = Image.new("RGBA", (target_w, target_h), (250, 248, 244, 255))

    # 中央配置を基準に、-200..200 をフレーム半分相当まで移動可能にする。
    base_x = (target_w - nw) / 2
    base_y = (target_h - nh) / 2
    shift_x = (x_adj / 200.0) * (target_w * 0.50)
    shift_y = -(y_adj / 200.0) * (target_h * 0.50)

    paste_x = int(round(base_x + shift_x))
    paste_y = int(round(base_y + shift_y))

    frame.alpha_composite(resized, (paste_x, paste_y))
    return frame

def prepare_photo(img, x_adj=0, y_adj=0, zoom=100):
    img = crop_with_adjustment(img, PHOTO_W, PHOTO_H, x_adj, y_adj, zoom)
    rgba = img.convert("RGBA")

    mask = Image.new("L", rgba.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, rgba.width, rgba.height), radius=34, fill=255)
    rgba.putalpha(mask)
    return rgba

def center_text(draw, y, text, font, fill):
    b = draw.textbbox((0, 0), text, font=font)
    draw.text(((W - (b[2]-b[0])) / 2, y), text, font=font, fill=fill)

def make_calendar(img, year, month, x_adj=0, y_adj=0, zoom=100, logo=None):
    canvas = Image.new("RGBA", (W, H), (250, 248, 244, 255))
    d = ImageDraw.Draw(canvas)

    photo = prepare_photo(img, x_adj, y_adj, zoom)
    canvas.alpha_composite(photo, (PHOTO_X, PHOTO_Y))

    center_text(d, CAL_TOP, f"{year}  /  {month:02d}", FONT_TITLE, (45,45,45,255))

    names = ["SUN","MON","TUE","WED","THU","FRI","SAT"]
    left, right = 70, W - 70
    top = CAL_TOP + 92
    cw = (right-left) / 7

    # 曜日見出し
    weekday_h = 56
    for c, name in enumerate(names):
        color = (185,45,45,255) if c == 0 else ((45,80,165,255) if c == 6 else (30,30,30,255))
        b = d.textbbox((0,0), name, font=FONT_WEEK)
        d.text(
            (left + c*cw + (cw-(b[2]-b[0]))/2, top),
            name, font=FONT_WEEK, fill=color
        )

    # 日別書き込み用グリッド
    # 実際に日付が存在する週だけ描画する。
    weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(year, month)
    week_count = len(weeks)

    grid_top = top + weekday_h
    available_grid_h = 456
    cell_h = available_grid_h / week_count
    grid_bottom = grid_top + cell_h * week_count
    line_color = (125, 120, 112, 255)
    line_width = 3

    for c in range(8):
        x = int(round(left + c * cw))
        d.line((x, int(round(grid_top)), x, int(round(grid_bottom))), fill=line_color, width=line_width)

    for r in range(week_count + 1):
        y = int(round(grid_top + r * cell_h))
        d.line((left, y, right, y), fill=line_color, width=line_width)

    pad_x = 10
    pad_y = 7
    for r, wk in enumerate(weeks):
        for c, day in enumerate(wk):
            if not day:
                continue
            s = str(day)
            color = (185,45,45,255) if c == 0 else ((45,80,165,255) if c == 6 else (20,20,20,255))
            x = int(round(left + c * cw + pad_x))
            y = int(round(grid_top + r * cell_h + pad_y))
            d.text((x, y), s, font=FONT_DAY, fill=color)

    if logo:
        # 日付領域から離して、最下部中央に小さく配置
        lw = 112
        lh = int(logo.height * lw / logo.width)
        lg = logo.resize((lw, lh), Image.Resampling.LANCZOS)
        logo_x = (W - lw) // 2
        logo_y = H - lh - 22
        canvas.alpha_composite(lg, (logo_x, logo_y))

    return canvas.convert("RGB")

async def load_logo():
    try:
        r = await window.fetch("./logo.png")
        ab = await r.arrayBuffer()
        arr = window.Uint8Array.new(ab)
        raw = bytes(arr.to_py())
        return Image.open(BytesIO(raw)).convert("RGBA")
    except Exception:
        return None

def image_to_data_url(img):
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    buf.close()
    return "data:image/jpeg;base64," + b64


def image_to_jpeg_bytes(img):
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    data = buf.getvalue()
    buf.close()
    return data

def pybytes_to_uint8(raw):
    arr = window.Uint8Array.new(len(raw))
    for i, b in enumerate(raw):
        arr[i] = b
    return arr

def add_result_card(month, data_url):
    results = document.getElementById("results")

    card = document.createElement("div")
    card.className = "result-card"

    img = document.createElement("img")
    img.src = data_url
    img.alt = f"{month}月カレンダー"
    img.loading = "lazy"

    title = document.createElement("div")
    title.className = "result-title"
    title.innerText = f"{month}月"

    card.appendChild(img)
    card.appendChild(title)
    results.appendChild(card)

@when("click", "#make_btn")
async def make_all(event):
    status = document.getElementById("status")
    progress = document.getElementById("progress")
    btn = document.getElementById("make_btn")

    year = int(document.getElementById("year").value)
    photos = window.selectedPhotos
    adjustments = window.photoAdjustments

    for i in range(12):
        if photos[i] is None:
            status.innerText = f"{i+1}月の写真がありません。"
            return

    btn.disabled = True
    progress.style.display = "block"
    progress.value = 0
    document.getElementById("results").innerHTML = ""
    document.getElementById("results_panel").classList.add("hidden")
    document.getElementById("desktop_download_btn").classList.add("hidden")

    GENERATED_JPEGS.clear()

    logo = await load_logo()

    try:
        for month in range(1, 13):
            status.innerText = f"{month}月を作成中… ({month}/12)"
            progress.value = month - 1
            await window.pauseFrame()

            photo = await js_file_to_image(photos[month-1])
            adj = adjustments[month-1]

            result = make_calendar(
                photo,
                year,
                month,
                x_adj=float(adj.x),
                y_adj=float(adj.y),
                zoom=float(adj.zoom),
                logo=logo
            )

            jpeg_bytes = image_to_jpeg_bytes(result)
            GENERATED_JPEGS[month] = jpeg_bytes
            data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")
            add_result_card(month, data_url)

            del result, photo
            progress.value = month
            await window.pauseFrame()

        status.innerText = "12か月分が完成しました。下の画像を保存してください。"
        document.getElementById("results_panel").classList.remove("hidden")

        if window.isDesktopLike():
            document.getElementById("desktop_download_btn").classList.remove("hidden")

        document.getElementById("results_panel").scrollIntoView({"behavior":"smooth"})

    except Exception as e:
        status.innerText = f"エラー: {e}"
        raise
    finally:
        btn.disabled = False


@when("pydownload", "#desktop_download_btn")
async def download_all_pc(event):
    status = document.getElementById("status")

    if len(GENERATED_JPEGS) != 12:
        status.innerText = "12か月分の画像がまだ完成していません。"
        return

    year = int(document.getElementById("year").value)
    status.innerText = "12か月分をZIPにまとめています…"

    zbuf = BytesIO()
    with ZipFile(zbuf, "w", ZIP_DEFLATED) as zf:
        for month in range(1, 13):
            zf.writestr(
                f"nekofukuro_calendar_{year}_{month:02d}.jpg",
                GENERATED_JPEGS[month]
            )

    raw = zbuf.getvalue()
    zbuf.close()

    window.downloadBytes(
        f"nekofukuro_calendar_{year}.zip",
        pybytes_to_uint8(raw),
        "application/zip"
    )
    status.innerText = "12か月分のZIPをダウンロードしました。"
