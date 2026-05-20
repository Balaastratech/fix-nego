"""
Response Validator for Gemini AI Responses
Ensures the AI follows the negotiation commander rules
"""
import logging
import re

from app.ai_assets import (
    RESPONSE_VALIDATOR_ALLOWED_FIRST_WORDS,
    RESPONSE_VALIDATOR_FORBIDDEN_FIRST_WORDS,
    build_response_correction_prompt,
)

logger = logging.getLogger(__name__)


class ResponseValidator:
    """Validates AI responses against negotiation commander rules"""
    
    # Allowed first words for responses
    ALLOWED_FIRST_WORDS = RESPONSE_VALIDATOR_ALLOWED_FIRST_WORDS
    
    # Forbidden first words
    FORBIDDEN_FIRST_WORDS = RESPONSE_VALIDATOR_FORBIDDEN_FIRST_WORDS

    @staticmethod
    def _strip_quoted_content(text: str) -> str:
        """
        Remove quoted payload text so command wrappers like:
        Ask: "Could we move equity?"
        are validated on the command frame, not the quoted sentence.
        """
        if not text:
            return ""
        return re.sub(r"(['\"])(?:(?=(\\?))\2.)*?\1", '""', text)
    
    @staticmethod
    def validate_response(text: str) -> dict:
        """
        Validate an AI response against the rules.
        
        Args:
            text: The AI's response text
            
        Returns:
            dict with:
                - valid: bool
                - violations: list of violation codes
                - correction_prompt: str (if violations found)
        """
        if not text or not text.strip():
            return {"valid": True, "violations": [], "correction_prompt": None}
        
        text = text.strip()
        violations = []
        unquoted_text = ResponseValidator._strip_quoted_content(text)
        
        # Rule 1: Check if ends with question mark
        if unquoted_text.rstrip().endswith('?'):
            violations.append("ENDS_WITH_QUESTION")
        
        # Rule 2: Check for forbidden first words
        first_words = text.split()[:3]  # Check first 3 words for phrases
        first_word = first_words[0] if first_words else ""
        
        # Check single word
        if first_word in ResponseValidator.FORBIDDEN_FIRST_WORDS:
            violations.append(f"FORBIDDEN_START:{first_word}")
        
        # Check two-word phrases
        if len(first_words) >= 2:
            two_word = f"{first_words[0]} {first_words[1]}"
            if two_word in ResponseValidator.FORBIDDEN_FIRST_WORDS:
                violations.append(f"FORBIDDEN_START:{two_word}")
        
        # Rule 3: Check if starts with allowed action word
        starts_with_allowed = any(
            text.startswith(word) for word in ResponseValidator.ALLOWED_FIRST_WORDS
        )
        if not starts_with_allowed and not violations:
            violations.append(f"MISSING_ACTION_START")
        
        # Rule 4: Check for vague language
        vague_patterns = [
            r'\byou could\b',
            r'\byou might\b',
            r'\bconsider\b',
            r'\bmaybe\b',
            r'\bperhaps\b',
            r'\bone option\b',
            r'\ba few options\b'
        ]
        for pattern in vague_patterns:
            if re.search(pattern, unquoted_text, re.IGNORECASE):
                violations.append("VAGUE_LANGUAGE")
                break
        
        # Rule 5: Check for multiple questions in text
        question_count = unquoted_text.count('?')
        if question_count > 0:
            violations.append(f"CONTAINS_QUESTIONS:{question_count}")
        
        # Generate correction prompt if violations found
        correction_prompt = None
        if violations:
            correction_prompt = ResponseValidator._generate_correction(violations, text)
        
        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "correction_prompt": correction_prompt
        }
    
    @staticmethod
    def _generate_correction(violations: list, original_text: str) -> str:
        """Generate a correction prompt based on violations"""
        
        violation_messages = []
        
        for violation in violations:
            if violation == "ENDS_WITH_QUESTION":
                violation_messages.append("You ended with a question mark")
            elif violation.startswith("FORBIDDEN_START:"):
                word = violation.split(":", 1)[1]
                violation_messages.append(f"You started with forbidden word '{word}'")
            elif violation == "MISSING_ACTION_START":
                violation_messages.append("You must start with: Ask/Say/Counter/Tell/Push/Walk/Stay/Offer")
            elif violation == "VAGUE_LANGUAGE":
                violation_messages.append("You used vague language like 'you could' or 'consider'")
            elif violation.startswith("CONTAINS_QUESTIONS:"):
                violation_messages.append("You asked questions")
        
        return build_response_correction_prompt(violation_messages)
    
    @staticmethod
    def should_send_correction(violations: list) -> bool:
        """
        For command mode, any validation failure should trigger a correction.
        Silent drops create hung turns where the client waits forever.
        """
        return bool(violations)
