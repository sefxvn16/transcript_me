/**
 * Logic trình phát Audio tuần tự (Playlist Queue & Prefetching Buffer)
 * Cho Chế độ 2: Dịch trực tuyến và Đọc luôn
 */

class AudiobookPlayer {
    constructor() {
        this.sessionId = null;
        this.totalChunks = 0;
        this.currentIndex = 0;
        this.chunks = []; // Lưu trữ metadata & nội dung của từng đoạn
        this.isPlaying = false;
        this.isLoadingChunk = false;
        
        // Audio element HTML5
        this.audio = new Audio();
        this.setupAudioListeners();

        // DOM Elements
        this.dom = {};
        this.initDOMElements();
    }

    initDOMElements() {
        this.dom = {
            playerContainer: document.getElementById("onlinePlayerSection"),
            chunkListContainer: document.getElementById("chunksList"),
            activeText: document.getElementById("activeText"),
            currentChunkBadge: document.getElementById("currentChunkBadge"),
            playPauseBtn: document.getElementById("playerPlayPauseBtn"),
            playIcon: document.getElementById("playerPlayIcon"),
            pauseIcon: document.getElementById("playerPauseIcon"),
            prevBtn: document.getElementById("playerPrevBtn"),
            nextBtn: document.getElementById("playerNextBtn"),
            progressBar: document.getElementById("playerProgressBar"),
            progressFill: document.getElementById("playerProgressFill"),
            timeCurrent: document.getElementById("playerTimeCurrent"),
            timeDuration: document.getElementById("playerTimeDuration"),
            speedSelect: document.getElementById("playerSpeedSelect"),
            playerStatusText: document.getElementById("playerStatusText"),
            playerTitle: document.getElementById("playerBookTitle")
        };

        if (this.dom.playPauseBtn) {
            this.dom.playPauseBtn.addEventListener("click", () => this.togglePlayPause());
        }
        if (this.dom.prevBtn) {
            this.dom.prevBtn.addEventListener("click", () => this.prevChunk());
        }
        if (this.dom.nextBtn) {
            this.dom.nextBtn.addEventListener("click", () => this.nextChunk());
        }
        if (this.dom.speedSelect) {
            this.dom.speedSelect.addEventListener("change", (e) => {
                this.audio.playbackRate = parseFloat(e.target.value);
            });
        }
        if (this.dom.progressBar) {
            this.dom.progressBar.addEventListener("click", (e) => this.seek(e));
        }
    }

    setupAudioListeners() {
        this.audio.addEventListener("play", () => {
            this.isPlaying = true;
            this.updatePlayPauseUI();
        });

        this.audio.addEventListener("pause", () => {
            this.isPlaying = false;
            this.updatePlayPauseUI();
        });

        this.audio.addEventListener("timeupdate", () => {
            this.updateTimeline();
        });

        this.audio.addEventListener("loadedmetadata", () => {
            if (this.dom.timeDuration) {
                this.dom.timeDuration.innerText = this.formatTime(this.audio.duration || 0);
            }
        });

        // Tự động chuyển tiếp đoạn kế tiếp khi phát xong (Seamless Queue)
        this.audio.addEventListener("ended", () => {
            console.log(`[Player] Đã phát xong đoạn ${this.currentIndex + 1}. Tự động chuyển đoạn tiếp theo.`);
            if (this.currentIndex + 1 < this.totalChunks) {
                this.loadAndPlayChunk(this.currentIndex + 1);
            } else {
                this.setStatus("🎉 Đã đọc xong toàn bộ cuốn sách!");
                this.isPlaying = false;
                this.updatePlayPauseUI();
            }
        });

        this.audio.addEventListener("error", (e) => {
            console.error("[Player] Audio Error:", e);
            if (!this.audio.src) return;
            this.setStatus("⚠️ Lỗi phát âm thanh đoạn này. Bấm chọn lại đoạn để thử lại.", true);
        });
    }

    formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return "00:00";
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
    }

    updateTimeline() {
        if (!this.dom.progressFill || !this.audio.duration) return;
        const percent = (this.audio.currentTime / this.audio.duration) * 100;
        this.dom.progressFill.style.width = `${percent}%`;
        if (this.dom.timeCurrent) {
            this.dom.timeCurrent.innerText = this.formatTime(this.audio.currentTime);
        }
    }

    seek(e) {
        if (!this.audio.duration || !this.dom.progressBar) return;
        const rect = this.dom.progressBar.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const width = rect.width;
        const seekTime = (clickX / width) * this.audio.duration;
        this.audio.currentTime = seekTime;
    }

    updatePlayPauseUI() {
        if (!this.dom.playIcon || !this.dom.pauseIcon) return;
        if (this.isPlaying) {
            this.dom.playIcon.classList.add("hidden");
            this.dom.pauseIcon.classList.remove("hidden");
        } else {
            this.dom.playIcon.classList.remove("hidden");
            this.dom.pauseIcon.classList.add("hidden");
        }
    }

    setStatus(text, isError = false) {
        if (this.dom.playerStatusText) {
            this.dom.playerStatusText.innerText = text;
            this.dom.playerStatusText.className = isError 
                ? "text-xs font-medium text-red-500 animate-pulse" 
                : "text-xs font-medium text-slate-500";
        }
    }

    /**
     * Khởi tạo giao diện và nạp danh sách đoạn từ server
     */
    startSession(sessionData) {
        this.sessionId = sessionData.session_id;
        this.totalChunks = sessionData.total_chunks;
        this.chunks = sessionData.chunks;
        this.currentIndex = 0;

        if (this.dom.playerTitle) {
            this.dom.playerTitle.innerText = sessionData.title || "Tác phẩm";
        }

        // Hiển thị container
        if (this.dom.playerContainer) {
            this.dom.playerContainer.classList.remove("hidden");
            this.dom.playerContainer.scrollIntoView({ behavior: "smooth" });
        }

        // Render danh sách chunk vào cột bên trái
        this.renderChunkList();

        // Bắt đầu phát ngay đoạn 1 (index 0)
        this.loadAndPlayChunk(0);
    }

    renderChunkList() {
        if (!this.dom.chunkListContainer) return;
        this.dom.chunkListContainer.innerHTML = "";

        this.chunks.forEach((chunk, idx) => {
            const card = document.createElement("div");
            card.id = `chunk-card-${idx}`;
            card.className = `p-3 rounded-xl border border-slate-200/70 hover:border-indigo-400 bg-white/70 hover:bg-indigo-50/40 cursor-pointer transition-all duration-200 flex flex-col gap-1.5 shadow-sm text-left`;
            card.innerHTML = `
                <div class="flex items-center justify-between">
                    <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700" id="chunk-badge-${idx}">Đoạn ${idx + 1}</span>
                    <span class="text-[11px] text-slate-500">~${Math.round(chunk.estimated_seconds)}s</span>
                </div>
                <p class="text-xs text-slate-600 line-clamp-2 leading-relaxed" id="chunk-preview-${idx}"></p>
            `;
            // Văn bản từ PDF gán qua textContent để ký tự "<...>" không bị hiểu là HTML
            card.querySelector("p").textContent = chunk.preview || "Nội dung đoạn...";

            card.addEventListener("click", () => {
                this.loadAndPlayChunk(idx);
            });

            this.dom.chunkListContainer.appendChild(card);
        });
    }

    highlightActiveChunkInList(index) {
        // Xóa highlight cũ
        document.querySelectorAll("[id^='chunk-card-']").forEach(el => {
            el.classList.remove("ring-2", "ring-indigo-600", "bg-indigo-50", "border-indigo-500");
            el.classList.add("bg-white/70", "border-slate-200/70");
        });

        // Thêm highlight mới
        const activeCard = document.getElementById(`chunk-card-${index}`);
        if (activeCard) {
            activeCard.classList.remove("bg-white/70", "border-slate-200/70");
            activeCard.classList.add("ring-2", "ring-indigo-600", "bg-indigo-50", "border-indigo-500");
            activeCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }

        // Cập nhật badge góc
        if (this.dom.currentChunkBadge) {
            this.dom.currentChunkBadge.innerText = `Đoạn ${index + 1} / ${this.totalChunks}`;
        }
    }

    /**
     * Tải và phát một đoạn cụ thể
     */
    async loadAndPlayChunk(index) {
        if (index < 0 || index >= this.totalChunks) return;
        this.currentIndex = index;
        this.isLoadingChunk = true;
        // Mỗi lần chuyển đoạn có một token; response của lần chuyển cũ về muộn sẽ bị bỏ qua
        const token = this.loadToken = (this.loadToken || 0) + 1;

        this.audio.pause();
        this.highlightActiveChunkInList(index);
        this.setStatus(`⏳ Đang tải và tạo giọng nói Đoạn ${index + 1}...`);

        // Nạp trước 2 đoạn kế tiếp ngay, không chờ đoạn hiện tại phát
        this.prefetchNextChunks(index);

        try {
            const resp = await fetch(`/api/player/chunk/${this.sessionId}/${index}`);
            if (token !== this.loadToken) return;
            if (!resp.ok) {
                throw new Error(`HTTP error ${resp.status}`);
            }

            const data = await resp.json();
            if (token !== this.loadToken) return;

            // Cập nhật dữ liệu vào mảng
            this.chunks[index] = Object.assign(this.chunks[index] || {}, data);

            if (this.dom.activeText) {
                this.dom.activeText.innerText = data.text || "(Đoạn trống)";
            }

            // Gán audio và phát
            if (data.audio_url) {
                this.audio.src = data.audio_url;
                if (this.dom.speedSelect) {
                    this.audio.playbackRate = parseFloat(this.dom.speedSelect.value);
                }
                
                this.isLoadingChunk = false;
                await this.audio.play();
                this.setStatus(`🔊 Đang phát Đoạn ${index + 1}/${this.totalChunks}`);
            }
            this.isLoadingChunk = false;

        } catch (err) {
            if (token !== this.loadToken || err.name === "AbortError") return;
            this.isLoadingChunk = false;
            if (err.name === "NotAllowedError") {
                // Trình duyệt chặn tự phát: audio đã sẵn sàng, chờ người dùng bấm Play
                this.setStatus(`▶️ Đoạn ${index + 1} đã sẵn sàng, bấm Play để phát`);
                return;
            }
            console.error(`Lỗi tải đoạn ${index}:`, err);
            this.setStatus(`❌ Không thể phát đoạn ${index + 1}: ${err.message}`, true);
        }
    }

    /**
     * Gửi yêu cầu chuẩn bị trước các đoạn tiếp theo (Prefetching)
     */
    async prefetchNextChunks(currentIndex) {
        const nextIndices = [];
        if (currentIndex + 1 < this.totalChunks) nextIndices.push(currentIndex + 1);
        if (currentIndex + 2 < this.totalChunks) nextIndices.push(currentIndex + 2);

        if (nextIndices.length === 0) return;

        try {
            await fetch(`/api/player/prefetch/${this.sessionId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ chunk_indices: nextIndices })
            });
            console.log(`[Prefetch] Đã gửi yêu cầu chuẩn bị trước cho đoạn: ${nextIndices.map(n => n + 1).join(", ")}`);
        } catch (e) {
            console.warn("[Prefetch] Gửi prefetch thất bại:", e);
        }
    }

    togglePlayPause() {
        if (!this.audio.src) {
            if (this.totalChunks > 0) {
                this.loadAndPlayChunk(this.currentIndex);
            }
            return;
        }

        if (this.isPlaying) {
            this.audio.pause();
            this.setStatus(`⏸️ Đã tạm dừng Đoạn ${this.currentIndex + 1}`);
        } else {
            this.audio.play();
            this.setStatus(`🔊 Đang phát Đoạn ${this.currentIndex + 1}/${this.totalChunks}`);
        }
    }

    nextChunk() {
        if (this.currentIndex + 1 < this.totalChunks) {
            this.loadAndPlayChunk(this.currentIndex + 1);
        }
    }

    prevChunk() {
        if (this.currentIndex > 0) {
            this.loadAndPlayChunk(this.currentIndex - 1);
        }
    }
}

// Khởi tạo global instance
window.audiobookPlayer = new AudiobookPlayer();
