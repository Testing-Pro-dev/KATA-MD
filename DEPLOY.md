# 🔥 Kata-MD — Deploy to Render (Free & 24/7)

## Step 1 — Create GitHub Account
Go to https://github.com and sign up free

## Step 2 — Create New Repository
1. Click the **+** button → **New repository**
2. Name it: `kata-md`
3. Set to **Public**
4. Click **Create repository**

## Step 3 — Upload Files
Upload these 3 files to your repo:
- `main.py`
- `requirements.txt`
- `Procfile`

## Step 4 — Create Render Account
Go to https://render.com and sign up with your GitHub account

## Step 5 — Deploy on Render
1. Click **New** → **Web Service**
2. Connect your GitHub repo `kata-md`
3. Fill in:
   - **Name:** kata-md
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
4. Click **Advanced** → **Add Environment Variables:**

| Key | Value |
|-----|-------|
| GREEN_INSTANCE_ID | 7107575522 |
| GREEN_INSTANCE_TOKEN | your_token_here |
| OWNER_NUMBER | 27743266789 |
| BOT_NAME | Kata-MD |
| PREFIX | . |

5. Click **Create Web Service**

## Step 6 — Done! 🎉
Render will build and deploy your bot automatically.
It runs 24/7 for FREE on Render's free tier!

## Keep Alive (Important!)
Render free tier sleeps after 15 mins of inactivity.
To keep it awake 24/7, use UptimeRobot:
1. Go to https://uptimerobot.com (free)
2. Add monitor → HTTP(s)
3. URL: your Render app URL (e.g. https://kata-md.onrender.com)
4. Interval: every 5 minutes
Done — bot stays online forever! 🔥
