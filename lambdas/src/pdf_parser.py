"""PDF parsing module using Docling to extract structured chunks with coordinates."""

import os


def parse_pdf_to_chunks(pdf_path):
    """
    Extract all text chunks from PDF with their coordinates.
    
    Args:
        pdf_path: Path to the PDF file
    
    Returns:
        List of dictionaries containing text, page, bbox, element_type, and chunk_id
    """
    # Create all necessary cache directories in /tmp (Lambda runtime requirement)
    # These must be created at runtime since Lambda provides a fresh /tmp each time
    # Note: The Dockerfile creates a symlink from rapidocr package dir to /tmp/rapidocr_models
    cache_dirs = [
        '/tmp/output',
        '/tmp/rapidocr_models',  # RapidOCR models (symlinked from package dir)
        '/tmp/torch',
        '/tmp/huggingface',
        '/tmp/huggingface/hub',
        '/tmp/transformers',
        '/tmp/docling_models',
        '/tmp/docling_scratch',
        '/tmp/.cache',
        '/tmp/sentence_transformers',
    ]
    
    print("📁 Creating cache directories in /tmp...")
    for cache_dir in cache_dirs:
        os.makedirs(cache_dir, exist_ok=True)
    print(f"✓ Created {len(cache_dirs)} cache directories")
    
    # Configure all ML frameworks to use /tmp for model storage (Lambda-safe)
    # RapidOCR configuration
    os.environ.setdefault('RAPIDOCR_HOME', '/tmp/rapidocr_models')
    
    # PyTorch configuration
    os.environ.setdefault('TORCH_HOME', '/tmp/torch')
    
    # HuggingFace/Transformers configuration
    os.environ.setdefault('HF_HOME', '/tmp/huggingface')
    os.environ.setdefault('TRANSFORMERS_CACHE', '/tmp/transformers')
    os.environ.setdefault('HUGGINGFACE_HUB_CACHE', '/tmp/huggingface/hub')
    
    # Docling-specific configuration
    os.environ.setdefault('DOCLING_SERVE_ARTIFACTS_PATH', '/tmp/docling_models')
    os.environ.setdefault('DOCLING_SERVE_SCRATCH_PATH', '/tmp/docling_scratch')
    
    # Generic cache directories
    os.environ.setdefault('XDG_CACHE_HOME', '/tmp/.cache')
    
    # Sentence Transformers (if used by Docling)
    os.environ.setdefault('SENTENCE_TRANSFORMERS_HOME', '/tmp/sentence_transformers')
    
    # Lazy import to avoid loading heavy ML dependencies during Lambda initialization
    from docling.document_converter import DocumentConverter
    
    # convert PDF to DoclingDocument
    converter = DocumentConverter()
    conv_res = converter.convert(source=pdf_path)
    doc = conv_res.document

    chunks = []
    chunk_counter = 0
    
    # Extract tables first (they have special handling)
    for table in doc.tables:
        # Get table provenance for location
        if hasattr(table, 'prov') and table.prov:
            prov = table.prov[0]
            bbox = prov.bbox
            page_ix = prov.page_no - 1
            
            # Export table as markdown for structured text
            table_text = table.export_to_markdown()
            
            chunks.append({
                "chunk_id": f"chunk_{chunk_counter:03d}",
                "text": table_text,
                "page": page_ix + 1,
                "bbox": (bbox.l, bbox.t, bbox.r, bbox.b),
                "element_type": "table"
            })
            chunk_counter += 1
    
    # Extract text items
    skipped_no_text = 0
    skipped_no_prov = 0
    max_page_seen = 0
    
    for item, _level in doc.iterate_items():
        text = getattr(item, "text", None)
        if not text or not text.strip():
            skipped_no_text += 1
            continue
        
        # Get provenance (location info)
        if not hasattr(item, 'prov') or not item.prov:
            skipped_no_prov += 1
            continue
            
        prov = item.prov[0]
        bbox = prov.bbox
        page_ix = prov.page_no - 1
        max_page_seen = max(max_page_seen, page_ix + 1)
        
        # Get element type
        element_type = item.label.value if hasattr(item, 'label') and hasattr(item.label, 'value') else None
        
        chunks.append({
            "chunk_id": f"chunk_{chunk_counter:03d}",
            "text": text,
            "page": page_ix + 1,
            "bbox": (bbox.l, bbox.t, bbox.r, bbox.b),
            "element_type": element_type
        })
        chunk_counter += 1
    
    return chunks

if __name__ == "__main__":
    import json
    
    pdf_path = "contrato.pdf"
    
    # Extract all chunks from the entire document
    print("Parsing entire document...")
    chunks = parse_pdf_to_chunks(pdf_path)
    
    print("\n" + "=" * 50)
    print(f"EXTRACTED {len(chunks)} CHUNKS")
    print("=" * 50)
    
    # Save chunks to JSON (with previews for agno agent)
    with open("/tmp/document_chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    
    # Display summary
    element_types = {}
    for chunk in chunks:
        etype = chunk['element_type'] or 'unknown'
        element_types[etype] = element_types.get(etype, 0) + 1
    
    print("\nElement Type Summary:")
    for etype, count in sorted(element_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {etype}: {count}")
    
    print("\n" + "=" * 50)
    print("✅ All chunks saved to /tmp/document_chunks.json")
    print(f"✅ Total chunks: {len(chunks)}")
    print("\n🎯 Ready for agno agent integration!")
    print("   Each chunk contains:")
    print("   - text: Content")
    print("   - page: Page number") 
    print("   - bbox: Coordinates (l, t, r, b)")
    print("   - element_type: Type classification")
    print("=" * 50)