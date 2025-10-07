CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    source_url TEXT,
    title TEXT,
    content TEXT,
    published TIMESTAMP
);
