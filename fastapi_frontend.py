#!/usr/bin/env python3
"""
FastAPI Frontend Interface for TrendMind

This provides a modern REST API and web interface for TrendMind data collection.
Features automatic API documentation, data validation, and async support.

Usage:
    python fastapi_frontend.py
    
Then visit:
    - Web UI: http://localhost:8000
    - API Docs: http://localhost:8000/docs
    - OpenAPI Schema: http://localhost:8000/openapi.json
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator
import uvicorn

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

from get_data import DataOrchestrator
from src.db_postgres import get_article_count_by_source, get_articles_for_processing
from utils.logger import get_logger

# Initialize FastAPI app
app = FastAPI(
    title="TrendMind Data Collector",
    description="AI trend data collection and analysis API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Setup templates
templates_dir = Path("templates")
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory="templates")

# Setup static files (if needed)
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

logger = get_logger("fastapi_frontend")

# Pydantic models for request/response validation
class SourcesRequest(BaseModel):
    """Request model for data collection"""
    sources: List[str]
    days_back: Optional[int] = 7
    
    @validator('sources')
    def validate_sources(cls, v):
        if not v:
            raise ValueError('At least one source must be provided')
        return v
    
    @validator('days_back')
    def validate_days_back(cls, v):
        if v is not None and (v < 1 or v > 365):
            raise ValueError('days_back must be between 1 and 365')
        return v

class SourceResult(BaseModel):
    """Individual source processing result"""
    source_url: str
    source_type: str
    articles: List[Dict[str, Any]]
    new_count: int
    cached_count: int
    error: Optional[str]
    processing_time: float

class CollectionResponse(BaseModel):
    """Response model for data collection"""
    success: bool
    sources: List[SourceResult]
    summary: Dict[str, Any]
    timestamp: str

class StatsResponse(BaseModel):
    """Response model for statistics"""
    success: bool
    stats: Dict[str, int]
    total_articles: int
    source_count: int
    days_back: int

# Dependency to get orchestrator instance
def get_orchestrator():
    """Dependency to provide DataOrchestrator instance"""
    return DataOrchestrator()

# API Routes
@app.post("/api/collect", response_model=CollectionResponse)
async def collect_data(
    request: SourcesRequest, 
    orchestrator: DataOrchestrator = Depends(get_orchestrator)
):
    """
    Collect data from multiple sources
    
    - **sources**: List of source URLs or Twitter handles
    - **days_back**: Number of days to look back (1-365)
    
    Returns detailed results including new articles, cached articles, and processing statistics.
    """
    try:
        logger.info(f"API collect request: {len(request.sources)} sources, {request.days_back} days back")
        
        result = orchestrator.process_all_sources(request.sources, request.days_back)
        
        # Convert to response model format
        sources_response = [
            SourceResult(
                source_url=s['source_url'],
                source_type=s['source_type'],
                articles=s['articles'],
                new_count=s['new_count'],
                cached_count=s['cached_count'],
                error=s['error'],
                processing_time=s['processing_time']
            )
            for s in result['sources']
        ]
        
        return CollectionResponse(
            success=result['success'],
            sources=sources_response,
            summary=result['summary'],
            timestamp=result['timestamp']
        )
        
    except Exception as e:
        logger.error(f"API collect error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats", response_model=StatsResponse)
async def get_stats(days_back: int = 7):
    """
    Get database statistics
    
    - **days_back**: Number of days to include in statistics (default: 7)
    
    Returns article counts by source and overall statistics.
    """
    try:
        if days_back < 1 or days_back > 365:
            raise HTTPException(status_code=400, detail="days_back must be between 1 and 365")
        
        stats = get_article_count_by_source(days_back)
        
        return StatsResponse(
            success=True,
            stats=stats,
            total_articles=sum(stats.values()) if stats else 0,
            source_count=len(stats) if stats else 0,
            days_back=days_back
        )
        
    except Exception as e:
        logger.error(f"API stats error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/collect/single")
async def collect_single_source(
    source_url: str,
    days_back: int = 7,
    orchestrator: DataOrchestrator = Depends(get_orchestrator)
):
    """
    Collect data from a single source
    
    - **source_url**: Single source URL or Twitter handle
    - **days_back**: Number of days to look back
    
    Returns results for the single source.
    """
    try:
        if not source_url:
            raise HTTPException(status_code=400, detail="source_url is required")
            
        if days_back < 1 or days_back > 365:
            raise HTTPException(status_code=400, detail="days_back must be between 1 and 365")
        
        result = orchestrator.process_source(source_url, days_back)
        
        return {
            "success": True,
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"API single source error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recent-articles")
async def get_recent_articles(
    limit: int = 10,
    days_back: int = 3,
    sources: Optional[str] = None
):
    """
    Get recent articles from the database
    
    - **limit**: Maximum number of articles to return
    - **days_back**: Number of days to look back
    - **sources**: Comma-separated list of source URLs to filter by
    
    Returns list of recent articles with metadata.
    """
    try:
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
            
        # Get source list
        if sources:
            source_list = [s.strip() for s in sources.split(',')]
        else:
            # Get all sources from stats
            stats = get_article_count_by_source(days_back)
            source_list = list(stats.keys())
        
        if not source_list:
            return {
                "success": True,
                "articles": [],
                "count": 0
            }
        
        # Limit to top sources to avoid large queries
        source_list = source_list[:20]
        
        articles = get_articles_for_processing(source_list, days_back)
        
        # Limit results and format
        limited_articles = articles[:limit]
        
        return {
            "success": True,
            "articles": [
                {
                    "id": article["id"],
                    "source_url": article["source_url"],
                    "source_type": article["source_type"],
                    "title": article["title"],
                    "content": article["content"][:500] + "..." if len(article.get("content", "")) > 500 else article.get("content", ""),
                    "link": article["link"],
                    "published_date": article["published_date"].isoformat() if article.get("published_date") else None,
                    "scraped_date": article["scraped_date"].isoformat() if article.get("scraped_date") else None
                }
                for article in limited_articles
            ],
            "count": len(limited_articles),
            "total_available": len(articles)
        }
        
    except Exception as e:
        logger.error(f"API recent articles error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Web UI Routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page with data collection form"""
    try:
        # Get basic statistics for display
        stats = get_article_count_by_source(days_back=7)
        
        # Handle case where stats might be None or empty
        if stats and isinstance(stats, dict):
            total_articles = sum(stats.values())
            source_count = len(stats)
            top_sources = list(stats.items())[:5]
        else:
            total_articles = 0
            source_count = 0
            top_sources = []
        
        return templates.TemplateResponse("index.html", {
            "request": request,
            "total_articles": total_articles,
            "source_count": source_count,
            "top_sources": top_sources
        })
    except Exception as e:
        logger.error(f"Index page error: {str(e)}")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": str(e),
            "total_articles": 0,
            "source_count": 0,
            "top_sources": []
        })

@app.post("/collect", response_class=HTMLResponse)
async def web_collect_data(
    request: Request,
    sources: str = Form(...),
    days_back: int = Form(7),
    orchestrator: DataOrchestrator = Depends(get_orchestrator)
):
    """Handle form submission for data collection"""
    try:
        if not sources.strip():
            return templates.TemplateResponse("index.html", {
                "request": request,
            "error": "Please provide at least one source URL or handle",
            "total_articles": 0,
            "source_count": 0,
            "top_sources": []
        })        # Parse sources (can be newline or comma separated)
        if '\\n' in sources:
            source_list = [s.strip() for s in sources.split('\\n') if s.strip()]
        else:
            source_list = [s.strip() for s in sources.split(',') if s.strip()]
        
        # Process sources
        result = orchestrator.process_all_sources(source_list, days_back)
        
        return templates.TemplateResponse("results.html", {
            "request": request,
            "result": result
        })
        
    except Exception as e:
        logger.error(f"Web collect error: {str(e)}")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": f"Error during data collection: {str(e)}",
            "total_articles": 0,
            "source_count": 0,
            "top_sources": []
        })

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard with statistics and recent articles"""
    try:
        # Get statistics for different time periods
        stats_7d = get_article_count_by_source(7)
        stats_30d = get_article_count_by_source(30)
        
        # Handle case where stats might be None or not dict
        if stats_7d and isinstance(stats_7d, dict):
            stats_7d_list = list(stats_7d.items())
            sources = list(stats_7d.keys())[:10]
        else:
            stats_7d_list = []
            sources = []
            
        if stats_30d and isinstance(stats_30d, dict):
            stats_30d_list = list(stats_30d.items())[:10]
        else:
            stats_30d_list = []
        
        # Get recent articles
        recent_articles = get_articles_for_processing(sources, 3) if sources else []
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "stats_7d": stats_7d_list,
            "stats_30d": stats_30d_list,
            "recent_articles": recent_articles[:20]  # Limit to 20 for display
        })
        
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "error": str(e)
        })

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Starting TrendMind FastAPI application")
    
    # Create templates if they don't exist
    if not (templates_dir / "base.html").exists():
        logger.info("Creating HTML templates...")
        create_fastapi_templates()
        logger.info("Templates created successfully")

def create_fastapi_templates():
    """Create HTML templates for FastAPI"""
    
    # Base template (same as before but with FastAPI URLs)
    base_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}TrendMind Data Collector{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand" href="/">TrendMind</a>
            <div class="navbar-nav">
                <a class="nav-link" href="/">Home</a>
                <a class="nav-link" href="/dashboard">Dashboard</a>
                <a class="nav-link" href="/docs">API Docs</a>
            </div>
        </div>
    </nav>
    
    <div class="container mt-4">
        {% if error %}
            <div class="alert alert-danger alert-dismissible fade show">
                {{ error }}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        {% endif %}
        
        {% block content %}{% endblock %}
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''
    
    # Index template (updated for FastAPI)
    index_template = '''{% extends "base.html" %}

{% block title %}TrendMind - AI Trend Data Collector{% endblock %}

{% block content %}
<div class="row">
    <div class="col-md-8">
        <h1>TrendMind Data Collector</h1>
        <p class="lead">Collect and analyze AI trend data from multiple sources</p>
        
        <form method="POST" action="/collect">
            <div class="mb-3">
                <label for="sources" class="form-label">Sources (URLs or handles)</label>
                <textarea class="form-control" id="sources" name="sources" rows="10" 
                          placeholder="Enter source URLs or Twitter handles, one per line or comma-separated:&#10;&#10;https://garymarcus.substack.com/&#10;https://x.com/karpathy&#10;https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml&#10;https://x.com/sama"></textarea>
                <div class="form-text">Supports: Twitter handles, RSS feeds, Substack blogs</div>
            </div>
            
            <div class="mb-3">
                <label for="days_back" class="form-label">Days Back</label>
                <select class="form-select" id="days_back" name="days_back">
                    <option value="1">1 day</option>
                    <option value="3">3 days</option>
                    <option value="7" selected>7 days</option>
                    <option value="14">14 days</option>
                    <option value="30">30 days</option>
                </select>
            </div>
            
            <button type="submit" class="btn btn-primary">Collect Data</button>
        </form>
    </div>
    
    <div class="col-md-4">
        <div class="card">
            <div class="card-header">
                <h5>Current Statistics</h5>
            </div>
            <div class="card-body">
                <p><strong>Total Articles:</strong> {{ total_articles }}</p>
                <p><strong>Active Sources:</strong> {{ source_count }}</p>
                
                {% if top_sources %}
                <h6>Top Sources (7 days):</h6>
                <ul class="list-unstyled">
                    {% for source, count in top_sources %}
                    <li>{{ source|truncate(30) }}: {{ count }}</li>
                    {% endfor %}
                </ul>
                {% endif %}
                
                <div class="mt-3">
                    <a href="/docs" class="btn btn-outline-primary btn-sm">API Documentation</a>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}'''
    
    # Results and dashboard templates (same as before)
    results_template = '''{% extends "base.html" %}

{% block title %}Collection Results - TrendMind{% endblock %}

{% block content %}
<h1>Data Collection Results</h1>

<div class="row mb-4">
    <div class="col-md-12">
        <div class="card">
            <div class="card-header">
                <h5>Summary</h5>
            </div>
            <div class="card-body">
                <div class="row text-center">
                    <div class="col-md-2">
                        <h3>{{ result.summary.total_sources }}</h3>
                        <p>Total Sources</p>
                    </div>
                    <div class="col-md-2">
                        <h3>{{ result.summary.successful_sources }}</h3>
                        <p>Successful</p>
                    </div>
                    <div class="col-md-2">
                        <h3>{{ result.summary.total_articles }}</h3>
                        <p>Total Articles</p>
                    </div>
                    <div class="col-md-3">
                        <h3>{{ result.summary.new_articles }}</h3>
                        <p>New Articles</p>
                    </div>
                    <div class="col-md-3">
                        <h3>{{ result.summary.cached_articles }}</h3>
                        <p>Cached Articles</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="row">
    <div class="col-md-12">
        <h3>Source Details</h3>
        {% for source in result.sources %}
        <div class="card mb-3">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span>
                    <strong>{{ source.source_url }}</strong>
                    <span class="badge bg-secondary">{{ source.source_type }}</span>
                </span>
                <span class="text-muted">{{ "%.2f"|format(source.processing_time) }}s</span>
            </div>
            <div class="card-body">
                {% if source.error %}
                    <div class="alert alert-danger">{{ source.error }}</div>
                {% else %}
                    <p>
                        <strong>Articles:</strong> {{ source.articles|length }}
                        ({{ source.new_count }} new, {{ source.cached_count }} cached)
                    </p>
                    
                    {% if source.articles %}
                    <details>
                        <summary>View Articles ({{ source.articles|length }})</summary>
                        <div class="mt-2">
                            {% for article in source.articles[:5] %}
                            <div class="border-start border-3 border-primary ps-3 mb-2">
                                <h6>{{ article.title or "No Title" }}</h6>
                                <small class="text-muted">{{ article.published or "No Date" }}</small>
                                <p>{{ article.content|truncate(200) }}</p>
                            </div>
                            {% endfor %}
                            {% if source.articles|length > 5 %}
                            <p><em>... and {{ source.articles|length - 5 }} more articles</em></p>
                            {% endif %}
                        </div>
                    </details>
                    {% endif %}
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<div class="mt-4">
    <a href="/" class="btn btn-primary">Collect More Data</a>
    <a href="/dashboard" class="btn btn-outline-primary">View Dashboard</a>
</div>
{% endblock %}'''
    
    dashboard_template = '''{% extends "base.html" %}

{% block title %}Dashboard - TrendMind{% endblock %}

{% block content %}
<h1>TrendMind Dashboard</h1>

{% if error %}
    <div class="alert alert-danger">{{ error }}</div>
{% else %}
<div class="row mb-4">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h5>Last 7 Days</h5>
            </div>
            <div class="card-body">
                {% if stats_7d %}
                    {% for source, count in stats_7d %}
                    <div class="d-flex justify-content-between">
                        <span>{{ source|truncate(40) }}</span>
                        <span class="badge bg-primary">{{ count }}</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <p>No data available</p>
                {% endif %}
            </div>
        </div>
    </div>
    
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h5>Last 30 Days</h5>
            </div>
            <div class="card-body">
                {% if stats_30d %}
                    {% for source, count in stats_30d %}
                    <div class="d-flex justify-content-between">
                        <span>{{ source|truncate(40) }}</span>
                        <span class="badge bg-success">{{ count }}</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <p>No data available</p>
                {% endif %}
            </div>
        </div>
    </div>
</div>

{% if recent_articles %}
<div class="row">
    <div class="col-md-12">
        <h3>Recent Articles</h3>
        {% for article in recent_articles %}
        <div class="card mb-2">
            <div class="card-body">
                <h6>{{ article.get('title') or "No Title" }}</h6>
                <small class="text-muted">
                    {{ article.get('source_url') }} - {{ article.get('published_date') }}
                </small>
                <p>{{ (article.get('content') or '')|truncate(200) }}</p>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endif %}
{% endif %}
{% endblock %}'''
    
    # Write templates to files
    (templates_dir / "base.html").write_text(base_template)
    (templates_dir / "index.html").write_text(index_template)
    (templates_dir / "results.html").write_text(results_template)
    (templates_dir / "dashboard.html").write_text(dashboard_template)

if __name__ == "__main__":
    print("Starting TrendMind FastAPI Server...")
    print("Web UI: http://localhost:8080")
    print("API Docs: http://localhost:8080/docs")
    print("Press Ctrl+C to stop")
    
    uvicorn.run(
        "fastapi_frontend:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )