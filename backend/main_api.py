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
templates_dir = Path("frontend/templates")
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory="frontend/templates")

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
    # if not (templates_dir / "base.html").exists():
    #     logger.info("Creating HTML templates...")
    #     create_fastapi_templates()
    #     logger.info("Templates created successfully")

if __name__ == "__main__":
    print("Starting TrendMind FastAPI Server...")
    print("Web UI: http://localhost:8000")
    print("API Docs: http://localhost:8000/docs")
    print("Press Ctrl+C to stop")
    
    uvicorn.run(
        "fastapi_frontend:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )