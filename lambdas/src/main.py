"""Main script to parse PDF and extract information using agno agent."""

import json
import argparse
import os
import shutil
from pathlib import Path
from datetime import datetime
from pdf_parser import parse_pdf_to_chunks
from agents import ContractInformationAgent, InstallmentSeriesAgent
from agents.contract_information_agent import load_chunks, save_result
from cutout_extractor import CutoutExtractor, save_cutout_manifest
from report_generator import generate_units_report

# Import S3Provider para downloads do S3 e HTTPProvider para notificações
import sys
sys.path.insert(0, os.path.dirname(__file__))
from s3_provider import S3Provider
from http_provider import HTTPProvider

def cleanup_output_directory(output_dir: str) -> None:
    """Clean up the output directory before each run."""
    output_path = Path(output_dir)
    if output_path.exists():
        print(f"🧹 Cleaning output directory: {output_dir}")
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"✓ Output directory ready: {output_dir}")


def upload_cutouts_to_s3(
    s3_provider: S3Provider,
    cutout_paths: dict,
    bucket_name: str,
    job_id: str
) -> dict:
    """
    Upload all cutout images to S3 with consistent key structure.
    
    New structure: contracts/{job_id}/unit_{index}/{fieldName}.png
    
    Args:
        s3_provider: S3Provider instance
        cutout_paths: Dictionary mapping field names to lists of local file paths
                     Format: "unit{N}_{fieldName}" -> [local_paths]
        bucket_name: S3 bucket name
        job_id: Unique job identifier for organizing files
        
    Returns:
        Dictionary mapping field names to lists of S3 URIs
    """
    s3_cutout_paths = {}
    total_uploaded = 0
    
    print(f"📤 Uploading cutouts to S3 bucket: {bucket_name}")
    
    for field_key, local_paths in cutout_paths.items():
        s3_cutout_paths[field_key] = []
        
        # Extract unit index and field name from field_key
        # Format: "unit1_fieldName" -> unit_index=1, field_name="fieldName"
        if '_' in field_key:
            parts = field_key.split('_', 1)
            unit_part = parts[0]  # e.g., "unit1"
            field_name = parts[1]  # e.g., "buyerName"
            
            # Extract unit index
            unit_index = unit_part.replace('unit', '')
        else:
            # Fallback
            unit_index = '0'
            field_name = field_key
        
        for local_path in local_paths:
            try:
                # Extract file extension
                ext = os.path.splitext(local_path)[1]
                
                # Create new S3 key structure:
                # contracts/{job_id}/images/unit_{index}/{fieldName}.png
                s3_key = f"contracts/{job_id}/images/unit_{unit_index}/{field_name}{ext}"
                
                # Determine content type based on file extension
                content_type_map = {
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp'
                }
                content_type = content_type_map.get(ext.lower(), 'application/octet-stream')
                
                # Upload file to S3
                s3_uri = s3_provider.upload_file_from_path(
                    local_path=local_path,
                    bucket_name=bucket_name,
                    key=s3_key,
                    extra_args={'ContentType': content_type}
                )
                
                s3_cutout_paths[field_key].append(s3_uri)
                total_uploaded += 1
                
            except Exception as e:
                print(f"⚠️  Warning: Failed to upload {local_path}: {e}")
                continue
    
    print(f"✓ Uploaded {total_uploaded} cutout images to S3")
    return s3_cutout_paths


def upload_result_file_to_s3(
    s3_provider: S3Provider,
    local_path: str,
    bucket_name: str,
    job_id: str,
    filename: str,
    content_type: str = 'application/json'
) -> str:
    """
    Upload a result file to S3 with proper error handling.
    
    Args:
        s3_provider: S3Provider instance
        local_path: Path to the local file
        bucket_name: S3 bucket name
        job_id: Unique job identifier
        filename: Filename to use in S3 (e.g., 'document_chunks.json')
        content_type: MIME type of the file
        
    Returns:
        S3 URI of the uploaded file
        
    Raises:
        Exception: If upload fails
    """
    try:
        s3_key = f"contracts/{job_id}/{filename}"
        
        s3_uri = s3_provider.upload_file_from_path(
            local_path=local_path,
            bucket_name=bucket_name,
            key=s3_key,
            extra_args={'ContentType': content_type}
        )
        
        print(f"✓ Uploaded {filename} to S3: {s3_uri}")
        return s3_uri
        
    except Exception as e:
        print(f"⚠️  Warning: Failed to upload {filename} to S3: {e}")
        raise


def save_raw_text_from_chunks(chunks: list, output_path: str) -> None:
    """
    Generate and save raw text file from document chunks.
    
    Args:
        chunks: List of document chunks with text and page information
        output_path: Path where to save the raw text file
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            current_page = None
            
            for chunk in chunks:
                page = chunk.get('page')
                text = chunk.get('text', '')
                
                # Add page marker when page changes
                if page != current_page:
                    if current_page is not None:
                        f.write("\n\n")
                    f.write(f"{'=' * 60}\n")
                    f.write(f"PAGE {page}\n")
                    f.write(f"{'=' * 60}\n\n")
                    current_page = page
                
                # Write chunk text
                f.write(text)
                f.write("\n\n")
        
        print(f"✓ Saved raw text to {output_path}")
        
    except Exception as e:
        print(f"⚠️  Warning: Failed to save raw text: {e}")
        raise


def merge_results_with_cutouts(
    contract_result: list,
    installment_result: list,
    s3_cutout_paths: dict
) -> list:
    """
    Merge contract and installment results and map chunk_id to chunk_file_key (S3 URIs).
    
    Args:
        contract_result: List of contract extraction results
        installment_result: List of installment extraction results
        s3_cutout_paths: Dictionary mapping field keys to S3 URIs
                        Format: "unit1_fieldName" -> ["s3://..."]
        
    Returns:
        List of merged results with chunk_file_key instead of chunk_id
    """
    merged_units = []
    
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
    
    # Process each unit
    for unit_idx, contract_unit in enumerate(contract_result):
        unit_number = unit_idx + 1
        
        # Start with contract data
        merged_unit = {
            'unit': contract_unit.get('unit', {}).copy(),
            'sources': [],
            'confidence': contract_unit.get('confidence', {}).copy()
        }
        
        # Add installment data if available
        if unit_idx < len(installment_result):
            installment_unit = installment_result[unit_idx]
            installment_plans = installment_unit.get('unit', {}).get('installmentPlans', [])
            
            if installment_plans:
                merged_unit['unit']['installmentPlans'] = installment_plans
            
            # Merge confidence
            installment_confidence = installment_unit.get('confidence', {})
            merged_unit['confidence'].update(installment_confidence)
        
        # Process contract sources and map to S3 URIs
        for source in dedupe_sources(contract_unit.get('sources', [])):
            field = source.get('field')
            chunk_id = source.get('chunk_id')
            
            # Build field key for lookup in s3_cutout_paths
            field_key = f"unit{unit_number}_{field}"
            
            # Get S3 URI from cutout paths
            s3_uris = s3_cutout_paths.get(field_key, [])
            
            if s3_uris:
                # Use the first S3 URI (usually there's only one per field)
                chunk_file_key = s3_uris[0]
            else:
                # If no cutout available, keep original chunk_id or set to None
                chunk_file_key = chunk_id if chunk_id != 'calculated' else None
            
            merged_unit['sources'].append({
                'field': field,
                'chunk_id': chunk_id,
                'chunk_file_key': chunk_file_key
            })
        
        # Add installment sources if available
        if unit_idx < len(installment_result):
            installment_sources = dedupe_sources(installment_result[unit_idx].get('sources', []))
            
            for source in installment_sources:
                field = source.get('field')
                chunk_id = source.get('chunk_id')
                
                # Skip if already in sources (from contract)
                if any(s['field'] == field and s.get('chunk_id') == chunk_id for s in merged_unit['sources']):
                    continue
                
                field_key = f"unit{unit_number}_{field}"
                s3_uris = s3_cutout_paths.get(field_key, [])
                
                if s3_uris:
                    chunk_file_key = s3_uris[0]
                else:
                    chunk_file_key = chunk_id
                
                merged_unit['sources'].append({
                    'field': field,
                    'chunk_file_key': chunk_file_key
                })
        
        merged_units.append(merged_unit)
    
    return merged_units

def _log_chunk_coverage(label: str, units: list):
    missing = []
    for unit_idx, unit in enumerate(units or []):
        for source in unit.get('sources', []):
            if not source.get('chunk_id'):
                missing.append((unit_idx + 1, source.get('field')))

    if missing:
        print(f"\n⚠️  [{label}] {len(missing)} sources missing chunk_id:")
        for unit_number, field in missing:
            print(f"   - Unit {unit_number}, field '{field}'")
    else:
        print(f"\n✓ [{label}] All sources include chunk_id")


def send_extraction_results_to_endpoint(
    http_provider: HTTPProvider,
    api_url: str,
    api_key: str,
    contract_id: str,
    output_path: str,
    status: str = "success",
    error_message: str = None,
    error_type: str = None
) -> bool:
    """
    Helper function to send extraction results to the backend HTTP endpoint.
    
    Args:
        http_provider: HTTPProvider instance
        api_url: Base URL of the backend API
        api_key: API key for authentication
        contract_id: UUID of the contract
        output_path: S3 path prefix where results are stored
        status: "success" or "error"
        error_message: Optional error message if status is "error"
        error_type: Optional error type if status is "error"
        
    Returns:
        True if the request was successful, False otherwise.
    """
    payload = {
        'contract_id': contract_id,
        'output_path': output_path,
        'status': status,
    }
    if error_message:
        payload['error_message'] = error_message
    if error_type:
        payload['error_type'] = error_type

    return http_provider.send_extraction_results(
        api_url=api_url,
        api_key=api_key,
        payload=payload
    )


# Entrypoint of the Lambda function
def handler(event, context):
    """
    Lambda handler para processar mensagens SQS com informações de arquivos PDF no S3.
    
    Args:
        event: Evento do Lambda contendo mensagens do SQS
        context: Contexto de execução do Lambda
    """
    # Obter bucket name da variável de ambiente (configuração de infraestrutura)
    bucket_name = os.environ.get('S3_BUCKET_NAME')
    if not bucket_name:
        print(f"❌ Error: S3_BUCKET_NAME environment variable not set")
        raise ValueError("S3_BUCKET_NAME environment variable is required")
    
    print(f"📦 Using S3 bucket: {bucket_name}")
    
    # Inicializa o S3Provider
    # Autenticação: Usa AWS_ACCESS_KEY_ID e AWS_SECRET_ACCESS_KEY se disponíveis,
    # caso contrário usa IAM Role do Lambda (default credential chain)
    s3_provider = S3Provider()
    
    # Get API URL and API Key from environment
    api_url = os.environ.get('API_URL')
    api_key = os.environ.get('API_KEY')
    
    # Initialize HTTP provider
    http_provider = HTTPProvider()
    
    for record in event['Records']:
        contract_id = None  # Initialize contract_id for error reporting outside try block
        output_path = None  # Initialize output_path for error reporting outside try block
        try:
            # Parse da mensagem SQS
            message = json.loads(record['body'])
            file_key = message.get('file_key')
            contract_id = message.get('contract_id')
            
            if not file_key:
                print(f"❌ Error: 'file_key' not found in message: {message}")
                continue
            
            if not contract_id:
                print(f"❌ Error: 'contract_id' not found in message: {message}")
                continue
            
            print(f"📥 Processing file: s3://{bucket_name}/{file_key}")
            
            # Define o caminho local no /tmp do Lambda
            file_name = file_key.split('/')[-1]
            local_file_path = f"/tmp/{file_name}"
            
            # Faz o download do arquivo do S3 usando S3Provider
            print(f"⬇️  Downloading from S3 to {local_file_path}...")
            s3_provider.download_file_to_path(bucket_name, file_key, local_file_path)
            print(f"✓ File downloaded successfully")
            
            job_id = contract_id
            output_path = f"contracts/{contract_id}/"
            
            # Processa o arquivo with error handling
            try:
                main(
                    pdf_path=local_file_path,
                    bucket_name=bucket_name,
                    job_id=job_id
                )
                
                # Send success notification to endpoint
                if api_url and api_key:
                    print(f"\n[8/8] Sending extraction results to backend endpoint...")
                    success = send_extraction_results_to_endpoint(
                        http_provider=http_provider,
                        api_url=api_url,
                        api_key=api_key,
                        contract_id=contract_id,
                        output_path=output_path,
                        status="success"
                    )
                    if success:
                        print(f"✓ Successfully notified backend endpoint")
                    else:
                        print(f"⚠️  Failed to notify backend endpoint (non-blocking)")
                else:
                    print(f"⚠️  Skipping endpoint notification: API_URL or API_KEY not set")
                
            except Exception as processing_error:
                # Log the error
                error_type = type(processing_error).__name__
                error_message = str(processing_error)
                print(f"❌ Error processing contract: {error_type} - {error_message}")
                import traceback
                traceback.print_exc()
                
                # Send error notification to endpoint
                if api_url and api_key:
                    print(f"\n[Error Notification] Sending error to backend endpoint...")
                    send_extraction_results_to_endpoint(
                        http_provider=http_provider,
                        api_url=api_url,
                        api_key=api_key,
                        contract_id=contract_id,
                        output_path=output_path,
                        status="error",
                        error_message=error_message,
                        error_type=error_type
                    )
                else:
                    print(f"⚠️  Skipping error notification: API_URL or API_KEY not set")
                
            finally:
                # Cleanup: remove o arquivo temporário após processamento
                if os.path.exists(local_file_path):
                    os.remove(local_file_path)
                    print(f"🧹 Cleaned up temporary file: {local_file_path}")
                    
        except Exception as e:
            print(f"❌ Error processing record: {e}")
            import traceback
            traceback.print_exc()
            # If contract_id and output_path are available, attempt to send error notification
            if contract_id and output_path and api_url and api_key:
                print(f"\n[Error Notification - SQS Record Level] Sending error to backend endpoint...")
                send_extraction_results_to_endpoint(
                    http_provider=HTTPProvider(),  # Re-initialize if needed
                    api_url=api_url,
                    api_key=api_key,
                    contract_id=contract_id,
                    output_path=output_path,
                    status="error",
                    error_message=str(e),
                    error_type=type(e).__name__
                )
            continue  # Continue processing other messages
    
def main(pdf_path, bucket_name: str = None, job_id: str = None):
    """
    Main execution flow.
    
    Args:
        pdf_path: Path to the PDF file to process
        bucket_name: S3 bucket name for uploading cutouts (optional)
        job_id: Unique job identifier for organizing S3 files (optional)
    """
    print("=" * 60)
    print("Contract Information Extraction System")
    print("=" * 60)
    
    # Configuration
    OUTPUT_DIR = "/tmp/output"
    
    # Generate job_id if not provided (use PDF filename and timestamp)
    if job_id is None:
        import time
        pdf_filename = os.path.splitext(os.path.basename(pdf_path))[0]
        timestamp = int(time.time())
        job_id = f"{pdf_filename}_{timestamp}"
    
    print(f"📝 Job ID: {job_id}")
    
    # Clean up output directory
    cleanup_output_directory(OUTPUT_DIR)

    chunks_output = os.path.join(OUTPUT_DIR, "document_chunks.json")
    result_output = os.path.join(OUTPUT_DIR, "extraction_result.json")
    
    # Step 1: Parse PDF to chunks (if not already done)
    print("\n[1/7] Parsing PDF document...")
    try:
        # Try to load existing chunks
        chunks = load_chunks(chunks_output)
        print(f"✓ Loaded {len(chunks)} chunks from {chunks_output}")
    except FileNotFoundError:
        # Parse PDF if chunks don't exist
        chunks = parse_pdf_to_chunks(pdf_path)
        
        # Save chunks
        with open(chunks_output, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Extracted {len(chunks)} chunks from {pdf_path}")
        print(f"✓ Saved chunks to {chunks_output}")
        
        # Generate and save raw text file
        raw_text_output = os.path.join(OUTPUT_DIR, "document_text.txt")
        save_raw_text_from_chunks(chunks, raw_text_output)
        
        # Upload chunks and raw text to S3 if bucket provided
        if bucket_name:
            try:
                s3_provider = S3Provider()
                upload_result_file_to_s3(
                    s3_provider=s3_provider,
                    local_path=chunks_output,
                    bucket_name=bucket_name,
                    job_id=job_id,
                    filename="document_chunks.json",
                    content_type='application/json'
                )
                upload_result_file_to_s3(
                    s3_provider=s3_provider,
                    local_path=raw_text_output,
                    bucket_name=bucket_name,
                    job_id=job_id,
                    filename="document_text.txt",
                    content_type='text/plain'
                )
            except Exception as e:
                print(f"⚠️  Warning: Failed to upload chunks/text to S3: {e}")
    
    # Display chunk statistics
    element_types = {}
    for chunk in chunks:
        etype = chunk['element_type'] or 'unknown'
        element_types[etype] = element_types.get(etype, 0) + 1
    
    print("\n  Chunk Statistics:")
    for etype, count in sorted(element_types.items(), key=lambda x: x[1], reverse=True):
        print(f"    - {etype}: {count}")
    
    # Step 2: Initialize extraction agents
    print("\n[2/7] Setting up extraction agents...")
    contract_information_agent = ContractInformationAgent(model="gpt-4o-mini")
    installment_series_agent = InstallmentSeriesAgent(model="gpt-4o-mini")
    
    # Display configured fields
    contract_fields = contract_information_agent.get_field_descriptions()
    installment_fields = installment_series_agent.get_field_descriptions()
    
    print(f"✓ Contract Information Agent: {len(contract_fields)} fields")
    for field, desc in contract_fields.items():
        print(f"    - {field}: {desc}")
    
    print(f"✓ Installment Series Agent: {len(installment_fields)} fields")
    for field, desc in installment_fields.items():
        print(f"    - {field}: {desc}")
    
    # Step 3: Run contract information extraction
    print("\n[3/7] Running contract information agent for data extraction...")
    contract_result = contract_information_agent.extract_information(chunks)
    _log_chunk_coverage("Contract information", contract_result)
    
    # Save contract result
    contract_output = os.path.join(OUTPUT_DIR, "contract_extraction_result.json")
    save_result(contract_result, contract_output)
    
    print(f"✓ Contract information extraction complete!")
    print(f"✓ Results saved to {contract_output}")
    
    # Upload contract result to S3 if bucket provided
    if bucket_name:
        try:
            s3_provider = S3Provider()
            upload_result_file_to_s3(
                s3_provider=s3_provider,
                local_path=contract_output,
                bucket_name=bucket_name,
                job_id=job_id,
                filename="contract_extraction_result.json",
                content_type='application/json'
            )
        except Exception as e:
            print(f"⚠️  Warning: Failed to upload contract result to S3: {e}")
    
    # Step 4: Run installment series extraction
    print("\n[4/7] Running installment series agent for payment extraction...")
    installment_result = installment_series_agent.extract_information(chunks)
    _log_chunk_coverage("Installment information", installment_result)
    
    # Save installment result
    from agents.installment_series_agent import save_result as save_installment_result
    # Save installment result in our Database
    installment_output = os.path.join(OUTPUT_DIR, "installment_extraction_result.json")
    save_installment_result(installment_result, installment_output)
    
    print(f"✓ Installment series extraction complete!")
    print(f"✓ Results saved to {installment_output}")
    
    # Upload installment result to S3 if bucket provided
    if bucket_name:
        try:
            s3_provider = S3Provider()
            upload_result_file_to_s3(
                s3_provider=s3_provider,
                local_path=installment_output,
                bucket_name=bucket_name,
                job_id=job_id,
                filename="installment_extraction_result.json",
                content_type='application/json'
            )
        except Exception as e:
            print(f"⚠️  Warning: Failed to upload installment result to S3: {e}")
    
    # Combine results for backward compatibility
    result = contract_result
    
    # Display results
    print("\n" + "=" * 60)
    print("EXTRACTION RESULTS")
    print("=" * 60)
    
    print("\n📋 Extracted Data:")
    # Handle new array structure
    if isinstance(result, list):
        units_data = result
    else:
        # Fallback for old structure
        units_data = result.get('units', [result])
    
    print(f"  Found {len(units_data)} unit(s) in the contract")
    
    for unit_idx, unit_data in enumerate(units_data):
        print(f"\n  🏠 Unit {unit_idx + 1}:")
        
        # Extract unit, sources, and confidence from the structure
        unit = unit_data.get('unit', unit_data)  # Fallback for old structure
        sources = unit_data.get('sources', [])
        confidence = unit_data.get('confidence', {})
        
        for field, value in unit.items():
            conf = confidence.get(field, 'unknown')
            print(f"    {field.replace('_', ' ').title()}:")
            print(f"      Value: {value}")
            print(f"      Confidence: {conf}")
    
    print(f"\n📍 Sources Used:")
    
    # Collect all sources for display
    all_sources = []
    for unit_idx, unit_data in enumerate(units_data):
        sources = unit_data.get('sources', [])
        for source in sources:
            source['unit_index'] = unit_idx
            all_sources.append(source)
    
    print(f"  Total chunks referenced: {len(all_sources)}")
    
    for source in all_sources[:5]:  # Show first 5 sources
        unit_idx = source.get('unit_index', 'N/A')
        field = source.get('field', 'unknown')
        chunk_id = source.get('chunk_id', 'N/A')
        page = source.get('page', 'N/A')
        print(f"\n  Unit {unit_idx + 1 if unit_idx != 'N/A' else 'N/A'} - Field: {field}")
        print(f"    Chunk: {chunk_id} (Page {page})")
        
        excerpt = source.get('text_excerpt')
        if excerpt:
            print(f"    Excerpt: {excerpt[:100]}...")
        else:
            print(f"    Excerpt: (no excerpt available)")
    
    if len(all_sources) > 5:
        print(f"\n  ... and {len(all_sources) - 5} more sources")
    
    # Display installment results
    print(f"\n💳 Installment Plans:")
    if isinstance(installment_result, list) and installment_result:
        total_plans = 0
        for unit_data in installment_result:
            unit = unit_data.get('unit', {})
            installment_plans = unit.get('installmentPlans', [])
            total_plans += len(installment_plans)
        
        print(f"  Found {total_plans} installment plan(s) across {len(installment_result)} unit(s)")
        
        for unit_idx, unit_data in enumerate(installment_result):
            unit = unit_data.get('unit', {})
            unit_code = unit.get("unitCode", "Unknown")
            installment_plans = unit.get('installmentPlans', [])
            
            if installment_plans:
                print(f"\n  🏠 Unit {unit_idx + 1} ({unit_code}):")
                for plan_idx, plan in enumerate(installment_plans):
                    series = plan.get("series", "Unknown")
                    installments = plan.get("totalInstallments", "Unknown")
                    amount = plan.get("installmentAmount", "N/A")
                    print(f"    📋 Plan {plan_idx + 1}:")
                    print(f"      Series: {series}")
                    print(f"      Installments: {installments}")
                    if amount != "N/A" and amount is not None:
                        print(f"      Amount: R$ {amount:,.2f}")
                    else:
                        print(f"      Amount: N/A")
    else:
        print("  No installment plans found")
    
    # Step 5: Extract cutouts
    print("\n[5/7] Extracting cutout images from PDF...")
    cutouts_dir = os.path.join(OUTPUT_DIR, "cutouts")
    
    # Combine contract and installment results for cutout extraction
    combined_result = contract_result.copy() if isinstance(contract_result, list) else [contract_result]
    
    # Add installment data to the combined result
    if isinstance(installment_result, list):
        for unit_idx, installment_unit in enumerate(installment_result):
            if unit_idx < len(combined_result):
                # Add installment sources and installmentPlans to existing unit
                installment_sources = installment_unit.get('sources', [])
                installment_plans = installment_unit.get('unit', {}).get('installmentPlans', [])
                installment_confidence = installment_unit.get('confidence', {})
                
                combined_result[unit_idx]['sources'].extend(installment_sources)
                
                # Add installmentPlans to the unit data
                if 'unit' not in combined_result[unit_idx]:
                    combined_result[unit_idx]['unit'] = {}
                combined_result[unit_idx]['unit']['installmentPlans'] = installment_plans
                
                # Merge installment confidence with existing confidence
                if 'confidence' not in combined_result[unit_idx]:
                    combined_result[unit_idx]['confidence'] = {}
                combined_result[unit_idx]['confidence'].update(installment_confidence)
            else:
                # Add new unit if installment has more units than contract
                combined_result.append(installment_unit)
    
    # Extract cutout images
    with CutoutExtractor(pdf_path) as extractor:
        cutout_paths = extractor.extract_cutouts(
            extraction_result=combined_result,
            output_dir=cutouts_dir,
            padding=10,
            scale=2.0,
            chunks=chunks
        )
    
    print(f"\n✓ Extracted {sum(len(paths) for paths in cutout_paths.values())} cutout images")
    
    # Upload cutouts to S3 if bucket_name is provided
    final_cutout_paths = cutout_paths  # Will be replaced with S3 URIs if upload succeeds
    s3_cutout_paths = None  # Track if S3 upload was successful
    
    if bucket_name:
        try:
            # S3Provider usa credenciais de ambiente ou IAM role automaticamente
            s3_provider = S3Provider()
            s3_cutout_paths = upload_cutouts_to_s3(
                s3_provider=s3_provider,
                cutout_paths=cutout_paths,
                bucket_name=bucket_name,
                job_id=job_id
            )
            final_cutout_paths = s3_cutout_paths
            print(f"✓ All cutouts uploaded to S3")
        except Exception as e:
            print(f"⚠️  Warning: Failed to upload cutouts to S3: {e}")
            print(f"   Using local paths in manifest instead")
            s3_cutout_paths = None
    
    # Save cutout manifest (with S3 URIs if uploaded, otherwise local paths)
    cutout_manifest_path = os.path.join(OUTPUT_DIR, "cutout_manifest.json")
    save_cutout_manifest(final_cutout_paths, cutout_manifest_path)
    print(f"✓ Cutout manifest saved to {cutout_manifest_path}")
    
    # Upload cutout manifest to S3 if bucket provided
    if bucket_name:
        try:
            s3_provider = S3Provider()
            upload_result_file_to_s3(
                s3_provider=s3_provider,
                local_path=cutout_manifest_path,
                bucket_name=bucket_name,
                job_id=job_id,
                filename="cutout_manifest.json",
                content_type='application/json'
            )
        except Exception as e:
            print(f"⚠️  Warning: Failed to upload cutout manifest to S3: {e}")
    
    # Step 6: Generate markdown report
    print("\n[6/7] Generating markdown report...")
    
    # Generate markdown report using combined result
    markdown_report_path = generate_units_report(combined_result, OUTPUT_DIR, cutout_manifest_path)
    print(f"✓ Markdown report saved to: {markdown_report_path}")
    
    # Upload markdown report to S3 if bucket provided
    if bucket_name:
        try:
            s3_provider = S3Provider()
            upload_result_file_to_s3(
                s3_provider=s3_provider,
                local_path=markdown_report_path,
                bucket_name=bucket_name,
                job_id=job_id,
                filename="report.md",
                content_type='text/markdown'
            )
        except Exception as e:
            print(f"⚠️  Warning: Failed to upload markdown report to S3: {e}")
    
    # Step 7: Save merged results for inspection and upload to S3
    print("\n[7/7] Saving merged results...")
    
    if bucket_name and s3_cutout_paths is not None:
        # Merge results and map chunk IDs to S3 file keys
        merged_results = merge_results_with_cutouts(
            contract_result=contract_result,
            installment_result=installment_result,
            s3_cutout_paths=s3_cutout_paths
        )
        
        # Save merged results for inspection
        merged_output = os.path.join(OUTPUT_DIR, "merged_notification_payload.json")
        with open(merged_output, 'w', encoding='utf-8') as f:
            json.dump({
                'jobId': job_id,
                'bucketName': bucket_name,
                'status': 'success',
                'processedAt': datetime.utcnow().isoformat() + 'Z',
                'units': merged_results
            }, f, indent=2, ensure_ascii=False)
        print(f"✓ Merged notification payload saved to: {merged_output}")
        
        # Upload merged notification payload to S3
        try:
            s3_provider = S3Provider()
            upload_result_file_to_s3(
                s3_provider=s3_provider,
                local_path=merged_output,
                bucket_name=bucket_name,
                job_id=job_id,
                filename="merged_notification_payload.json",
                content_type='application/json'
            )
        except Exception as e:
            print(f"⚠️  Warning: Failed to upload merged notification payload to S3: {e}")
        
        # Note: HTTP endpoint notification is now handled in the handler() function
    else:
        print(f"⚠️  Skipping merged results upload: S3 upload was not successful or bucket not provided")
    
    print("\n" + "=" * 60)
    print("✅ Processing complete!")
    print(f"📄 Contract results available in: {contract_output}")
    print(f"💳 Installment results available in: {installment_output}")
    print(f"🖼️  Cutout images available in: {cutouts_dir}")
    print(f"📊 Markdown report available in: {markdown_report_path}")
    print(f"📁 All output files in: {OUTPUT_DIR}/")
    
    if bucket_name:
        print("\n📤 S3 Uploads:")
        print(f"   Bucket: {bucket_name}")
        print(f"   Base Path: contracts/{job_id}/")
        print(f"   Files uploaded:")
        print(f"     - document_chunks.json")
        print(f"     - document_text.txt")
        print(f"     - contract_extraction_result.json")
        print(f"     - installment_extraction_result.json")
        print(f"     - cutout_manifest.json")
        print(f"     - report.md")
        if s3_cutout_paths:
            print(f"     - images/unit_*/{{fieldName}}.png (cutouts)")
            print(f"     - merged_notification_payload.json")
    
    print("=" * 60)

