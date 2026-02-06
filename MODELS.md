# 模型配置说明

本项目通过 **Ollama** 管理和调用所有本地模型。

## 一、所需模型

### 阶段2：OCR 视觉模型

用于将 PDF 页面图像识别为结构化 Markdown（文字、公式、表格、图表）。

| 模型 | Ollama 名称 | 大小 | 显存占用 | 说明 |
|------|-------------|------|----------|------|
| **Qwen2.5-VL-7B (推荐)** | `qwen2.5vl:7b` | ~5 GB | ~8 GB | 性价比最高，学术 OCR 质量好 |
| Qwen2.5-VL-72B | `qwen2.5vl:72b` | ~42 GB | 需量化 | 质量最好，但 32GB 显存需 Q4 量化 |
| MiniCPM-V 2.6 | `minicpm-v` | ~5 GB | ~8 GB | 备选，中文场景不错 |
| LLaMA 3.2 Vision | `llama3.2-vision` | ~7 GB | ~11 GB | 备选，英文论文效果好 |

```bash
# 推荐安装
ollama pull qwen2.5vl:7b
```

### 阶段4：LLM 文本分析模型

用于对结构化 Markdown 进行深度分析和总结。

| 模型 | Ollama 名称 | 大小 | 显存占用 | 说明 |
|------|-------------|------|----------|------|
| **Qwen3-30B-A3B (推荐)** | `qwen3:30b-a3b` | ~18 GB | ~20 GB | MoE 架构，激活参数仅 3B，速度快 |
| Qwen3-32B | `qwen3:32b` | ~19 GB | ~22 GB | 全参数，质量略高但更慢 |
| DeepSeek-V2.5 | `deepseek-v2.5` | ~16 GB | ~18 GB | 备选，推理能力强 |
| QwQ-32B | `qwq:32b` | ~19 GB | ~22 GB | 备选，推理链思考能力好 |

```bash
# 推荐安装
ollama pull qwen3:30b-a3b
```

## 二、显存规划 (RTX 5090 32GB)

```
阶段2 (OCR):  qwen2.5vl:7b  → ~8 GB   ✅ 充裕
              ↓ 阶段结束后 Ollama 自动管理显存
阶段4 (LLM):  qwen3:30b-a3b → ~20 GB  ✅ 安全
```

两个模型**串行使用，不会同时占用显存**。峰值约 20 GB，在 32 GB 内安全运行。

## 三、快速安装

```bash
# 1. 安装 Ollama (如未安装)
curl -fsSL https://ollama.com/install.sh | sh

# 2. 下载模型
ollama pull qwen2.5vl:7b
ollama pull qwen3:30b-a3b

# 3. 验证
ollama list
```

## 四、CLI 使用示例

```bash
# 使用默认模型
python -m src.main --input papers/example.pdf --mode comprehensive

# 指定模型
python -m src.main --input papers/example.pdf \
    --ocr-model qwen2.5vl:7b \
    --llm-model qwen3:30b-a3b \
    --mode quick
```

## 五、调用方式

本项目通过 Ollama 的 Python 客户端 (`ollama` 包) 与模型交互：

- **OCR 模型**：调用 `ollama.chat()` 传入图片 + 提示词，获取 Markdown
- **LLM 模型**：调用 `ollama.chat()` 传入文本 prompt，获取分析结果
- 无需手动管理 GPU 显存，Ollama 会自动处理模型加载/卸载

```bash
pip install ollama
```
