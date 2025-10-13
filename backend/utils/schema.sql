-- Create articles table for AI News Tracker
CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL,      -- 'twitter', 'rss', 'substack'
    source_url VARCHAR(500) NOT NULL,      -- full source URL/handle
    title TEXT,                            -- NULL for tweets
    content TEXT NOT NULL,
    link VARCHAR(500),                     -- article URL, NULL for tweets
    published_date TIMESTAMP,              -- when content was published
    scraped_date TIMESTAMP DEFAULT NOW(),  -- when we scraped it
    
    -- Prevent duplicate articles
    -- For tweets: unique by source_url + published_date
    -- For articles: unique by source_url + published_date
    CONSTRAINT unique_article UNIQUE(source_url, published_date)
);

-- Index for fast lookups by source and date range
CREATE INDEX IF NOT EXISTS idx_source_date 
ON articles(source_url, published_date DESC);

-- Index for checking freshness of scraped data
CREATE INDEX IF NOT EXISTS idx_scraped_date 
ON articles(scraped_date DESC);

-- Index for source type filtering
CREATE INDEX IF NOT EXISTS idx_source_type 
ON articles(source_type);

-- Optional: Add a table to track scraping stats/history
CREATE TABLE IF NOT EXISTS scraping_logs (
    id SERIAL PRIMARY KEY,
    source_url VARCHAR(500) NOT NULL,
    scrape_timestamp TIMESTAMP DEFAULT NOW(),
    articles_found INTEGER DEFAULT 0,
    articles_inserted INTEGER DEFAULT 0,
    errors TEXT,
    duration_seconds DECIMAL(10, 2)
);

CREATE INDEX IF NOT EXISTS idx_scraping_logs_source 
ON scraping_logs(source_url, scrape_timestamp DESC);

-- View to see latest scraping activity per source
CREATE OR REPLACE VIEW latest_scrapes AS
SELECT DISTINCT ON (source_url)
    source_url,
    scrape_timestamp,
    articles_found,
    articles_inserted
FROM scraping_logs
ORDER BY source_url, scrape_timestamp DESC;

-- View to see article counts by source
CREATE OR REPLACE VIEW article_counts AS
SELECT 
    source_type,
    source_url,
    COUNT(*) as total_articles,
    MAX(published_date) as latest_article,
    MAX(scraped_date) as last_scraped
FROM articles
GROUP BY source_type, source_url
ORDER BY total_articles DESC;