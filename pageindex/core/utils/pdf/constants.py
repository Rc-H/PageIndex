import re


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

DEFAULT_IMAGE_ALT_TEXT = "image"
DEFAULT_TABLE_TITLE = "表格"
MAX_IMAGE_TITLE_LENGTH = 15
MAX_TABLE_TITLE_LENGTH = 15

IMAGE_TITLE_PROMPT = (
    "请概括这张图片的核心内容，只返回一个中文标题，不超过15个字，"
    "不要解释，不要标点，不要引号。"
)

IMAGE_DESCRIPTION_PROMPT = (
    "请详细描述这张图片中包含的所有关键信息。"
    "如果图片包含文字，请提取所有重要文字内容；"
    "如果是流程图，请描述每个步骤和流转关系；"
    "如果是表格，请描述表格的列名和关键数据；"
    "如果是组织架构图，请描述层级和人员关系。"
    "用中文回答，限制在200字以内，不要使用项目符号。"
)
MAX_IMAGE_DESCRIPTION_LENGTH = 200

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
