# 本地文献解读 Pipeline 技术方案

> 基于 RTX 5090 32GB 显存的本地大模型文献解读系统

## 1. 项目概述

### 1.1 目标

构建一个完全本地化的学术文献解读系统，能够：

- 自动解析 PDF 学术论文
- 识别文字、公式、表格、图表
- 生成结构化的 Markdown 中间文档
- 利用 LLM 进行深度分析和总结

### 1.2 硬件配置

| 组件 | 规格 |
|------|------|
| GPU | RTX 5090 32GB |
| 显存策略 | 串行处理，按需加载/卸载模型 |
| 峰值显存 | ~24GB |

### 1.3 核心思路

```
PDF文献 → 页面拆分 → 逐页OCR/理解 → 结构化Markdown → LLM深度总结
```

将多模态问题转化为纯文本问题，让 LLM 专注于理解和推理。

---

## 2. 系统架构

### 2.1 整体流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                        PDF 文献输入                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段1: PDF预处理                                                │
│  ├─ 工具: PyMuPDF (CPU)                                         │
│  ├─ 显存: 0GB                                                   │
│  └─ 输出: 页面图像 + 元信息                                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段2: 逐页OCR与理解                                            │
│  ├─ 模型: DeepSeek-OCR2                                         │
│  ├─ 显存: ~16-20GB                                              │
│  ├─ 功能: 文字识别 + 公式转换 + 图表理解 + 表格解析                  │
│  └─ 输出: 每页Markdown + 元素分类                                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                          [卸载模型]
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段3: 文档整合                                                 │
│  ├─ 工具: Python (CPU)                                          │
│  ├─ 显存: 0GB                                                   │
│  ├─ 功能: 合并页面 + 构建结构索引                                  │
│  └─ 输出: 完整Markdown文档 (保存到磁盘)                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段4: LLM深度分析                                              │
│  ├─ 模型: Qwen3-30B-A3B / DeepSeek-V2.5                         │
│  ├─ 显存: ~20-24GB                                              │
│  ├─ 功能: 论文理解 + 方法分析 + 研究启发                           │
│  └─ 输出: 结构化分析报告                                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      最终输出                                    │
│  ├─ paper_structured.md    (中间文档，可复用)                     │
│  ├─ paper_analysis.json    (分析结果)                            │
│  └─ paper_summary.md       (人类可读报告)                         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 显存使用时序

```
时间 ──────────────────────────────────────────────────────────►

阶段1   ████ (CPU only, 0GB)
        │
阶段2   │    ████████████████████ (DeepSeek-OCR2, ~16-20GB)
        │                        │
        │                   [模型卸载]
        │                        │
阶段3   │                        ████ (CPU only, 0GB)
        │                             │
阶段4   │                             ████████████████ (LLM, ~20-24GB)

显存    0GB ─────────────────────────────────────────────────────
        │
       16GB ─────────────────────█████████████
        │                                    │
       24GB ──────────────────────────────────────────█████████████
        │
       32GB ═══════════════════════════════════════════════════════ (上限)
```

---

## 3. 各阶段详细设计

### 3.1 阶段1：PDF预处理

**目标**：将 PDF 拆分为独立页面图像

**工具**：PyMuPDF (fitz) - 纯 CPU 运行，不占用显存

**输入**：PDF 文件路径

**输出**：
- 页面图像列表（PNG 格式，200 DPI）
- PDF 元信息（标题、作者、页数）

```python
def stage1_pdf_preprocessing(pdf_path):
    """
    PDF预处理：拆分为页面图像
    
    Args:
        pdf_path: PDF文件路径
        
    Returns:
        pages: 页面信息列表
        metadata: PDF元信息
    """
    import fitz
    
    doc = fitz.open(pdf_path)
    pages = []
    
    for page_num, page in enumerate(doc):
        # 高DPI渲染，保证OCR质量
        pix = page.get_pixmap(dpi=200)
        img_path = f"{Config.CACHE_DIR}/page_{page_num:03d}.png"
        pix.save(img_path)
        
        pages.append({
            "page_num": page_num,
            "image_path": img_path,
            "width": pix.width,
            "height": pix.height
        })
    
    metadata = {
        "title": doc.metadata.get("title", ""),
        "author": doc.metadata.get("author", ""),
        "total_pages": len(doc)
    }
    
    return pages, metadata
```

**关键参数**：
- DPI 设置为 200，平衡质量和处理速度
- 输出 PNG 格式，无损压缩

---

### 3.2 阶段2：逐页OCR与理解

**目标**：对每页进行 OCR 识别和语义理解

**模型**：DeepSeek-OCR2

**显存占用**：约 16-20GB

**输入**：页面图像

**输出**：
- 每页的 Markdown 内容
- 检测到的元素类型（标题、摘要、公式、图表、表格、参考文献）

```python
def stage2_ocr_understanding(pages):
    """
    逐页OCR与理解
    
    DeepSeek-OCR2 功能：
    - 文字识别（保持段落结构）
    - 公式识别（转换为LaTeX）
    - 表格识别（转换为Markdown表格）
    - 图表理解（生成描述性文字）
    """
    # 加载模型
    ocr_model = load_model("deepseek-ocr2")
    
    page_contents = []
    
    for page in pages:
        result = ocr_model.process(
            image=page["image_path"],
            prompt="""请完整解析这一页学术论文内容：
            1. 识别所有文字，保持原有段落结构
            2. 如果有数学公式，转换为LaTeX格式
            3. 如果有表格，转换为Markdown表格
            4. 如果有图片/图表，描述其内容和关键信息
            5. 标注章节标题层级
            
            输出格式：Markdown
            """
        )
        
        content = {
            "page_num": page["page_num"],
            "markdown": result.text,
            "detected_elements": classify_elements(result)
        }
        
        page_contents.append(content)
        print(f"Page {page['page_num']} processed")
    
    # 卸载模型释放显存
    if Config.UNLOAD_AFTER_STAGE:
        del ocr_model
        torch.cuda.empty_cache()
    
    return page_contents


def classify_elements(ocr_result):
    """识别页面包含的元素类型"""
    elements = []
    text = ocr_result.text.lower()
    
    if "abstract" in text[:500]:
        elements.append("abstract")
    if "\\begin{equation}" in text or "$$" in text:
        elements.append("equations")
    if "|" in text and "---" in text:
        elements.append("tables")
    if "figure" in text or "fig." in text:
        elements.append("figures")
    if "references" in text or "bibliography" in text:
        elements.append("references")
    
    return elements
```

**处理时间估算**（单页）：
- 简单页面（纯文字）：5-10秒
- 复杂页面（公式+图表）：15-25秒

---

### 3.3 阶段3：文档整合与结构化

**目标**：将各页内容整合为完整的结构化文档

**工具**：纯 Python 处理，不需要 GPU

**输入**：各页 Markdown 内容

**输出**：
- 完整的 Markdown 文档
- 文档结构索引

```python
def stage3_document_assembly(page_contents, metadata):
    """
    文档整合与结构化
    
    功能：
    - 合并所有页面内容
    - 构建文档结构索引
    - 保存中间文档（便于调试和复用）
    """
    
    full_markdown = ""
    structure = {
        "title": "",
        "abstract": "",
        "sections": [],
        "figures": [],
        "tables": [],
        "references_start": None
    }
    
    for content in page_contents:
        full_markdown += content["markdown"] + "\n\n---\n\n"
        
        # 构建结构索引
        if "abstract" in content["detected_elements"]:
            structure["abstract"] = extract_abstract(content["markdown"])
    
    # 保存中间文档
    output_path = f"{Config.OUTPUT_DIR}/{metadata.get('title', 'paper')}_structured.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_markdown)
    
    return full_markdown, structure, output_path
```

**重要说明**：保存中间 Markdown 文档非常关键，便于：
- 调试各阶段输出
- 复用已处理的内容（避免重复 OCR）
- 人工检查 OCR 质量

---

### 3.4 阶段4：LLM深度分析

**目标**：对整合后的文档进行深度分析

**模型选择**：
- Qwen3-30B-A3B（MoE 架构，激活参数少）
- DeepSeek-V2.5

**显存占用**：约 20-24GB

**输入**：结构化 Markdown 文档

**输出**：结构化的论文分析报告

```python
def stage4_llm_analysis(full_markdown, structure, analysis_type="comprehensive"):
    """
    LLM深度分析
    
    分析类型：
    - comprehensive: 全面分析
    - quick: 快速总结
    - methodology_focus: 方法论聚焦
    """
    
    llm = load_model(Config.LLM_MODEL)
    
    prompts = {
        "comprehensive": """
            作为运筹学领域的研究者，请深度分析这篇论文：
            
            ## 需要输出的内容：
            
            ### 1. 论文概述
            - 研究问题是什么？
            - 属于哪个细分领域？
            
            ### 2. 方法论分析
            - 核心算法/模型是什么？
            - 创新点在哪里？
            - 与现有方法（如Tabu Search, ALNS）的关系？
            
            ### 3. 实验设计
            - 使用了什么benchmark？
            - 对比了哪些baseline？
            - 关键实验结果？
            
            ### 4. 对我研究的启发
            - 对PASP问题有什么可借鉴之处？
            - 是否有可复用的技术组件？
            
            ### 5. 局限性与未来方向
            
            论文内容如下：
            {content}
        """,
        
        "quick": """
            快速总结这篇论文的：
            1. 一句话概括（50字内）
            2. 核心贡献（3点）
            3. 关键结果
            
            论文内容：{content}
        """,
        
        "methodology_focus": """
            专注分析这篇论文的方法论：
            1. 问题建模（目标函数、约束条件）
            2. 求解算法的详细步骤
            3. 算法复杂度分析
            4. 参数设置
            
            论文内容：{content}
        """
    }
    
    # 处理长文档
    if len(full_markdown) > 50000:
        analysis = hierarchical_analysis(llm, full_markdown, structure, prompts[analysis_type])
    else:
        analysis = llm.generate(prompts[analysis_type].format(content=full_markdown))
    
    # 卸载模型
    if Config.UNLOAD_AFTER_STAGE:
        del llm
        torch.cuda.empty_cache()
    
    return analysis
```

**长文档处理策略**：

```python
def hierarchical_analysis(llm, content, structure, prompt):
    """
    分层分析策略（处理超长文档）
    
    步骤：
    1. 按章节分块
    2. 对各部分独立总结
    3. 整合各部分总结生成最终分析
    """
    
    sections = split_by_sections(content, structure)
    
    section_summaries = []
    for section in sections:
        summary = llm.generate(f"总结以下章节的核心内容（200字内）：\n{section}")
        section_summaries.append(summary)
    
    combined = "\n\n".join(section_summaries)
    final_analysis = llm.generate(prompt.format(content=combined))
    
    return final_analysis
```

---

## 4. 主流程代码

```python
"""
本地文献解读Pipeline
硬件：RTX 5090 32GB
"""

class Config:
    # 模型选择
    OCR_MODEL = "deepseek-ocr2"
    LLM_MODEL = "qwen3-30b-a3b"
    
    # 路径配置
    INPUT_DIR = "./papers/"
    OUTPUT_DIR = "./processed/"
    CACHE_DIR = "./cache/"
    
    # 显存管理
    UNLOAD_AFTER_STAGE = True


def process_paper(pdf_path, analysis_type="comprehensive"):
    """
    完整的论文处理流程
    
    显存使用时序：
    ├─ 阶段1: ~0GB (CPU only)
    ├─ 阶段2: ~16-20GB (DeepSeek-OCR2)
    ├─ 阶段3: ~0GB (CPU only)  
    └─ 阶段4: ~20-24GB (Qwen3-30B)
    
    峰值显存：~24GB，在32GB显存内安全运行
    """
    
    print(f"Processing: {pdf_path}")
    
    # 阶段1：PDF拆分
    print("Stage 1: PDF preprocessing...")
    pages, metadata = stage1_pdf_preprocessing(pdf_path)
    
    # 阶段2：OCR理解
    print("Stage 2: OCR and understanding...")
    page_contents = stage2_ocr_understanding(pages)
    
    # 阶段3：文档整合
    print("Stage 3: Document assembly...")
    full_markdown, structure, md_path = stage3_document_assembly(page_contents, metadata)
    
    # 阶段4：LLM分析
    print("Stage 4: LLM deep analysis...")
    analysis = stage4_llm_analysis(full_markdown, structure, analysis_type)
    
    # 保存最终结果
    output = {
        "metadata": metadata,
        "structured_doc_path": md_path,
        "analysis": analysis,
        "structure": structure
    }
    
    save_results(output, pdf_path)
    
    return output


def batch_process(pdf_dir, analysis_type="quick"):
    """批量处理多篇论文"""
    
    papers = list(Path(pdf_dir).glob("*.pdf"))
    results = []
    
    for pdf_path in papers:
        try:
            result = process_paper(str(pdf_path), analysis_type)
            results.append(result)
        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")
            continue
    
    generate_batch_report(results)
    return results


if __name__ == "__main__":
    # 单篇深度分析
    result = process_paper("./papers/example.pdf", "comprehensive")
    
    # 批量快速处理
    # results = batch_process("./papers/", "quick")
```

---

## 5. 时间估算

以一篇 20 页学术论文为例：

| 阶段 | 操作 | 预估耗时 | 瓶颈 |
|------|------|----------|------|
| 阶段1 | PDF拆分为图像 | 2-5秒 | CPU/磁盘IO |
| 阶段2 | 逐页OCR理解（20页） | 3-8分钟 | GPU推理 |
| 阶段3 | 文档整合 | 1-2秒 | CPU |
| 阶段4 | LLM深度分析 | 1-3分钟 | GPU推理 |
| 模型加载/卸载 | 两次 | 30-60秒 | 显存带宽 |

**总计：约 5-12 分钟/篇**

---

## 6. 使用场景

### 6.1 批量筛选

下载 20 篇相关论文，晚上挂着跑 `batch_process`，第二天早上查看结果，快速判断哪几篇值得精读。

### 6.2 快速定位

拿到一篇新论文，先跑 `quick` 模式，看分析报告里的方法论部分，决定是否深入阅读原文。

### 6.3 文献管理

所有处理过的论文都有结构化 Markdown 存档，后续想查某个方法细节可以直接搜索，不用重新翻 PDF。

---

## 7. 依赖安装

```bash
# Python依赖
pip install pymupdf torch transformers

# 模型下载（通过Ollama或Hugging Face）
ollama pull deepseek-ocr2
ollama pull qwen3:30b-a3b
```

---

## 8. 目录结构

```
project/
├── papers/                 # 输入：待处理的PDF文献
├── cache/                  # 缓存：页面图像等中间文件
├── processed/              # 输出：处理结果
│   ├── paper1_structured.md
│   ├── paper1_analysis.json
│   └── paper1_summary.md
├── config.py               # 配置文件
├── pipeline.py             # 主流程
├── stage1_preprocess.py    # 阶段1：PDF预处理
├── stage2_ocr.py           # 阶段2：OCR理解
├── stage3_assembly.py      # 阶段3：文档整合
├── stage4_analysis.py      # 阶段4：LLM分析
└── utils.py                # 工具函数
```

---

## 9. 后续优化方向

1. **阶段2并行**：使用较小的 OCR 模型（如 Qwen2.5-VL-7B-Q4），可以 batch 处理多页
2. **智能跳过**：检测到 References 后跳过后续页面
3. **增量处理**：检测 PDF 是否已处理过，避免重复工作
4. **Web UI**：构建简单的 Web 界面，方便上传和查看结果
