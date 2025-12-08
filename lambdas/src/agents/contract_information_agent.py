"""Contract information agent for extracting property data from parsed PDF chunks."""

import json
from typing import Dict, List, Any
from agno.agent import Agent
from agno.models.openai import OpenAIChat
import dotenv

env = dotenv.load_dotenv()


def calculate_price_per_m2(sell_value: float, area_m2: float) -> float:
    """
    Calculate the price per square meter.
    
    Args:
        sell_value: Total selling price/value
        area_m2: Area in square meters
    
    Returns:
        Price per square meter rounded to 2 decimal places
    """
    if area_m2 < 0:
        raise ValueError("Area must be greater than 0")

    if area_m2 == 0:
        return 0.00
    
    price_per_m2 = sell_value / area_m2
    return round(price_per_m2, 2)


class ContractInformationAgent:
    """Agent that analyzes contract documents to extract structured property information."""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        """
        Initialize the contract information agent.
        
        Args:
            model: The LLM model to use
        """
        # Field definitions - generalized and modular
        self.fields_to_extract = {
            "unitCode": {
                "description": "Unique property identifier - can be a number, string, or complex identifier (e.g., '64', 'LOTE Nº 64 QUADRA D', 'APTO 101 BLOCO A', 'CASA 15 LOTEAMENTO XYZ') - MANDATORY: Every unit MUST have a unitCode",
                "type": "string"
            },
            "sellValue": {
                "description": "TOTAL selling price/value of the property - NOT installments, NOT partial payments, NOT commissions - ONLY the complete total value",
                "type": "number"
            },
            "buyerName": {
                "description": "Full name of the buyer/purchaser",
                "type": "string"
            },
            "buyerDocumentNumber": {
                "description": "Buyer's document number (CPF for individuals or CNPJ for companies) - used to differentiate buyers",
                "type": "string"
            },
            "areaM2": {
                "description": "Total area of the property in square meters",
                "type": "number"
            },
            "pricePerM2": {
                "description": "Price per square meter (use calculate_price_per_m2 tool)",
                "type": "number"
            },
            "signingDate": {
                "description": "Date when the contract was signed or executed - MUST be in ISO 8601 format (YYYY-MM-DD) - usually accompanying the city/state information.",
                "type": "string"
            },
            "indexerBaseDate": {
                "description": "Base date for indexer calculations - the reference date from which indexer adjustments are calculated. MUST be in ISO 8601 format (YYYY-MM-DD). Usually found near indexer mentions or payment schedule sections.",
                "type": "string"
            },
        }
        
        # Business Rules - Domain-specific extraction rules
        self.business_rules = """
## BUSINESS RULES - CONTRACT INFORMATION EXTRACTION

### Entity Identification Rules
• Each property/unit MUST have a UNIQUE unitCode (number, string, or complex identifier)
• unitCode examples: '64', 'LOTE Nº XX QUADRA Y', 'APTO 101 BLOCO A', 'CASA 15 LOTEAMENTO XYZ'
• CRITICAL: NO duplicate unitCodes - same unitCode = same entity
• Group ALL information belonging to the same unitCode together
• Different unitCodes = different entities
• If no unitCode found, IGNORE that information
• If a new UnitCode is found, create a new unit object
• Unless explicitly stated, assume this unit buyerName, areaM2 and signingDate are the same as the previous unit

### Field Extraction Rules
• sellValue = TOTAL property value, NOT installments or partial payments
• Look for 'Preço Total', 'Valor Total', 'Preço da Unidade' for sellValue
• IGNORE payment schedules, commissions, or installment amounts
• Use calculate_price_per_m2 tool for price per square meter calculations
• For paid/completed items, set value to 0.00 if applicable
• signingDate: Usually on last pages or next to city/state information - MUST be in ISO 8601 format (YYYY-MM-DD)
• indexerBaseDate: Base date for indexer calculations - usually found near indexer mentions (IPCA, IGPM, SELIC, INCC) or payment schedule sections. Look for phrases like "data base", "data de referência", "a partir de", "desde". MUST be in ISO 8601 format (YYYY-MM-DD)
• buyerName: If multiple buyers for the same unit, use the first buyer name and ignore the rest
• buyerDocumentNumber: Extract CPF (for individuals) or CNPJ (for companies) associated with the buyer
• All dates must be converted to ISO 8601 format (YYYY-MM-DD) before returning
"""

        # JSON Structure Rules - Technical implementation rules
        self.json_rules = """
## JSON STRUCTURE RULES

### Response Format
Return a JSON array where each element contains:
• 'unit': Object with all extracted field values
• 'sources': Array of source citations for each field
• 'confidence': Object with confidence levels (high/medium/low)

### Source Citation Rules
• Each source must include: field, chunk_id
• CRITICAL: Each source MUST have a 'field' property indicating which field it belongs to
• Assign confidence level (high/medium/low) for each field

### JSON Formatting Rules
• Use double quotes for all strings
• No trailing commas
• All object keys must be quoted
• Ensure proper nesting of objects and arrays
• Return ONLY valid JSON array, no markdown or explanations
"""

        # Implementation Rules - How to use chunks and tools
        self.implementation_rules = """
## IMPLEMENTATION RULES

### Core Principles
• Always cite sources with chunk_id
• Set confidence to LOW if uncertain about any information
• Group related information by unique entity identifiers
• Use available tools for calculations when needed

### Chunk Processing
• Use the EXACT [CHUNK ID: chunk_XXX] identifier shown in the prompt
• Multiple fields can be found in the same chunk - reuse chunks as needed
• If information is not found, set value to null and explain in sources

### Entity Grouping Implementation
• CRITICAL: Same unitCode = same entity - combine all information
• CRITICAL: NEVER create multiple units with the same unitCode
• If multiple buyers for same unit, combine them into one unit
• MANDATORY: One unitCode = One unit object, regardless of how many buyers
"""

        self.agent = Agent(
            name="Contract Information Agent",
            model=OpenAIChat(id=model),
            instructions=(
                "You are a document analysis expert specializing in structured data extraction from real estate contracts. "
                "Extract specific property information and organize it by unique entities (units).\n\n"
                + self.business_rules + "\n" + self.json_rules + "\n" + self.implementation_rules
            ),
            tools=[calculate_price_per_m2],
            markdown=False
        )
    
    def extract_information(
        self,
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract specific information from document chunks.
        
        Args:
            chunks: List of document chunks with text, page, bbox, and element_type
        
        Returns:
            Dictionary with extracted_data, sources, and confidence levels
        """
        # Create prompt with chunks and extraction request
        prompt = self._build_extraction_prompt(chunks, self.fields_to_extract)
        
        # Run agent and get response
        run_response = self.agent.run(prompt, stream=False)
        
        # Extract the content from the response
        content = run_response.content
        
        # Parse JSON from the content
        # The agent should return JSON, but may wrap it in markdown code blocks
        if isinstance(content, str):
            # Remove markdown code blocks if present
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Try to parse JSON with better error handling
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {e}")
                print(f"Content preview: {content[:200]}...")
                print(f"Error at position {e.pos}: {content[max(0, e.pos-50):e.pos+50]}")
                
                # Try to fix common JSON issues
                content = self._fix_json_issues(content)
                try:
                    result = json.loads(content)
                    print("✓ Fixed JSON and parsed successfully")
                except json.JSONDecodeError as e2:
                    print(f"Still failed to parse JSON: {e2}")
                    # Return a minimal structure to prevent complete failure
                    result = [{"unit": {}, "sources": [], "confidence": {}}]
        else:
            result = content
        
        return result
    
    def _fix_json_issues(self, content: str) -> str:
        """
        Try to fix common JSON issues in the agent's response.
        
        Args:
            content: The JSON string that failed to parse
            
        Returns:
            Potentially fixed JSON string
        """
        # Common fixes
        fixes = [
            # Fix trailing commas
            (r',(\s*[}\]])', r'\1'),
            # Fix missing quotes around keys
            (r'(\w+):', r'"\1":'),
            # Fix single quotes to double quotes
            (r"'([^']*)'", r'"\1"'),
            # Fix unescaped quotes in strings
            (r'"(.*?)"(?=\s*:)', r'"\1"'),
        ]
        
        import re
        for pattern, replacement in fixes:
            content = re.sub(pattern, replacement, content)
        
        return content
    
    def get_field_descriptions(self) -> Dict[str, str]:
        """
        Get the field descriptions used by this agent.
        
        Returns:
            Dictionary mapping field names to their descriptions
        """
        return self.fields_to_extract.copy()
    
    def _build_extraction_prompt(
        self,
        chunks: List[Dict[str, Any]],
        fields_to_extract: Dict[str, str]
    ) -> str:
        """Build the prompt for information extraction."""
        prompt_parts = [
            "# DOCUMENT CHUNKS",
            "Below are chunks extracted from a document:",
            ""
        ]
        
        # Add all chunks with their full text content
        for chunk in chunks:
            chunk_id = chunk.get('chunk_id', 'unknown')
            prompt_parts.extend([
                f"[CHUNK ID: {chunk_id}]",
                f"Type: {chunk['element_type']}",
                f"Text:",
                chunk['text'],
                ""
            ])
        
        prompt_parts.extend([
            "# EXTRACTION REQUEST",
            "Extract the following information from the chunks above:",
            ""
        ])
        
        for field, field_info in fields_to_extract.items():
            if isinstance(field_info, dict):
                description = field_info["description"]
                field_type = field_info["type"]
                prompt_parts.append(f"• **{field}** ({field_type}): {description}")
            else:
                prompt_parts.append(f"• **{field}**: {field_info}")
        
        prompt_parts.extend([
            "",
            "# EXTRACTION INSTRUCTIONS",
            "",
            "## Document Analysis",
            "• Analyze the document to identify ALL entities (units/properties) present",
            "• If contract doesn't contain multiple units, use information from the first unit",
            "",
            "## Data Extraction Process",
            "• Extract information for each entity separately",
            "• If information is not found, set value to null and explain in sources",
            "",
            "## Field-Specific Implementation Notes",
            "• signingDate: Do NOT use the dates of digital signatures",
            "• indexerBaseDate: Look for base dates near indexer mentions or payment schedules. Common phrases: 'data base', 'data de referência', 'a partir de', 'desde'",
            "• Information can be repeated between entities if the same"
        ])
        
        return "\n".join(prompt_parts)


def load_chunks(json_path: str) -> List[Dict[str, Any]]:
    """Load document chunks from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_result(result: Dict[str, Any], output_path: str) -> None:
    """Save extraction result to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

