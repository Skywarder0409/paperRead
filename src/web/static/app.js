/* paperRead 前端交互逻辑 */

(function () {
    "use strict";

    // ── DOM 元素 ──
    const uploadZone = document.getElementById("uploadZone");
    const fileInput = document.getElementById("fileInput");
    const fileList = document.getElementById("fileList");
    const ocrSelect = document.getElementById("ocrModel");
    const llmSelect = document.getElementById("llmModel");
    const btnAnalyze = document.getElementById("btnAnalyze");
    const errorMsg = document.getElementById("errorMsg");
    const progressSection = document.getElementById("progressSection");
    const progressStage = document.getElementById("progressStage");
    const progressPercent = document.getElementById("progressPercent");
    const progressFill = document.getElementById("progressFill");
    const progressDetail = document.getElementById("progressDetail");
    const resultSection = document.getElementById("resultSection");
    const resultMarkdown = document.getElementById("resultMarkdown");
    const resultJson = document.getElementById("resultJson");
    const btnDownloadMd = document.getElementById("btnDownloadMd");
    const btnDownloadJson = document.getElementById("btnDownloadJson");

    // ── 状态 ──
    let uploadedFileId = null;
    let uploadedFiles = [];
    let lastResultMarkdown = "";
    let lastResultJson = null;

    // ── 初始化 ──
    loadModels();

    // ── 上传区域事件 ──
    uploadZone.addEventListener("click", () => fileInput.click());

    uploadZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploadZone.classList.add("dragover");
    });

    uploadZone.addEventListener("dragleave", () => {
        uploadZone.classList.remove("dragover");
    });

    uploadZone.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadZone.classList.remove("dragover");
        const files = Array.from(e.dataTransfer.files).filter(f =>
            f.name.toLowerCase().endsWith(".pdf")
        );
        if (files.length) uploadFiles(files);
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length) {
            uploadFiles(Array.from(fileInput.files));
        }
    });

    // ── 开始分析 ──
    btnAnalyze.addEventListener("click", startAnalysis);

    // ── 结果标签切换 ──
    document.querySelectorAll(".result-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".result-tab").forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            const target = tab.dataset.tab;
            resultMarkdown.style.display = target === "markdown" ? "" : "none";
            resultJson.style.display = target === "json" ? "" : "none";
        });
    });

    // ── 下载按钮 ──
    btnDownloadMd.addEventListener("click", () => {
        if (!lastResultMarkdown) return;
        const title = lastResultJson && lastResultJson.metadata
            ? lastResultJson.metadata.title || "report"
            : "report";
        downloadFile(title + "_summary.md", lastResultMarkdown, "text/markdown");
    });

    btnDownloadJson.addEventListener("click", () => {
        if (!lastResultJson) return;
        const title = lastResultJson.metadata
            ? lastResultJson.metadata.title || "report"
            : "report";
        downloadFile(title + "_analysis.json", JSON.stringify(lastResultJson, null, 2), "application/json");
    });

    function downloadFile(filename, content, mimeType) {
        const blob = new Blob([content], { type: mimeType + ";charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // ── 加载模型列表 ──
    async function loadModels() {
        try {
            const resp = await fetch("/api/models");
            const data = await resp.json();

            if (data.error) {
                showError(data.error);
                return;
            }

            fillSelect(ocrSelect, data.ocr_models, "选择 OCR 模型");
            fillSelect(llmSelect, data.llm_models, "选择 LLM 模型");
            checkReady();
        } catch (e) {
            showError("无法加载模型列表: " + e.message);
        }
    }

    function fillSelect(select, models, placeholder) {
        select.innerHTML = "";
        if (!models.length) {
            select.innerHTML = `<option value="">${placeholder} (无可用模型)</option>`;
            return;
        }
        models.forEach((m, i) => {
            const opt = document.createElement("option");
            opt.value = m.name;
            const sizeMB = (m.size / 1e9).toFixed(1);
            opt.textContent = `${m.name} (${sizeMB} GB)`;
            if (i === 0) opt.selected = true;
            select.appendChild(opt);
        });
    }

    // ── 上传文件 ──
    async function uploadFiles(files) {
        const formData = new FormData();
        files.forEach(f => formData.append("files", f));

        hideError();
        try {
            const resp = await fetch("/api/upload", { method: "POST", body: formData });
            const data = await resp.json();

            if (data.error) {
                showError(data.error);
                return;
            }

            uploadedFileId = data.file_id;
            uploadedFiles = data.files;
            renderFileList();
            checkReady();
        } catch (e) {
            showError("上传失败: " + e.message);
        }
    }

    function renderFileList() {
        fileList.innerHTML = "";
        uploadedFiles.forEach((f, i) => {
            const div = document.createElement("div");
            div.className = "file-item";
            div.innerHTML = `
                <span class="file-item-name">${escapeHtml(f.name)}</span>
                <button class="file-item-remove" data-index="${i}">&times;</button>
            `;
            fileList.appendChild(div);
        });

        fileList.querySelectorAll(".file-item-remove").forEach(btn => {
            btn.addEventListener("click", () => {
                const idx = parseInt(btn.dataset.index);
                uploadedFiles.splice(idx, 1);
                if (!uploadedFiles.length) uploadedFileId = null;
                renderFileList();
                checkReady();
            });
        });
    }

    // ── 表单就绪检查 ──
    function checkReady() {
        btnAnalyze.disabled = !(
            uploadedFileId &&
            uploadedFiles.length &&
            ocrSelect.value &&
            llmSelect.value
        );
    }

    ocrSelect.addEventListener("change", checkReady);
    llmSelect.addEventListener("change", checkReady);

    // ── 开始分析 ──
    async function startAnalysis() {
        hideError();
        btnAnalyze.disabled = true;
        btnAnalyze.textContent = "分析中...";

        const analysisType = document.querySelector('input[name="analysisType"]:checked').value;

        const formData = new FormData();
        formData.append("file_id", uploadedFileId);
        formData.append("ocr_model", ocrSelect.value);
        formData.append("llm_model", llmSelect.value);
        formData.append("analysis_type", analysisType);

        try {
            const resp = await fetch("/api/analyze", { method: "POST", body: formData });
            const data = await resp.json();

            if (data.error) {
                showError(data.error);
                resetButton();
                return;
            }

            // 显示进度
            progressSection.classList.add("active");
            resultSection.classList.remove("active");
            updateProgress(0, "正在初始化...", "等待 Pipeline 启动");
            progressSection.scrollIntoView({ behavior: "smooth", block: "center" });

            // 连接 SSE
            connectSSE(data.job_id);
        } catch (e) {
            showError("启动分析失败: " + e.message);
            resetButton();
        }
    }

    function resetButton() {
        btnAnalyze.disabled = false;
        btnAnalyze.textContent = "开始分析";
    }

    // ── SSE 进度监听 ──
    function connectSSE(jobId) {
        const source = new EventSource(`/api/progress/${jobId}`);

        source.addEventListener("progress", (e) => {
            const data = JSON.parse(e.data);
            const pct = Math.round(data.progress * 100);
            const stageName = data.stage
                ? `阶段 ${data.stage}/4: ${data.stage_name}`
                : data.stage_name;
            updateProgress(pct, stageName, data.detail);
        });

        source.addEventListener("done", (e) => {
            source.close();
            const data = JSON.parse(e.data);
            if (data.status === "completed") {
                updateProgress(100, "分析完成", "正在加载结果...");
                fetchResults(jobId);
            } else {
                showError("分析失败");
                resetButton();
            }
        });

        source.addEventListener("heartbeat", () => {
            // 保持连接
        });

        source.onerror = () => {
            source.close();
            // 尝试获取结果（可能已完成）
            setTimeout(() => fetchResults(jobId), 1000);
        };
    }

    function updateProgress(pct, stage, detail) {
        progressFill.style.width = pct + "%";
        progressPercent.textContent = pct + "%";
        progressStage.textContent = stage;
        progressDetail.textContent = detail;
    }

    // ── 获取结果 ──
    async function fetchResults(jobId) {
        try {
            const resp = await fetch(`/api/results/${jobId}`);
            const data = await resp.json();

            if (data.status === "running") {
                setTimeout(() => fetchResults(jobId), 2000);
                return;
            }

            if (data.error) {
                showError("获取结果失败: " + data.error);
                resetButton();
                return;
            }

            // 保存原始数据用于下载
            lastResultMarkdown = data.markdown;
            lastResultJson = data.json_data;

            // 渲染结果
            resultMarkdown.innerHTML = simpleMarkdown(data.markdown);
            resultJson.innerHTML = `<pre>${escapeHtml(JSON.stringify(data.json_data, null, 2))}</pre>`;
            resultJson.style.display = "none";

            resultSection.classList.add("active");
            resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
            resetButton();
        } catch (e) {
            showError("获取结果失败: " + e.message);
            resetButton();
        }
    }

    // ── 简易 Markdown 渲染 ──
    function simpleMarkdown(md) {
        if (!md) return "<p>无结果</p>";
        let html = escapeHtml(md);

        // 代码块
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>");

        // 表格
        html = html.replace(/((?:\|.+\|\n)+)/g, (match) => {
            const rows = match.trim().split("\n");
            let table = "<table>";
            rows.forEach((row, i) => {
                if (row.match(/^\|[\s\-:|]+\|$/)) return; // 分隔行
                const cells = row.split("|").filter(c => c.trim() !== "");
                const tag = i === 0 ? "th" : "td";
                table += "<tr>" + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join("") + "</tr>";
            });
            return table + "</table>";
        });

        // 标题
        html = html.replace(/^######\s+(.+)$/gm, "<h6>$1</h6>");
        html = html.replace(/^#####\s+(.+)$/gm, "<h5>$1</h5>");
        html = html.replace(/^####\s+(.+)$/gm, "<h4>$1</h4>");
        html = html.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
        html = html.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
        html = html.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");

        // 引用
        html = html.replace(/^&gt;\s+(.+)$/gm, "<blockquote>$1</blockquote>");

        // 粗体和斜体
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

        // 行内代码
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

        // 无序列表
        html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
        html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

        // 水平线
        html = html.replace(/^---$/gm, "<hr>");

        // 段落
        html = html.replace(/\n\n/g, "</p><p>");
        html = "<p>" + html + "</p>";

        // 清理空段落
        html = html.replace(/<p>\s*<\/p>/g, "");
        html = html.replace(/<p>(<h[1-6]>)/g, "$1");
        html = html.replace(/(<\/h[1-6]>)<\/p>/g, "$1");
        html = html.replace(/<p>(<table>)/g, "$1");
        html = html.replace(/(<\/table>)<\/p>/g, "$1");
        html = html.replace(/<p>(<ul>)/g, "$1");
        html = html.replace(/(<\/ul>)<\/p>/g, "$1");
        html = html.replace(/<p>(<blockquote>)/g, "$1");
        html = html.replace(/(<\/blockquote>)<\/p>/g, "$1");
        html = html.replace(/<p>(<hr>)/g, "$1");
        html = html.replace(/(<hr>)<\/p>/g, "$1");
        html = html.replace(/<p>(<pre>)/g, "$1");
        html = html.replace(/(<\/pre>)<\/p>/g, "$1");

        return html;
    }

    // ── 工具函数 ──
    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function showError(msg) {
        errorMsg.textContent = msg;
        errorMsg.classList.add("active");
    }

    function hideError() {
        errorMsg.classList.remove("active");
    }
})();
