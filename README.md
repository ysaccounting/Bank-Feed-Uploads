# Bank Feed Uploads

Converts credit card transaction exports from various platforms into a standard
Date / Description / Amount format for QBO bank feed upload.

## Supported Platforms
Divvy CR, Divvy PF, EvoPay, Global Rewards, Slash, Taekus, Wex CR, Wex PF

## Project Structure
```
app.py            ← Flask backend
index.html        ← Frontend UI
parsers.py        ← All platform parsers
requirements.txt  ← Dependencies
railway.json      ← Railway deployment config
```

## Run Locally
```bash
pip install -r requirements.txt
python app.py     # http://localhost:5000
```

## Deploy to Railway
1. Push repo to GitHub
2. Railway → New Project → Deploy from GitHub repo
3. Add environment variables: SUPABASE_URL, SUPABASE_KEY
