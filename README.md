# Transaction CSV Converter

A Streamlit app that reformats credit card transaction exports from various platforms into a standard Date / Description / Amount format for QBO upload.

## Supported Platforms
- Divvy PF
- Divvy CR
- Slash
- Wex PF
- Wex CR
- Taekus
- Global Rewards

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set main file to `app.py`
5. Deploy

## Project Structure

```
tx_converter/
├── app.py            # Main Streamlit app
├── requirements.txt  # Python dependencies
└── README.md         # This file
```
