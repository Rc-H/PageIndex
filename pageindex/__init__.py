def page_index(*args, **kwargs):
    from pageindex.core.indexers.pdf.indexer import page_index as impl

    return impl(*args, **kwargs)


def page_index_main(*args, **kwargs):
    from pageindex.core.indexers.pdf.indexer import page_index_main as impl

    return impl(*args, **kwargs)


async def md_to_tree(*args, **kwargs):
    from pageindex.core.indexers.markdown.indexer import md_to_tree as impl

    return await impl(*args, **kwargs)


def create_app(*args, **kwargs):
    from pageindex.api.app import create_app as impl

    return impl(*args, **kwargs)


__all__ = ["page_index", "page_index_main", "md_to_tree", "create_app"]
