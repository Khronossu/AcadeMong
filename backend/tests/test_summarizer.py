import json
import pytest
from unittest.mock import patch
from db.postgres import fetchrow
from engines.summarizer import summarize_session
from memory.long_term_memory import create_chat_session, save_message

@pytest.mark.asyncio
async def test_summarize_session_writes_to_db(make_user, db_pool):
    """Test that summarizing a session successfully extracts and stores the profile data."""
    # 1. Setup User and Session
    user_id = await make_user()
    session_id = await create_chat_session(user_id, "dreamer")
    
    # 2. Add Mock Chat History
    await save_message(session_id, "user", "ผมอยากเป็นโปรแกรมเมอร์ ต้องเรียนคณะอะไรครับ?")
    await save_message(session_id, "assistant", "แนะนำให้เรียนคณะวิศวกรรมศาสตร์ สาขาคอมพิวเตอร์ครับ หรือวิทยาศาสตร์คอมพิวเตอร์")
    
    # 3. Mock the Ollama LLM response to simulate Typhoon2 returning JSON
    mock_json_response = json.dumps({
        "personality_summary": "ผู้ใช้มีความสนใจในด้านเทคโนโลยีและการเขียนโปรแกรม",
        "strengths": {
            "skills": ["Programming"],
            "explored_majors": ["คณะวิศวกรรมศาสตร์", "วิทยาศาสตร์คอมพิวเตอร์"],
            "career_interests": ["Programmer"]
        },
        "user_profile_updates": {
            "current_school": "Triam Udom",
            "gpax": 3.85
        }
    })
    
    # 4. Execute the Summarizer with mocked LLM
    with patch("engines.summarizer.chat", return_value=mock_json_response) as mock_chat:
        await summarize_session(user_id, session_id)
        
        # Verify that the LLM was called
        mock_chat.assert_called_once()
        
    # 5. Verify the results in PostgreSQL
    profile_row = await fetchrow(
        "SELECT personality_summary, strengths FROM user_career_profiles WHERE user_id = $1",
        user_id
    )
    
    assert profile_row is not None
    assert profile_row["personality_summary"] == "ผู้ใช้มีความสนใจในด้านเทคโนโลยีและการเขียนโปรแกรม"
    
    # Parse the JSONB strengths column
    strengths = json.loads(profile_row["strengths"])
    assert "Programmer" in strengths["career_interests"]
    assert "คณะวิศวกรรมศาสตร์" in strengths["explored_majors"]

    # Verify the user_profiles table update
    user_profile_row = await fetchrow(
        "SELECT current_school, gpax FROM user_profiles WHERE user_id = $1",
        user_id
    )
    assert user_profile_row is not None
    assert user_profile_row["current_school"] == "Triam Udom"
    assert float(user_profile_row["gpax"]) == 3.85
