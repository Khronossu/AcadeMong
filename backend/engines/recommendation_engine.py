"""Major Recommendation Engine — Two-Stage Filter & Score."""

import json
from typing import Any
from uuid import UUID

from db.postgres import fetch, fetchrow

async def recommend_majors(
    user_id: UUID,
    interests: list[str] = None,
    preferred_universities: list[str] = None,
    limit: int = 5
) -> list[dict[str, Any]]:
    """Recommend majors based on Two-Stage rule-based scoring (0-100 scale)."""
    
    # 1. Fetch user profile
    profile = await fetchrow("SELECT gpax FROM user_profiles WHERE user_id = $1", user_id)
    gpax = float(profile["gpax"]) if profile and profile["gpax"] else 0.0

    # 2. Fetch test scores
    scores_rows = await fetch("SELECT subject, score FROM user_test_scores WHERE user_id = $1", user_id)
    user_scores = {row["subject"]: float(row["score"]) for row in scores_rows}

    # 3. Fetch all majors and projects via CTE
    query = """
        SELECT 
            m.id as major_id, m.name as major_name, m.field as major_field,
            f.name as faculty_name, u.name as university_name,
            ap.id as project_id, ap.project_name, ap.gpax_min,
            json_agg(
                json_build_object('subject', sr.subject, 'min_score', sr.min_score, 'weight', sr.weight_percent)
            ) as reqs
        FROM majors m
        JOIN faculties f ON m.faculty_id = f.id
        JOIN universities u ON f.university_id = u.id
        JOIN tcas_rounds tr ON tr.major_id = m.id
        JOIN admission_projects ap ON ap.tcas_round_id = tr.id
        LEFT JOIN subject_requirements sr ON sr.admission_project_id = ap.id
        GROUP BY m.id, m.name, m.field, f.name, u.name, ap.id, ap.project_name, ap.gpax_min
    """
    projects = await fetch(query)

    results = []
    
    for p in projects:
        # ----------------------------------------------------
        # STAGE 1: Hard Filtering
        # ----------------------------------------------------
        req_gpax = float(p["gpax_min"]) if p["gpax_min"] else 0.0
        if gpax > 0 and gpax < req_gpax:
            continue  # Drop: GPAX too low

        # Parse subject reqs (handle the case where json_agg returns [ { subject: null } ] or a JSON string)
        raw_reqs = p["reqs"]
        if isinstance(raw_reqs, str):
            raw_reqs = json.loads(raw_reqs)
        raw_reqs = raw_reqs or []
        reqs = [r for r in raw_reqs if isinstance(r, dict) and r.get("subject")]

        failed_subject = False
        for req in reqs:
            min_score = float(req.get("min_score") or 0.0)
            subj = req["subject"]
            user_score = user_scores.get(subj, 0.0)
            if user_score < min_score:
                failed_subject = True
                break
                
        if failed_subject:
            continue  # Drop: Failed a subject minimum
            
        # ----------------------------------------------------
        # STAGE 2: Weighted Scoring (Max 100 Points)
        # ----------------------------------------------------
        score = 0.0
        
        # 1. Academic Fit (Max 50)
        if reqs:
            # We scale it: (calculated_score / max_possible_score) * 50
            # Assuming sum of weights is 100:
            academic_sum = 0.0
            for req in reqs:
                subj = req["subject"]
                w = float(req.get("weight") or 0.0)
                uscore = user_scores.get(subj, 0.0)
                academic_sum += (uscore / 100.0) * w
                
            score += academic_sum * 0.5  # Scale 100 max to 50 max
        else:
            # If no subject requirements, grant 35/50 as a baseline if GPAX passed.
            score += 35.0
            
        # 2. Interest Match (Max 30)
        if interests:
            major_name = (p["major_name"] or "").lower()
            major_field = (p["major_field"] or "").lower()
            if any(i.lower() in major_name or i.lower() in major_field for i in interests):
                score += 30.0
                
        # 3. University Preference (Max 20)
        if preferred_universities:
            uni_name = (p["university_name"] or "").lower()
            if any(u.lower() in uni_name for u in preferred_universities):
                score += 20.0
                
        results.append({
            "major_name": p["major_name"],
            "faculty_name": p["faculty_name"],
            "university_name": p["university_name"],
            "project_name": p["project_name"],
            "fit_score": round(score, 2)
        })

    # Sort descending by score
    results.sort(key=lambda x: x["fit_score"], reverse=True)
    
    # Deduplicate by major/university/faculty so we don't spam 5 rounds of the same major
    seen = set()
    top_picks = []
    for r in results:
        identifier = f"{r['university_name']}-{r['faculty_name']}-{r['major_name']}"
        if identifier not in seen:
            seen.add(identifier)
            top_picks.append(r)
            if len(top_picks) >= limit:
                break
                
    return top_picks
