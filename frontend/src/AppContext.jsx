import React, { createContext, useState, useContext, useRef, useCallback } from 'react';
import { STYLES, VOICES, API_BASE, MODE_MAP, DURATION_OPTIONS } from './constants';

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  const [step, setStep] = useState('config');
  
  const [activeMode, setActiveMode] = useState('storyteller');
  const [topic, setTopic] = useState('');
  const [scriptText, setScriptText] = useState('');
  const [ratio, setRatio] = useState('9:16');
  const [numScenes, setNumScenes] = useState(6);
  const [targetDuration, setTargetDuration] = useState('30s');
  const [narrationTone, setNarrationTone] = useState('viral');
  const [voice, setVoice] = useState('vi-VN-NamMinhNeural');
  const [style, setStyle] = useState(STYLES[0].value);
  const [bgm, setBgm] = useState('auto');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  
  const [useVeo, setUseVeo] = useState(false);
  const [useAnimatedCaptions, setUseAnimatedCaptions] = useState(true);
  const [ctaText, setCtaText] = useState('');
  const [speechRate, setSpeechRate] = useState('+0%');
  const [speechPitch, setSpeechPitch] = useState('+0Hz');
  const [bgmVolume, setBgmVolume] = useState(15);
  const [negativePrompt, setNegativePrompt] = useState('');
  const [characterDescription, setCharacterDescription] = useState('');
  const [useFrameChaining, setUseFrameChaining] = useState(true);
  const [useKenBurns, setUseKenBurns] = useState(true);
  const [useBeatSync, setUseBeatSync] = useState(false);
  const [useVeoAmbientAudio, setUseVeoAmbientAudio] = useState(true);
  const [useGpuEncode, setUseGpuEncode] = useState(true);
  const [hookZoomBoost, setHookZoomBoost] = useState(true);
  const [useSfx, setUseSfx] = useState(true);
  const [sfxVolume, setSfxVolume] = useState(50);
  const [subtitleStyle, setSubtitleStyle] = useState('karaoke_bold');
  const [colorGrading, setColorGrading] = useState('warm_cinematic');
  const [watermarkText, setWatermarkText] = useState('');  
  const [hookText, setHookText] = useState('');
  const [uploadSessionId, setUploadSessionId] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [coverImageSessionId, setCoverImageSessionId] = useState(null);
  const [coverImageName, setCoverImageName] = useState('');
  const [coverImageLoading, setCoverImageLoading] = useState(false);
  const [coverImagePosition, setCoverImagePosition] = useState('start');
  const [useBreathing, setUseBreathing] = useState(false);
  const [hookEffect, setHookEffect] = useState('word_by_word');
  
  const [scenes, setScenes] = useState([]);
  const [scriptLoading, setScriptLoading] = useState(false);
  
  const [status, setStatus] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [jobMessage, setJobMessage] = useState('');
  const [progressLog, setProgressLog] = useState([]);
  const [videoUrl, setVideoUrl] = useState(null);
  const [srtUrl, setSrtUrl] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  const audioRef = useRef(null);

  const playPreview = useCallback((type, id) => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    const audioUrl = `${API_BASE}/api/preview/${type}/${id}`;
    const audio = new Audio(audioUrl);
    if (type === 'bgm') {
      audio.volume = bgmVolume / 100;
    }
    audio.play().catch(e => alert("Lỗi phát audio: " + e.message + "\n(Vui lòng tương tác với trang web trước khi nghe hoặc kiểm tra kết nối tới Backend)"));
    audioRef.current = audio;
  }, [bgmVolume]);

  const handleReset = () => {
    setStep('config');
    setScenes([]);
    setStatus('idle');
    setProgress(0);
    setJobMessage('');
    setProgressLog([]);
    setVideoUrl(null);
    setSrtUrl(null);
    setErrorMsg('');
    setUploadSessionId(null);
    setUploadedFiles([]);
    setCoverImageSessionId(null);
    setCoverImageName('');
  };

  const needsUpload = activeMode === 'img2vid' || activeMode === 'slideshow';
  const needsScript = activeMode === 'script';
  const needsTopic = !needsUpload && !needsScript;

  const applyPreset = useCallback((preset) => {
    if (!preset) return;
    if (preset.aspect_ratio) setRatio(preset.aspect_ratio);
    if (preset.voice) setVoice(preset.voice);
    if (preset.art_style) setStyle(preset.art_style);
    if (preset.bgm_track !== undefined) setBgm(preset.bgm_track === null ? 'none' : preset.bgm_track);
    if (preset.target_duration) setTargetDuration(preset.target_duration);
    if (preset.narration_tone) setNarrationTone(preset.narration_tone);
    if (preset.speech_rate) setSpeechRate(preset.speech_rate);
    if (preset.speech_pitch) setSpeechPitch(preset.speech_pitch);
    if (preset.bgm_volume !== undefined) setBgmVolume(preset.bgm_volume);
    if (preset.subtitle_style) setSubtitleStyle(preset.subtitle_style);
    if (preset.color_grading) setColorGrading(preset.color_grading);
    if (preset.use_sfx !== undefined) setUseSfx(preset.use_sfx);
    if (preset.sfx_volume !== undefined) setSfxVolume(preset.sfx_volume);
  }, []);

  const contextValue = {
    step, setStep, activeMode, setActiveMode, topic, setTopic, scriptText, setScriptText,
    ratio, setRatio, numScenes, setNumScenes, targetDuration, setTargetDuration,
    narrationTone, setNarrationTone, voice, setVoice, style, setStyle,
    bgm, setBgm, apiKey, setApiKey, showApiKey, setShowApiKey,
    useVeo, setUseVeo, useAnimatedCaptions, setUseAnimatedCaptions, ctaText, setCtaText,
    speechRate, setSpeechRate, speechPitch, setSpeechPitch, bgmVolume, setBgmVolume,
    negativePrompt, setNegativePrompt, characterDescription, setCharacterDescription,
    useFrameChaining, setUseFrameChaining, useKenBurns, setUseKenBurns,
    useBeatSync, setUseBeatSync, useVeoAmbientAudio, setUseVeoAmbientAudio,
    useGpuEncode, setUseGpuEncode, hookZoomBoost, setHookZoomBoost,
    useSfx, setUseSfx, sfxVolume, setSfxVolume,
    subtitleStyle, setSubtitleStyle, colorGrading, setColorGrading, watermarkText, setWatermarkText,
    hookText, setHookText,
    uploadSessionId, setUploadSessionId, uploadedFiles, setUploadedFiles,
    uploadLoading, setUploadLoading, scenes, setScenes, scriptLoading, setScriptLoading,
    status, setStatus, progress, setProgress, jobMessage, setJobMessage,
    progressLog, setProgressLog, videoUrl, setVideoUrl, srtUrl, setSrtUrl,
    errorMsg, setErrorMsg, playPreview, handleReset, applyPreset,
    needsUpload, needsScript, needsTopic,
    coverImageSessionId, setCoverImageSessionId,
    coverImageName, setCoverImageName,
    coverImageLoading, setCoverImageLoading,
    coverImagePosition, setCoverImagePosition,
    useBreathing, setUseBreathing,
    hookEffect, setHookEffect
  };

  return (
    <AppContext.Provider value={contextValue}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);
