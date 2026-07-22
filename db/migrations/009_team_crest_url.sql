-- Team crest images for the frontend. Nullable: historical teams that
-- never appear in current-season football-data.org data (the only source
-- with crest images) won't have one. Every fixture shown in the frontend
-- is a current-season team resolved via football-data.org, so this covers
-- everything actually displayed.
ALTER TABLE teams ADD COLUMN crest_url TEXT;
