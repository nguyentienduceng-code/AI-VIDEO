import { create } from 'zustand';
import { STYLES, API_BASE, HOOK_SFX_OPTIONS } from './constants';

const WS_BASE = API_BASE.replace(/^http/, 'ws');
const MAX_RECONNECT_ATTEMPTS = 6;
// Không nhận được tin nhắn nào trong 3 phút → coi như kết nối chết (server im lặng
// hoặc TCP half-open, hai trường hợp mà `onclose` KHÔNG bao giờ bắn ra).
const STALL_TIMEOUT_MS = 180000;

const INITIAL_STATE = {
  step: 'config',

  activeMode: 'storyteller',
  topic: '',
  scriptText: '',
  ratio: '9:16',
  numScenes: 6,
  targetDuration: '30s',
  narrationTone: 'viral',
  contentNiche: '',
  voice: 'vi-VN-NamMinhNeural',
  style: STYLES[0].value,
  bgm: 'auto',
  introBgm: 'none',
  introBgmDuration: 0,
  apiKey: '',
  showApiKey: false,

  useVeo: false,
  ctaText: '',
  speechRate: '+0%',
  speechPitch: '+0Hz',
  bgmVolume: 15,
  negativePrompt: '',
  characterDescription: '',
  useFrameChaining: true,
  useKenBurns: true,
  useBeatSync: false,
  useVeoAmbientAudio: true,
  useGpuEncode: true,
  hookZoomBoost: true,
  usePatternInterrupt: true,
  useSfx: true,
  sfxVolume: 8,
  subtitleStyle: 'karaoke_bold',
  colorGrading: 'warm_cinematic',
  useAudioDucking: true,
  watermarkText: '',
  hookText: '',
  hookVariants: [],     // A/B Hook variants trả về từ AI (B3)
  scriptReview: null,   // Script Review kết quả (B2): { quality_score, review_notes, passed }
  hookQuote: '',
  outroText: '',
  uploadSessionId: null,
  uploadedFiles: [],
  uploadLoading: false,
  coverImageSessionId: null,
  coverImageName: '',
  coverImageLoading: false,
  coverImagePosition: 'start',
  useBreathing: false,
  hookEffect: 'carousel_quote',
  preferStockVideo: false,
  visualSource: 'auto',
  useSinglePassNarration: false,
  hookReelSfx: 'tick_wood',
  hookSfxVolume: 100,
  outroEffect: 'cta_card',
  outroReelSfx: 'none',
  outroSfxVolume: 100,

  scenes: [],
  estimatedDurationS: 0,
  scriptLoading: false,

  status: 'idle',
  progress: 0,
  jobMessage: '',
  progressLog: [],
  videoUrl: null,
  srtUrl: null,
  errorMsg: '',
  // Thông báo KHÔNG phải lỗi về kịch bản vừa sinh — vd "đã cân lại nhịp các cảnh".
  // Tách khỏi errorMsg vì đây là việc bình thường đã làm xong, không phải sự cố.
  scriptNotice: '',
  activeJobId: null,
};

const capitalize = (s) => s[0].toUpperCase() + s.slice(1);
// Mọi setX hỗ trợ cả giá trị trực tiếp lẫn updater dạng hàm (prev => next), giữ đúng
// cách gọi cũ kiểu setScenes(prev => prev.map(...)) từ AppContext.
const resolveValue = (value, current) => (typeof value === 'function' ? value(current) : value);

// Dùng chung cho setHookEffect VÀ applyPreset: 2 nơi này đều có thể đổi hookEffect
// cùng lúc với hookReelSfx, nên phải validate chéo ở CẢ HAI, không chỉ 1 nơi.
// LỖI CŨ: applyPreset gán thẳng preset.hook_reel_sfx mà không qua bước này — preset cũ
// (lưu trước khi có 3 hook mới, hoặc sửa tay qua API) có thể mang cặp (hook_effect,
// hook_reel_sfx) không khớp nhau, vd hook "Màn đen" nhưng sfx "Máy đếm tiền" (chỉ hợp
// lệ cho Carousel) — backend vẫn resolve ra file thật (HOOK_REEL_SOUNDS là 1 dict
// phẳng dùng chung mọi hook) nên phát NHẦM tiếng mà không có lỗi/cảnh báo nào.
const resolveValidHookSfx = (hookEffect, currentSfx) => {
  const options = HOOK_SFX_OPTIONS[hookEffect] || [];
  if (options.length > 0 && !options.some((o) => o.value === currentSfx)) {
    return options[0].value;
  }
  return currentSfx;
};

// Socket/timer sống ở module scope (không phải React state) vì chúng không cần kéo theo
// re-render — y hệt tinh thần của các useRef trong AppContext cũ, chỉ khác là store là
// singleton nên không cần buộc vào vòng đời của một component Provider.
let voiceAudioEl = null;
let bgmAudioEl = null;
let wsConn = null;
let reconnectTimer = null;
let stallTimer = null;
let reconnectAttempts = 0;
let jobFinished = false;

export const useAppStore = create((set, get) => {
  const setters = {};
  for (const key of Object.keys(INITIAL_STATE)) {
    if (key === 'hookEffect') {
      setters['setHookEffect'] = (effect) =>
        set((state) => ({
          hookEffect: effect,
          hookReelSfx: resolveValidHookSfx(effect, state.hookReelSfx),
        }));
    } else if (key === 'outroEffect') {
      setters['setOutroEffect'] = (effect) =>
        set((state) => ({
          outroEffect: effect,
          outroReelSfx: resolveValidHookSfx(effect, state.outroReelSfx),
        }));
    } else {
      setters[`set${capitalize(key)}`] = (value) =>
        set((state) => ({ [key]: resolveValue(value, state[key]) }));
    }
  }

  const stopAllAudio = () => {
    if (voiceAudioEl) {
      voiceAudioEl.pause();
      voiceAudioEl.currentTime = 0;
    }
    if (bgmAudioEl) {
      bgmAudioEl.pause();
      bgmAudioEl.currentTime = 0;
    }
  };

  const playPreview = (type, id) => {
    stopAllAudio();
    const audioUrl = `${API_BASE}/api/preview/${type}/${id}`;
    const audio = new Audio(audioUrl);
    if (type === 'bgm') {
      audio.volume = get().bgmVolume / 100;
      bgmAudioEl = audio;
    } else {
      voiceAudioEl = audio;
    }
    audio.play().catch(e => alert("Lỗi phát audio: " + e.message + "\n(Vui lòng tương tác với trang web trước khi nghe hoặc kiểm tra kết nối tới Backend)"));
  };

  const playMixPreview = (voiceId, bgmId) => {
    stopAllAudio();
    const voiceAudio = new Audio(`${API_BASE}/api/preview/voice/${voiceId}`);
    const bgmAudio = new Audio(`${API_BASE}/api/preview/bgm/${bgmId}`);
    bgmAudio.volume = get().bgmVolume / 100;

    voiceAudioEl = voiceAudio;
    bgmAudioEl = bgmAudio;

    let loopCount = 0;
    voiceAudio.addEventListener('ended', () => {
      if (loopCount < 1) {
        loopCount++;
        voiceAudio.currentTime = 0;
        voiceAudio.play().catch(e => console.log(e));
      } else {
        bgmAudio.pause(); // Dừng BGM khi giọng đọc kết thúc vòng lặp
      }
    });

    voiceAudio.play().catch(e => console.log(e));
    bgmAudio.play().catch(e => console.log(e));
  };

  // ── WebSocket theo dõi tiến trình render ─────────────────────────────────
  const clearJobTimers = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (stallTimer) {
      clearTimeout(stallTimer);
      stallTimer = null;
    }
  };

  const teardownJobSocket = () => {
    jobFinished = true;   // chặn onclose lên lịch reconnect
    clearJobTimers();
    const ws = wsConn;
    wsConn = null;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    }
  };

  const subscribeToJob = (jobId) => {
    teardownJobSocket();          // huỷ socket của lần render trước, nếu còn
    jobFinished = false;
    reconnectAttempts = 0;
    set({ activeJobId: jobId });

    const armStallWatchdog = () => {
      if (stallTimer) clearTimeout(stallTimer);
      stallTimer = setTimeout(() => {
        if (!jobFinished && wsConn) wsConn.close();  // → onclose → reconnect
      }, STALL_TIMEOUT_MS);
    };

    const scheduleReconnect = () => {
      if (jobFinished) return;
      clearJobTimers();
      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        set({
          status: 'error',
          errorMsg: 'Mất kết nối tới máy chủ và không kết nối lại được. Video có thể vẫn đang render — tải lại trang để kiểm tra.',
        });
        return;
      }
      const delay = Math.min(1000 * 2 ** reconnectAttempts, 15000) + Math.random() * 500;
      reconnectAttempts += 1;
      set({ jobMessage: `Mất kết nối — đang thử kết nối lại (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...` });
      reconnectTimer = setTimeout(connect, delay);
    };

    function connect() {
      if (jobFinished) return;
      let ws;
      try {
        ws = new WebSocket(`${WS_BASE}/api/ws/job-status/${jobId}`);
      } catch {
        scheduleReconnect();
        return;
      }
      wsConn = ws;

      ws.onopen = () => {
        reconnectAttempts = 0;
        set({ errorMsg: '' });
        armStallWatchdog();
      };

      ws.onmessage = (event) => {
        armStallWatchdog();
        let msg;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return;   // khung hỏng: bỏ qua, đừng để exception thoát ra khỏi handler
        }
        if (msg.progress !== undefined) set({ progress: msg.progress });
        if (msg.message) {
          set((state) => ({
            jobMessage: msg.message,
            progressLog: state.progressLog[state.progressLog.length - 1] === msg.message
              ? state.progressLog
              : [...state.progressLog, msg.message],
          }));
        }
        if (msg.status === 'done') {
          teardownJobSocket();
          set({
            status: 'done',
            step: 'done',
            ...(msg.video_url ? { videoUrl: `${API_BASE}${msg.video_url}` } : {}),
            ...(msg.srt_url ? { srtUrl: `${API_BASE}${msg.srt_url}` } : {}),
          });
        } else if (msg.status === 'error') {
          teardownJobSocket();
          set({ status: 'error', step: 'rendering', errorMsg: msg.error || msg.message || 'Có lỗi xảy ra' });
        }
      };

      // onerror LUÔN kéo theo onclose → chỉ đặt logic reconnect ở onclose, tránh
      // lên lịch hai lần cho cùng một lần rớt.
      ws.onerror = () => {};
      ws.onclose = () => {
        if (wsConn === ws) wsConn = null;
        if (jobFinished) return;
        scheduleReconnect();
      };
    }

    connect();
  };

  const handleReset = () => {
    teardownJobSocket();
    set({
      activeJobId: null,
      step: 'config',
      scenes: [],
      status: 'idle',
      progress: 0,
      jobMessage: '',
      progressLog: [],
      videoUrl: null,
      srtUrl: null,
      errorMsg: '',
      uploadSessionId: null,
      uploadedFiles: [],
      coverImageSessionId: null,
      coverImageName: '',
    });
  };

  const handleCancelRender = async () => {
    const jobId = get().activeJobId;
    if (!jobId) return;
    try {
      await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: 'DELETE' });
    } catch (e) {
      console.error(e);
    }
  };

  const applyPreset = (preset) => {
    if (!preset) return;
    const patch = {};
    if (preset.aspect_ratio) patch.ratio = preset.aspect_ratio;
    if (preset.voice) patch.voice = preset.voice;
    if (preset.art_style) patch.style = preset.art_style;
    if (preset.bgm_track !== undefined) patch.bgm = preset.bgm_track === null ? 'none' : preset.bgm_track;
    if (preset.intro_bgm_track !== undefined) patch.introBgm = preset.intro_bgm_track;
    if (preset.intro_bgm_duration !== undefined) patch.introBgmDuration = preset.intro_bgm_duration;
    if (preset.target_duration) patch.targetDuration = preset.target_duration;
    if (preset.narration_tone) patch.narrationTone = preset.narration_tone;
    if (preset.speech_rate) patch.speechRate = preset.speech_rate;
    if (preset.speech_pitch) patch.speechPitch = preset.speech_pitch;
    if (preset.bgm_volume !== undefined) patch.bgmVolume = preset.bgm_volume;
    if (preset.subtitle_style) patch.subtitleStyle = preset.subtitle_style;
    if (preset.color_grading) patch.colorGrading = preset.color_grading;
    if (preset.prefer_stock_video !== undefined) patch.preferStockVideo = preset.prefer_stock_video;
    if (preset.visual_source) patch.visualSource = preset.visual_source;
    if (preset.use_single_pass_narration !== undefined) patch.useSinglePassNarration = preset.use_single_pass_narration;
    if (preset.use_sfx !== undefined) patch.useSfx = preset.use_sfx;
    if (preset.sfx_volume !== undefined) patch.sfxVolume = preset.sfx_volume;
    if (preset.use_audio_ducking !== undefined) patch.useAudioDucking = preset.use_audio_ducking;
    // Preset lưu hook_sfx_volume theo thang % (đúng con số trên thanh trượt), nên gán
    // thẳng vào state — KHÔNG nhân/chia 100 ở đây. Thiếu dòng này thì lưu preset xong
    // nạp lại, riêng mức âm lượng Hook SFX âm thầm quay về mặc định 100 trong khi mọi
    // thiết lập khác đều được khôi phục.
    if (preset.hook_sfx_volume !== undefined) patch.hookSfxVolume = preset.hook_sfx_volume;

    // Nâng cao (Dành riêng cho preset đặc biệt như Import JSON)
    if (preset.use_ken_burns !== undefined) patch.useKenBurns = preset.use_ken_burns;
    if (preset.hook_zoom_boost !== undefined) patch.hookZoomBoost = preset.hook_zoom_boost;
    if (preset.use_breathing !== undefined) patch.useBreathing = preset.use_breathing;
    if (preset.use_frame_chaining !== undefined) patch.useFrameChaining = preset.use_frame_chaining;
    if (preset.use_beat_sync !== undefined) patch.useBeatSync = preset.use_beat_sync;
    if (preset.hook_effect) patch.hookEffect = preset.hook_effect;
    if (preset.use_veo !== undefined) patch.useVeo = preset.use_veo;
    if (preset.content_niche !== undefined) patch.contentNiche = preset.content_niche;

    // LỖI CŨ: hookReelSfx được gán thẳng từ preset.hook_reel_sfx, không đi qua cùng
    // bước validate chéo với hookEffect như setHookEffect (xem resolveValidHookSfx).
    // Preset cũ (lưu trước khi có 3 hook mới, hoặc sửa tay qua API) có thể mang cặp
    // (hook_effect, hook_reel_sfx) không khớp nhau — vd hook "Màn đen" + sfx "Máy đếm
    // tiền" (chỉ hợp lệ cho Carousel). Validate theo hookEffect SẮP ÁP DỤNG (patch nếu
    // preset có, không thì giữ nguyên hookEffect hiện tại) — không phải hookEffect cũ.
    const effectiveHookEffect = patch.hookEffect ?? get().hookEffect;
    const requestedSfx = preset.hook_reel_sfx ?? get().hookReelSfx;
    patch.hookReelSfx = resolveValidHookSfx(effectiveHookEffect, requestedSfx);
    
    // Tương tự cho outroEffect
    if (preset.outro_effect) patch.outroEffect = preset.outro_effect;
    if (preset.outro_sfx_volume !== undefined) patch.outroSfxVolume = preset.outro_sfx_volume;
    
    const effectiveOutroEffect = patch.outroEffect ?? get().outroEffect;
    const requestedOutroSfx = preset.outro_reel_sfx ?? get().outroReelSfx;
    patch.outroReelSfx = resolveValidHookSfx(effectiveOutroEffect, requestedOutroSfx);

    set(patch);
  };

  return {
    ...INITIAL_STATE,
    ...setters,
    playPreview,
    playMixPreview,
    stopAllAudio,
    handleReset,
    handleCancelRender,
    applyPreset,
    subscribeToJob,
  };
});

// Dẫn xuất thuần từ activeMode — không lưu trong state vì luôn tính lại được, tránh
// một nguồn sự thật thứ hai có thể lệch pha với activeMode.
export const needsUpload = (activeMode) => activeMode === 'img2vid' || activeMode === 'slideshow';
export const needsScript = (activeMode) => activeMode === 'script';
export const needsTopic = (activeMode) => !needsUpload(activeMode) && !needsScript(activeMode);
