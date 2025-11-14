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

# Import S3Provider para downloads do S3 e SNSProvider para notificações
import sys
sys.path.insert(0, os.path.dirname(__file__))
from s3_provider import S3Provider
from sns_provider import SNSProvider

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
                # contracts/{job_id}/unit_{index}/{fieldName}.png
                s3_key = f"contracts/{job_id}/unit_{unit_index}/{field_name}{ext}"
                
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
        for source in contract_unit.get('sources', []):
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
                'chunk_file_key': chunk_file_key
            })
        
        # Add installment sources if available
        if unit_idx < len(installment_result):
            installment_sources = installment_result[unit_idx].get('sources', [])
            
            for source in installment_sources:
                field = source.get('field')
                chunk_id = source.get('chunk_id')
                
                # Skip if already in sources (from contract)
                if any(s['field'] == field for s in merged_unit['sources']):
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


def send_sns_notification(
    sns_provider: SNSProvider,
    topic_arn: str,
    merged_results: list,
    job_id: str,
    bucket_name: str,
    status: str = "success"
) -> str:
    """
    Send SNS notification with extraction results.
    
    Args:
        sns_provider: SNSProvider instance
        topic_arn: ARN of the SNS topic
        merged_results: List of merged extraction results
        job_id: Job identifier
        bucket_name: S3 bucket name
        status: Processing status (default: "success")
        
    Returns:
        Message ID from SNS
    """
    # Build notification payload
    notification_payload = {
        'jobId': job_id,
        'bucketName': bucket_name,
        'status': status,
        'processedAt': datetime.utcnow().isoformat() + 'Z',
        'units': merged_results
    }
    
    # Send to SNS
    message_id = sns_provider.publish_message(
        topic_arn=topic_arn,
        message=notification_payload,
        subject=f"Contract Processing Complete - {job_id}"
    )
    
    return message_id


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
    
    for record in event['Records']:
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
            
            # Processa o arquivo
            main(
                pdf_path=local_file_path,
                bucket_name=bucket_name,
                job_id=job_id
            )
            
            # Cleanup: remove o arquivo temporário após processamento
            if os.path.exists(local_file_path):
                os.remove(local_file_path)
                print(f"🧹 Cleaned up temporary file: {local_file_path}")
                
        except Exception as e:
            print(f"❌ Error processing record: {e}")
            import traceback
            traceback.print_exc()
            # Continue processando outras mensagens
            continue
    
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
    
    # Save contract result
    contract_output = os.path.join(OUTPUT_DIR, "contract_extraction_result.json")
    save_result(contract_result, contract_output)
    
    print(f"✓ Contract information extraction complete!")
    print(f"✓ Results saved to {contract_output}")
    
    # Step 4: Run installment series extraction
    print("\n[4/7] Running installment series agent for payment extraction...")
    installment_result = installment_series_agent.extract_information(chunks)
    
    # Save installment result
    from agents.installment_series_agent import save_result as save_installment_result
    # Save installment result in our Database
    installment_output = os.path.join(OUTPUT_DIR, "installment_extraction_result.json")
    save_installment_result(installment_result, installment_output)
    
    print(f"✓ Installment series extraction complete!")
    print(f"✓ Results saved to {installment_output}")
    
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
    
    # Step 6: Generate markdown report
    print("\n[6/7] Generating markdown report...")
    
    # Generate markdown report using combined result
    markdown_report_path = generate_units_report(combined_result, OUTPUT_DIR, cutout_manifest_path)
    print(f"✓ Markdown report saved to: {markdown_report_path}")
    
    # Step 7: Send SNS notification (only if S3 upload was successful)
    print("\n[7/7] Sending SNS notification...")
    
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
        
        # Get SNS topic ARN from environment
        sns_topic_arn = os.environ.get('SNS_TOPIC_ARN')
        
        if sns_topic_arn:
            try:
                sns_provider = SNSProvider()
                message_id = send_sns_notification(
                    sns_provider=sns_provider,
                    topic_arn=sns_topic_arn,
                    merged_results=merged_results,
                    job_id=job_id,
                    bucket_name=bucket_name,
                    status='success'
                )
                print(f"✓ SNS notification sent successfully! Message ID: {message_id}")
            except Exception as e:
                print(f"⚠️  Warning: Failed to send SNS notification: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"⚠️  Skipping SNS notification: SNS_TOPIC_ARN environment variable not set")
    else:
        print(f"⚠️  Skipping SNS notification: S3 upload was not successful or bucket not provided")
    
    print("\n" + "=" * 60)
    print("✅ Processing complete!")
    print(f"📄 Contract results available in: {contract_output}")
    print(f"💳 Installment results available in: {installment_output}")
    print(f"🖼️  Cutout images available in: {cutouts_dir}")
    print(f"📊 Markdown report available in: {markdown_report_path}")
    print(f"📁 All output files in: {OUTPUT_DIR}/")
    print("=" * 60)

