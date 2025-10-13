from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from enum import Enum

from src.scraper import scrape_source
from src.clustering import cluster_articles, summarize_cluster, generate_final_overview
from utils.logger import get_logger

app = FastAPI(title="AI News Tracker API")
logger = get_logger("api")

# In-memory job storage (use Redis/DB for production)
jobs = {}


class JobStatus(str, Enum):
    PENDING = "pending"
    SCRAPING = "scraping"
    CLUSTERING = "clustering"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


class SourcesRequest(BaseModel):
    sources: List[str]
    days_back: int = 7
    
    class Config:
        json_schema_extra = {
            "example": {
                "sources": [
                    "https://x.com/karpathy",
                    "https://garymarcus.substack.com/feed",
                    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"
                ],
                "days_back": 7
            }
        }


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ============================================================================
# OPTION 1: SYNCHRONOUS ENDPOINT (Simple, but blocks)
# ============================================================================

@app.post("/analyze/sync")
async def analyze_sync(request: SourcesRequest):
    """
    Synchronous analysis: scrape, cluster, and summarize all in one request.
    
    ⚠️ Warning: This can take 30-60 seconds for many sources.
    Use /analyze/async for better UX.
    """
    logger.info(f"Sync analysis requested for {len(request.sources)} sources")
    
    try:
        # Step 1: Scrape all sources
        logger.info("Starting scraping phase")
        all_articles = []
        scraping_summary = {
            "total_sources": len(request.sources),
            "new_articles": 0,
            "cached_articles": 0
        }
        
        for source in request.sources:
            result = scrape_source(source, days_back=request.days_back)
            all_articles.extend(result['results'])
            scraping_summary['new_articles'] += result.get('new_count', 0)
            scraping_summary['cached_articles'] += result.get('cached_count', 0)
        
        if not all_articles:
            raise HTTPException(status_code=404, detail="No articles found")
        
        # Step 2: Cluster articles
        logger.info(f"Clustering {len(all_articles)} articles")
        clusters = cluster_articles(all_articles)
        
        # Step 3: Summarize each cluster
        logger.info(f"Summarizing {len(clusters)} clusters")
        cluster_summaries = []
        for cluster in clusters:
            summary = summarize_cluster(cluster)
            cluster_summaries.append(summary)
        
        # Step 4: Generate final overview
        logger.info("Generating final overview")
        final_overview = generate_final_overview(cluster_summaries, top_n=5)
        
        return {
            "status": "completed",
            "scraping_summary": scraping_summary,
            "total_articles": len(all_articles),
            "clusters_found": len(clusters),
            "final_overview": final_overview,
            "cluster_details": cluster_summaries
        }
        
    except Exception as e:
        logger.error(f"Sync analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# OPTION 2: ASYNCHRONOUS ENDPOINTS (Better UX)
# ============================================================================

def process_sources_background(job_id: str, sources: List[str], days_back: int):
    """
    Background task that processes sources asynchronously.
    Updates job status as it progresses.
    """
    logger.info(f"Background job {job_id} started")
    
    try:
        # Update status: Scraping
        jobs[job_id]["status"] = JobStatus.SCRAPING
        jobs[job_id]["progress"] = "Collecting articles from sources..."
        
        all_articles = []
        scraping_summary = {
            "total_sources": len(sources),
            "new_articles": 0,
            "cached_articles": 0,
            "per_source": {}
        }
        
        for i, source in enumerate(sources):
            jobs[job_id]["progress"] = f"Scraping source {i+1}/{len(sources)}: {source}"
            logger.info(f"Job {job_id}: Scraping {source}")
            
            result = scrape_source(source, days_back=days_back)
            all_articles.extend(result['results'])
            
            scraping_summary['new_articles'] += result.get('new_count', 0)
            scraping_summary['cached_articles'] += result.get('cached_count', 0)
            scraping_summary['per_source'][source] = {
                "articles": len(result['results']),
                "new": result.get('new_count', 0),
                "cached": result.get('cached_count', 0)
            }
        
        if not all_articles:
            jobs[job_id]["status"] = JobStatus.FAILED
            jobs[job_id]["error"] = "No articles found from any source"
            return
        
        # Update status: Clustering
        jobs[job_id]["status"] = JobStatus.CLUSTERING
        jobs[job_id]["progress"] = f"Clustering {len(all_articles)} articles..."
        logger.info(f"Job {job_id}: Clustering {len(all_articles)} articles")
        
        clusters = cluster_articles(all_articles)
        
        # Update status: Summarizing
        jobs[job_id]["status"] = JobStatus.SUMMARIZING
        jobs[job_id]["progress"] = f"Summarizing {len(clusters)} topic clusters..."
        logger.info(f"Job {job_id}: Summarizing {len(clusters)} clusters")
        
        cluster_summaries = []
        for i, cluster in enumerate(clusters):
            jobs[job_id]["progress"] = f"Summarizing cluster {i+1}/{len(clusters)}: {cluster['topic_name']}"
            summary = summarize_cluster(cluster)
            cluster_summaries.append(summary)
        
        # Generate final overview
        jobs[job_id]["progress"] = "Generating final overview..."
        logger.info(f"Job {job_id}: Generating final overview")
        
        final_overview = generate_final_overview(cluster_summaries, top_n=5)
        
        # Mark as completed
        jobs[job_id]["status"] = JobStatus.COMPLETED
        jobs[job_id]["completed_at"] = datetime.now()
        jobs[job_id]["result"] = {
            "scraping_summary": scraping_summary,
            "total_articles": len(all_articles),
            "clusters_found": len(clusters),
            "final_overview": final_overview,
            "cluster_details": cluster_summaries
        }
        
        logger.info(f"Job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        jobs[job_id]["status"] = JobStatus.FAILED
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["completed_at"] = datetime.now()


@app.post("/analyze/async", response_model=JobResponse)
async def analyze_async(request: SourcesRequest, background_tasks: BackgroundTasks):
    """
    Start asynchronous analysis job.
    Returns immediately with job_id.
    Use /status/{job_id} to check progress.
    """
    job_id = str(uuid.uuid4())
    
    logger.info(f"Async job {job_id} created for {len(request.sources)} sources")
    
    # Create job entry
    jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.PENDING,
        "progress": "Job queued",
        "created_at": datetime.now(),
        "sources": request.sources,
        "days_back": request.days_back,
        "completed_at": None,
        "result": None,
        "error": None
    }
    
    # Start background task
    background_tasks.add_task(
        process_sources_background,
        job_id,
        request.sources,
        request.days_back
    )
    
    return JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=f"Analysis job started. Check status at /status/{job_id}"
    )


@app.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Check the status of an analysis job.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress=job.get("progress"),
        created_at=job["created_at"],
        completed_at=job.get("completed_at"),
        result=job.get("result"),
        error=job.get("error")
    )


@app.get("/results/{job_id}")
async def get_job_results(job_id: str):
    """
    Get the final results of a completed job.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed yet. Current status: {job['status']}"
        )
    
    return job["result"]


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """API health check and info."""
    return {
        "name": "AI News Tracker API",
        "version": "2.0",
        "endpoints": {
            "sync": "/analyze/sync (POST)",
            "async": "/analyze/async (POST)",
            "status": "/status/{job_id} (GET)",
            "results": "/results/{job_id} (GET)"
        }
    }


@app.get("/jobs")
async def list_jobs(limit: int = 10):
    """
    List recent jobs.
    """
    recent_jobs = sorted(
        jobs.values(),
        key=lambda x: x["created_at"],
        reverse=True
    )[:limit]
    
    return {
        "total_jobs": len(jobs),
        "recent_jobs": [
            {
                "job_id": job["job_id"],
                "status": job["status"],
                "created_at": job["created_at"],
                "sources_count": len(job["sources"])
            }
            for job in recent_jobs
        ]
    }


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """
    Delete a job from memory.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    del jobs[job_id]
    logger.info(f"Job {job_id} deleted")
    
    return {"message": f"Job {job_id} deleted successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)