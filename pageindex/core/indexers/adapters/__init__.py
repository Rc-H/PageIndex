from pageindex.core.indexers.adapters.base import DocumentAdapter
from pageindex.core.indexers.adapters.markdown import MarkdownAdapter
from pageindex.core.indexers.adapters.pdf import PdfAdapter, page_index, page_index_main
from pageindex.core.indexers.adapters.word import WordAdapter

__all__ = ["DocumentAdapter", "MarkdownAdapter", "PdfAdapter", "WordAdapter", "page_index", "page_index_main"]
