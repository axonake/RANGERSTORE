# Line Ranger ID Store

ร้านขาย ID เกม Line Ranger พร้อมระบบ Link ID อัตโนมัติ

## 🚀 Deploy to Production

### Option 1: Railway (แนะนำ - ง่ายสุด)

1. ไปที่ [railway.app](https://railway.app)
2. Login ด้วย GitHub
3. New Project → Deploy from GitHub repo
4. เพิ่ม PostgreSQL database
5. ตั้ง Environment Variables:
   ```
   SECRET_KEY=your-secret-key-here
   TW_MERCHANT_PHONE=0631351022
   ```
6. Deploy!

### Option 2: Render

1. ไปที่ [render.com](https://render.com)
2. New → Web Service
3. Connect GitHub repo
4. เพิ่ม PostgreSQL database (New → PostgreSQL)
5. ตั้ง Environment Variables เหมือนข้างบน

### Option 3: Supabase + Vercel

1. สร้าง PostgreSQL ที่ [supabase.com](https://supabase.com)
2. Copy Connection String
3. Deploy Flask ที่ Vercel/Railway โดยตั้ง `DATABASE_URL`

---

## 🛠 Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run (uses SQLite locally)
python app.py
```

## 📦 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Production only |
| `SECRET_KEY` | Flask secret key | Yes |
| `TW_MERCHANT_PHONE` | เบอร์รับเงินอั่งเปา | Yes |
| `ADB_PATH` | Path to adb.exe | Local only |

## 📁 Structure

```
├── app.py              # Main Flask app
├── config.py           # Configuration
├── adb_handler.py      # ADB automation
├── requirements.txt    # Dependencies
├── Procfile           # Production server
├── templates/         # HTML templates
├── static/            # CSS, JS, images
└── products/          # XML files
```
