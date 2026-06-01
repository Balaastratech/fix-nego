from app.services.ask_transcript_state import best_candidate, should_replace_frontend_text


def test_best_candidate_rejects_cross_ask_deepgram_tail_when_gemini_has_current_start():
    capture = {
        "gemini_input_text": "Okay, that sounds good. Explain me more what you are seeing right now properly.",
        "transcript_candidates": {
            "gemini_live_input": {
                "text": "Okay, that sounds good. Explain me more what you are seeing right now properly.",
                "source": "gemini_live_input",
                "is_final": False,
                "priority": 30,
                "updated_at_ms": 20,
            },
            "deepgram_ask": {
                "text": "It to me what you are seeing right now. Okay, that sounds good. Explain me more what you are seeing",
                "source": "deepgram_ask",
                "is_final": True,
                "priority": 70,
                "updated_at_ms": 30,
            },
        },
    }

    selected = best_candidate(capture)

    assert selected["source"] == "gemini_live_input"
    assert selected["text"].startswith("Okay, that sounds good")


def test_best_candidate_uses_longer_gemini_when_deepgram_final_is_truncated_same_ask():
    capture = {
        "gemini_input_text": "Now you are seeing a different screen explain it to me what you are seeing right now.",
        "transcript_candidates": {
            "gemini_live_input": {
                "text": "Now you are seeing a different screen explain it to me what you are seeing right now.",
                "source": "gemini_live_input",
                "is_final": False,
                "priority": 30,
                "updated_at_ms": 20,
            },
            "deepgram_ask": {
                "text": "Now you are seeing a different screen.",
                "source": "deepgram_ask",
                "is_final": True,
                "priority": 70,
                "updated_at_ms": 30,
            },
        },
    }

    selected = best_candidate(capture)

    assert selected["source"] == "gemini_live_input"
    assert selected["text"].endswith("right now.")


def test_late_gemini_does_not_replace_different_deepgram_question():
    assert not should_replace_frontend_text(
        "deepgram_ask",
        "gemini_live_input",
        "What is my name?",
        "Okay, that sounds good. Explain me more what you are seeing right now properly.",
    )
