import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RotateCcw, PenLine, Play, AlertTriangle, Clipboard, Plus, Code } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from '../store';
import { API_BASE, MODE_MAP, DURATION_OPTIONS } from '../constants';
import { validateImportPayload, normalizeImportPayload } from '../lib/sharedSchema';
import { toast } from '../lib/toast.jsx';
import SceneList from './SceneList';

const CACHE_PROBE_DELAY_MS = 600;
const BREAK_SNIPPET = '<break time="1s"/>';
const FALLBACK_WPS = 3.0;
const SHOT_MIN_S = 2.5;
const SHOT_MAX_S = 6.5;
const SCENE_TRANSITION_OVERHEAD = 0.5;

const BREAK_TAG_RE = /<break[^>]*>/gi;
const BREAK_TIME_RE = /<break[^>]*time\s*=\s*"([\d.]+)\s*(ms|s)"[^>]*>/gi;

const countWords = (text) => {
  const cleaned = (text || '').replace(BREAK_TAG_RE, ' ').trim();
  return cleaned ? cleaned.split(/\s+/).length : 0;
};

const breakSeconds = (text) => {
  let total = 0;
  for (const [, value, unit] of (text || '').matchAll(BREAK_TIME_RE)) {
    const v = parseFloat(value);
    if (!Number.isNaN(v)) total += unit.toLowerCase() === 'ms' ? v / 1000 : v;
  }
  return total;
};

const estimateSceneSeconds = (scene, wps) => {
  const words = countWords(scene?.text);
  const speech = words > 0 ? words / (wps || FALLBACK_WPS) : 0;
  return speech + breakSeconds(scene?.text) + (scene?.pause_after_ms || 0) / 1000;
};

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
    negativePrompt: s.negativePrompt, apiKey: s.apiKey, useVeo: s.useVeo,
    ctaText: s.ctaText, setCtaText: s.setCtaText,
    characterDescription: s.characterDescription,
    useFrameChaining: s.useFrameChaining, useKenBurns: s.useKenBurns, useBeatSync: s.useBeatSync,
    useVeoAmbientAudio: s.useVeoAmbientAudio, useGpuEncode: s.useGpuEncode,
    hookZoomBoost: s.hookZoomBoost, usePatternInterrupt: s.usePatternInterrupt,
    useSfx: s.useSfx, sfxVolume: s.sfxVolume, subtitleStyle: s.subtitleStyle, colorGrading: s.colorGrading,
    watermarkText: s.watermarkText, watermarkLogo: s.watermarkLogo,
    coverImageSessionId: s.coverImageSessionId, coverImagePosition: s.coverImagePosition,
    useAudioDucking: s.useAudioDucking,
    useBreathing: s.useBreathing, hookEffect: s.hookEffect, hookQuote: s.hookQuote, setHookQuote: s.setHookQuote,
    hookText: s.hookText, setHookText: s.setHookText,
    outroText: s.outroText, setOutroText: s.setOutroText,
    preferStockVideo: s.preferStockVideo, visualSource: s.visualSource,
    useSinglePassNarration: s.useSinglePassNarration,
    hookReelSfx: s.hookReelSfx,
    hookSfxVolume: s.hookSfxVolume,
    outroEffect: s.outroEffect, outroReelSfx: s.outroReelSfx, outroSfxVolume: s.outroSfxVolume,
    subscribeToJob: s.subscribeToJob, stopAllAudio: s.stopAllAudio,
    estimatedDurationS: s.estimatedDurationS, setEstimatedDurationS: s.setEstimatedDurationS,
    scriptNotice: s.scriptNotice, setScriptNotice: s.setScriptNotice,
    hookVariants: s.hookVariants, scriptReview: s.scriptReview, narrationTone: s.narrationTone,
    useFastAssembly: s.useFastAssembly, contentNiche: s.contentNiche,
  })));

  const [cacheStatus, setCacheStatus] = useState(null);
  const [probing, setProbing] = useState(false);
  const [expandedAdvanced, setExpandedAdvanced] = useState(new Set());
  const [collapsedScenes, setCollapsedScenes] = useState(new Set());
  const [isDragging, setIsDragging] = useState(false);

  const validCollapsedCount = [...collapsedScenes].filter(i => i < ctx.scenes.length).length;
  const isAllCollapsed = ctx.scenes.length > 0 && validCollapsedCount === ctx.scenes.length;

  const toggleCollapseAll = () => {
    if (isAllCollapsed) {
      setCollapsedScenes(new Set());
    } else {
      setCollapsedScenes(new Set(ctx.scenes.map((_, i) => i)));
    }
  };

  const toggleSceneCollapse = (idx) => {
    setCollapsedScenes(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const [customSfxList, setCustomSfxList] = useState([]);

  useEffect(() => {
    fetch(`${API_BASE}/api/sfx-list`)
      .then(res => res.json())
      .then(data => setCustomSfxList(data.sfx_list || []))
      .catch(err => toast("Không tải được danh sách SFX: " + err.message, { type: 'error' }));
  }, []);

  const handleUploadSfx = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) return toast("File quá lớn! Tối đa 10MB.", { type: 'error' });
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/api/upload-sfx`, { method: 'POST', body: formData });
      const data = await res.json();
      if (res.ok) {
        setCustomSfxList(prev => [...prev, { value: data.filename, label: data.label }]);
        toast("Upload thành công!", { type: 'success' });
      } else {
        toast(data.detail || "Upload thất bại.", { type: 'error' });
      }
    } catch (err) {
      toast("Lỗi kết nối: " + err.message, { type: 'error' });
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
  const [previewIdx, setPreviewIdx] = useState(null);
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
        use_veo: ctx.useVeo, cta_text: ctx.ctaText || undefined,
        character_description: ctx.characterDescription || undefined, use_frame_chaining: ctx.useFrameChaining,
        use_ken_burns: ctx.useKenBurns, use_beat_sync: ctx.useBeatSync, use_veo_ambient_audio: ctx.useVeoAmbientAudio,
        use_gpu_encode: ctx.useGpuEncode, hook_zoom_boost: ctx.hookZoomBoost, use_pattern_interrupt: ctx.usePatternInterrupt,
        use_sfx: ctx.useSfx, sfx_volume: ctx.sfxVolume / 100,
        use_audio_ducking: ctx.useAudioDucking, narration_tone: ctx.narrationTone,
        subtitle_style: ctx.subtitleStyle, color_grading: ctx.colorGrading, watermark_text: ctx.watermarkText || undefined,
        watermark_logo: ctx.watermarkLogo ? "logo_ntd" : undefined,
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
        use_fast_assembly: ctx.useFastAssembly,
        // ── BookTok import: content_niche được normalizeImportPayload() map từ niche_category ──
        // Bước 3 (2026-08-15): truyền content_niche vào request để resolve_blueprint() chọn
        // hiệu ứng phù hợp thể loại thay vì fallback default.
        content_niche: ctx.contentNiche || undefined,
      };
      const res = await fetch(`${API_BASE}/api/render-video`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi server');
      }
      const data = await res.json();
      ctx.subscribeToJob(data.job_id);
    } catch (err) {
      ctx.setStatus('error');
      ctx.setErrorMsg(err.message);
    }
  };

  const probeSignature = useMemo(() => JSON.stringify([
    ctx.scenes.map(s => [s.text, s.image_prompt, s.emotion, s.speech_rate_modifier, s.override_asset]),
    ctx.voice, ctx.speechRate, ctx.speechPitch, ctx.useBreathing,
    ctx.ratio, ctx.style, ctx.negativePrompt, MODE_MAP[ctx.activeMode],
    ctx.visualSource, ctx.preferStockVideo, ctx.useVeo,
    ctx.contentNiche,  // ← BookTok import: content_niche ảnh hưởng resolve_blueprint timing
  ]), [ctx.scenes, ctx.voice, ctx.speechRate, ctx.speechPitch, ctx.useBreathing,
      ctx.ratio, ctx.style, ctx.negativePrompt, ctx.activeMode, ctx.visualSource,
      ctx.preferStockVideo, ctx.useVeo, ctx.contentNiche]);

  const [timing, setTiming] = useState({ wps: FALLBACK_WPS, isLearned: false, hook: null, outro: null });
  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({
      voice: ctx.voice || '', rate: ctx.speechRate || '+0%',
      hook_effect: ctx.hookEffect || '', hook_text: ctx.hookText || '',
      outro_effect: ctx.outroEffect || '', outro_text: ctx.outroText || '',
      cta_text: ctx.ctaText || '',
    });
    fetch(`${API_BASE}/api/timing-profile?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled && d?.words_per_second > 0) {
          setTiming({ wps: d.words_per_second, isLearned: Boolean(d.is_learned), hook: d.hook || null, outro: d.outro || null });
        }
      })
      .catch(() => { /* backend chưa chạy: dùng FALLBACK_WPS */ });
    return () => { cancelled = true; };
  }, [ctx.voice, ctx.speechRate, ctx.hookEffect, ctx.hookText, ctx.outroEffect, ctx.outroText, ctx.ctaText]);

  const sceneSeconds = useMemo(
    () => ctx.scenes.map((s) => estimateSceneSeconds(s, timing.wps)),
    [ctx.scenes, timing.wps],
  );

  const durationBudget = useMemo(() => {
    const speech = sceneSeconds.reduce((sum, s) => sum + s, 0);
    const total = speech + ctx.scenes.length * SCENE_TRANSITION_OVERHEAD;
    const opt = DURATION_OPTIONS.find((o) => o.value === ctx.targetDuration);
    const targetS = opt ? parseFloat(opt.value) : null;
    const tooLongScenes = sceneSeconds.filter((s) => s > SHOT_MAX_S).length;
    return {
      total, targetS, tooLongScenes,
      isOver: targetS != null && total > targetS * 1.15,
      isUnder: targetS != null && total < targetS * 0.7,
      durationLabel: opt ? opt.label : ctx.targetDuration,
    };
  }, [sceneSeconds, ctx.scenes.length, ctx.targetDuration]);

  const timeline = useMemo(() => {
    const speech = durationBudget.total;
    const hookLead = timing.hook?.narration_lead ?? 0;
    const outroDur = timing.outro?.duration ?? 0;
    return {
      hookLead, speech, outroDur,
      total: hookLead + speech + outroDur,
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
            scenes: ctx.scenes, voice: ctx.voice,
            speech_rate: ctx.speechRate, speech_pitch: ctx.speechPitch,
            use_breathing: ctx.useBreathing,
            aspect_ratio: ctx.ratio, art_style: ctx.style,
            negative_prompt: ctx.negativePrompt || '',
            mode: MODE_MAP[ctx.activeMode],
            visual_source: ctx.visualSource, prefer_stock_video: ctx.preferStockVideo,
            use_veo: ctx.useVeo,
          }),
          signal: controller.signal,
        });
        if (!res.ok) throw new Error('probe failed');
        const data = await res.json();
        setCacheStatus(data.scenes || []);
      } catch (err) {
        if (err.name !== 'AbortError') setCacheStatus(null);
      } finally {
        setProbing(false);
      }
    }, CACHE_PROBE_DELAY_MS);
    return () => { controller.abort(); clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probeSignature]);

  const updateScene = useCallback((index, field, value) => {
    ctx.setScenes(prev => prev.map((s, i) => i === index ? { ...s, [field]: value } : s));
  }, [ctx]);

  const removeScene = useCallback((index) => {
    ctx.setScenes(prev => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, scene: i + 1 })));
  }, [ctx]);

  const moveScene = useCallback((from, to) => {
    if (to < 0 || to >= ctx.scenes.length) return;
    ctx.setScenes(prev => {
      const arr = [...prev];
      const [item] = arr.splice(from, 1);
      arr.splice(to, 0, item);
      return arr.map((s, i) => ({ ...s, scene: i + 1 }));
    });
  }, [ctx]);

  const insertBreak = useCallback((idx, textareaEl) => {
    const current = ctx.scenes[idx]?.text || '';
    const at = textareaEl ? textareaEl.selectionStart : current.length;
    const next = current.slice(0, at) + BREAK_SNIPPET + current.slice(at);
    updateScene(idx, 'text', next);
    requestAnimationFrame(() => {
      if (!textareaEl) return;
      textareaEl.focus();
      textareaEl.setSelectionRange(at + BREAK_SNIPPET.length, at + BREAK_SNIPPET.length);
    });
  }, [ctx.scenes, updateScene]);

  const stopPreview = useCallback(() => {
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current = null;
    }
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setPreviewIdx(null);
  }, []);

  useEffect(() => stopPreview, [stopPreview]);

  const previewScene = useCallback(async (idx) => {
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
          text: scene.text || '', voice: ctx.voice,
          speech_rate: ctx.speechRate, speech_pitch: ctx.speechPitch,
          speech_rate_modifier: scene.speech_rate_modifier || '0%',
          emotion: scene.emotion || '', use_breathing: ctx.useBreathing,
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
      setCacheStatus(prev => prev
        ? prev.map((s, i) => i === idx ? { ...s, audio_cached: true } : s)
        : prev);
    } catch (err) {
      ctx.setErrorMsg(err.message);
      stopPreview();
    }
  }, [previewIdx, ctx, stopPreview, updateScene]);

  const uploadOverride = useCallback(async (idx, file) => {
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
  }, [ctx]);

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
        // File mồ côi trong overrides/ không gây hại
      }
    }
  }, [ctx]);

  // ── Rebalance ──────────────────────────────────────────────────────────
  const [balancing, setBalancing] = useState(false);
  const [balancePreview, setBalancePreview] = useState(null);

  const requestRebalance = useCallback(async () => {
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
  }, [ctx]);

  const applyRebalance = useCallback(() => {
    if (!balancePreview?.scenes?.length) return;
    ctx.setScenes(balancePreview.scenes);
    setBalancePreview(null);
  }, [balancePreview, ctx]);

  // ── Full-mode script editor ─────────────────────────────────────────────
  const [fullMode, setFullMode] = useState(false);
  const [fullText, setFullText] = useState('');
  const [resplitting, setResplitting] = useState(false);
  const [resplitPreview, setResplitPreview] = useState(null);
  const [keepBoundaries, setKeepBoundaries] = useState(false);
  const [fullPlaying, setFullPlaying] = useState(false);
  const [fullLoading, setFullLoading] = useState(false);
  const [fullAt, setFullAt] = useState(null);
  const [fullScope, setFullScope] = useState(null);
  const [fullProgress, setFullProgress] = useState(null);
  const fullAudioRef = useRef(null);
  const fullUrlRef = useRef(null);

  const scenesToText = useCallback(
    (scenes) => scenes.map(s => (s.text || '').trim()).filter(Boolean).join('\n\n'),
    []
  );

  const openFullMode = () => {
    setFullText(scenesToText(ctx.scenes));
    setResplitPreview(null);
    setFullMode(true);
  };

  const coSuaChuaLuu = fullMode && fullText.trim() !== scenesToText(ctx.scenes).trim();

  const closeFullMode = () => {
    if (coSuaChuaLuu && !window.confirm(
      'Bạn đã sửa lời thoại nhưng chưa chia lại thành cảnh.\n\nĐóng bây giờ sẽ mất toàn bộ phần sửa. Vẫn đóng?'
    )) return;
    setFullMode(false);
    setResplitPreview(null);
    stopFullPreview();
  };

  const fullPollRef = useRef(null);

  const stopFullPreview = useCallback(() => {
    if (fullPollRef.current) { clearInterval(fullPollRef.current); fullPollRef.current = null; }
    if (fullAudioRef.current) { fullAudioRef.current.pause(); fullAudioRef.current = null; }
    if (fullUrlRef.current) { URL.revokeObjectURL(fullUrlRef.current); fullUrlRef.current = null; }
    setFullPlaying(false);
    setFullLoading(false);
    setFullAt(null);
    setFullProgress(null);
  }, []);

  useEffect(() => stopFullPreview, [stopFullPreview]);

  const phatBanDoc = async (audioUrl, ranges) => {
    const audio = new Audio(`${API_BASE}${audioUrl}`);
    fullAudioRef.current = audio;
    audio.addEventListener('timeupdate', () => {
      const t = audio.currentTime;
      const i = (ranges || []).findIndex(r => r && t >= r[0] && t <= r[1]);
      setFullAt(i >= 0 ? i : null);
    });
    audio.addEventListener('ended', () => { setFullPlaying(false); setFullAt(null); });
    await audio.play();
    setFullPlaying(true);
  };

  const previewFullScript = async () => {
    if (fullPlaying || fullLoading) { stopFullPreview(); return; }
    stopFullPreview();
    ctx.stopAllAudio?.();
    setFullLoading(true);
    setFullProgress({ percent: 0, message: 'Đang gửi yêu cầu...' });
    try {
      const res = await fetch(`${API_BASE}/api/preview-full-script`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenes: ctx.scenes, voice: ctx.voice,
          speech_rate: ctx.speechRate, speech_pitch: ctx.speechPitch,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Máy chủ trả lỗi ${res.status}`);
      if (data.estimate) setFullProgress({ percent: 0, message: data.estimate });

      fullPollRef.current = setInterval(async () => {
        try {
          const r = await fetch(`${API_BASE}/api/job-status/${data.job_id}`);
          if (!r.ok) return;
          const job = await r.json();
          setFullProgress({ percent: job.progress || 0, message: job.message || '' });
          if (job.status === 'error') {
            clearInterval(fullPollRef.current); fullPollRef.current = null;
            setFullLoading(false); setFullProgress(null);
            ctx.setErrorMsg(job.error || 'Không đọc thử được cả bài.');
          } else if (job.status === 'done' && job.audio_url) {
            clearInterval(fullPollRef.current); fullPollRef.current = null;
            setFullLoading(false); setFullProgress(null);
            setFullScope(job.cache_scope || null);
            if (job.cache_scope === 'per_scene') {
              setCacheStatus(prev => prev ? prev.map(s => ({ ...s, audio_cached: true })) : prev);
            }
            await phatBanDoc(job.audio_url, job.scene_ranges);
          }
        } catch { /* mạng chớp nháy */ }
      }, 1500);
    } catch (e) {
      stopFullPreview();
      ctx.setErrorMsg(`Không đọc thử được cả bài: ${e.message}`);
    }
  };

  const requestResplit = async () => {
    setResplitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/resplit-script`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_text: fullText, scenes: ctx.scenes,
          voice: ctx.voice, speech_rate: ctx.speechRate,
          rebalance: !keepBoundaries,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Máy chủ trả lỗi ${res.status}`);
      setResplitPreview(data);
    } catch (e) {
      ctx.setErrorMsg(`Không chia lại được kịch bản: ${e.message}`);
    } finally {
      setResplitting(false);
    }
  };

  const applyResplit = () => {
    if (!resplitPreview?.scenes?.length) return;
    ctx.setScenes(resplitPreview.scenes);
    setResplitPreview(null);
    setFullMode(false);
    stopFullPreview();
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes('Files')) setIsDragging(true);
  };
  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };
  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && (file.type === "application/json" || file.name.endsWith(".json"))) {
      const reader = new FileReader();
      reader.onload = (ev) => processJsonString(ev.target.result);
      reader.readAsText(file);
    } else if (file) {
      toast("Vui lòng thả file JSON hợp lệ.", { type: 'warning' });
    }
  };

  const processJsonString = (jsonStr) => {
    try {
      jsonStr = jsonStr.replace(/^```json\s*/i, '').replace(/^```\s*/, '').replace(/```\s*$/i, '').trim();
      jsonStr = jsonStr.replace(/,\s*([\]}])/g, '$1');
      const data = JSON.parse(jsonStr);
      if (data.scenes && Array.isArray(data.scenes)) {
        const normalized = normalizeImportPayload(data);
        const warnings = validateImportPayload(data);
        if (warnings.length > 0) {
          const proceed = window.confirm(
            `Có ${warnings.length} cảnh báo khi nhập JSON:\n\n${warnings.slice(0, 8).join('\n')}` +
            (warnings.length > 8 ? `\n... và ${warnings.length - 8} cảnh báo khác.` : '') +
            `\n\nBấm OK để tiếp tục, hoặc Cancel để hủy.`
          );
          if (!proceed) return;
        }
        ctx.setScenes(normalized.scenes);
        if (normalized.estimated_duration_s !== undefined) ctx.setEstimatedDurationS(normalized.estimated_duration_s);
        if (data.hook_text !== undefined) ctx.setHookText(data.hook_text);
        if (data.hook_quote !== undefined) ctx.setHookQuote(data.hook_quote);
        if (data.cta_text !== undefined) ctx.setCtaText(data.cta_text);
        if (data.recommended_bgm) ctx.setBgm(data.recommended_bgm);
        if (data.outro_text !== undefined) ctx.setOutroText(data.outro_text);
        toast(`Nhập JSON thành công! ${normalized.scenes.length} cảnh đã được dàn trang.`, { type: 'success' });
      } else if (Array.isArray(data)) {
        const normalized = normalizeImportPayload(data);
        const warnings = validateImportPayload({ scenes: normalized.scenes });
        if (warnings.length > 0) {
          const proceed = window.confirm(`Có ${warnings.length} cảnh báo.\n\nTiếp tục?`);
          if (!proceed) return;
        }
        ctx.setScenes(normalized.scenes);
        toast(`Nhập mảng JSON thành công! ${normalized.scenes.length} cảnh.`, { type: 'success' });
      } else {
        toast('Lỗi: Cấu trúc JSON không hợp lệ.', { type: 'error' });
      }
    } catch (err) {
      toast('Lỗi parse JSON: ' + err.message, { type: 'error' });
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div
      className="editor-layout"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{ position: 'relative' }}
    >
      {isDragging && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(34, 197, 94, 0.1)',
          border: '2px dashed var(--green)',
          zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          backdropFilter: 'blur(2px)',
          borderRadius: 8,
          pointerEvents: 'none'
        }}>
          <div style={{
            background: 'var(--surface)', padding: '24px 48px',
            borderRadius: 12, boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            color: 'var(--green)', fontSize: 24, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 12
          }}>
            <Code size={32} /> Thả file JSON vào đây để nạp kịch bản
          </div>
        </div>
      )}

      {/* ── Render button (lives here so it can call handleRenderVideo directly) ── */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end' }}>
        <button type="button" className="btn-generate" style={{ width: 'auto', padding: '10px 24px' }} onClick={handleRenderVideo}>
          <Play size={16} /> Render Video (Bước 2)
        </button>
      </div>

      <SceneList
        cacheStatus={cacheStatus}
        collapsedScenes={collapsedScenes}
        expandedAdvanced={expandedAdvanced}
        previewIdx={previewIdx}
        uploadingIdx={uploadingIdx}
        customSfxList={customSfxList}
        sceneSeconds={sceneSeconds}
        timing={timing}
        durationBudget={durationBudget}
        timeline={timeline}
        probing={probing}
        balancing={balancing}
        balancePreview={balancePreview}
        resplitting={resplitting}
        resplitPreview={resplitPreview}
        fullMode={fullMode}
        fullText={fullText}
        fullLoading={fullLoading}
        fullPlaying={fullPlaying}
        fullAt={fullAt}
        fullProgress={fullProgress}
        fullScope={fullScope}
        keepBoundaries={keepBoundaries}
        ctx={ctx}
        onScenesChange={ctx.setScenes}
        onToggleCollapse={toggleSceneCollapse}
        onToggleAdvanced={toggleAdvanced}
        onUpdate={updateScene}
        onRemove={removeScene}
        onMoveUp={(idx) => moveScene(idx, idx - 1)}
        onMoveDown={(idx) => moveScene(idx, idx + 1)}
        onPreview={previewScene}
        onStopPreview={stopPreview}
        onInsertBreak={insertBreak}
        onUploadOverride={uploadOverride}
        onClearOverride={clearOverride}
        onToggleCollapseAll={toggleCollapseAll}
        isAllCollapsed={isAllCollapsed}
        onOpenFullMode={openFullMode}
        onCloseFullMode={closeFullMode}
        coSuaChuaLuu={coSuaChuaLuu}
        onFullTextChange={(t) => { setFullText(t); if (resplitPreview) setResplitPreview(null); }}
        onFullPlay={previewFullScript}
        onSetKeepBoundaries={setKeepBoundaries}
        onRequestResplit={requestResplit}
        onApplyResplit={applyResplit}
        onRequestRebalance={requestRebalance}
        onApplyRebalance={applyRebalance}
        onSetBalancePreview={setBalancePreview}
        onSetResplitPreview={setResplitPreview}
        onUploadSfx={handleUploadSfx}
      />
    </div>
  );
}
