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
    const progressFileInfo = document.getElementById("progressFileInfo");
    const resultSection = document.getElementById("resultSection");
    const resultMarkdown = document.getElementById("resultMarkdown");
    const resultJson = document.getElementById("resultJson");
    const btnDownloadMd = document.getElementById("btnDownloadMd");
    const btnDownloadJson = document.getElementById("btnDownloadJson");
    const btnShutdown = document.getElementById("btnShutdown");
    const papersLibrary = document.getElementById("papersLibrary");

    // ── 状态 ──
    const ACTIVE_JOB_KEY = "paperread_active_job";
    let uploadedFileId = null;
    let uploadedFiles = [];
    let selectedLibraryFiles = [];
    let lastResultMarkdown = "";
    let lastResultJson = null;

    const historyList = document.getElementById("historyList");
    const historySearch = document.getElementById("historySearch");
    const historyPageSize = document.getElementById("historyPageSize");
    const historyPagination = document.getElementById("historyPagination");

    // ── 历史状态 ──
    let historyPage = 1;

    // ── 初始化 ──
    loadModels();
    loadHistory();
    loadPapers();
    tryResumeJob();

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

    // ── 关闭服务器 ──
    btnShutdown.addEventListener("click", async () => {
        if (!confirm("确定要关闭服务器吗？所有进行中的任务将终止。")) return;
        try {
            await fetch("/api/shutdown", { method: "POST" });
        } catch {
            // 连接断开是预期行为
        }
        document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:#6b5c4d;font-size:18px;">服务器已关闭</div>';
    });

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
            loadPapers(); // 刷新论文库
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
            (uploadedFileId && uploadedFiles.length || selectedLibraryFiles.length) &&
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
        if (uploadedFileId) formData.append("file_id", uploadedFileId);
        if (selectedLibraryFiles.length) formData.append("filenames", JSON.stringify(selectedLibraryFiles));
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

            // 保存 job 信息到 localStorage
            localStorage.setItem(ACTIVE_JOB_KEY, JSON.stringify({
                jobId: data.job_id,
                fileCount: data.file_count,
                startedAt: Date.now()
            }));

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

            if (data.file_total > 1) {
                progressFileInfo.textContent = `${data.file_title}  (${data.file_index}/${data.file_total})`;
            } else {
                progressFileInfo.textContent = "";
            }
        });

        source.addEventListener("done", (e) => {
            source.close();
            localStorage.removeItem(ACTIVE_JOB_KEY);
            progressFileInfo.textContent = "";
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
            progressFileInfo.textContent = "";
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

            localStorage.removeItem(ACTIVE_JOB_KEY);

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
            loadHistory();
            loadPapers(); // 刷新论文库，以防有新保存的
        } catch (e) {
            localStorage.removeItem(ACTIVE_JOB_KEY);
            showError("获取结果失败: " + e.message);
            resetButton();
        }
    }

    // ── 论文库 ──
    async function loadPapers() {
        try {
            const resp = await fetch("/api/papers");
            const data = await resp.json();
            renderPapersLibrary(data.papers);
        } catch (e) {
            papersLibrary.innerHTML = '<div class="papers-library-status">加载论文库失败</div>';
        }
    }

    function renderPapersLibrary(papers) {
        if (!papers || !papers.length) {
            papersLibrary.innerHTML = '<div class="papers-library-status">论文库为空</div>';
            return;
        }

        papersLibrary.innerHTML = "";
        papers.forEach(p => {
            const div = document.createElement("div");
            div.className = "paper-lib-item";
            if (selectedLibraryFiles.includes(p.name)) {
                div.classList.add("selected");
            }
            div.innerHTML = `
                <span class="paper-lib-item-icon">&#128196;</span>
                <span class="paper-lib-item-name">${escapeHtml(p.name)}</span>
            `;
            div.addEventListener("click", () => {
                if (selectedLibraryFiles.includes(p.name)) {
                    selectedLibraryFiles = selectedLibraryFiles.filter(name => name !== p.name);
                    div.classList.remove("selected");
                } else {
                    selectedLibraryFiles.push(p.name);
                    div.classList.add("selected");
                }
                checkReady();
            });
            papersLibrary.appendChild(div);
        });
    }

    // ── 页面刷新后恢复进行中的任务 ──
    async function tryResumeJob() {
        const saved = localStorage.getItem(ACTIVE_JOB_KEY);
        if (!saved) return;

        let info;
        try { info = JSON.parse(saved); } catch { localStorage.removeItem(ACTIVE_JOB_KEY); return; }

        try {
            const resp = await fetch(`/api/results/${info.jobId}`);
            if (resp.status === 202) {
                // 仍在运行，立即恢复进度显示
                const data = await resp.json();
                progressSection.classList.add("active");
                resultSection.classList.remove("active");
                btnAnalyze.disabled = true;
                btnAnalyze.textContent = "分析中...";
                // 用服务器快照立即还原进度条
                if (data.progress) {
                    const p = data.progress;
                    const pct = Math.round(p.progress * 100);
                    const stageName = p.stage
                        ? `阶段 ${p.stage}/4: ${p.stage_name}`
                        : p.stage_name;
                    updateProgress(pct, stageName, p.detail);
                    if (p.file_total > 1) {
                        progressFileInfo.textContent = `${p.file_title}  (${p.file_index}/${p.file_total})`;
                    }
                } else {
                    updateProgress(0, "恢复连接...", "正在重新获取进度");
                }
                connectSSE(info.jobId);
            } else if (resp.ok) {
                // 已完成，直接显示结果
                localStorage.removeItem(ACTIVE_JOB_KEY);
                const data = await resp.json();
                lastResultMarkdown = data.markdown;
                lastResultJson = data.json_data;
                resultMarkdown.innerHTML = simpleMarkdown(data.markdown);
                resultJson.innerHTML = `<pre>${escapeHtml(JSON.stringify(data.json_data, null, 2))}</pre>`;
                resultJson.style.display = "none";
                resultSection.classList.add("active");
            } else {
                // 任务不存在（服务器重启等），清除
                localStorage.removeItem(ACTIVE_JOB_KEY);
            }
        } catch {
            localStorage.removeItem(ACTIVE_JOB_KEY);
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

    function formatTime(isoStr) {
        if (!isoStr) return "";
        try {
            const d = new Date(isoStr);
            if (isNaN(d.getTime())) return "";
            const pad = (n) => String(n).padStart(2, "0");
            return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
        } catch {
            return "";
        }
    }

    function showError(msg) {
        errorMsg.textContent = msg;
        errorMsg.classList.add("active");
    }

    function hideError() {
        errorMsg.classList.remove("active");
    }

    // ── 历史论文 ──
    let searchTimer = null;
    historySearch.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            historyPage = 1;
            loadHistory();
        }, 300);
    });

    historyPageSize.addEventListener("change", () => {
        historyPage = 1;
        loadHistory();
    });

    async function loadHistory() {
        try {
            const search = historySearch.value.trim();
            const pageSize = historyPageSize.value;
            const params = new URLSearchParams({ page: historyPage, page_size: pageSize });
            if (search) params.set("search", search);

            const resp = await fetch("/api/history?" + params);
            const data = await resp.json();
            renderHistory(data.items);
            renderPagination(data.total, data.page, data.page_size);
        } catch (e) {
            // 静默失败，不影响主功能
        }
    }

    function renderHistory(items) {
        if (!items.length) {
            historyList.innerHTML = '<div class="history-empty">暂无历史记录</div>';
            return;
        }

        historyList.innerHTML = "";
        items.forEach(item => {
            const div = document.createElement("div");
            div.className = "history-item";

            const typeMap = {
                comprehensive: "综合分析",
                quick: "快速总结",
                methodology_focus: "方法论聚焦",
            };
            const typeName = typeMap[item.analysis_type] || item.analysis_type;
            const submittedAt = formatTime(item.submitted_at);
            const completedAt = formatTime(item.completed_at);

            div.innerHTML = `
                <div class="history-item-info">
                    <div class="history-item-title">${escapeHtml(item.title)}</div>
                    <div class="history-item-meta">${escapeHtml(typeName)} · ${escapeHtml(item.model)}${submittedAt ? ` · 提交: ${submittedAt}` : ""}${completedAt ? ` · 完成: ${completedAt}` : ""}</div>
                </div>
                <div class="history-item-actions">
                    <button class="btn-history btn-history-read">阅读</button>
                    <div class="download-dropdown">
                        <button class="btn-history">下载 ▾</button>
                        <div class="download-dropdown-menu">
                            <button class="download-dropdown-item" data-file="${escapeHtml(item.files.summary)}">summary.md</button>
                            <button class="download-dropdown-item" data-file="${escapeHtml(item.files.analysis)}">analysis.json</button>
                            <button class="download-dropdown-item" data-file="${escapeHtml(item.files.structured)}">structured.md</button>
                        </div>
                    </div>
                </div>
            `;

            // 阅读按钮
            div.querySelector(".btn-history-read").addEventListener("click", () => {
                readHistoryFile(item.files.summary);
            });

            // 下载下拉
            const dropdownBtn = div.querySelector(".download-dropdown > .btn-history");
            const dropdownMenu = div.querySelector(".download-dropdown-menu");

            dropdownBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                document.querySelectorAll(".download-dropdown-menu.active").forEach(m => {
                    if (m !== dropdownMenu) m.classList.remove("active");
                });
                dropdownMenu.classList.toggle("active");
            });

            dropdownMenu.querySelectorAll(".download-dropdown-item").forEach(btn => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    dropdownMenu.classList.remove("active");
                    downloadHistoryFile(btn.dataset.file);
                });
            });

            historyList.appendChild(div);
        });
    }

    function renderPagination(total, page, pageSize) {
        historyPagination.innerHTML = "";
        const totalPages = Math.ceil(total / pageSize);
        if (totalPages <= 1) return;

        // 上一页
        const prevBtn = document.createElement("button");
        prevBtn.textContent = "‹";
        prevBtn.disabled = page <= 1;
        prevBtn.addEventListener("click", () => { historyPage = page - 1; loadHistory(); });
        historyPagination.appendChild(prevBtn);

        // 页码按钮（最多显示 7 个）
        const pages = computePageNumbers(page, totalPages, 7);
        pages.forEach(p => {
            if (p === "...") {
                const span = document.createElement("span");
                span.className = "page-info";
                span.textContent = "...";
                historyPagination.appendChild(span);
            } else {
                const btn = document.createElement("button");
                btn.textContent = p;
                if (p === page) btn.classList.add("active");
                btn.addEventListener("click", () => { historyPage = p; loadHistory(); });
                historyPagination.appendChild(btn);
            }
        });

        // 下一页
        const nextBtn = document.createElement("button");
        nextBtn.textContent = "›";
        nextBtn.disabled = page >= totalPages;
        nextBtn.addEventListener("click", () => { historyPage = page + 1; loadHistory(); });
        historyPagination.appendChild(nextBtn);

        // 总数提示
        const info = document.createElement("span");
        info.className = "page-info";
        info.textContent = `共 ${total} 条`;
        historyPagination.appendChild(info);
    }

    function computePageNumbers(current, total, maxButtons) {
        if (total <= maxButtons) {
            return Array.from({ length: total }, (_, i) => i + 1);
        }
        const pages = [];
        pages.push(1);
        let start = Math.max(2, current - 1);
        let end = Math.min(total - 1, current + 1);
        // 保证中间至少3个
        if (current <= 3) end = Math.min(total - 1, 4);
        if (current >= total - 2) start = Math.max(2, total - 3);

        if (start > 2) pages.push("...");
        for (let i = start; i <= end; i++) pages.push(i);
        if (end < total - 1) pages.push("...");
        pages.push(total);
        return pages;
    }

    // 点击其他地方关闭下拉菜单
    document.addEventListener("click", () => {
        document.querySelectorAll(".download-dropdown-menu.active").forEach(m => {
            m.classList.remove("active");
        });
    });

    async function readHistoryFile(filename) {
        try {
            const resp = await fetch(`/api/history/${encodeURIComponent(filename)}`);
            if (!resp.ok) throw new Error("加载失败");
            const text = await resp.text();

            resultMarkdown.innerHTML = simpleMarkdown(text);
            resultJson.innerHTML = "";
            resultJson.style.display = "none";

            // 切换 tab 到报告
            document.querySelectorAll(".result-tab").forEach(t => t.classList.remove("active"));
            document.querySelector('.result-tab[data-tab="markdown"]').classList.add("active");
            resultMarkdown.style.display = "";

            resultSection.classList.add("active");
            resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (e) {
            showError("加载历史报告失败: " + e.message);
        }
    }

    async function downloadHistoryFile(filename) {
        try {
            const resp = await fetch(`/api/history/${encodeURIComponent(filename)}`);
            if (!resp.ok) throw new Error("下载失败");
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            showError("下载失败: " + e.message);
        }
    }
})();
