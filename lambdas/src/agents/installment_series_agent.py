"""
Installment Series Agent for extracting payment schedule information from contract documents.

This agent specializes in identifying and extracting installment series information
for units, including recurring and non-recurring payment patterns.
"""

import json
from typing import Dict, List, Any
from agno.agent import Agent
from agno.models.openai import OpenAIChat
import dotenv

env = dotenv.load_dotenv()


class InstallmentSeriesAgent:
    """
    AI agent specialized in extracting installment series information from contract documents.
    
    This agent analyzes document chunks to identify payment schedules, installment patterns,
    and series types for each unit in the contract.
    """
    
    def __init__(self, model: str = "gpt-4o-mini"):
        """
        Initialize the Installment Series Agent.
        
        Args:
            model: The OpenAI model to use for extraction
        """
        self.model = model
        
        # Define the fields to extract for installment series
        self.fields_to_extract = {
            "installmentPlans": {
                "description": "Array of installment plans for each unit",
                "type": "array",
                "sub_fields": {
                    "unitCode": {
                        "description": "Unit identifier code",
                        "type": "string",
                    },
                    "totalInstallments": {
                        "description": "Total number of installments",
                        "type": "integer",
                    },
                    "series": {
                        "description": "Installment series type",
                        "type": "string",
                        "enum": ["MENSAL", "CHAVES", "ATO", "UNICA", "TRIMESTRAL", "ANUAL", "BIMESTRAL", "BIENAL"]
                    },
                    "indexerCode": {
                        "description": "Indexer code for the installment plan. Look for keywords like 'IPCA', 'IGPM', 'SELIC', 'INCC', 'corrigido pelo', 'atualizado pelo' in the contract text. If no indexer is specified, use 'REAL'. Common patterns: 'corrigido pelo IPCA', 'atualizado pelo IGPM', 'SELIC', 'INCC'.",
                        "type": "string",
                        "enum": ["REAL", "INCC", "IPCA", "IGPM", "SELIC"]
                    },
                    "firstDueDate": {
                        "description": "First due date of the installment plan - MUST be in ISO 8601 format (YYYY-MM-DD)",
                        "type": "string",
                    },
                    "totalValue": {
                        "description": "Total value of the installment plan",
                        "type": "number",
                    },
                    "installmentAmount": {
                        "description": "Amount per installment",
                        "type": "number",
                    }
                }
            }
        }
        
        # Business Rules - Domain-specific extraction rules
        self.business_rules = """
## BUSINESS RULES - INSTALLMENT SERIES EXTRACTION

### Entity Identification Rules
- Each property/unit MUST have a UNIQUE unitCode (number, string, or complex identifier)
- unitCode examples: '64', 'LOTE Nº XX QUADRA Y', 'APTO 101 BLOCO A'
- CRITICAL: NO duplicate unitCodes - same unitCode = same entity
- Group ALL installment information belonging to the same unitCode together
- Different unitCodes = different entities
- If no unitCode found, IGNORE that information
- If a new UnitCode is found, create a new unit object

### Installment Series Classification Rules
**CRITICAL: MUST ALWAYS USE EXACT ENUM VALUES (MENSAL, TRIMESTRAL, ANUAL, BIMESTRAL, BIENAL, CHAVES, ATO, UNICA) - NO EXCEPTIONS**

#### Recurring Payments (Regular Installments)
- **MENSAL**: Monthly payments (parcelas mensais, mensalmente)
- **TRIMESTRAL**: Quarterly payments (parcelas trimestrais, trimestralmente)
- **ANUAL**: Annual payments (parcelas anuais, anualmente)
- **BIMESTRAL**: Bi-monthly payments (parcelas bimestrais, bimestralmente)
- **BIENAL**: Bi-annual payments (parcelas bienais, bienalmente)

#### Non-Recurring Payments (One-time Payments)
- **CHAVES**: Explicitly stated as "chaves"
- **ATO**: First payment in the sequence (default for non-recurring unless stated otherwise)
- **UNICA**: Single payment after recurring installments

**ENUM COMPLIANCE RULES:**
- ONLY use values from the enum list above
- NEVER create custom or modified values
- If uncertain about classification, use ATO as default for non-recurring

### Payment Status Rules
- CRITICAL: If a unit is marked as "QUITADA" (paid/settled), do NOT create any installment plans for it
- Look for keywords like "QUITADA", "PAGA", "LIQUIDADA", to identify paid units
- Only extract installment plans for units that are still pending payment
- If no payment status is found, assume the unit is pending and extract installment plans

### Installment Plan Rules
- Each unit can have multiple installment plans
- Each payment plan must be a separate installmentPlan object
- Non-recurring plans (CHAVES, ATO, UNICA) MUST have totalInstallments = 1
- Recurring plans should have totalInstallments > 1
- Look for payment patterns in the text (e.g., "X parcelas mensais", "Y parcelas anuais")
- Extract installment amounts, dates, and indexer codes when available
- All dates must be converted to ISO 8601 format (YYYY-MM-DD) before returning

### Indexer Code Extraction Rules
- Look for explicit mentions of indexers: IPCA, IGPM, SELIC, INCC
- Common patterns: "corrigido pelo IPCA", "atualizado pelo IGPM", "SELIC", "INCC"
- If no indexer is mentioned, default to REAL
- Indexer codes are typically found near payment schedules or installment descriptions
- Extract indexerCode for each installment plan separately
"""

        # JSON Structure Rules - Technical implementation rules
        self.json_rules = """
## JSON STRUCTURE RULES

### Response Format
- Return ONLY valid JSON array, no markdown or explanations
- Each element must contain:
  - 'unit': Object with unitCode and installmentPlans array
  - 'sources': Array of source citations for each field
  - 'confidence': Object with confidence levels (high/medium/low)
- Include installmentPlans array within each unit object

### Source Citation Rules
- Each source must include: field, chunk_id
- CRITICAL: Each source MUST have a 'field' property indicating which field it belongs to
- Assign confidence level (high/medium/low) for each field

### JSON Formatting Rules
- Use double quotes for all strings
- No trailing commas
- All object keys must be quoted
- Ensure proper nesting of objects and arrays
- Return ONLY the JSON array, no other text
"""

        # Implementation Rules - How to use chunks and tools
        self.implementation_rules = """
## IMPLEMENTATION RULES

### Core Principles
- Extract installment series information for each unit
- Identify both recurring and non-recurring payment patterns
- Focus on payment schedule patterns and series classification
- Always cite sources with chunk_id
- Set confidence to LOW if uncertain about any information
- Group related information by unique entity identifiers
- Return ONLY valid JSON array, no markdown or explanations

### Chunk Processing
- Use the EXACT [CHUNK ID: chunk_XXX] identifier shown in the prompt
- Multiple fields can be found in the same chunk - reuse chunks as needed
- If information is not found, set value to null and explain in sources

### Entity Grouping Implementation
- CRITICAL: Same unitCode = same entity - combine all information
- CRITICAL: NEVER create multiple units with the same unitCode
- Group ALL installment information belonging to the same unitCode together
"""

        # Agent instructions combining all rules
        self.instructions = """
# INSTALLMENT SERIES EXTRACTION AGENT
""" + self.business_rules + "\n" + self.json_rules + "\n" + self.implementation_rules
        
        self.agent = Agent(
            name="Installment Series Agent",
            model=OpenAIChat(id=model),
            instructions=self.instructions,
            markdown=False
        )
    
    def get_field_descriptions(self) -> Dict[str, str]:
        """Get descriptions of fields this agent extracts."""
        return {field: info["description"] for field, info in self.fields_to_extract.items()}
    
    def extract_information(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract installment series information from document chunks.
        
        Args:
            chunks: List of document chunks to analyze
            
        Returns:
            List containing extracted installment series information
        """
        # Create prompt with chunks and extraction request
        prompt = self._build_extraction_prompt(chunks)
        
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
        
        # Ensure result is a list
        if not isinstance(result, list):
            result = [result]
        
        return result
    
    def _build_extraction_prompt(self, chunks: List[Dict[str, Any]]) -> str:
        """Build the extraction prompt from document chunks."""
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
            "Extract installment series information from the chunks above:",
            "",
            "## Document Analysis",
            "• Analyze the document to identify ALL entities (units/properties) present",
            "• If no unitCode found, IGNORE that information",
            "",
            "## Data Extraction Process",
            "• Extract installment information for each entity separately",
            "• If information is not found, set value to null and explain in sources",
            "",
            "## Field-Specific Implementation Notes",
            "• Look for payment patterns in the text (e.g., 'X parcelas mensais', 'Y parcelas anuais')",
            "• Extract installment amounts, dates, and indexer codes when available",
            "• For indexerCode: Look for keywords like 'IPCA', 'IGPM', 'SELIC', 'INCC', 'corrigido pelo', 'atualizado pelo'. If not found, use 'REAL'",
            "• Information can be repeated between entities if the same",
            "",
            "Return the result as valid JSON with the following structure:",
            json.dumps([
                {
                    "unit": {
                        "unitCode": "string",
                        "installmentPlans": [
                            {
                                "totalInstallments": "integer",
                                "series": "string (enum: MENSAL, CHAVES, ATO, UNICA, TRIMESTRAL, ANUAL, BIMESTRAL, BIENAL)",
                                "indexerCode": "string (optional, enum: REAL, INCC, IPCA, IGPM, SELIC - default to REAL if not specified)",
                                "firstDueDate": "string (ISO 8601 format - YYYY-MM-DD)",
                                "totalValue": "number (optional)",
                                "installmentAmount": "number (optional)"
                            }
                        ]
                    },
                    "sources": [
                        {
                            "field": "string",
                            "chunk_id": "string"
                        }
                    ],
                    "confidence": {
                        "unitCode": "high/medium/low",
                        "installmentPlans": "high/medium/low"
                    }
                }
            ], indent=2)
        ])
        
        return "\n".join(prompt_parts)
    
    
    def _fix_json_issues(self, content: str) -> str:
        """
        Try to fix common JSON issues in the agent's response.
        
        Args:
            content: The JSON string that failed to parse
            
        Returns:
            Potentially fixed JSON string
        """
        import re
        
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
        
        for pattern, replacement in fixes:
            content = re.sub(pattern, replacement, content)
        
        return content


def load_chunks(file_path: str) -> List[Dict[str, Any]]:
    """Load document chunks from a JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('chunks', [])
    except Exception as e:
        print(f"Error loading chunks: {e}")
        return []


def save_result(result: Dict[str, Any], file_path: str) -> None:
    """Save extraction result to a JSON file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"✓ Installment series result saved to {file_path}")
    except Exception as e:
        print(f"Error saving result: {e}")
