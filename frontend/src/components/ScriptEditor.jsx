import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RotateCcw, PenLine, Play, AlertTriangle, ChevronUp, ChevronDown, Trash2, Plus, Film, Volume2, Code, Upload, X, Pause, Music, Headphones, Square, Settings } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from '../store';
import { API_BASE, MODE_MAP, TRANSITIONS, SFX_OPTIONS, DURATION_OPTIONS } from '../constants';

// Chờ user ngừng gõ rồi mới hỏi backend. Gõ một câu dài mà không có độ trễ này thì
// mỗi phím là một request quét cả thư mục cache.
const CACHE_PROBE_DELAY_MS = 600;

const BREAK_SNIPPET = '<break time="1s"/>';

// Tốc độ đọc dự phòng, CHỈ dùng khi chưa hỏi được backend. Con số thật lấy từ
// /api/timing-profile — nó tự hiệu chỉnh theo giọng người dùng đang dùng.
//
// LỖI CŨ: file này giữ hằng số riêng "12 từ/cảnh" và cảnh báo dựa trên SỐ TỪ, trong
// khi backend ước lượng bằng 2.6 và 3.0 từ/giây ở hai chỗ khác nhau. Ba thước đo lệch
// nhau tới 15% nên cảnh báo trên màn hình không bao giờ khớp thời lượng video thật —
// user rút gọn kịch bản theo cảnh báo mà video vẫn dài quá, hoặc ngược lại.
const FALLBACK_WPS = 3.0;

// Nhịp xem: một ảnh đứng yên quá 6.5 giây là ì, dưới 2.5 giây là chớp qua chưa kịp nhìn.
const SHOT_MIN_S = 2.5;
const SHOT_MAX_S = 6.5;
const SCENE_TRANSITION_OVERHEAD = 0.5;  // khớp gemini_service.SCENE_TRANSITION_OVERHEAD

const BREAK_TAG_RE = /<break[^>]*>/gi;
const BREAK_TIME_RE = /<break[^>]*time\s*=\s*"([\d.]+)\s*(ms|s)"[^>]*>/gi;

// Bỏ thẻ <break time="..."/> trước khi đếm — đây là điều khiển nhịp đọc, không phải
// lời thoại thật, đếm cả vào sẽ làm số từ ảo tăng so với những gì người xem thực nghe.
const countWords = (text) => {
  const cleaned = (text || '').replace(BREAK_TAG_RE, ' ').trim();
  return cleaned ? cleaned.split(/\s+/).length : 0;
};

// Khoảng lặng do thẻ <break/> tạo ra — có thật trong file audio nên phải cộng vào thời
// lượng, nhưng không phải thời gian đọc chữ (khớp duration_model.break_seconds).
const breakSeconds = (text) => {
  let total = 0;
  for (const [, value, unit] of (text || '').matchAll(BREAK_TIME_RE)) {
    const v = parseFloat(value);
    if (!Number.isNaN(v)) total += unit.toLowerCase() === 'ms' ? v / 1000 : v;
  }
  return total;
};

// Thời lượng dự kiến của một cảnh, cùng công thức với duration_model.estimate_duration.
const estimateSceneSeconds = (scene, wps) => {
  const words = countWords(scene?.text);
  const speech = words > 0 ? words / (wps || FALLBACK_WPS) : 0;
  return speech + breakSeconds(scene?.text) + (scene?.pause_after_ms || 0) / 1000;
};

// Nhãn thời lượng cạnh mỗi cảnh: xanh = nhịp đẹp, vàng = quá ngắn, đỏ = quá dài.
function SceneTiming({ seconds }) {
  if (!seconds) return null;
  const tooLong = seconds > SHOT_MAX_S;
  const tooShort = seconds < SHOT_MIN_S;
  const color = tooLong ? 'var(--red, #ef4444)' : tooShort ? 'var(--amber, #f59e0b)' : 'var(--text-dim, #94a3b8)';
  const title = tooLong
    ? `Cảnh dài ~${seconds.toFixed(1)}s. Một ảnh đứng yên quá ${SHOT_MAX_S}s khiến nhịp video ì — cân nhắc tách bớt câu sang cảnh mới.`
    : tooShort
      ? `Cảnh chỉ ~${seconds.toFixed(1)}s. Ảnh chớp qua nhanh hơn ${SHOT_MIN_S}s thì người xem chưa kịp nhìn — cân nhắc gộp với cảnh liền kề.`
      : `Ước lượng ~${seconds.toFixed(1)}s — nhịp tốt.`;
  return (
    <span style={{ color, fontSize: 11, fontWeight: 600 }} title={title}>
      ~{seconds.toFixed(1)}s
    </span>
  );
}

export default function ScriptEditor() {
  const ctx = useAppStore(useShallow((s) => ({
    scenes: s.scenes, setScenes: s.setScenes,
    errorMsg: s.errorMsg, setErrorMsg: s.setErrorMsg,
    setStep: s.setStep, setStatus: s.setStatus, setProgress: s.setProgress,
    setJobMessage: s.setJobMessage, setProgressLog: s.setProgressLog,
    setVideoUrl: s.setVideoUrl, setSrtUrl: s.setSrtUrl,
    activeMode: s.activeMode, ratio: s.ratio, voice: s.voice, style: s.style,
    bgm: s.bgm, setBgm: s.setBgm,
    introBgm: s.introBgm, introBgmDuration: s.introBgmDuration,
    speechRate: s.speechRate, speechPitch: s.speechPitch, bgmVolume: s.bgmVolume,
    targetDuration: s.targetDuration,
    uploadSessionId: s.uploadSessionId,
    negativePrompt: s.negativePrompt, apiKey: s.apiKey, useVeo: s.useVeo, ctaText: s.ctaText, setCtaText: s.setCtaText,
    useAnimatedCaptions: s.useAnimatedCaptions, characterDescription: s.characterDescription,
    useFrameChaining: s.useFrameChaining, useKenBurns: s.useKenBurns, useBeatSync: s.useBeatSync,
    useVeoAmbientAudio: s.useVeoAmbientAudio, useGpuEncode: s.useGpuEncode, hookZoomBoost: s.hookZoomBoost,
    useSfx: s.useSfx, sfxVolume: s.sfxVolume, subtitleStyle: s.subtitleStyle, colorGrading: s.colorGrading,
    watermarkText: s.watermarkText, coverImageSessionId: s.coverImageSessionId, coverImagePosition: s.coverImagePosition,
    useAudioDucking: s.useAudioDucking,
    useBreathing: s.useBreathing, hookEffect: s.hookEffect, hookQuote: s.hookQuote, setHookQuote: s.setHookQuote,
    hookText: s.hookText, setHookText: s.setHookText,
    outroText: s.outroText, setOutroText: s.setOutroText,
    preferStockVideo: s.preferStockVideo, visualSource: s.visualSource,
    useSinglePassNarration: s.useSinglePassNarration, hookReelSfx: s.hookReelSfx,
    // LỖI CŨ: payload render đọc ctx.hookSfxVolume nhưng dòng này thiếu nó → undefined
    // / 100 = NaN → JSON.stringify biến thành null → Pydantic từ chối, MỌI lần bấm
    // Render trả 422. Thanh trượt Hook SFX có ba mắt xích và đã đứt ở cả ba: model,
    // render_kwargs, và ngay đây.
    hookSfxVolume: s.hookSfxVolume,
    outroEffect: s.outroEffect, outroReelSfx: s.outroReelSfx, outroSfxVolume: s.outroSfxVolume,
    subscribeToJob: s.subscribeToJob, stopAllAudio: s.stopAllAudio,
    estimatedDurationS: s.estimatedDurationS, setEstimatedDurationS: s.setEstimatedDurationS,
    scriptNotice: s.scriptNotice, setScriptNotice: s.setScriptNotice,
  })));

  // Trạng thái bộ nhớ đệm từng cảnh: null = chưa biết, [] = mảng theo chỉ số cảnh.
  const [cacheStatus, setCacheStatus] = useState(null);
  const [probing, setProbing] = useState(false);
  const [expandedAdvanced, setExpandedAdvanced] = useState(new Set());
  
  const [customSfxList, setCustomSfxList] = useState([]);
  
  useEffect(() => {
    fetch(`${API_BASE}/api/sfx-list`)
      .then(res => res.json())
      .then(data => setCustomSfxList(data.sfx_list || []))
      .catch(err => console.error("Failed to load custom SFX", err));
  }, []);

  const handleUploadSfx = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) return alert("File quá lớn! Tối đa 10MB.");
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await fetch(`${API_BASE}/api/upload-sfx`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        setCustomSfxList(prev => [...prev, { value: data.filename, label: data.label }]);
        alert("Upload thành công!");
      } else {
        alert(data.detail || "Upload thất bại.");
      }
    } catch (err) {
      alert("Lỗi kết nối: " + err.message);
    }
    e.target.value = '';
  };

  const toggleAdvanced = (idx) => {
    setExpandedAdvanced(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };
  const [uploadingIdx, setUploadingIdx] = useState(null);
  const [previewIdx, setPreviewIdx] = useState(null);   // cảnh đang sinh/đang phát
  const textareaRefs = useRef([]);
  const previewAudioRef = useRef(null);
  const previewUrlRef = useRef(null);

  const handleRenderVideo = async () => {
    if (!ctx.scenes.length) return ctx.setErrorMsg('Chưa có cảnh nào để render!');
    ctx.setErrorMsg('');
    ctx.setStep('rendering');
    ctx.setStatus('loading');
    ctx.setProgress(0);
    ctx.setJobMessage('Đang khởi tạo...');
    ctx.setProgressLog([]);
    ctx.setVideoUrl(null);
    ctx.setSrtUrl(null);

    try {
      const payload = {
        scenes: ctx.scenes, mode: MODE_MAP[ctx.activeMode], aspect_ratio: ctx.ratio, voice: ctx.voice,
        art_style: ctx.style,
        bgm_track: ctx.bgm === 'none' ? null : ctx.bgm, upload_session_id: ctx.uploadSessionId || undefined,
        speech_rate: ctx.speechRate, speech_pitch: ctx.speechPitch, bgm_volume: ctx.bgmVolume / 100,
        negative_prompt: ctx.negativePrompt || undefined, gemini_api_key: ctx.apiKey || undefined,
        use_veo: ctx.useVeo, cta_text: ctx.ctaText || undefined, use_animated_captions: ctx.useAnimatedCaptions,
        character_description: ctx.characterDescription || undefined, use_frame_chaining: ctx.useFrameChaining,
        use_ken_burns: ctx.useKenBurns, use_beat_sync: ctx.useBeatSync, use_veo_ambient_audio: ctx.useVeoAmbientAudio,
        use_gpu_encode: ctx.useGpuEncode, hook_zoom_boost: ctx.hookZoomBoost,
        use_sfx: ctx.useSfx, sfx_volume: ctx.sfxVolume / 100,
        use_audio_ducking: ctx.useAudioDucking,
        subtitle_style: ctx.subtitleStyle, color_grading: ctx.colorGrading, watermark_text: ctx.watermarkText || undefined,
        cover_image_session_id: ctx.coverImageSessionId || undefined,
        cover_image_position: ctx.coverImagePosition,
        use_breathing: ctx.useBreathing, hook_effect: ctx.hookEffect, hook_quote: ctx.hookQuote,
        hook_text: ctx.hookText,
        prefer_stock_video: ctx.preferStockVideo,
        visual_source: ctx.visualSource,
        intro_bgm_track: ctx.introBgm === 'none' ? null : ctx.introBgm,
        intro_bgm_duration: ctx.introBgmDuration,
        use_single_pass_narration: ctx.useSinglePassNarration,
        hook_reel_sfx: ctx.hookReelSfx,
        hook_sfx_volume: ctx.hookSfxVolume / 100,
        outro_effect: ctx.outroEffect,
        outro_text: ctx.outroText,
        outro_reel_sfx: ctx.outroReelSfx,
        outro_sfx_volume: ctx.outroSfxVolume / 100,
      };

      const res = await fetch(`${API_BASE}/api/render-video`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi server');
      }

      const data = await res.json();

      // Vòng đời socket thuộc về AppProvider: component này đã unmount từ lúc
      // setStep('rendering') ở đầu hàm, nên không thể tự dọn dẹp kết nối.
      ctx.subscribeToJob(data.job_id);
    } catch (err) {
      ctx.setStatus('error');
      ctx.setErrorMsg(err.message);
    }
  };

  // ── Đèn báo bộ nhớ đệm ────────────────────────────────────────────────────
  // Hỏi backend xem cảnh nào đã có sẵn giọng/hình trong cache. Chạy lại mỗi khi user
  // sửa bất cứ thứ gì ảnh hưởng tới khoá cache (lời thoại, mô tả ảnh, giọng, tốc độ...).
  // useMemo tránh JSON.stringify lại toàn bộ scenes trên những re-render không đổi gì
  // liên quan tới cache (vd: mở/đóng accordion, đổi previewIdx).
  const probeSignature = useMemo(() => JSON.stringify([
    ctx.scenes.map(s => [s.text, s.image_prompt, s.emotion, s.speech_rate_modifier, s.override_asset]),
    ctx.voice, ctx.speechRate, ctx.speechPitch, ctx.useBreathing,
    ctx.ratio, ctx.style, ctx.negativePrompt, MODE_MAP[ctx.activeMode],
    ctx.visualSource, ctx.preferStockVideo, ctx.useVeo,
  ]), [ctx.scenes, ctx.voice, ctx.speechRate, ctx.speechPitch, ctx.useBreathing,
      ctx.ratio, ctx.style, ctx.negativePrompt, ctx.activeMode, ctx.visualSource,
      ctx.preferStockVideo, ctx.useVeo]);

  // ── Tốc độ đọc thật, hỏi thẳng backend ───────────────────────────────────
  // Không giữ hằng số riêng ở đây nữa: backend tự hiệu chỉnh con số này theo số đo
  // thật của từng giọng sau mỗi lần render, nên hỏi lại mỗi khi user đổi giọng/tốc độ.
  // Hỏi luôn cả thời lượng hook/outro trong cùng lời gọi này. KHÔNG tính lại bằng JS:
  // blackout_question và typewriter_quote có thời lượng ĐỘNG theo độ dài chữ, nên một
  // bản sao công thức ở đây sẽ lệch ngay lần đầu ai đó chỉnh ở Python — đúng loại lệch
  // mà /api/timing-profile được sinh ra để dập (xem docstring của nó).
  const [timing, setTiming] = useState({ wps: FALLBACK_WPS, isLearned: false, hook: null, outro: null });
  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({
      voice: ctx.voice || '', rate: ctx.speechRate || '+0%',
      hook_effect: ctx.hookEffect || '', hook_text: ctx.hookText || '',
      outro_effect: ctx.outroEffect || '', outro_text: ctx.outroText || '',
    });
    fetch(`${API_BASE}/api/timing-profile?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled && d?.words_per_second > 0) {
          setTiming({
            wps: d.words_per_second,
            isLearned: Boolean(d.is_learned),
            hook: d.hook || null,
            outro: d.outro || null,
          });
        }
      })
      .catch(() => { /* backend chưa chạy: dùng FALLBACK_WPS, không làm phiền user */ });
    return () => { cancelled = true; };
  }, [ctx.voice, ctx.speechRate, ctx.hookEffect, ctx.hookText, ctx.outroEffect, ctx.outroText]);

  const sceneSeconds = useMemo(
    () => ctx.scenes.map((s) => estimateSceneSeconds(s, timing.wps)),
    [ctx.scenes, timing.wps],
  );

  // ── Cảnh báo thời lượng ──────────────────────────────────────────────────
  // Đo bằng GIÂY chứ không bằng số từ. Số từ chỉ là đại lượng trung gian, còn thứ user
  // thực sự quan tâm — và thứ quyết định video có bị đọc lê thê hay không — là giây.
  // Không chặn render (LLM đôi khi cố ý viết dài hơn ở cảnh cao trào), chỉ báo để cân nhắc.
  const durationBudget = useMemo(() => {
    const speech = sceneSeconds.reduce((sum, s) => sum + s, 0);
    const total = speech + ctx.scenes.length * SCENE_TRANSITION_OVERHEAD;
    const opt = DURATION_OPTIONS.find((o) => o.value === ctx.targetDuration);
    const targetS = opt ? parseFloat(opt.value) : null;
    const tooLongScenes = sceneSeconds.filter((s) => s > SHOT_MAX_S).length;
    return {
      total,
      targetS,
      tooLongScenes,
      // Ngưỡng 15%: dưới mức đó thì chênh lệch nằm trong sai số ước lượng, cảnh báo chỉ gây nhiễu.
      isOver: targetS != null && total > targetS * 1.15,
      isUnder: targetS != null && total < targetS * 0.7,
      durationLabel: opt ? opt.label : ctx.targetDuration,
    };
  }, [sceneSeconds, ctx.scenes.length, ctx.targetDuration]);

  // ── Bố cục thời gian của video thành phẩm ────────────────────────────────
  // Hook/outro CỘNG THÊM vào tổng thời lượng chứ không lấy bớt từ lời thoại — kịch bản
  // được sinh ra mà không hề biết tới chúng (GenerateScriptRequest không có trường
  // hook/outro nào). Nên chọn "30s" rồi bật cả hook lẫn outro sẽ ra video ~37s.
  // Bảng này để thấy con số đó NGAY LÚC CHỈNH thay vì phát hiện sau khi render xong.
  //
  // Dùng narration_lead chứ không dùng duration của hook: carousel_quote có clip 4.5s
  // nhưng chỉ dời lời thoại 2.35s vì pha Quote cố ý phủ lên đầu Cảnh 1 — lấy duration
  // sẽ cộng dư 2.15 giây không có thật.
  const timeline = useMemo(() => {
    const speech = durationBudget.total;
    const hookLead = timing.hook?.narration_lead ?? 0;
    const outroDur = timing.outro?.duration ?? 0;
    return {
      hookLead,
      speech,
      outroDur,
      total: hookLead + speech + outroDur,
      // Cửa sổ nhạc mở màn khi để "hết Cảnh 1": backend lấy mốc KẾT THÚC cảnh 1 trên
      // timeline, tức đã gồm phần dời do hook (xem actual_intro_bgm_duration ở main.py).
      introBgmAuto: hookLead + (sceneSeconds[0] ?? 0),
    };
  }, [durationBudget.total, timing.hook, timing.outro, sceneSeconds]);

  useEffect(() => {
    if (!ctx.scenes.length) { setCacheStatus(null); return; }
    const controller = new AbortController();
    setProbing(true);
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/cache-probe`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            scenes: ctx.scenes,
            voice: ctx.voice,
            speech_rate: ctx.speechRate,
            speech_pitch: ctx.speechPitch,
            use_breathing: ctx.useBreathing,
            aspect_ratio: ctx.ratio,
            art_style: ctx.style,
            negative_prompt: ctx.negativePrompt || '',
            mode: MODE_MAP[ctx.activeMode],
            visual_source: ctx.visualSource,
            prefer_stock_video: ctx.preferStockVideo,
            use_veo: ctx.useVeo,
          }),
          signal: controller.signal,
        });
        if (!res.ok) throw new Error('probe failed');
        const data = await res.json();
        setCacheStatus(data.scenes || []);
      } catch (err) {
        // Backend tắt hoặc probe lỗi: giấu đèn báo đi thay vì hiện thông tin sai.
        if (err.name !== 'AbortError') setCacheStatus(null);
      } finally {
        setProbing(false);
      }
    }, CACHE_PROBE_DELAY_MS);

    return () => { controller.abort(); clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probeSignature]);

  const updateScene = (index, field, value) => {
    ctx.setScenes(prev => prev.map((s, i) => i === index ? { ...s, [field]: value } : s));
  };
  const removeScene = (index) => {
    ctx.setScenes(prev => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, scene: i + 1 })));
  };
  const addScene = () => {
    ctx.setScenes(prev => [...prev, { scene: prev.length + 1, text: '', image_prompt: '' }]);
  };
  const moveScene = (from, to) => {
    if (to < 0 || to >= ctx.scenes.length) return;
    ctx.setScenes(prev => {
      const arr = [...prev];
      const [item] = arr.splice(from, 1);
      arr.splice(to, 0, item);
      return arr.map((s, i) => ({ ...s, scene: i + 1 }));
    });
  };

  // ── Vi chỉnh: chèn thẻ ngắt nghỉ tại đúng vị trí con trỏ ───────────────────
  const insertBreak = (idx) => {
    const el = textareaRefs.current[idx];
    const current = ctx.scenes[idx]?.text || '';
    const at = el ? el.selectionStart : current.length;
    const next = current.slice(0, at) + BREAK_SNIPPET + current.slice(at);
    updateScene(idx, 'text', next);
    // Trả con trỏ về sau thẻ vừa chèn, nếu không user gõ tiếp sẽ nhảy về đầu ô.
    requestAnimationFrame(() => {
      if (!el) return;
      el.focus();
      el.setSelectionRange(at + BREAK_SNIPPET.length, at + BREAK_SNIPPET.length);
    });
  };

  // ── Nghe thử giọng đọc của riêng 1 cảnh ───────────────────────────────────
  // Bản nghe thử đi qua ĐÚNG bộ tham số mà lúc render sẽ dùng, nên nó nạp luôn vào
  // TTS cache: nghe thử xong, đèn cảnh đó chuyển 🟢 và render không phải sinh lại nữa.
  const stopPreview = useCallback(() => {
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current = null;
    }
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);   // không thu hồi thì blob rò rỉ trong tab
      previewUrlRef.current = null;
    }
    setPreviewIdx(null);
  }, []);

  // Rời trang / bấm Render giữa chừng: đừng để tiếng đọc thử vang tiếp trên nền.
  useEffect(() => stopPreview, [stopPreview]);

  const previewScene = async (idx) => {
    if (previewIdx === idx) { stopPreview(); return; }
    stopPreview();
    ctx.stopAllAudio();
    setPreviewIdx(idx);
    const scene = ctx.scenes[idx];
    try {
      const res = await fetch(`${API_BASE}/api/preview-scene-voice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: scene.text || '',
          voice: ctx.voice,
          speech_rate: ctx.speechRate,
          speech_pitch: ctx.speechPitch,
          speech_rate_modifier: scene.speech_rate_modifier || '0%',
          emotion: scene.emotion || '',
          use_breathing: ctx.useBreathing,
          mode: MODE_MAP[ctx.activeMode],
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Không nghe thử được.');
      }
      const url = URL.createObjectURL(await res.blob());
      previewUrlRef.current = url;
      const audio = new Audio(url);
      previewAudioRef.current = audio;
      audio.addEventListener('ended', stopPreview);
      await audio.play();
      // Nghe thử vừa sinh giọng đúng khoá cache → cập nhật lại đèn cho cảnh này.
      setCacheStatus(prev => prev
        ? prev.map((s, i) => i === idx ? { ...s, audio_cached: true } : s)
        : prev);
    } catch (err) {
      ctx.setErrorMsg(err.message);
      stopPreview();
    }
  };

  // ── Ghi đè thủ công: tải ảnh/video của mình lên cho riêng 1 cảnh ───────────
  const uploadOverride = async (idx, file) => {
    if (!file) return;
    setUploadingIdx(idx);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API_BASE}/api/scene-asset`, { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Tải lên thất bại.');
      ctx.setScenes(prev => prev.map((s, i) => i === idx
        ? { ...s, override_asset: data.asset_id, override_kind: data.kind }
        : s));
    } catch (err) {
      ctx.setErrorMsg(err.message);
    } finally {
      setUploadingIdx(null);
    }
  };

  const clearOverride = useCallback(async (idx) => {
    const assetId = ctx.scenes[idx]?.override_asset;
    ctx.setScenes(prev => prev.map((s, i) => {
      if (i !== idx) return s;
      const { override_asset: _a, override_kind: _k, ...rest } = s;
      return rest;
    }));
    if (assetId) {
      try {
        await fetch(`${API_BASE}/api/scene-asset/${assetId}`, { method: 'DELETE' });
      } catch {
        // File mồ côi trong overrides/ không gây hại — đừng chặn thao tác của user vì nó.
      }
    }
  }, [ctx]);

  const handleImportJson = () => {
    let jsonStr = prompt('Dán mã JSON kịch bản (từ AI) vào đây:');
    if (!jsonStr) return;
    try {
      // Auto-repair JSON từ LLM
      jsonStr = jsonStr.replace(/^```json\s*/i, '').replace(/^```\s*/, '').replace(/```\s*$/i, '').trim();
      jsonStr = jsonStr.replace(/,\s*([\]}])/g, '$1'); // Fix trailing commas
      
      const data = JSON.parse(jsonStr);
      if (data.scenes && Array.isArray(data.scenes)) {
        ctx.setScenes(data.scenes);
        if (data.estimated_duration_s !== undefined) ctx.setEstimatedDurationS(data.estimated_duration_s);
        if (data.hook_text !== undefined) ctx.setHookText(data.hook_text);
        if (data.hook_quote !== undefined) ctx.setHookQuote(data.hook_quote);
        if (data.cta_text !== undefined) ctx.setCtaText(data.cta_text);
        if (data.recommended_bgm) ctx.setBgm(data.recommended_bgm);
        alert('Nhập JSON thành công! Cảnh đã được dàn trang.');
      } else if (Array.isArray(data)) {
        ctx.setScenes(data);
        alert('Nhập mảng JSON thành công! Cảnh đã được dàn trang.');
      } else {
        alert('Lỗi: Cấu trúc JSON không hợp lệ (không tìm thấy scenes).');
      }
    } catch (e) {
      alert('Lỗi parse JSON: ' + e.message);
    }
  };

  // ── Chia lại nhịp ────────────────────────────────────────────────────────
  // Backend chỉ TRẢ VỀ đề xuất, không tự lưu. Việc gộp hai cảnh làm một khiến một
  // image_prompt bị bỏ đi, nên phải cho user xem trước và tự quyết định.
  const [balancing, setBalancing] = useState(false);
  const [balancePreview, setBalancePreview] = useState(null);

  const requestRebalance = async () => {
    setBalancing(true);
    try {
      const res = await fetch(`${API_BASE}/api/rebalance-scenes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenes: ctx.scenes, voice: ctx.voice, speech_rate: ctx.speechRate }),
      });
      if (!res.ok) throw new Error(`Máy chủ trả lỗi ${res.status}`);
      setBalancePreview(await res.json());
    } catch (e) {
      ctx.setErrorMsg(`Không chia lại được nhịp: ${e.message}`);
    } finally {
      setBalancing(false);
    }
  };

  const applyRebalance = () => {
    if (!balancePreview?.scenes?.length) return;
    ctx.setScenes(balancePreview.scenes);
    setBalancePreview(null);
  };

  // Nguồn hình quyết định cảnh sẽ tốn gì khi tạo mới — hiện trong tooltip để user hiểu
  // vì sao đèn đỏ, thay vì chỉ biết là đỏ.
  const SOURCE_LABEL = {
    ai_image: 'ảnh AI',
    stock_video: 'video thật Pexels',
    veo: 'video AI Veo',
    override: 'hình bạn tự tải lên',
  };

  const CacheDot = ({ state, kindLabel, source }) => {
    if (probing || state === undefined) {
      return <span style={{ opacity: 0.4 }} title="Đang kiểm tra bộ nhớ đệm...">⚪ {kindLabel}</span>;
    }
    const via = source ? ` (${SOURCE_LABEL[source] || source})` : '';
    return state
      ? <span style={{ color: 'var(--green)' }} title={`${kindLabel}${via}: đã có sẵn trong bộ nhớ đệm, render lại sẽ dùng ngay.`}>🟢 {kindLabel}</span>
      : <span style={{ color: 'var(--red)' }} title={`${kindLabel}${via}: chưa có — cảnh này sẽ phải tạo mới, tốn thời gian và quota.`}>🔴 {kindLabel}</span>;
  };

  const reusedCount = cacheStatus
    ? cacheStatus.filter(s => s.audio_cached && s.image_cached).length
    : null;

  return (
    <div className="editor-layout">
      <div className="editor-toolbar">
        <button className="btn-outline" onClick={() => ctx.setStep('config')}><RotateCcw size={14} /> Quay lại cài đặt</button>
        <div className="editor-toolbar-info">
          <PenLine size={14} /> {ctx.scenes.length} cảnh
          {reusedCount !== null && (
            <span style={{ marginLeft: 10 }} title="Cảnh đã có đủ giọng đọc + hình trong bộ nhớ đệm sẽ được tái dùng, render gần như tức thì.">
              — 🟢 <strong>{reusedCount}</strong> cảnh tái dùng, 🔴 <strong>{ctx.scenes.length - reusedCount}</strong> cảnh tạo mới
            </span>
          )}
          {ctx.scenes.length > 0 && (
            <span
              style={{ marginLeft: 16, padding: '2px 8px', background: 'var(--surface-hover)', borderRadius: 4, border: '1px solid var(--border)' }}
              title={
                'Hook và Outro CỘNG THÊM vào tổng thời lượng, không lấy bớt từ lời thoại — '
                + 'kịch bản được sinh ra mà không biết tới chúng. Muốn video đúng mốc mong '
                + 'muốn thì chọn thời lượng kịch bản thấp hơn khoảng bằng tổng hook + outro.'
              }
            >
              ⏳ Video <strong>~{timeline.total.toFixed(1)}s</strong>
              {(timeline.hookLead > 0 || timeline.outroDur > 0) && (
                <span style={{ opacity: 0.75, marginLeft: 6 }}>
                  = {timeline.hookLead > 0 && `${timeline.hookLead.toFixed(1)}s hook + `}
                  {timeline.speech.toFixed(1)}s lời
                  {timeline.outroDur > 0 && ` + ${timeline.outroDur.toFixed(1)}s outro`}
                </span>
              )}
            </span>
          )}
          {ctx.scenes.length > 0 && ctx.introBgm && ctx.introBgm !== 'none' && (
            <span
              style={{ marginLeft: 8, padding: '2px 8px', background: 'var(--surface-hover)', borderRadius: 4, border: '1px solid var(--border)' }}
              title={
                'Khoảng thời gian nhạc mở màn chiếm, trước khi chuyển êm sang nhạc nền chính. '
                + 'Chọn "hết Cảnh 1" thì mốc này tự tính từ timeline thật (đã gồm phần dời do hook).'
              }
            >
              🎵 Nhạc mở màn phủ <strong>
                {(ctx.introBgmDuration > 0 ? ctx.introBgmDuration : timeline.introBgmAuto).toFixed(1)}s
              </strong>
              {!(ctx.introBgmDuration > 0) && <span style={{ opacity: 0.75 }}> (hết Cảnh 1)</span>}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn-outline" style={{ borderColor: 'var(--amber)', color: 'var(--amber)', padding: '10px 16px' }} onClick={handleImportJson}>
            <Code size={16} /> Import JSON
          </button>
          <button className="btn-generate" style={{ width: 'auto', padding: '10px 24px', marginTop: 0 }} onClick={handleRenderVideo}>
            <Play size={16} /> Render Video (Bước 2)
          </button>
        </div>
      </div>

      {ctx.errorMsg && <div className="error-box" style={{ marginBottom: 16 }}><AlertTriangle size={16} /> {ctx.errorMsg}</div>}

      {ctx.scriptNotice && (
        <div
          className="warning-box"
          style={{ marginBottom: 16, borderColor: 'var(--green, #22c55e)', color: 'var(--green, #22c55e)' }}
        >
          <span style={{ flex: 1 }}>{ctx.scriptNotice}</span>
          <button className="btn-icon" onClick={() => ctx.setScriptNotice('')} title="Đóng thông báo">
            <X size={14} />
          </button>
        </div>
      )}

      {(durationBudget.isOver || durationBudget.isUnder || durationBudget.tooLongScenes > 0) && (
        <div className="warning-box" style={{ marginBottom: 16 }}>
          <AlertTriangle size={16} />
          <span>
            Kịch bản đọc hết khoảng <strong>{Math.round(durationBudget.total)}s</strong>
            {durationBudget.targetS != null && <> so với mục tiêu {durationBudget.durationLabel}</>}
            {durationBudget.isOver && ' — dài hơn đáng kể, cân nhắc rút gọn lời thoại.'}
            {durationBudget.isUnder && ' — ngắn hơn nhiều, có thể thêm ý cho đủ nhịp.'}
            {durationBudget.tooLongScenes > 0 && (
              <> Có <strong>{durationBudget.tooLongScenes}</strong> cảnh vượt {SHOT_MAX_S}s (xem nhãn đỏ ở từng cảnh) — ảnh đứng yên quá lâu làm nhịp video ì.</>
            )}
            {!timing.isLearned && (
              <em style={{ opacity: 0.75 }}> Ước lượng theo tốc độ đọc mặc định {timing.wps} từ/giây; sau vài lần render sẽ tự khớp với giọng bạn dùng.</em>
            )}
          </span>
          <button
            className="btn-outline"
            onClick={requestRebalance}
            disabled={balancing || !ctx.scenes.length}
            title="Chia lại ranh giới các cảnh cho đều nhịp. KHÔNG sửa một chữ nào trong lời thoại — chỉ di chuyển chỗ ngắt cảnh. Bạn sẽ được xem trước rồi mới quyết định."
            style={{ marginLeft: 12, whiteSpace: 'nowrap', flexShrink: 0 }}
          >
            {balancing ? 'Đang tính...' : 'Chia lại nhịp'}
          </button>
        </div>
      )}

      {balancePreview && (
        <div className="warning-box" style={{ marginBottom: 16, display: 'block', borderColor: 'var(--green, #22c55e)' }}>
          {(() => {
            const { before, after, groups, changed } = balancePreview.report;
            if (!changed) {
              return (
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span>Kịch bản đã chia đều rồi — không có gì cần đổi.</span>
                  <button className="btn-outline" onClick={() => setBalancePreview(null)}>Đóng</button>
                </div>
              );
            }
            return (
              <>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Đề xuất chia lại nhịp</div>
                <table style={{ fontSize: 12, marginBottom: 10, borderSpacing: '14px 2px' }}>
                  <tbody>
                    <tr style={{ opacity: 0.7 }}><td /><td>hiện tại</td><td>sau khi chia</td></tr>
                    <tr><td>Số cảnh</td><td>{before.scenes}</td><td><strong>{after.scenes}</strong></td></tr>
                    <tr><td>Cảnh dài nhất</td><td>{before.longest}s</td><td><strong>{after.longest}s</strong></td></tr>
                    <tr><td>Cảnh ngắn nhất</td><td>{before.shortest}s</td><td><strong>{after.shortest}s</strong></td></tr>
                    <tr><td>Số cảnh lệch nhịp</td><td>{before.off_pace}</td><td><strong>{after.off_pace}</strong></td></tr>
                  </tbody>
                </table>
                <div style={{ maxHeight: 180, overflowY: 'auto', fontSize: 12, marginBottom: 10 }}>
                  {groups.map((g) => (
                    <div key={g.scene} style={{ opacity: g.action === 'keep' ? 0.6 : 1 }}>
                      Cảnh {g.scene}: {g.seconds}s
                      {g.action === 'merge' && <> — gộp lời của cảnh {g.from_scenes.join(' + ')}</>}
                      {g.action === 'split' && <> — tách từ cảnh {g.from_scenes[0]}</>}
                      {g.too_long && <span style={{ color: 'var(--red, #ef4444)' }}> (vẫn dài, câu quá dài không cắt được)</span>}
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 10 }}>
                  Lời thoại giữ nguyên từng chữ. Nhưng khi hai cảnh gộp làm một, ảnh của cảnh bị gộp
                  sẽ không còn được dùng — các cảnh đã tự tải hình lên và thẻ trích dẫn thì luôn giữ nguyên.
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn-outline" onClick={applyRebalance} style={{ borderColor: 'var(--green, #22c55e)', color: 'var(--green, #22c55e)', fontWeight: 700 }}>Áp dụng</button>
                  <button className="btn-outline" onClick={() => setBalancePreview(null)}>Huỷ</button>
                </div>
              </>
            );
          })()}
        </div>
      )}

      <div className="scene-list">
        {ctx.scenes.map((scene, idx) => {
          const status = cacheStatus?.[idx];
          const hasOverride = Boolean(scene.override_asset);
          const bgmOverridden = scene.bgm_volume !== undefined && scene.bgm_volume !== null;

          return (
            <div key={idx} className="scene-card">
              <div className="scene-header">
                <div className="scene-number">Cảnh {idx + 1}</div>
                <div style={{ display: 'flex', gap: 12, fontSize: 11, alignItems: 'center', marginLeft: 12 }}>
                  <CacheDot state={status?.audio_cached} kindLabel="Giọng" />
                  <CacheDot state={status?.image_cached} kindLabel="Hình" source={status?.image_source} />
                  <SceneTiming seconds={sceneSeconds[idx]} />
                </div>
                <div className="scene-actions">
                  <button className="btn-icon" onClick={() => moveScene(idx, idx - 1)} disabled={idx === 0} title="Di chuyển lên"><ChevronUp size={14} /></button>
                  <button className="btn-icon" onClick={() => moveScene(idx, idx + 1)} disabled={idx === ctx.scenes.length - 1} title="Di chuyển xuống"><ChevronDown size={14} /></button>
                  <button className="btn-icon btn-danger" onClick={() => removeScene(idx)} title="Xóa cảnh" disabled={ctx.scenes.length <= 1}><Trash2 size={14} /></button>
                </div>
              </div>
              <div className="scene-fields">
                <div className="scene-field">
                  <label className="field-label" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span>LỜI THOẠI (TIẾNG VIỆT)</span>
                    <button
                      type="button"
                      className="btn-icon"
                      onClick={() => previewScene(idx)}
                      disabled={!scene.text?.trim()}
                      title="Nghe thử giọng đọc của riêng cảnh này (có cả nhịp nghỉ). Bản nghe thử được lưu lại luôn — cảnh sẽ chuyển 🟢 và lúc render không phải sinh lại."
                      style={{ padding: '2px 8px', fontSize: 11, fontWeight: 600, color: previewIdx === idx ? 'var(--amber)' : undefined }}
                    >
                      {previewIdx === idx
                        ? <><Square size={11} style={{ verticalAlign: 'text-bottom' }} /> Dừng</>
                        : <><Headphones size={11} style={{ verticalAlign: 'text-bottom' }} /> Nghe thử</>}
                    </button>
                    <button
                      type="button"
                      className="btn-icon"
                      onClick={() => insertBreak(idx)}
                      title={`Chèn ${BREAK_SNIPPET} tại vị trí con trỏ — ép giọng đọc dừng hẳn 1 giây để ngưng đọng cảm xúc. Sửa số giây trực tiếp trong thẻ (vd time="2.5s"), tối đa 5s.`}
                      style={{ padding: '2px 8px', fontSize: 11, fontWeight: 600 }}
                    >
                      <Pause size={11} style={{ verticalAlign: 'text-bottom' }} /> Chèn nhịp nghỉ
                    </button>
                    {scene.text?.includes('<break') && (
                      <span style={{ fontSize: 11, color: 'var(--amber)', fontWeight: 400 }}>
                        ⏸ Có ngắt nghỉ cảm xúc
                        {ctx.useSinglePassNarration && ' — bị bỏ qua khi bật "Đọc liền mạch cả bài"'}
                      </span>
                    )}
                  </label>
                  <textarea
                    ref={el => { textareaRefs.current[idx] = el; }}
                    className="form-textarea scene-textarea"
                    value={scene.text}
                    onChange={e => updateScene(idx, 'text', e.target.value)}
                    placeholder="Lời thoại sẽ được đọc bằng TTS..."
                    rows={3}
                  />
                </div>

                <div className="scene-field">
                  <label className="field-label" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span>MÔ TẢ HÌNH ẢNH (TIẾNG ANH)</span>
                    <label
                      className="btn-icon"
                      style={{ padding: '2px 8px', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}
                      title="Dùng ảnh/video của bạn thay cho hình AI sinh cho riêng cảnh này (khi AI vẽ hỏng ngón tay, khuôn mặt...). Chấp nhận PNG, JPG, WEBP, MP4, MOV — tối đa 200MB."
                    >
                      <Upload size={11} style={{ verticalAlign: 'text-bottom' }} />
                      {uploadingIdx === idx ? ' Đang tải...' : ' Tải ảnh/video của tôi'}
                      <input
                        type="file"
                        accept=".png,.jpg,.jpeg,.webp,.bmp,.mp4,.mov,.webm"
                        style={{ display: 'none' }}
                        disabled={uploadingIdx === idx}
                        onChange={e => { uploadOverride(idx, e.target.files?.[0]); e.target.value = ''; }}
                      />
                    </label>
                  </label>

                  {hasOverride ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', border: '1px solid var(--green)', borderRadius: 8, marginBottom: 8 }}>
                      {scene.override_kind === 'video' ? (
                        <video src={`${API_BASE}/api/scene-asset/${scene.override_asset}`} style={{ width: 54, height: 54, objectFit: 'cover', borderRadius: 6 }} muted />
                      ) : (
                        <img src={`${API_BASE}/api/scene-asset/${scene.override_asset}`} alt="" style={{ width: 54, height: 54, objectFit: 'cover', borderRadius: 6 }} />
                      )}
                      <span style={{ flex: 1, fontSize: 12, color: 'var(--green)' }}>
                        Đang dùng {scene.override_kind === 'video' ? 'video' : 'ảnh'} của bạn — mô tả bên dưới sẽ bị bỏ qua ở cảnh này.
                      </span>
                      <button className="btn-icon btn-danger" onClick={() => clearOverride(idx)} title="Gỡ, trả cảnh về cho AI sinh hình"><X size={14} /></button>
                    </div>
                  ) : null}

                  <textarea
                    className="form-textarea scene-textarea"
                    value={scene.image_prompt}
                    onChange={e => updateScene(idx, 'image_prompt', e.target.value)}
                    placeholder="Image prompt for AI image generation..."
                    rows={2}
                    disabled={hasOverride}
                    style={hasOverride ? { opacity: 0.5 } : undefined}
                  />
                </div>

                {hasOverride ? null : (() => {
                  const hasClaim = /\d{2,}|\b[A-ZĐ][a-zà-ỹ]+\s[A-ZĐ]/.test(scene.text || "");
                  const warning = (hasClaim && !scene.source_quote) 
                    ? "Cảnh có chứa số liệu hoặc tên riêng nhưng chưa có nguồn gốc (source_quote). Vui lòng kiểm tra lại để tránh AI bịa thông tin." 
                    : null;
                  
                  return warning ? (
                    <div style={{ background: 'var(--surface-hover)', borderLeft: '3px solid var(--amber)', padding: '8px 12px', fontSize: 12, color: 'var(--amber)', marginTop: 8, borderRadius: '0 4px 4px 0' }}>
                      <AlertTriangle size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
                      {warning}
                    </div>
                  ) : null;
                })()}

                <div style={{ marginTop: 12 }}>
                  <button 
                    className="btn-outline" 
                    style={{ width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 6, fontSize: 12, padding: '8px 0', background: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.1)' }}
                    onClick={() => toggleAdvanced(idx)}
                  >
                    <Settings size={14} /> {expandedAdvanced.has(idx) ? 'Ẩn Cài đặt nâng cao' : 'Cài đặt Nâng cao (Nguồn hình, Chuyển cảnh, SFX...)'}
                  </button>
                </div>

                {expandedAdvanced.has(idx) && (
                  <div className="advanced-scene-settings" style={{ animation: 'fadeIn 0.2s', marginTop: 12 }}>
                    <div className="scene-field" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                      <div style={{ flex: 1, minWidth: 160 }}>
                        <label className="field-label"><Film size={12} style={{ verticalAlign: 'middle' }} /> NGUỒN HÌNH (RIÊNG CẢNH NÀY)</label>
                        <select
                          className="form-select form-select-sm"
                          value={scene.visual_source || 'auto'}
                          onChange={e => updateScene(idx, 'visual_source', e.target.value)}
                          disabled={hasOverride}
                        >
                          <option value="auto">Auto (Theo cài đặt chung)</option>
                          <option value="ai_image">Ảnh AI (AI Image)</option>
                          <option value="stock_video">Video thật (Pexels)</option>
                        </select>
                      </div>
                    </div>

                    <div className="scene-field" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12, padding: '10px 12px', background: 'var(--surface)', borderRadius: 6, border: '1px solid var(--border)' }}>
                      <div style={{ flex: 1, minWidth: 140 }}>
                        <label className="field-label">LOẠI CẢNH (TYPE)</label>
                        <select
                          className="form-select form-select-sm"
                          value={scene.scene_type || 'narration'}
                          onChange={e => updateScene(idx, 'scene_type', e.target.value)}
                        >
                          <option value="narration">Kể chuyện (Voice)</option>
                          <option value="quote_card">Quote Card (Không Voice)</option>
                        </select>
                      </div>
                      <div style={{ flex: 1, minWidth: 120 }}>
                        <label className="field-label">NHỊP NGHỈ (ms)</label>
                        <input
                          type="number"
                          className="form-input form-input-sm"
                          value={scene.pause_after_ms || 0}
                          onChange={e => updateScene(idx, 'pause_after_ms', parseInt(e.target.value) || 0)}
                          min={0} max={3000} step={100}
                        />
                      </div>
                      <div style={{ flex: 2, minWidth: 200 }}>
                        <label className="field-label">NGUỒN TRÍCH DẪN (Chống bịa)</label>
                        <input
                          type="text"
                          className="form-input form-input-sm"
                          value={scene.source_quote || ''}
                          onChange={e => updateScene(idx, 'source_quote', e.target.value)}
                          placeholder="Nguyên văn tài liệu gốc..."
                        />
                      </div>
                    </div>

                    <div className="scene-field" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12 }}>
                      <div style={{ flex: 1, minWidth: 160 }}>
                        <label className="field-label"><Film size={12} style={{ verticalAlign: 'middle' }} /> CHUYỂN CẢNH (sang cảnh sau)</label>
                        <select
                          className="form-select form-select-sm"
                          value={scene.transition || 'crossfade'}
                          onChange={e => updateScene(idx, 'transition', e.target.value)}
                        >
                          {TRANSITIONS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                      </div>
                      <div style={{ flex: 1, minWidth: 200 }}>
                        <label className="field-label"><Volume2 size={12} style={{ verticalAlign: 'middle' }} /> TIẾNG ĐỘNG (SFX) CẢNH NÀY</label>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center', width: '100%' }}>
                          <select
                            className="form-select form-select-sm"
                            value={scene.sfx || ''}
                            onChange={e => {
                              const val = e.target.value;
                              updateScene(idx, 'sfx', val);
                              if (val) {
                                const audio = new Audio(`${API_BASE}/api/preview/sfx/${val}`);
                                const vol = scene.sfxVolume !== undefined ? scene.sfxVolume : 100;
                                audio.volume = (ctx.sfxVolume ? (ctx.sfxVolume / 100) : 0.5) * (vol / 100);
                                audio.play().catch(err => console.error("SFX preview error:", err));
                              }
                            }}
                            style={{ flex: 1, minWidth: 0 }}
                          >
                            <optgroup label="SFX Mặc định">
                              {SFX_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                            </optgroup>
                            {customSfxList.length > 0 && (
                              <optgroup label="SFX Tự Tải Lên">
                                {customSfxList.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                              </optgroup>
                            )}
                          </select>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4, width: 80, flexShrink: 0 }}>
                            <span style={{ fontSize: 10, color: 'gray' }}>Vol</span>
                            <input
                              type="range"
                              className="vol-slider"
                              min="0"
                              max="200"
                              value={scene.sfxVolume !== undefined ? scene.sfxVolume : 100}
                              onChange={e => {
                                const vol = Number(e.target.value);
                                updateScene(idx, 'sfxVolume', vol);
                                if (scene.sfx) {
                                  const audio = new Audio(`${API_BASE}/api/preview/sfx/${scene.sfx}`);
                                  audio.volume = (ctx.sfxVolume ? (ctx.sfxVolume / 100) : 0.5) * (vol / 100);
                                  audio.play().catch(err => console.error("SFX preview error:", err));
                                }
                              }}
                              style={{ flex: 1, minWidth: 0 }}
                              title={`Âm lượng SFX cảnh này: ${scene.sfxVolume !== undefined ? scene.sfxVolume : 100}%`}
                            />
                          </div>
                          <label className="btn btn-sm btn-outline-secondary" style={{ padding: '2px 6px', fontSize: 11, display: 'flex', alignItems: 'center', gap: 2, cursor: 'pointer' }} title="Tải SFX của riêng bạn">
                            <span>➕</span>
                            <input type="file" accept=".wav,.mp3" style={{ display: 'none' }} onChange={handleUploadSfx} />
                          </label>
                        </div>
                      </div>
                      <div style={{ flex: 1, minWidth: 200 }}>
                        <label className="field-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <Music size={12} style={{ verticalAlign: 'middle' }} />
                          <span>NHẠC NỀN CẢNH NÀY</span>
                          <input
                            type="checkbox"
                            checked={bgmOverridden}
                            title="Chỉnh riêng âm lượng nhạc nền cho cảnh này (vd: cảnh nói thầm giảm còn 5%, cảnh kết đẩy lên 50%). Bỏ chọn = theo mức chung của cả video."
                            onChange={e => updateScene(idx, 'bgm_volume', e.target.checked ? ctx.bgmVolume / 100 : undefined)}
                          />
                        </label>
                        {bgmOverridden ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <input
                              type="range" min="0" max="100" step="5"
                              className="form-range"
                              style={{ flex: 1 }}
                              value={Math.round(scene.bgm_volume * 100)}
                              onChange={e => updateScene(idx, 'bgm_volume', Number(e.target.value) / 100)}
                            />
                            <span style={{ fontSize: 12, minWidth: 34, textAlign: 'right' }}>{Math.round(scene.bgm_volume * 100)}%</span>
                          </div>
                        ) : (
                          <div style={{ fontSize: 12, color: 'var(--text-muted)', paddingTop: 6 }}>
                            Theo mức chung ({ctx.bgmVolume}%)
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <button className="btn-add-scene" onClick={addScene}><Plus size={16} /> Thêm cảnh mới</button>
    </div>
  );
}
