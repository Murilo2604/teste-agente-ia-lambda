"""Extract cutout images from PDF based on extraction results."""

import fitz  # PyMuPDF
from pathlib import Path
from typing import Dict, Any, List
import json


class CutoutExtractor:
    """Extract image cutouts from PDF based on bounding boxes."""
    
    def __init__(self, pdf_path: str):
        """
        Initialize the cutout extractor.
        
        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
    
    def extract_cutouts(
        self,
        extraction_result: Dict[str, Any],
        output_dir: str = "/tmp/cutouts",
        padding: int = 5,
        scale: float = 2.0,
        chunks: List[Dict[str, Any]] = None
    ) -> Dict[str, List[str]]:
        """
        Extract cutout images for each extracted field.
        
        Args:
            extraction_result: The extraction result with sources
            output_dir: Directory to save cutout images
            padding: Padding in pixels around the bounding box
            scale: Scale factor for image quality (higher = better quality)
            chunks: List of document chunks to get page and bbox information
        
        Returns:
            Dictionary mapping field names to lists of cutout image paths
        """
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Store chunks for lookup
        self.chunks = chunks or []
        
        cutout_paths = {}

        def dedupe_sources(sources):
            seen = set()
            filtered = []
            for source in sources or []:
                key = (source.get('field'), source.get('chunk_id'))
                if key in seen:
                    continue
                seen.add(key)
                filtered.append(source)
            return filtered
        
        # Handle new array structure
        if isinstance(extraction_result, list):
            units_data = extraction_result
        else:
            # Fallback for old structure
            units_data = extraction_result.get('units', [extraction_result])
        
        # Process each unit
        for unit_idx, unit_data in enumerate(units_data):
            sources = dedupe_sources(unit_data.get('sources', []))
            print(f"Processing unit {unit_idx + 1} with {len(sources)} sources")
            
            for source in sources:
                field = source.get('field')
                chunk_id = source.get('chunk_id')
                
                # Skip if no required data
                if not field:
                    print(f"⚠️  Source missing field name for unit {unit_idx + 1}; skipping cutout")
                    continue
                if not chunk_id:
                    print(f"⚠️  Source '{field}' missing chunk_id for unit {unit_idx + 1}; skipping cutout")
                    continue
                    continue
                
                # Find the chunk to get page and bbox information
                chunk_data = None
                for chunk in self.chunks:
                    if chunk.get('chunk_id') == chunk_id:
                        chunk_data = chunk
                        break
                
                if not chunk_data:
                    print(f"Warning: Could not find chunk {chunk_id}")
                    continue
                
                page_num = chunk_data.get('page')
                bbox = chunk_data.get('bbox')
                
                # Skip if no bbox or page data
                if not bbox or page_num is None:
                    continue
                
                # Parse bbox if it's a string
                parsed_bbox = self._parse_bbox(bbox)
                if not parsed_bbox:
                    print(f"Warning: Could not parse bbox for {field}: {bbox}")
                    continue
                
                # Extract cutout
                cutout_path = self._extract_single_cutout(
                    field=field,
                    unit_index=unit_idx,
                    chunk_id=chunk_id,
                    page_num=page_num,
                    bbox=parsed_bbox,
                    output_dir=output_path,
                    padding=padding,
                    scale=scale
                )
                
                if cutout_path:
                    field_key = f"unit{unit_idx + 1}_{field}"
                    if field_key not in cutout_paths:
                        cutout_paths[field_key] = []
                    cutout_paths[field_key].append(cutout_path)
                    print(f"✓ Added cutout for {field_key}")
                else:
                    print(f"✗ Failed to extract cutout for {field} (unit {unit_idx + 1})")
        
        return cutout_paths
    
    def _parse_bbox(self, bbox) -> List[float]:
        """
        Parse bbox from various formats (string, list, tuple).
        
        Args:
            bbox: Bounding box in various formats
            
        Returns:
            List of 4 float values [left, top, right, bottom] or None if parsing fails
        """
        try:
            # If it's already a list or tuple, convert to list
            if isinstance(bbox, (list, tuple)):
                if len(bbox) == 4:
                    return [float(x) for x in bbox]
                return None
            
            # If it's a string, try to parse it
            if isinstance(bbox, str):
                # Remove parentheses and split by comma
                bbox_str = bbox.strip('()')
                coords = [float(x.strip()) for x in bbox_str.split(',')]
                if len(coords) == 4:
                    return coords
                return None
            
            return None
            
        except (ValueError, AttributeError) as e:
            print(f"Error parsing bbox '{bbox}': {e}")
            return None
    
    def _extract_single_cutout(
        self,
        field: str,
        unit_index: int,
        chunk_id: str,
        page_num: int,
        bbox: List[float],
        output_dir: Path,
        padding: int,
        scale: float
    ) -> str:
        """
        Extract a single cutout image.
        
        Args:
            field: Field name
            unit_index: Unit index (0 for first unit, 1 for second unit)
            chunk_id: Chunk ID (e.g., "chunk_000")
            page_num: Page number (1-indexed)
            bbox: Bounding box [left, top, right, bottom]
            output_dir: Output directory path
            padding: Padding in pixels
            scale: Scale factor
        
        Returns:
            Path to the saved cutout image
        """
        try:
            # Convert to 0-indexed page number
            page_idx = page_num - 1
            
            if page_idx < 0 or page_idx >= len(self.doc):
                print(f"Warning: Page {page_num} out of range")
                return None
            
            page = self.doc[page_idx]
            page_rect = page.rect
            page_height = page_rect.height
            
            # Extract bbox coordinates
            # Docling uses BOTTOMLEFT origin, PyMuPDF uses TOPLEFT
            l, t, r, b = bbox
            
            # Convert coordinates from Docling (BOTTOMLEFT) to PyMuPDF (TOPLEFT)
            pdf_y_top = page_height - t
            pdf_y_bottom = page_height - b
            
            # Add padding and ensure within page bounds
            padded_rect = fitz.Rect(
                max(0, l - padding),
                max(0, pdf_y_top - padding),
                min(page_rect.width, r + padding),
                min(page_rect.height, pdf_y_bottom + padding)
            )
            
            # Extract the region as an image
            matrix = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(clip=padded_rect, matrix=matrix)
            
            # Generate filename
            filename = f"unit{unit_index + 1}_{field}_{chunk_id}_page{page_num}.png"
            output_file = output_dir / filename
            
            # Save the image
            pix.save(str(output_file))
            
            print(f"✓ Extracted cutout: {filename}")
            return str(output_file)
            
        except Exception as e:
            print(f"Error extracting cutout for {field}: {e}")
            return None
    
    def close(self):
        """Close the PDF document."""
        if self.doc:
            self.doc.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def save_cutout_manifest(
    cutout_paths: Dict[str, List[str]],
    output_file: str = "/tmp/cutout_manifest.json"
):
    """
    Save a manifest file with all cutout paths.
    
    Args:
        cutout_paths: Dictionary of field names to cutout paths
        output_file: Output manifest file path
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cutout_paths, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Saved cutout manifest to {output_file}")

