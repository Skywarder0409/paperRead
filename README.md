# paperRead - 本地论文智能解读

基于本地大模型的学术论文自动分析系统。通过 Ollama 调用本地视觉模型和语言模型，实现 PDF 论文的 OCR 识别、结构化整理和深度分析，全程离线运行，数据不出本地。

## 功能特性

- **4 阶段 Pipeline**: PDF 预处理 → OCR 识别 → 文档整合 → LLM 深度分析
- **多种分析模式**: 综合分析、快速总结、方法论聚焦
- **Web 前端**: 浏览器操作界面，支持拖拽上传、实时进度、结果下载
- **CLI 命令行**: 支持单篇分析和批量处理
- **智能分块**: 长文档自动分块 → 分层总结 → 整合分析
- **显存优化**: 各阶段模型按需加载/卸载，单卡即可运行

## 系统要求

- Python 3.10+
- [Ollama](https://ollama.com/) 已安装并运行
- NVIDIA GPU（推荐 24GB+ 显存）
- 至少一个 OCR/视觉模型和一个 LLM 模型已通过 Ollama 下载

## 安装

```bash
# 克隆项目
git clone <repo-url>
cd paperRead

# 创建 conda 环境
conda create -n paperRead python=3.10
conda activate paperRead

# 安装依赖
pip install -r requirements.txt

# 确保 Ollama 正在运行
ollama serve
```

### Ollama 模型准备

```bash
# OCR/视觉模型（任选）
ollama pull glm-ocr:bf16
ollama pull qwen3-vl:8b

# LLM 模型（任选）
ollama pull qwen3:32b
ollama pull glm-4.7-flash:q4_K_M
```

## 使用方式

### Web 前端（推荐）

```bash
conda activate paperRead
python -m src.web.app
# 浏览器访问 http://localhost:8000
```

操作流程：上传 PDF → 选择 OCR/LLM 模型 → 选择分析模式 → 开始分析 → 查看/下载报告

### 命令行

```bash
# 单篇综合分析
python -m src.main --input papers/example.pdf --mode comprehensive

# 快速总结
python -m src.main --input papers/example.pdf --mode quick

# 批量处理
python -m src.main --batch papers/ --mode quick

# 从阶段 4 开始（复用已有 OCR 结果）
python -m src.main --input output/example_structured.md --stage 4

# 自定义模型
python -m src.main --input papers/example.pdf --ocr-model qwen3-vl:8b --llm-model qwen3:32b
```

## 项目结构

```
paperRead/
├── src/
│   ├── main.py                  # CLI 入口
│   ├── pipeline.py              # Pipeline 主编排器
│   ├── config.py                # 全局配置
│   ├── models.py                # 数据模型定义
│   ├── preprocess/
│   │   └── preprocess.py        # PDF → 页面图片（PyMuPDF）
│   ├── ocr/
│   │   ├── ocr_engine.py        # Ollama 视觉模型 OCR
│   │   └── element_classifier.py
│   ├── assembly/
│   │   ├── assembler.py         # Markdown 文档整合
│   │   └── section_parser.py    # 章节结构解析
│   ├── analysis/
│   │   ├── llm_engine.py        # Ollama LLM 分析引擎
│   │   ├── chunking.py          # 长文档分块策略
│   │   └── prompts.py           # 分析提示词模板
│   ├── utils/
│   │   ├── logger.py            # 日志系统
│   │   ├── report_generator.py  # 报告生成
│   │   ├── file_ops.py          # 文件操作
│   │   └── gpu_manager.py       # GPU 显存管理
│   └── web/
│       ├── app.py               # FastAPI Web 服务
│       ├── pipeline_wrapper.py  # Pipeline 异步包装 + SSE 进度推送
│       └── static/
│           ├── index.html       # 前端页面
│           ├── style.css        # 样式
│           └── app.js           # 前端交互逻辑
├── papers/                      # 输入：PDF 文件
├── output/                      # 输出：分析报告
├── cache/                       # 缓存：页面图片、上传文件
├── requirements.txt
└── README.md
```

## Pipeline 工作流程

| 阶段 | 名称 | 说明 | 显存占用 |
|------|------|------|---------|
| 1 | PDF 预处理 | PyMuPDF 将 PDF 渲染为 PNG 页面图片 | ~0 GB |
| 2 | OCR 识别 | 视觉模型逐页识别，输出 Markdown | ~4-16 GB |
| 3 | 文档整合 | 合并页面内容，解析章节结构 | ~0 GB |
| 4 | LLM 分析 | 语言模型深度分析，生成报告 | ~8-24 GB |

各阶段模型用完即卸载，峰值显存 = 单个最大模型的占用。

## 输出文件

每篇论文分析完成后在 `output/` 目录生成：

- `{标题}_structured.md` — OCR 识别后的完整文档
- `{标题}_summary.md` — 人类可读的分析报告
- `{标题}_analysis.json` — 结构化分析数据

## 配置说明

通过 CLI 参数或 `PipelineConfig` 调整：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--ocr-model` | `deepseek-ocr2` | OCR 视觉模型名称 |
| `--llm-model` | `qwen3-30b-a3b` | LLM 分析模型名称 |
| `--mode` | `comprehensive` | 分析模式 |
| `--dpi` | `200` | PDF 渲染分辨率 |
| `--max-tokens` | `4096` | LLM 最大生成长度 |
| `--stage` | `1` | 起始阶段（可跳过已完成的步骤） |

## 技术栈

- **PDF 解析**: PyMuPDF
- **模型推理**: Ollama（本地部署）
- **Web 后端**: FastAPI + SSE（Server-Sent Events）
- **Web 前端**: 原生 HTML/CSS/JS
