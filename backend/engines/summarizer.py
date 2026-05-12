import json
import logging
from uuid import UUID

from db.postgres import execute
from memory.long_term_memory import get_messages
from models.model_router import get_model_config
from models.ollama_client import chat

logger = logging.getLogger(__name__)

async def summarize_session(user_id: UUID, session_id: UUID) -> None:
    """Summarize a chat session and extract structural insights using Typhoon2.
    
    The extracted JSON is saved to user_career_profiles.
    """
    messages = await get_messages(session_id)
    if not messages:
        logger.info(f"No messages found for session {session_id}, skipping summarization.")
        return

    # Format conversation history
    chat_history = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        chat_history += f"{role}: {content}\n"

    system_prompt = (
        "You are an expert AI extraction system for Thai high school students (TCAS system).\n"
        "Analyze the following conversation history between a student and an AI advisor.\n"
        "Your task is to extract structured profile information and return EXACTLY a valid JSON object.\n\n"
        "EXPECTED JSON SCHEMA:\n"
        "{\n"
        '  "personality_summary": "A 2-3 sentence summary of the user\'s personality, academic habits, and traits in Thai",\n'
        '  "strengths": {\n'
        '    "skills": ["Skill 1", "Skill 2"],\n'
        '    "explored_majors": ["คณะวิศวกรรมศาสตร์", "คณะวิทยาศาสตร์"],\n'
        '    "career_interests": ["Programmer", "Data Scientist"]\n'
        "  },\n"
        '  "user_profile_updates": {\n'
        '    "current_school": "ชื่อโรงเรียน (ถ้ามี)",\n'
        '    "gpax": 3.50\n'
        "  }\n"
        "}\n\n"
        "INSTRUCTIONS:\n"
        "1. Extract the majors and careers the user explicitly mentioned or showed interest in.\n"
        "2. If the user mentions their GPAX or current school, extract it into `user_profile_updates`.\n"
        "3. If there is not enough information for a field, provide an empty list `[]`, empty string `\"\"`, or `null`.\n"
        "4. Output MUST be valid JSON only, without any markdown formatting like ```json ... ```."
    )

    try:
        cfg = get_model_config("dreamer_chat")
        
        # We enforce a strict JSON output by prompting.
        response_text = await chat(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Conversation History:\n{chat_history}"}
            ],
            temperature=0.1,  # Lower temperature for extraction
            top_p=0.9,
            max_tokens=500
        )
        
        # Clean up response text to ensure it's JSON (sometimes models add markdown formatting)
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        extracted_data = json.loads(response_text)
        
        personality_summary = extracted_data.get("personality_summary", "")
        strengths = extracted_data.get("strengths", {})

        # Ensure user_career_profiles row exists or update it
        await execute(
            """
            INSERT INTO user_career_profiles (user_id, personality_summary, strengths, updated_at)
            VALUES ($1, $2, $3::jsonb, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                personality_summary = EXCLUDED.personality_summary,
                strengths = EXCLUDED.strengths,
                updated_at = EXCLUDED.updated_at
            """,
            user_id,
            personality_summary,
            json.dumps(strengths)
        )
        
        # Update user_profiles if new data is found
        user_profile_updates = extracted_data.get("user_profile_updates", {})
        if user_profile_updates:
            current_school = user_profile_updates.get("current_school")
            gpax = user_profile_updates.get("gpax")
            
            set_clauses = []
            values = [user_id]
            if current_school and str(current_school).strip():
                values.append(str(current_school).strip())
                set_clauses.append(f"current_school = ${len(values)}")
            
            if gpax is not None and str(gpax).strip():
                try:
                    gpax_float = float(gpax)
                    values.append(gpax_float)
                    set_clauses.append(f"gpax = ${len(values)}")
                except ValueError:
                    pass
            
            if set_clauses:
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                query = f"""
                    INSERT INTO user_profiles (user_id, current_school, gpax, updated_at)
                    VALUES ($1, {f'${len(values)-1}' if current_school else 'NULL'}, {f'${len(values)}' if gpax else 'NULL'}, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE SET {', '.join(set_clauses)}
                """
                # Handle the dynamic INSERT VALUES correctly or just do an UPDATE since we have ON CONFLICT
                # Actually, simpler is to do an UPDATE since profile creation is usually handled elsewhere.
                # If we want to be safe, we can just do UPDATE.
                update_query = f"UPDATE user_profiles SET {', '.join(set_clauses)} WHERE user_id = $1"
                await execute(update_query, *values)

        logger.info(f"Successfully summarized and saved profile for user {user_id} from session {session_id}")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from summarizer output for session {session_id}: {e}")
    except Exception as e:
        logger.error(f"Error during session summarization for session {session_id}: {e}")
