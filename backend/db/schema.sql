-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- 1. CORE SYSTEM & ANALYTICS
-- ==========================================

-- Table: users (Stores Auth linking and system handles)
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    firebase_uid    VARCHAR(128) UNIQUE NOT NULL, -- UID from Firebase Auth
    username        VARCHAR(50) UNIQUE,           -- User-defined handle
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: user_profiles (Demographic data for Analytics)
CREATE TABLE IF NOT EXISTS user_profiles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    date_of_birth   DATE,
    avatar_url      TEXT,
    address         TEXT,         -- Combined House No, Village, Road
    sub_district    VARCHAR(100), -- แขวง/ตำบล
    district        VARCHAR(100), -- เขต/อำเภอ
    province        VARCHAR(100), -- จังหวัด
    postal_code     VARCHAR(10),
    current_school  VARCHAR(255),
    gpax            NUMERIC(3, 2), -- 0.00 to 4.00
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 2. AI 1: THAI CAREER DREAMER & CATALOG
-- ==========================================

-- Table: user_career_profiles (AI-extracted traits)
CREATE TABLE IF NOT EXISTS user_career_profiles (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    personality_summary TEXT,
    strengths           JSONB, -- List of strengths
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: industry_groups (Master Data for Industries)
CREATE TABLE IF NOT EXISTS industry_groups (
    id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name    VARCHAR(150) UNIQUE NOT NULL -- e.g., 'งานไอที งานเทคโนโลยีสื่อสาร'
);

-- Table: career_catalog (Standardized Job Data from JobsDB)
CREATE TABLE IF NOT EXISTS career_catalog (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    industry_group_id       UUID REFERENCES industry_groups(id) ON DELETE SET NULL,
    title                   VARCHAR(255) NOT NULL,
    overview_description    TEXT,
    avg_salary_thb          INTEGER,
    active_job_openings     INTEGER DEFAULT 0,
    responsibilities        JSONB, -- List of responsibilities
    education_requirements  JSONB, -- Steps to become this career
    top_skills              JSONB, -- Required skills list
    last_scraped_at         TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: user_recommended_careers (Link users to matched careers)
CREATE TABLE IF NOT EXISTS user_recommended_careers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    career_id       UUID REFERENCES career_catalog(id) ON DELETE CASCADE,
    match_score     FLOAT,
    ai_reasoning    TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, career_id)
);

-- ==========================================
-- 3. TCAS KNOWLEDGE GRAPH (Hierarchical)
-- ==========================================

-- Table: universities
CREATE TABLE IF NOT EXISTS universities (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) UNIQUE NOT NULL,
    location    TEXT
);

-- Table: faculties
CREATE TABLE IF NOT EXISTS faculties (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    university_id   UUID REFERENCES universities(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL
);

-- Table: majors
CREATE TABLE IF NOT EXISTS majors (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    faculty_id  UUID REFERENCES faculties(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    field       VARCHAR(100) -- e.g., 'Engineering', 'Science'
);

-- Table: tcas_rounds
CREATE TABLE IF NOT EXISTS tcas_rounds (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    major_id        UUID REFERENCES majors(id) ON DELETE CASCADE,
    round_number    INTEGER NOT NULL CHECK (round_number BETWEEN 1 AND 4),
    year            INTEGER NOT NULL
);

-- Table: admission_projects (The "Tracks" or "Quota" projects)
CREATE TABLE IF NOT EXISTS admission_projects (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tcas_round_id       UUID REFERENCES tcas_rounds(id) ON DELETE CASCADE,
    project_name        VARCHAR(255) NOT NULL, -- e.g., 'โครงการจุฬาฯ-ชนบท'
    seats               INTEGER,
    gpax_min            NUMERIC(3, 2),
    accepts_ged         BOOLEAN DEFAULT FALSE,
    specific_conditions TEXT,
    source_url          TEXT
);

-- Table: subject_requirements (Specific score requirements for each project)
CREATE TABLE IF NOT EXISTS subject_requirements (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admission_project_id UUID REFERENCES admission_projects(id) ON DELETE CASCADE,
    subject              VARCHAR(150) NOT NULL, -- e.g., 'TGAT', 'A-Level Math'
    min_score            FLOAT,
    weight_percent       FLOAT
);

-- ==========================================
-- 4. AI 2: TCAS RAG & COMPARATOR
-- ==========================================

-- Table: user_saved_majors (User's basket of interested majors)
CREATE TABLE IF NOT EXISTS user_saved_majors (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    major_id    UUID REFERENCES majors(id) ON DELETE CASCADE,
    notes       TEXT, -- Student's personal notes on this major
    saved_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, major_id)
);

-- ==========================================
-- 5. CHAT ENGINE (Separated by AI Mode)
-- ==========================================

-- Table: chat_sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    ai_mode     VARCHAR(20) NOT NULL, -- 'dreamer' OR 'tcas_rag'
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: chat_messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL, -- 'user' OR 'assistant'
    content     TEXT NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- 6. STUDENT TEST SCORES & HISTORICAL DATA
-- ==========================================

-- Table: user_test_scores (Student's actual exam results)
-- One row per subject per exam year per user. Used by the eligibility engine
-- to match against subject_requirements.min_score.
CREATE TABLE IF NOT EXISTS user_test_scores (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    subject     VARCHAR(50) NOT NULL, -- Must match controlled vocabulary in DATA_CONTRACT §7.1
    score       NUMERIC(6, 2) NOT NULL,
    exam_year   INTEGER NOT NULL,
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, subject, exam_year)
);

-- Table: historical_cutoffs (SCD Type 2 — year-over-year cutoff statistics)
-- Producer emits current values; ingestion script manages effective_from/effective_to.
-- Used to show safety margin trends ("last year's cutoff was X, you're at Y").
CREATE TABLE IF NOT EXISTS historical_cutoffs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admission_project_id UUID REFERENCES admission_projects(id) ON DELETE CASCADE,
    year                INTEGER NOT NULL,        -- TCAS admission cycle year
    score_type          VARCHAR(50) NOT NULL,    -- Controlled vocab: DATA_CONTRACT §7.2
    min_admitted_score  NUMERIC(8, 2),
    max_admitted_score  NUMERIC(8, 2),
    median_score        NUMERIC(8, 2),
    applicants_count    INTEGER,
    accepted_count      INTEGER,
    source_url          TEXT NOT NULL,
    effective_from      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    effective_to        TIMESTAMP WITH TIME ZONE,  -- NULL = current record
    UNIQUE(admission_project_id, year, score_type, effective_from)
);

-- ==========================================
-- INDEXES FOR PERFORMANCE
-- ==========================================
CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_career_catalog_industry ON career_catalog(industry_group_id);
CREATE INDEX IF NOT EXISTS idx_admission_projects_round ON admission_projects(tcas_round_id);
CREATE INDEX IF NOT EXISTS idx_user_test_scores_user ON user_test_scores(user_id);
CREATE INDEX IF NOT EXISTS idx_historical_cutoffs_project ON historical_cutoffs(admission_project_id);
CREATE INDEX IF NOT EXISTS idx_historical_cutoffs_current ON historical_cutoffs(admission_project_id, year, score_type) WHERE effective_to IS NULL;

-- ==========================================
-- ALTER: admission_projects — round_type + round_metadata
-- ==========================================

ALTER TABLE admission_projects
    ADD COLUMN IF NOT EXISTS round_type      VARCHAR(30),
    ADD COLUMN IF NOT EXISTS round_metadata  JSONB;

-- Trigger: round_type must match tcas_rounds.round_number (NULL = permissive).
CREATE OR REPLACE FUNCTION check_admission_round_type_matches()
RETURNS TRIGGER AS $$
DECLARE
    expected_round INTEGER;
    actual_round   INTEGER;
BEGIN
    IF NEW.round_type IS NULL THEN
        RETURN NEW;
    END IF;

    expected_round := CASE NEW.round_type
        WHEN 'portfolio'  THEN 1
        WHEN 'quota'      THEN 2
        WHEN 'admission'  THEN 3
        WHEN 'direct'     THEN 4
        ELSE NULL
    END;

    IF expected_round IS NULL THEN
        RAISE EXCEPTION 'admission_projects.round_type must be one of portfolio|quota|admission|direct, got %', NEW.round_type;
    END IF;

    SELECT round_number INTO actual_round
      FROM tcas_rounds
     WHERE id = NEW.tcas_round_id;

    IF actual_round IS DISTINCT FROM expected_round THEN
        RAISE EXCEPTION 'admission_projects.round_type=% expects tcas_rounds.round_number=%, got %',
            NEW.round_type, expected_round, actual_round;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_admission_round_type_matches ON admission_projects;
CREATE TRIGGER trg_admission_round_type_matches
    BEFORE INSERT OR UPDATE ON admission_projects
    FOR EACH ROW
    EXECUTE FUNCTION check_admission_round_type_matches();
