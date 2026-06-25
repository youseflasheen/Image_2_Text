# 📄 Image to Text — Document Extraction

Extract structured data from financial documents (invoices, receipts, contracts) using **Gemini Vision AI** and export to Excel.

## ✨ How It Works

1. **Upload** an image of any financial document
2. **Gemini Vision** reads the image directly and extracts all key-value pairs
3. **Download** a professionally styled Excel file with the extracted data

## 🛠️ Tech Stack

- **Backend:** FastAPI (Python)
- **AI:** Gemini 2.5 Flash Vision via OpenRouter
- **Export:** openpyxl (styled Excel files)
- **Frontend:** Vanilla HTML/CSS/JS

## 🚀 Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

1. Fork this repo
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select your forked repo
4. Add environment variable: `OPENROUTER_API_KEY` = your key from [openrouter.ai](https://openrouter.ai/)
5. Railway will auto-detect Python and deploy!

## 🏠 Run Locally

```bash
# Clone the repo
git clone https://github.com/youseflasheen/Image_2_Text.git
cd Image_2_Text

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set your API key
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY

# Run the server
uvicorn app:app --reload
```

Then open http://localhost:8000

## 🔑 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | ✅ | Your API key from [openrouter.ai](https://openrouter.ai/) |
| `LLM_MODEL` | ❌ | Model to use (default: `google/gemini-2.5-flash`) |
| `PORT` | ❌ | Server port (default: `8000`, auto-set by Railway) |

## 📋 Supported Documents

- Invoices (Arabic & English)
- Receipts
- Contracts
- Bank Statements
- Tax Forms
- Purchase Orders

## 📝 License

MIT
