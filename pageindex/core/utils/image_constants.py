"""Image-related constants shared between image_upload and pdf modules.

Kept outside pageindex.core.utils.pdf to avoid circular imports:
image_upload -> pdf/__init__ -> pdf/images -> image_upload.
"""

DEFAULT_IMAGE_ALT_TEXT = "image"
MAX_IMAGE_TITLE_LENGTH = 15

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
