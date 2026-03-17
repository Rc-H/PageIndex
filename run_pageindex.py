import argparse
import asyncio
import json
import os

from pageindex.core.indexers import DocumentIndexer, IndexerDependencies
from pageindex.core.utils.logger import configure_logging
from pageindex.infrastructure.llm import LLMProviderFactory
from pageindex.infrastructure.settings import load_settings


def main():
    parser = argparse.ArgumentParser(description="Process a document and generate a PageIndex structure")
    parser.add_argument("--pdf_path", type=str, help="Path to the PDF file")
    parser.add_argument("--md_path", type=str, help="Path to the Markdown file")
    parser.add_argument("--doc_path", type=str, help="Path to the Word file (.docx or .doc)")

    parser.add_argument("--toc-check-pages", type=int, default=20, help="Number of TOC pages to inspect")
    parser.add_argument("--max-pages-per-node", type=int, default=10, help="Maximum pages per node")
    parser.add_argument("--max-tokens-per-node", type=int, default=20000, help="Maximum tokens per node")
    parser.add_argument("--if-add-node-id", type=str, default="yes", help="Whether to add node id")
    parser.add_argument("--if-add-node-summary", type=str, default="yes", help="Whether to add node summary")
    parser.add_argument("--if-add-doc-description", type=str, default="no", help="Whether to add doc description")
    parser.add_argument("--if-add-node-text", type=str, default="no", help="Whether to add node text")
    parser.add_argument("--if-thinning", type=str, default="no", help="Whether to apply tree thinning")
    parser.add_argument("--thinning-threshold", type=int, default=5000, help="Minimum token threshold for thinning")
    parser.add_argument("--summary-token-threshold", type=int, default=200, help="Token threshold for summaries")
    args = parser.parse_args()

    provided_paths = [path for path in [args.pdf_path, args.md_path, args.doc_path] if path]
    if len(provided_paths) != 1:
        raise ValueError("Exactly one of --pdf_path, --md_path, or --doc_path must be specified")

    target_path = provided_paths[0]
    if not os.path.isfile(target_path):
        raise ValueError(f"Document not found: {target_path}")

    settings = load_settings()
    service_settings = settings.service
    llm_settings = settings.llm
    configure_logging(
        seq_url=service_settings.seq_url,
        seq_api_key=service_settings.seq_api_key,
        level=service_settings.log_level,
        timeout_seconds=service_settings.log_timeout_seconds,
    )
    indexer = DocumentIndexer(
        IndexerDependencies(
            libreoffice_command=service_settings.libreoffice_command,
            doc_conversion_timeout_seconds=service_settings.doc_conversion_timeout_seconds,
            provider_type=llm_settings.provider,
            model=llm_settings.model,
        )
    )
    index_options = {
        "toc_check_page_num": args.toc_check_pages,
        "max_page_num_each_node": args.max_pages_per_node,
        "max_token_num_each_node": args.max_tokens_per_node,
        "if_add_node_id": args.if_add_node_id,
        "if_add_node_summary": args.if_add_node_summary,
        "if_add_doc_description": args.if_add_doc_description,
        "if_add_node_text": args.if_add_node_text,
        "if_thinning": args.if_thinning,
        "thinning_threshold": args.thinning_threshold,
        "summary_token_threshold": args.summary_token_threshold,
    }

    result = asyncio.run(
        indexer.index(
            file_path=target_path,
            index_options=index_options,
            llm_client=LLMProviderFactory.create(llm_settings),
        )
    )

    output_dir = "./results"
    os.makedirs(output_dir, exist_ok=True)
    file_stem = os.path.splitext(os.path.basename(target_path))[0]
    output_file = f"{output_dir}/{file_stem}_structure.json"
    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    print(f"Tree structure saved to: {output_file}")


if __name__ == "__main__":
    main()
