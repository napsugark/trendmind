#!/usr/bin/env python3
"""
TrendMind Backend API

Provides AI-powered trend analysis through a complete workflow:
1. Data Collection (Scraping)
2. Topic Clustering (LLM)
3. Summarization (LLM) 
4. Structured Results

Usage:
    python main_api.py
    
Then visit:
    - API Docs: http://localhost:8000/docs
    - Health Check: http://localhost:8000/health
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
import uvicorn

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

from get_data import DataOrchestrator
from src.db_postgres import get_article_count_by_source, get_articles_for_processing
from src.clustering import cluster_articles
from src.summarizer import summarize_clusters
from utils.logger import get_logger

# Initialize FastAPI app
app = FastAPI(
    title="TrendMind Backend API",
    description="AI-powered trend analysis: Scrape → Cluster → Summarize → Results",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = get_logger("main_api")

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

class AnalyzeRequest(BaseModel):
    """Request model for trend analysis"""
    sources: List[str]
    days_back: Optional[int] = 7
    max_clusters: Optional[int] = 5
    
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

class ClusterSummary(BaseModel):
    """Summary of a topic cluster"""
    topic_name: str
    article_count: int
    summary: str
    key_points: List[str]
    sources: List[str]

class AnalyzeResponse(BaseModel):
    """Response model for trend analysis"""
    success: bool
    clusters: List[ClusterSummary]
    total_articles: int
    processing_time: float
    timestamp: str

# Dependency to get orchestrator instance
def get_orchestrator():
    """Dependency to provide DataOrchestrator instance"""
    return DataOrchestrator()

# Main Analysis Endpoint
@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_trends(
    request: AnalyzeRequest,
    orchestrator: DataOrchestrator = Depends(get_orchestrator)
):
    """
    Complete trend analysis workflow:
    1. Scrape data from sources
    2. Cluster articles by topic using LLM
    3. Generate summaries for each cluster
    4. Return structured results
    
    - **sources**: List of source URLs or Twitter handles
    - **days_back**: Number of days to look back (1-365)
    - **max_clusters**: Maximum number of topic clusters (default: 5)
    
    Returns clustered and summarized trend analysis.
    """
    import time
    start_time = time.time()
    
    try:
        logger.info(f"Starting trend analysis: {len(request.sources)} sources, {request.days_back} days, max {request.max_clusters} clusters")
        
        # Step 1: Scrape data
        logger.info("Step 1: Scraping data from sources...")
        scrape_result = orchestrator.process_all_sources(request.sources, request.days_back)
        
        # Collect all articles
        all_articles = []
        for source_result in scrape_result['sources']:
            all_articles.extend(source_result['articles'])
        
        if not all_articles:
            return AnalyzeResponse(
                success=True,
                clusters=[],
                total_articles=0,
                processing_time=time.time() - start_time,
                timestamp=datetime.utcnow().isoformat()
            )
        
        logger.info(f"Collected {len(all_articles)} articles")
        
        # Step 2: Cluster articles by topic
        logger.info("Step 2: Clustering articles by topic...")
        clusters = cluster_articles(all_articles, max_clusters=request.max_clusters)
        
        # Step 3: Summarize each cluster
        logger.info("Step 3: Generating cluster summaries...")
        cluster_summaries = summarize_clusters(clusters)
        
        # Step 4: Format response
        response_clusters = []
        for cluster_summary in cluster_summaries:
            response_clusters.append(ClusterSummary(
                topic_name=cluster_summary['topic_name'],
                article_count=cluster_summary['article_count'],
                summary=cluster_summary['summary'],
                key_points=cluster_summary['key_points'],
                sources=cluster_summary['sources']
            ))
        
        processing_time = time.time() - start_time
        logger.info(f"Analysis completed in {processing_time:.2f}s: {len(response_clusters)} clusters")
        
        return AnalyzeResponse(
            success=True,
            clusters=response_clusters,
            total_articles=len(all_articles),
            processing_time=processing_time,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Legacy API Routes (for backward compatibility)
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

# Utility Endpoints

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
    logger.info("Starting TrendMind Backend API")
    logger.info("Workflow: Scrape → Cluster → Summarize → Results")

if __name__ == "__main__":
    print("Starting TrendMind Backend API...")
    print("API Docs: http://localhost:8000/docs")
    print("Health Check: http://localhost:8000/health")
    print("Main Endpoint: POST /analyze")
    print("Press Ctrl+C to stop")
    
    uvicorn.run(
        "main_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )