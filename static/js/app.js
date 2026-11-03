// Global State
let currentVideoPath = null;
let activeJobId = null;
let pollTimer = null;
let schedulerTimer = null;

// Initialize on Load
document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  setupDragAndDrop();
  updateLivePreview();
  fetchClipsList();
  fetchSchedulerStatus();
  schedulerTimer = setInterval(fetchSchedulerStatus, 4000);
});

// Setup Drag & Drop on Master Raw Zone
function setupDragAndDrop() {
  const dropZone = document.getElementById("raw-drop-zone");
  if (!dropZone) return;

  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
  });

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => {
      dropZone.classList.add("border-amber-400", "bg-amber-500/15", "scale-[1.01]");
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => {
      dropZone.classList.remove("border-amber-400", "bg-amber-500/15", "scale-[1.01]");
    }, false);
  });

  dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
      uploadRawFile(files[0]);
    }
  }, false);
}

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

// Open Raw Videos Folder in File Explorer
async function openRawFolder() {
  try {
    const res = await fetch("/api/open-raw-folder", { method: "POST" });
    const data = await res.json();
    if (!data.success) {
      alert("Folder path: " + data.path);
    }
  } catch (err) {
    console.error("Open folder failed:", err);
  }
}

// Handle Raw Video Input from File Picker
function handleRawUpload(event) {
  const file = event.target.files[0];
  if (file) {
    uploadRawFile(file);
  }
}

// Upload Raw File and Auto-Start
async function uploadRawFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const progressBox = document.getElementById("progress-box");
  progressBox.classList.remove("hidden");
  document.getElementById("progress-pct").textContent = "Uploading Episode...";
  document.getElementById("progress-part-status").textContent = file.name;

  try {
    const res = await fetch("/api/upload-raw", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload fail ho gaya.");

    // Update detected episode number in UI
    if (data.episode_num) {
      document.getElementById("input-episode-num").value = data.episode_num;
      updateLivePreview();
    }

    // Start tracking the background rendering job
    if (data.job_id) {
      activeJobId = data.job_id;
      pollJobStatus(activeJobId);
    }
  } catch (err) {
    alert(err.message);
    progressBox.classList.add("hidden");
  }
}

// Handle Direct Local File Path
async function handleSelectLocalFile() {
  const pathInput = document.getElementById("local-file-input").value.trim();
  if (!pathInput) {
    alert("Kripya valid video file path dalein!");
    return;
  }

  try {
    const res = await fetch("/api/select-local-video", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: pathInput })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "File load nahi ho saki.");

    currentVideoPath = data.video_path;
    const infoBox = document.getElementById("video-info-box");
    document.getElementById("video-info-name").textContent = data.filename;
    document.getElementById("video-info-stats").textContent = `Duration: ${data.duration_str} • Resolution: ${data.width}x${data.height}`;
    document.getElementById("video-info-parts").textContent = `~${data.estimated_parts} Clips (30s)`;
    infoBox.classList.remove("hidden");

    if (data.detected_episode) {
      document.getElementById("input-episode-num").value = data.detected_episode;
    }
    updateLivePreview();

    // Auto-prompt to start
    startGeneration();
  } catch (err) {
    alert(err.message);
  }
}

// Update Live 9:16 Mockup Preview
let previewTimeout = null;
function updateLivePreview() {
  clearTimeout(previewTimeout);
  previewTimeout = setTimeout(async () => {
    const epNum = document.getElementById("input-episode-num").value.trim() || "542";
    const partNum = parseInt(document.getElementById("input-start-part").value) || 1;

    try {
      const res = await fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          episode_num: epNum,
          part_num: partNum
        })
      });
      const data = await res.json();
      if (data.success) {
        document.getElementById("live-preview-img").src = data.preview_url;
      }
    } catch (e) {
      console.error("Preview render failed:", e);
    }
  }, 250);
}

// Manual Slicing Generation
async function startGeneration() {
  const pathInput = currentVideoPath || document.getElementById("local-file-input").value.trim();
  if (!pathInput) {
    alert("Pehle TMKOC episode video select ya drop karein!");
    return;
  }

  const epNum = document.getElementById("input-episode-num").value.trim() || "542";
  const startPart = parseInt(document.getElementById("input-start-part").value) || 1;
  const clipDur = parseInt(document.getElementById("input-clip-duration").value) || 30;
  const maxPartsVal = document.getElementById("input-max-parts").value.trim();
  const maxParts = maxPartsVal ? parseInt(maxPartsVal) : null;

  const btn = document.getElementById("btn-start-process");
  btn.disabled = true;
  btn.classList.add("opacity-50", "cursor-not-allowed");

  const progressBox = document.getElementById("progress-box");
  progressBox.classList.remove("hidden");

  try {
    const res = await fetch("/api/start-process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_path: pathInput,
        episode_num: epNum,
        clip_duration: clipDur,
        start_part: startPart,
        max_parts: maxParts,
        use_blurred_bg: true,
        auto_schedule: true
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Processing start nahi ho saki.");

    activeJobId = data.job_id;
    pollJobStatus(activeJobId);
  } catch (err) {
    alert(err.message);
    btn.disabled = false;
    btn.classList.remove("opacity-50", "cursor-not-allowed");
  }
}

// Poll Job Status
function pollJobStatus(jobId) {
  clearInterval(pollTimer);
  const startEpoch = Date.now();

  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/job-status/${jobId}`);
      const job = await res.json();

      const pct = job.progress || 0;
      document.getElementById("progress-pct").textContent = `${Math.round(pct)}%`;
      document.getElementById("progress-bar-fill").style.width = `${pct}%`;

      if (job.current_part && job.total_parts) {
        document.getElementById("progress-part-status").textContent = `Rendering Part ${job.current_part} of ${job.total_parts}`;
      }

      const elapsedSec = Math.round((Date.now() - startEpoch) / 1000);
      document.getElementById("progress-elapsed").textContent = `Elapsed: ${elapsedSec}s`;

      if (job.status === "completed") {
        clearInterval(pollTimer);
        document.getElementById("progress-pct").textContent = "100% Completed!";
        document.getElementById("progress-part-status").textContent = `Done! All ${job.clips.length} clips generated & scheduled.`;

        const btn = document.getElementById("btn-start-process");
        btn.disabled = false;
        btn.classList.remove("opacity-50", "cursor-not-allowed");

        fetchClipsList();
        fetchSchedulerStatus();
      } else if (job.status === "error") {
        clearInterval(pollTimer);
        alert("Processing error: " + (job.error || "Unknown error"));
        const btn = document.getElementById("btn-start-process");
        btn.disabled = false;
        btn.classList.remove("opacity-50", "cursor-not-allowed");
      }
    } catch (e) {
      console.error("Poll error:", e);
    }
  }, 1000);
}

// Fetch 5-Minute Scheduler Status
async function fetchSchedulerStatus() {
  try {
    const res = await fetch("/api/scheduler-status");
    const data = await res.json();

    document.getElementById("sched-pending-count").textContent = data.pending_count || 0;
    document.getElementById("sched-published-count").textContent = data.published_count || 0;

    const listEl = document.getElementById("scheduler-queue-list");
    if (!data.items || data.items.length === 0) {
      listEl.innerHTML = `
        <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80 text-center text-xs text-slate-500">
          Drop an episode above to start the 5-minute interval release queue.
        </div>`;
      return;
    }

    listEl.innerHTML = data.items.map(item => {
      let statusBadge = "";
      if (item.status === "published") {
        statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">PUBLISHED at ${item.published_at}</span>`;
      } else if (item.status === "publishing") {
        statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30 animate-pulse">RELEASING...</span>`;
      } else {
        const mins = Math.floor(item.seconds_remaining / 60);
        const secs = item.seconds_remaining % 60;
        const timeStr = `${mins}m ${secs < 10 ? '0' : ''}${secs}s`;
        statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30">In ${timeStr} (${item.scheduled_str})</span>`;
      }

      return `
        <div class="p-2.5 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between text-xs">
          <div class="flex items-center gap-2">
            <span class="w-6 h-6 rounded-lg bg-amber-500 text-black font-black flex items-center justify-center text-[10px]">P${item.part}</span>
            <div>
              <p class="font-bold text-slate-200">Part ${item.part} • Episode ${item.episode}</p>
              <p class="text-[10px] text-slate-500 font-mono">${item.filename || ''}</p>
            </div>
          </div>
          <div>
            ${statusBadge}
          </div>
        </div>
      `;
    }).join("");

    if (window.lucide) lucide.createIcons();
  } catch (e) {
    console.error("Scheduler fetch error:", e);
  }
}

// Fetch Generated Clips Gallery
async function fetchClipsList() {
  try {
    const res = await fetch("/api/clips");
    const clips = await res.json();

    document.getElementById("clips-count-badge").textContent = `${clips.length} Clips`;
    const grid = document.getElementById("clips-grid");

    if (clips.length === 0) {
      grid.innerHTML = `
        <div class="col-span-full py-8 text-center text-slate-500 text-xs">
          Abhi tak koi clips generate nahi hui hain. Upar video select karke drop karein!
        </div>`;
      return;
    }

    grid.innerHTML = clips.map(clip => `
      <div class="bg-slate-950 border border-slate-800 rounded-xl p-3 flex flex-col justify-between hover:border-amber-500/40 transition group">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-bold text-amber-400 truncate max-w-[150px]">${clip.filename}</span>
          <span class="text-[10px] text-slate-500">${clip.size_mb} MB</span>
        </div>
        <div class="aspect-[9/16] bg-slate-900 rounded-lg overflow-hidden relative flex items-center justify-center cursor-pointer mb-2.5" onclick="openVideoModal('${clip.url}', '${clip.filename}')">
          <video src="${clip.url}" class="w-full h-full object-cover"></video>
          <div class="absolute inset-0 bg-black/40 group-hover:bg-black/20 flex items-center justify-center transition">
            <div class="w-10 h-10 rounded-full bg-amber-500 text-black flex items-center justify-center shadow-lg group-hover:scale-110 transition">
              <i data-lucide="play" class="w-4 h-4 fill-current"></i>
            </div>
          </div>
        </div>
        <div class="flex gap-2">
          <button onclick="openVideoModal('${clip.url}', '${clip.filename}')" class="flex-1 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold transition text-center flex items-center justify-center gap-1">
            <i data-lucide="play" class="w-3 h-3 text-amber-400"></i>
            Play
          </button>
          <a href="${clip.url}" download="${clip.filename}" class="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-black rounded-lg text-xs font-bold transition flex items-center justify-center">
            <i data-lucide="download" class="w-3 h-3"></i>
          </a>
        </div>
      </div>
    `).join("");

    if (window.lucide) lucide.createIcons();
  } catch (e) {
    console.error("Clips fetch error:", e);
  }
}

// Video Modal Player
function openVideoModal(url, title) {
  const modal = document.getElementById("video-modal");
  const player = document.getElementById("modal-video-player");
  const titleEl = document.getElementById("modal-title");

  titleEl.textContent = title;
  player.src = url;
  modal.classList.remove("hidden");
  player.play();
}

function closeVideoModal() {
  const modal = document.getElementById("video-modal");
  const player = document.getElementById("modal-video-player");
  player.pause();
  player.src = "";
  modal.classList.add("hidden");
}
