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
  fetchDailyThumbnail();
  fetchSocialSettings();
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

// --- Daily Thumbnail Manager Functions ---
async function fetchDailyThumbnail() {
  try {
    const res = await fetch("/api/daily-thumbnail");
    const data = await res.json();
    const previewImg = document.getElementById("daily-thumb-preview");
    const placeholder = document.getElementById("daily-thumb-placeholder");
    const statusText = document.getElementById("daily-thumb-status");

    if (data.has_thumbnail && data.thumbnail_url) {
      previewImg.src = data.thumbnail_url;
      previewImg.classList.remove("hidden");
      placeholder.classList.add("hidden");
      statusText.innerHTML = `<span class="text-emerald-400 font-bold">✓ Active</span> (${data.updated_at})`;
    } else {
      previewImg.classList.add("hidden");
      placeholder.classList.remove("hidden");
      statusText.textContent = "No thumbnail set for today";
    }
  } catch (e) {
    console.error("Fetch thumbnail failed:", e);
  }
}

async function handleDailyThumbnailUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  const statusText = document.getElementById("daily-thumb-status");
  statusText.textContent = "Uploading & formatting to 9:16...";

  try {
    const res = await fetch("/api/upload-daily-thumbnail", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Thumbnail upload failed");

    fetchDailyThumbnail();
    fetchClipsList();
    alert("Daily Thumbnail uploaded successfully! Instagram & YouTube ke sabhi clips me apply ho gaya.");
  } catch (err) {
    alert(err.message);
    fetchDailyThumbnail();
  }
}

async function applyThumbnailToAll() {
  const statusText = document.getElementById("daily-thumb-status");
  statusText.textContent = "Applying to all clips...";
  try {
    const res = await fetch("/api/apply-thumbnail-to-all", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to apply");
    alert(data.message);
    fetchDailyThumbnail();
    fetchClipsList();
  } catch (e) {
    alert(e.message);
  }
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

// Poll Job Status with high-frequency updates (600ms)
function pollJobStatus(jobId) {
  clearInterval(pollTimer);
  const startEpoch = Date.now();

  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/job-status/${jobId}`);
      const job = await res.json();

      const pct = job.progress || 0;
      document.getElementById("progress-pct").textContent = `${Math.round(pct)}% (TURBO)`;
      document.getElementById("progress-bar-fill").style.width = `${pct}%`;

      if (job.total_parts) {
        document.getElementById("progress-part-status").textContent = `⚡ Parallel Multi-Core Rendering: ${job.clips ? job.clips.length : 0} of ${job.total_parts} finished`;
      }

      const elapsedSec = Math.round((Date.now() - startEpoch) / 1000);
      document.getElementById("progress-elapsed").textContent = `Elapsed: ${elapsedSec}s`;

      // Live update gallery as clips finish
      if (job.clips && job.clips.length > 0) {
        fetchClipsList();
      }

      if (job.status === "completed") {
        clearInterval(pollTimer);
        document.getElementById("progress-pct").textContent = `100% Done in ${job.elapsed_sec || elapsedSec}s!`;
        document.getElementById("progress-part-status").textContent = `⚡ All ${job.clips.length} clips generated at turbo speed!`;

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
  }, 600);
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
      <div class="bg-slate-950 border border-slate-800 rounded-xl p-3 flex flex-col justify-between hover:border-amber-500/40 transition group shadow-lg">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-extrabold text-amber-400 truncate max-w-[150px]">${clip.display_title || clip.filename}</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 font-mono">${clip.size_mb} MB</span>
        </div>
        <div class="aspect-[9/16] bg-slate-900 rounded-lg overflow-hidden relative flex items-center justify-center cursor-pointer mb-2.5" onclick="openVideoModal('${clip.url}', '${clip.display_title || clip.filename}')">
          <video src="${clip.url}" ${clip.thumbnail_url ? `poster="${clip.thumbnail_url}"` : ''} preload="metadata" class="w-full h-full object-cover"></video>
          <div class="absolute inset-0 bg-black/35 group-hover:bg-black/15 flex items-center justify-center transition">
            <div class="w-10 h-10 rounded-full bg-amber-500 text-black flex items-center justify-center shadow-lg group-hover:scale-110 transition">
              <i data-lucide="play" class="w-4 h-4 fill-current"></i>
            </div>
          </div>
          <div class="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/75 backdrop-blur text-[10px] text-amber-300 font-extrabold">
            PART ${clip.part || 1}
          </div>
          ${clip.thumbnail_url ? `
          <div class="absolute top-2 right-2 px-1.5 py-0.5 rounded bg-pink-600/80 backdrop-blur text-[9px] text-white font-bold flex items-center gap-1">
            <span>📸 Reel Cover</span>
          </div>` : ''}
        </div>
        <div class="space-y-1.5 mt-2">
          <!-- Row 1: Play, Cover, Video Download -->
          <div class="flex gap-1.5">
            <button onclick="openVideoModal('${clip.url}', '${clip.display_title || clip.filename}')" class="flex-1 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1">
              <i data-lucide="play" class="w-3 h-3 text-amber-400"></i>
              Play
            </button>
            ${clip.thumbnail_url ? `
            <a href="${clip.thumbnail_url}" download="${clip.filename.replace('.mp4', '_thumb.jpg')}" class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-pink-400 border border-pink-500/30 rounded-lg text-xs font-bold transition flex items-center justify-center" title="Download Thumbnail for Instagram / YouTube">
              <i data-lucide="image" class="w-3 h-3"></i>
            </a>` : ''}
            <a href="${clip.url}" download="${clip.filename}" class="px-2.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-black rounded-lg text-xs font-bold transition flex items-center justify-center" title="Download Short">
              <i data-lucide="download" class="w-3 h-3"></i>
            </a>
          </div>

          <!-- Row 2: 1-Click Upload & Copy Viral Tags -->
          <div class="flex gap-1.5">
            <button onclick="openSocialModal('${clip.filename}')" class="flex-1 py-1.5 bg-gradient-to-r from-pink-600 via-purple-600 to-red-600 hover:from-pink-500 hover:to-red-500 text-white rounded-lg text-xs font-extrabold transition flex items-center justify-center gap-1 shadow">
              <i data-lucide="share-2" class="w-3 h-3"></i>
              Upload / Post
            </button>
            <button onclick="copyClipMetadata('${clip.filename}')" class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-amber-400 border border-slate-700 rounded-lg text-xs font-bold transition flex items-center justify-center" title="Copy Caption & Viral Tags">
              <i data-lucide="copy" class="w-3 h-3"></i>
            </button>
          </div>
        </div>
      </div>
    `).join("");

    if (window.lucide) lucide.createIcons();
  } catch (e) {
    console.error("Clips fetch error:", e);
  }
}

// Video Modal Player (Forces fresh stream without browser cache pause)
function openVideoModal(url, title) {
  const modal = document.getElementById("video-modal");
  const player = document.getElementById("modal-video-player");
  const titleEl = document.getElementById("modal-title");

  titleEl.textContent = title;
  // Cache-busting timestamp ensures browser requests full complete file instead of stale partial buffer
  player.src = `${url}?t=${Date.now()}`;
  modal.classList.remove("hidden");
  player.load();
  player.play().catch(e => console.log("Autoplay waiting for interaction:", e));
}

function closeVideoModal() {
  const modal = document.getElementById("video-modal");
  const player = document.getElementById("modal-video-player");
  player.pause();
  player.src = "";
  modal.classList.add("hidden");
}

// --- Social Media Integration State & Handlers ---
let activeSocialFilename = null;

async function fetchSocialSettings() {
  try {
    const res = await fetch("/api/social/settings");
    const data = await res.json();
    
    // Update Instagram UI
    const igBadge = document.getElementById("ig-status-badge");
    const igUserText = document.getElementById("ig-connected-user");
    const igToggleAuto = document.getElementById("ig-toggle-auto");

    if (data.instagram) {
      if (igBadge) {
        igBadge.textContent = "Connected ✅";
        igBadge.className = "px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
      }
      if (igUserText) {
        igUserText.textContent = `@${data.instagram.username || 'tmkoc.925781'}`;
      }
      if (igToggleAuto) {
        igToggleAuto.checked = Boolean(data.instagram.auto_upload);
      }
    }

    // Update YouTube UI
    const ytBadge = document.getElementById("yt-status-badge");
    const ytForm = document.getElementById("yt-login-form");
    const ytConnectedBox = document.getElementById("yt-connected-box");
    const ytSecretsStatus = document.getElementById("yt-secrets-status");
    const ytToggleAuto = document.getElementById("yt-toggle-auto");
    const ytPrivacySelect = document.getElementById("yt-privacy-select");

    if (data.youtube && data.youtube.is_connected) {
      if (ytBadge) {
        ytBadge.textContent = "Connected ✅";
        ytBadge.className = "px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
      }
      if (ytForm) ytForm.classList.add("hidden");
      if (ytConnectedBox) ytConnectedBox.classList.remove("hidden");
      if (ytToggleAuto) ytToggleAuto.checked = Boolean(data.youtube.auto_upload);
      if (ytPrivacySelect && data.youtube.privacy_status) {
        ytPrivacySelect.value = data.youtube.privacy_status;
      }
    } else {
      if (ytBadge) {
        ytBadge.textContent = data.youtube && data.youtube.has_secrets ? "Ready to Connect ⚡" : "Disconnected";
        ytBadge.className = data.youtube && data.youtube.has_secrets 
          ? "px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30"
          : "px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-800 text-slate-400";
      }
      if (ytForm) ytForm.classList.remove("hidden");
      if (ytConnectedBox) ytConnectedBox.classList.add("hidden");
      if (ytSecretsStatus) {
        ytSecretsStatus.innerHTML = data.youtube && data.youtube.has_secrets 
          ? "<span class='text-emerald-400 font-bold'>✓ client_secrets.json automatically loaded from Downloads!</span>" 
          : "Upload client_secrets.json from Google Cloud";
      }
    }
  } catch (e) {
    console.error("Social settings fetch error:", e);
  }
}

let currentIgMode = "creds";

function setIgLoginMode(mode) {
  currentIgMode = mode;
  const tabCreds = document.getElementById("tab-ig-creds");
  const tabSession = document.getElementById("tab-ig-session");
  const fieldsCreds = document.getElementById("ig-fields-creds");
  const fieldsSession = document.getElementById("ig-fields-session");

  if (!tabCreds || !tabSession) return;

  if (mode === "session") {
    tabSession.className = "flex-1 py-1 rounded-md bg-pink-600 text-white transition";
    tabCreds.className = "flex-1 py-1 rounded-md text-slate-400 hover:text-white transition";
    if (fieldsCreds) fieldsCreds.classList.add("hidden");
    if (fieldsSession) fieldsSession.classList.remove("hidden");
  } else {
    tabCreds.className = "flex-1 py-1 rounded-md bg-pink-600 text-white transition";
    tabSession.className = "flex-1 py-1 rounded-md text-slate-400 hover:text-white transition";
    if (fieldsCreds) fieldsCreds.classList.remove("hidden");
    if (fieldsSession) fieldsSession.classList.add("hidden");
  }
}

async function handleInstagramConnect() {
  const btn = document.getElementById("btn-ig-connect");
  let payload = {};

  if (currentIgMode === "session") {
    const sessionId = document.getElementById("ig-input-sessionid").value.trim();
    if (!sessionId) {
      alert("Please paste your Instagram 'sessionid' cookie value.");
      return;
    }
    payload.session_id = sessionId;
  } else {
    const username = document.getElementById("ig-input-username").value.trim();
    const password = document.getElementById("ig-input-password").value;
    if (!username || !password) {
      alert("Please enter Instagram username and password (ya Session ID tab use karein).");
      return;
    }
    payload.username = username;
    payload.password = password;
  }

  const originalText = btn.innerHTML;
  btn.innerHTML = `<i data-lucide="loader" class="w-3.5 h-3.5 animate-spin"></i> Connecting...`;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch("/api/social/instagram/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Connection failed");

    showToast("Instagram connected successfully!");
    if (document.getElementById("ig-input-password")) document.getElementById("ig-input-password").value = "";
    if (document.getElementById("ig-input-sessionid")) document.getElementById("ig-input-sessionid").value = "";
    fetchSocialSettings();
  } catch (e) {
    alert("Instagram Error: " + e.message);
  } finally {
    btn.innerHTML = originalText;
    if (window.lucide) lucide.createIcons();
  }
}

async function handleInstagramDisconnect() {
  if (!confirm("Are you sure you want to disconnect Instagram?")) return;
  try {
    await fetch("/api/social/instagram/disconnect", { method: "POST" });
    showToast("Instagram disconnected.");
    fetchSocialSettings();
  } catch (e) {
    alert("Disconnect failed: " + e.message);
  }
}

async function toggleInstagramAuto(checkbox) {
  try {
    await fetch("/api/social/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform: "instagram", auto_upload: checkbox.checked })
    });
    showToast(checkbox.checked ? "Instagram Auto-Post ENABLED" : "Instagram Auto-Post DISABLED");
  } catch (e) {
    console.error("Toggle IG failed:", e);
  }
}

async function handleYouTubeSecretsFile(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  const status = document.getElementById("yt-secrets-status");
  status.textContent = "Uploading client_secrets.json...";

  try {
    const res = await fetch("/api/social/youtube/upload-secrets", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");

    status.textContent = "✓ client_secrets.json verified! Click Connect below.";
    showToast("Client Secrets uploaded!");
    fetchSocialSettings();
  } catch (e) {
    alert("YouTube Secrets Error: " + e.message);
    status.textContent = "Upload failed. Check format.";
  }
}

async function handleYouTubeConnect() {
  const btn = document.getElementById("btn-yt-connect");
  const originalText = btn.innerHTML;
  btn.innerHTML = `<i data-lucide="loader" class="w-3.5 h-3.5 animate-spin"></i> Authorizing Google Account...`;
  if (window.lucide) lucide.createIcons();

  showToast("Opening Google Authorization in your browser...");

  try {
    const res = await fetch("/api/social/youtube/connect", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Authorization failed");

    showToast("YouTube Channel connected!");
    fetchSocialSettings();
  } catch (e) {
    alert("YouTube Error: " + e.message);
  } finally {
    btn.innerHTML = originalText;
    if (window.lucide) lucide.createIcons();
  }
}

async function handleYouTubeDisconnect() {
  if (!confirm("Are you sure you want to disconnect YouTube?")) return;
  try {
    await fetch("/api/social/youtube/disconnect", { method: "POST" });
    showToast("YouTube disconnected.");
    fetchSocialSettings();
  } catch (e) {
    alert("Disconnect failed: " + e.message);
  }
}

async function toggleYouTubeAuto(checkbox) {
  try {
    await fetch("/api/social/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform: "youtube", auto_upload: checkbox.checked })
    });
    showToast(checkbox.checked ? "YouTube Auto-Post ENABLED" : "YouTube Auto-Post DISABLED");
  } catch (e) {
    console.error("Toggle YT failed:", e);
  }
}

async function handleYouTubePrivacyChange(select) {
  try {
    await fetch("/api/social/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform: "youtube", privacy_status: select.value })
    });
    showToast(`YouTube Visibility set to ${select.value.toUpperCase()}`);
  } catch (e) {
    console.error("YT privacy update failed:", e);
  }
}

// --- 1-Click Upload & Modal Handlers ---

async function openSocialModal(filename) {
  activeSocialFilename = filename;
  const modal = document.getElementById("social-modal");
  const title = document.getElementById("social-modal-title");
  const filenameEl = document.getElementById("social-modal-filename");
  const captionEl = document.getElementById("social-modal-caption");
  const resultBox = document.getElementById("social-upload-result");

  filenameEl.textContent = filename;
  title.textContent = `Upload / Post: ${filename}`;
  captionEl.value = "Loading metadata...";
  resultBox.className = "hidden";
  modal.classList.remove("hidden");

  try {
    const res = await fetch(`/api/social/metadata/${filename}`);
    const meta = await res.json();
    captionEl.value = meta.description;
  } catch (e) {
    captionEl.value = `TMKOC ${filename} 😂 #tmkoc #shorts #reels`;
  }
}

function closeSocialModal() {
  const modal = document.getElementById("social-modal");
  modal.classList.add("hidden");
  activeSocialFilename = null;
}

function copyCurrentModalCaption() {
  const caption = document.getElementById("social-modal-caption").value;
  navigator.clipboard.writeText(caption).then(() => {
    showToast("Caption Copied to Clipboard!");
  });
}

async function copyClipMetadata(filename) {
  try {
    const res = await fetch(`/api/social/metadata/${filename}`);
    const meta = await res.json();
    await navigator.clipboard.writeText(meta.description);
    showToast(`Part metadata & viral tags copied!`);
  } catch (e) {
    navigator.clipboard.writeText(`TMKOC ${filename} 😂 #tmkoc #shorts #reels`);
    showToast("Tags copied!");
  }
}

async function triggerDirectUpload(platform) {
  if (!activeSocialFilename) return;

  const resultBox = document.getElementById("social-upload-result");
  const caption = document.getElementById("social-modal-caption").value;

  resultBox.className = "p-3 rounded-xl text-xs font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30 flex items-center gap-2";
  resultBox.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i> Uploading to ${platform.toUpperCase()}... Please wait...`;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch("/api/social/upload-single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: activeSocialFilename,
        platform: platform,
        custom_caption: caption
      })
    });
    const data = await res.json();

    if (!data.success) {
      let errs = [];
      if (data.results?.instagram?.error) errs.push(`Instagram: ${data.results.instagram.error}`);
      if (data.results?.youtube?.error) errs.push(`YouTube: ${data.results.youtube.error}`);
      throw new Error(errs.join(" | ") || data.detail || "Upload failed");
    }

    let successHtml = `<div class="space-y-1">`;
    if (data.results?.instagram?.url) {
      successHtml += `<p class="text-emerald-400 font-bold">✓ Instagram Reel Live! <a href="${data.results.instagram.url}" target="_blank" class="underline text-pink-400 font-bold ml-1">Open Reel</a></p>`;
    }
    if (data.results?.youtube?.url) {
      successHtml += `<p class="text-emerald-400 font-bold">✓ YouTube Shorts Live! <a href="${data.results.youtube.url}" target="_blank" class="underline text-red-400 font-bold ml-1">Open Short</a></p>`;
    }
    successHtml += `</div>`;

    resultBox.className = "p-3 rounded-xl text-xs font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30";
    resultBox.innerHTML = successHtml;
    showToast("Upload Successful!");
  } catch (e) {
    resultBox.className = "p-3 rounded-xl text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/30";
    resultBox.innerHTML = `⚠️ ${e.message}`;
  }
}

function showToast(message) {
  const toast = document.getElementById("app-toast");
  const msgEl = document.getElementById("toast-message");
  if (!toast || !msgEl) return;

  msgEl.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => {
    toast.classList.add("hidden");
  }, 3500);
}
