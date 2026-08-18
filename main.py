from pyscript import document, window, when
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import base64, calendar

W, H = 1200, 1600
PHOTO_H = 960
CAL_TOP = 1015

def get_font(size, bold=False):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()

FONT_TITLE = get_font(52, True)
FONT_WEEK = get_font(30, True)
FONT_DAY = get_font(31)

async def js_file_to_image(file_obj):
    data_url = str(await window.readFileDataURL(file_obj))
    raw = base64.b64decode(data_url.split(",",1)[1])
    img = Image.open(BytesIO(raw))
    return ImageOps.exif_transpose(img).convert("RGB")

def cover_crop(img, tw, th):
    iw, ih = img.size
    scale = max(tw/iw, th/ih)
    nw, nh = int(iw*scale), int(ih*scale)
    img = img.resize((nw,nh), Image.Resampling.LANCZOS)
    left, top = (nw-tw)//2, (nh-th)//2
    return img.crop((left,top,left+tw,top+th))

def prepare_photo(img):
    img = cover_crop(img, W-100, PHOTO_H-60)
    rgba = img.convert("RGBA")
    mask = Image.new("L", rgba.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0,0,rgba.width,rgba.height), radius=34, fill=255)
    rgba.putalpha(mask)
    return rgba

def center_text(draw, y, text, font, fill):
    b = draw.textbbox((0,0), text, font=font)
    draw.text(((W-(b[2]-b[0]))/2, y), text, font=font, fill=fill)

def make_calendar(img, year, month, logo=None):
    canvas = Image.new("RGBA",(W,H),(250,248,244,255))
    d = ImageDraw.Draw(canvas)
    canvas.alpha_composite(prepare_photo(img),(50,38))
    center_text(d,CAL_TOP,f"{year}  /  {month:02d}",FONT_TITLE,(45,45,45,255))

    names=["SUN","MON","TUE","WED","THU","FRI","SAT"]
    left,right=80,W-80
    top=CAL_TOP+85
    cw=(right-left)/7
    rh=67
    for c,name in enumerate(names):
        color=(150,80,80,255) if c==0 else ((75,100,145,255) if c==6 else (75,75,75,255))
        b=d.textbbox((0,0),name,font=FONT_WEEK)
        d.text((left+c*cw+(cw-(b[2]-b[0]))/2,top),name,font=FONT_WEEK,fill=color)

    weeks=calendar.Calendar(firstweekday=6).monthdayscalendar(year,month)
    for r,wk in enumerate(weeks):
        for c,day in enumerate(wk):
            if not day: continue
            s=str(day)
            color=(150,80,80,255) if c==0 else ((75,100,145,255) if c==6 else (55,55,55,255))
            b=d.textbbox((0,0),s,font=FONT_DAY)
            d.text((left+c*cw+(cw-(b[2]-b[0]))/2,top+52+r*rh),s,font=FONT_DAY,fill=color)

    if logo:
        lw=180
        lh=int(logo.height*lw/logo.width)
        lg=logo.resize((lw,lh),Image.Resampling.LANCZOS)
        canvas.alpha_composite(lg,(W-lw-34,H-lh-20))
    return canvas.convert("RGB")

async def load_logo():
    try:
        r=await window.fetch("./logo.png")
        ab=await r.arrayBuffer()
        arr=window.Uint8Array.new(ab)
        # JS typed array -> Python list
        raw=bytes(arr.to_py())
        return Image.open(BytesIO(raw)).convert("RGBA")
    except Exception:
        return None

def to_uint8(raw):
    arr=window.Uint8Array.new(len(raw))
    for i,b in enumerate(raw):
        arr[i]=b
    return arr

@when("click","#make_btn")
async def make_all(event):
    status=document.getElementById("status")
    progress=document.getElementById("progress")
    btn=document.getElementById("make_btn")
    year=int(document.getElementById("year").value)

    # JS配列に保持した写真を直接利用
    photos=window.selectedPhotos
    if photos.length != 12:
        status.innerText="写真が12枚そろっていません。"
        return

    for i in range(12):
        if photos[i] is None:
            status.innerText=f"{i+1}月の写真がありません。"
            return

    btn.disabled=True
    progress.style.display="block"
    progress.value=0
    logo=await load_logo()
    zbuf=BytesIO()

    try:
        with ZipFile(zbuf,"w",ZIP_DEFLATED) as zf:
            for month in range(1,13):
                status.innerText=f"{month}月を作成中… ({month}/12)"
                progress.value=month-1
                await window.pauseFrame()

                photo=await js_file_to_image(photos[month-1])
                result=make_calendar(photo,year,month,logo)
                out=BytesIO()
                result.save(out,"JPEG",quality=90,optimize=True)
                zf.writestr(f"nekofukuro_calendar_{year}_{month:02d}.jpg",out.getvalue())
                out.close()
                del result, photo

        progress.value=12
        status.innerText="完成しました。ZIPを保存します…"
        raw=zbuf.getvalue()
        window.downloadBytes(f"nekofukuro_calendar_{year}.zip",to_uint8(raw),"application/zip")
        status.innerText="12か月分が完成しました。"
    except Exception as e:
        status.innerText=f"エラー: {e}"
        raise
    finally:
        btn.disabled=False
        zbuf.close()
