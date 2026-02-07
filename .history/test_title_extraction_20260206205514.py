#!/usr/bin/env python3
"""测试标题提取逻辑"""

from pathlib import Path
from src.assembly.section_parser import RegexSectionParser
from src.models import PageContent, ElementType

# 模拟第一页的内容
test_markdown = """# Note
Optimisation of unweighted/weighted maximum independent sets and minimum vertex covers
Wayne Pullan
School of Information and Communication Technology, Griffith University, Gold Coast Campus, Gold Coast, QLD, Australia

## ARTICLE INFO
Article history:
Received 16 October 2006
"""

# 创建模拟的 PageContent
page_content = PageContent(
    page_num=0,
    markdown=test_markdown,
    detected_elements=[]
)

# 测试解析器
parser = RegexSectionParser()
structure = parser.build_structure_index([page_content], test_markdown)

print(f"提取的标题: {structure.title}")
print(f"期望的标题: Optimisation of unweighted/weighted maximum independent sets and minimum vertex covers")
print(f"匹配: {structure.title == 'Optimisation of unweighted/weighted maximum independent sets and minimum vertex covers'}")
