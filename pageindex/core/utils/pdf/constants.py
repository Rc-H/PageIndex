import re

from pageindex.core.utils.image_constants import (  # noqa: F401 — re-export for compatibility
    DEFAULT_IMAGE_ALT_TEXT,
    IMAGE_DESCRIPTION_PROMPT,
    IMAGE_TITLE_PROMPT,
    MAX_IMAGE_DESCRIPTION_LENGTH,
    MAX_IMAGE_TITLE_LENGTH,
)

PAGE_NUMBER_ARTIFACT_PATTERNS = [
    re.compile(r"^\s*第\s*\d+\s*页\s*共\s*\d+\s*页\s*$"),
    re.compile(r"^\s*第\s*\d+\s*页\s*$"),
    re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE),
]

TEXT_BLOCK_TYPE = "text"
IMAGE_BLOCK_TYPE = "image"
TABLE_BLOCK_TYPE = "table"

IMAGE_ENGINE_NAME = "attachment_upload"
PDFPLUMBER_ENGINE_NAME = "pdfplumber"
CAMELOT_ENGINE_NAME = "camelot"

DEFAULT_TABLE_TITLE = "表格"
MAX_TABLE_TITLE_LENGTH = 15

PAGE_HEADER_TOP_RATIO = 0.15
PAGE_HEADER_MAX_HEIGHT_RATIO = 0.15
MIN_PAGES_FOR_HEADER = 2

PAGE_HEADER_DETECTION_PROMPT = (
    "以下是一张从PDF文档中提取的表格内容。\n"
    "注意：空白单元格可能包含图片（如公司Logo），这是正常现象。\n"
    "请判断它是否是页眉（即每页都会重复出现的表格，通常包含公司名称、文档标题、"
    "文档编号、版本号、日期等文档属性信息，而非正文内容）。\n"
    "只返回 JSON，格式为 {{\"is_header\": true}} 或 {{\"is_header\": false}}，不要输出其他内容。\n\n"
    "{table_markdown}"
)

TABLE_TITLE_PROMPT_TEMPLATE = (
    "你会收到一张表格的 Markdown 内容。\n"
    "请只返回一个中文标题，不超过15个字，概括这张表在比较或说明什么。\n"
    "不要解释，不要标点，不要引号。\n\n"
    "{table_markdown}"
)

TABLE_SUMMARY_PROMPT_TEMPLATE = (
    "你会收到一张表格的 Markdown 内容。\n"
    "请用中文总结这张表的核心信息，限制1到2句，不要使用项目符号。\n\n"
    "{table_markdown}"
)
