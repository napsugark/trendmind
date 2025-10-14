# TrendMind - AI Trend Analysis Platform

Modern, secure AI-powered trend analysis with enterprise-grade guardrails: **Scrape → Cluster → Summarize → Results**

## 🏗️ Architecture

```
┌─────────────────┐    HTTP/JSON    ┌──────────────────────┐
│  Frontend       │ ────────────── │  Backend API         │
│  (Static HTML)  │                │  (FastAPI)           │
└─────────────────┘                └──────────────────────┘
                                             │
                                             ▼
                                   ┌──────────────────────┐
                                   │  AI Workflow         │
                                   │  1. Scrape Data      │
                                   │  2. LLM Clustering   │
                                   │  3. LLM Summarization│
                                   │  4. Results          │
                                   └──────────────────────┘
```

## 🚀 Quick Start

### 1. Activate Virtual Environment & Start Backend API
```bash
source venv39/bin/activate
cd backend
python main_api.py
```

### 2. Open Frontend
Open `frontend/index.html` in your browser or serve it:
```bash
# Simple HTTP server (Langfuse uses 3000)
cd frontend
python3 -m http.server 3001
# Then visit: http://localhost:3001
```

### 3. Use the API
- **API Docs**: http://localhost:8000/docs
- **Main Endpoint**: `POST /analyze`
- **Health Check**: `GET /health`

## 📡 API Usage

### Analyze Trends
```bash
curl -X POST "http://localhost:8000/analyze" \
     -H "Content-Type: application/json" \
     -d '{
       "sources": [
         "https://garymarcus.substack.com/",
         "https://x.com/karpathy",
         "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"
       ],
       "days_back": 7,
       "max_clusters": 5
     }'
```

### Response Format
```json
{
  "success": true,
  "clusters": [
    {
      "topic_name": "AI Safety & Ethics",
      "article_count": 12,
      "summary": "Recent discussions focus on...",
      "key_points": [
        "Increased focus on AI alignment",
        "New regulatory frameworks proposed"
      ],
      "sources": ["https://garymarcus.substack.com/", "..."]
    }
  ],
  "total_articles": 45,
  "processing_time": 23.4,
  "timestamp": "2025-10-10T15:30:00"
}
```

## 📁 Project Structure

```
trendmind/
├── backend/
│   ├── main_api.py          # 🎯 Main FastAPI server
│   ├── get_data.py          # 📊 Data orchestration
│   ├── src/
│   │   ├── scraper.py       # 🕷️  Data collection
│   │   ├── clustering.py    # 🏷️  LLM clustering
│   │   ├── summarizer.py    # 📝 LLM summarization
│   │   └── db_postgres.py   # 💾 Database operations
│   └── utils/
│       └── logger.py        # 📋 Logging utilities
├── frontend/
│   ├── index.html          # 🌐 Modern web interface
│   └── favicon.svg         # 🎨 Custom favicon
├── venv39/                  # 🐍 Python virtual environment
├── requirements.txt         # 📦 Dependencies
└── .vscode/                 # ⚙️  VS Code configuration
    └── settings.json
```

## 🔄 Workflow

1. **User Input**: Sources, timeframe, clustering preferences
2. **Data Scraping**: Multi-source content collection (Twitter, RSS, Substack)
3. **AI Clustering**: LLM-powered topic grouping
4. **AI Summarization**: Generate insights for each cluster
5. **Structured Results**: JSON response with clustered summaries

## 🛠️ Configuration

Set up your `.env` file:
```bash
# Azure OpenAI (required for clustering & summarization)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_api_key
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-06-01

# Database (PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trend_mind_db
DB_USER=tm_user
DB_PASSWORD=your_password

# Qdrant Vector Database
QDRANT_HOST=qdrant_trendmind
QDRANT_PORT=6333

# Twitter API (optional)
TWITTER_BEARER_TOKEN=your_twitter_bearer_token

# Langfuse Observability
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key
```

## 🎯 Features

### Core Functionality
- ✅ **Multi-source scraping** (Twitter/X, RSS, Substack)
- ✅ **AI-powered clustering** (LLM topic detection)
- ✅ **Intelligent summarization** (key insights & trends)
- ✅ **Modern web interface** (gradient design, glass-morphism)
- ✅ **REST API** (FastAPI with auto-docs)

### Enterprise Features
- 🛡️ **Security guardrails** (input validation, content filtering)
- 🚦 **Rate limiting** (10/min, 100/hour per IP)
- 💰 **Cost controls** (daily token/request limits)
- 📊 **Full observability** (Langfuse integration)
- 🔧 **Prompt management** (versioned prompts in Langfuse)
- 💾 **Dual storage** (PostgreSQL + Qdrant vector DB)

### Developer Experience
- 🐍 **WSL Ubuntu support** (VS Code integration)
- 📝 **Type hints** (full Pylance support)
- 🔄 **Circuit breakers** (resilient external calls)
- 📋 **Structured logging** (security event tracking)

## 🔗 API Endpoints

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| POST | `/analyze` | 🎯 **Main workflow**: Scrape → Cluster → Summarize | 10/min |
| POST | `/api/collect` | Data collection only | 10/min |
| GET | `/api/stats` | Database statistics & metrics | 20/min |
| GET | `/api/recent-articles` | Recent articles with filters | 20/min |
| GET | `/health` | System health check | No limit |
| GET | `/docs` | Interactive API documentation | No limit |

## 📊 Example Output

**Input**: 3 sources, 7 days back
**Output**: 
- 45 articles collected
- 5 topic clusters identified
- AI-generated summaries with key insights
- Processing time: ~23 seconds

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.9+ (WSL Ubuntu recommended)
- PostgreSQL database
- Azure OpenAI API access
- Optional: Qdrant for vector storage

### Installation
```bash
# Clone repository
git clone https://github.com/napsugark/trend_mind.git
cd trendmind

# Create virtual environment
python3 -m venv venv39
source venv39/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env  # Edit with your API keys

# Start services
# 1. Backend API (port 8000)
cd backend && python main_api.py

# 2. Frontend (port 3001)
cd frontend && python3 -m http.server 3001

# 3. Langfuse (port 3000) - optional
cd langfuse && docker-compose up
```

## 🔧 VS Code Setup (WSL)

1. **Connect to WSL**: `Ctrl+Shift+P` → "WSL: Connect to WSL"
2. **Select Python Interpreter**: `Ctrl+Shift+P` → "Python: Select Interpreter" → Choose `./venv39/bin/python`
3. **Reload Window**: `Ctrl+Shift+P` → "Developer: Reload Window"

## 🚨 Troubleshooting

### Red Underlines in VS Code
- Ensure Python extension is installed **in WSL**
- Set correct Python interpreter path
- Restart Pylance: `Ctrl+Shift+P` → "Python: Restart Language Server"

### Import Resolution Issues
- Check `.vscode/settings.json` exists with correct paths
- Verify `__init__.py` files in `backend/` and `backend/src/`
- Restart VS Code if needed

### Database Connection Issues
- Verify PostgreSQL is running and accessible
- Check `.env` database credentials
- Test connection: `psql -h localhost -U tm_user -d trend_mind_db`

---

**Perfect for**: AI trend monitoring, market analysis, competitive intelligence, and research automation! 🚀