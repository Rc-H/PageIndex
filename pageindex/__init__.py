def page_index(*args, **kwargs):
    from pageindex.core.indexers.adapters.pdf import page_index as impl

    return impl(*args, **kwargs)


def page_index_main(*args, **kwargs):
    from pageindex.core.indexers.adapters.pdf import page_index_main as impl

    return impl(*args, **kwargs)


async def md_to_tree(*args, **kwargs):
    from pageindex.core.indexers.adapters.markdown import MarkdownAdapter
    from pageindex.core.indexers.document_indexer import IndexingOptions
    from pageindex.core.indexers.pipeline.context import PipelineContext
    from pageindex.infrastructure.settings import load_settings

    llm_settings = load_settings().llm

    options = IndexingOptions.from_raw(
        {
            "model": llm_settings.model,
            "if_thinning": "yes" if kwargs.get("if_thinning") else "no",
            "thinning_threshold": kwargs.get("min_token_threshold"),
            "if_add_node_summary": kwargs.get("if_add_node_summary", "no"),
            "summary_token_threshold": kwargs.get("summary_token_threshold"),
            "if_add_doc_description": kwargs.get("if_add_doc_description", "no"),
            "if_add_node_text": kwargs.get("if_add_node_text", "no"),
            "if_add_node_id": kwargs.get("if_add_node_id", "yes"),
        }
    )
    context = PipelineContext(
        source_path=kwargs["md_path"] if "md_path" in kwargs else args[0],
        provider_type=llm_settings.provider,
        model=options.model,
        options=options,
        llm_client=None,
    )
    return await MarkdownAdapter().build(context)


def create_app(*args, **kwargs):
    from pageindex.api.app import create_app as impl

    return impl(*args, **kwargs)


__all__ = ["page_index", "page_index_main", "md_to_tree", "create_app"]
