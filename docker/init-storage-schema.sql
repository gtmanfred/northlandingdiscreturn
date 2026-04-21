-- Create the storage schema required by supabase/storage-api.
-- This provides the base tables that the storage-api tenant migrations build upon.
-- Columns added by individual migrations (0007, 0011, 0012, 0013, 0015, 0016)
-- are intentionally omitted here and will be added by the storage-api on startup.

CREATE SCHEMA IF NOT EXISTS storage;

CREATE TABLE IF NOT EXISTS storage.buckets (
    id text NOT NULL PRIMARY KEY,
    name text NOT NULL,
    owner uuid,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS storage.objects (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    bucket_id text REFERENCES storage.buckets(id),
    name text,
    owner uuid,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    last_accessed_at timestamptz DEFAULT now(),
    metadata jsonb,
    UNIQUE (bucket_id, name)
);

CREATE TABLE IF NOT EXISTS storage.migrations (
    id integer PRIMARY KEY,
    name varchar(100) UNIQUE NOT NULL,
    hash varchar(40) NOT NULL,
    executed_at timestamp DEFAULT current_timestamp
);
