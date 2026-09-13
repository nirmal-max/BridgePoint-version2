"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

export type VoiceProfile = {
  full_name: string; primary_skill: string; sub_skills: string[]; experience_years: number;
  expected_rate: number; operating_location: string; availability: string; language: string;
  transcript: string; confidence: number;
};

const languages = [["ta", "Tamil"], ["te", "Telugu"], ["hi", "Hindi"], ["en", "English"]] as const;

/** Adapted from Ubiquity's OnboardingModal recorder lifecycle for BridgePoint signup. */
export default function VoiceRegistration({ onExtract, onCancel }: { onExtract: (profile: VoiceProfile) => void; onCancel: () => void }) {
  const [language, setLanguage] = useState("en");
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [volume, setVolume] = useState(0);
  const [speechDetected, setSpeechDetected] = useState(false);
  const [error, setError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const audioContext = useRef<AudioContext | null>(null);
  const frame = useRef<number | null>(null);
  const timer = useRef<number | null>(null);
  const started = useRef(0);
  const volumeSamples = useRef<number[]>([]);

  const cleanup = () => {
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
    if (frame.current) cancelAnimationFrame(frame.current); frame.current = null;
    if (timer.current) clearInterval(timer.current); timer.current = null;
    void audioContext.current?.close(); audioContext.current = null;
  };
  useEffect(() => cleanup, []);

  const startMeter = (mediaStream: MediaStream) => {
    const context = new AudioContext({ sampleRate: 16000 });
    const analyser = context.createAnalyser(); analyser.fftSize = 256; analyser.smoothingTimeConstant = .7;
    context.createMediaStreamSource(mediaStream).connect(analyser); audioContext.current = context;
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => { analyser.getByteTimeDomainData(data); let total = 0; for (const value of data) total += ((value - 128) / 128) ** 2;
      const level = Math.min(100, Math.sqrt(total / data.length) * 320); volumeSamples.current.push(level);
      if (volumeSamples.current.length > 120) volumeSamples.current.shift(); setVolume(level); setSpeechDetected(level > 3.5); frame.current = requestAnimationFrame(tick); };
    tick();
  };

  const startRecording = async () => {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") { setError("Microphone recording is not supported in this browser."); return; }
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      stream.current = mediaStream; chunks.current = []; volumeSamples.current = []; setSeconds(0); startMeter(mediaStream);
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
      const activeRecorder = new MediaRecorder(mediaStream, { mimeType }); recorder.current = activeRecorder;
      activeRecorder.ondataavailable = event => { if (event.data.size) chunks.current.push(event.data); };
      activeRecorder.onstop = async () => {
        const duration = (Date.now() - started.current) / 1000;
        const average = volumeSamples.current.reduce((total, item) => total + item, 0) / Math.max(volumeSamples.current.length, 1);
        const blob = new Blob(chunks.current, { type: activeRecorder.mimeType || "audio/webm" }); cleanup(); setRecording(false);
        if (duration < 1.5 || average < 1.5 || !blob.size) { setError("No audible speech detected. Please record again and speak closer to the microphone."); return; }
        setProcessing(true);
        try { onExtract((await api.voiceOnboard(blob, language)).structured_profile); }
        catch (reason) { setError(reason instanceof Error ? reason.message : "BridgePoint couldn't understand the recording. Please record again."); }
        finally { setProcessing(false); }
      };
      activeRecorder.start(250); started.current = Date.now(); timer.current = window.setInterval(() => setSeconds(value => value + .1), 100); setRecording(true);
    } catch { setError("Microphone access was denied. Please allow microphone access and try again."); cleanup(); }
  };
  const stopRecording = () => recorder.current?.state === "recording" && recorder.current.stop();

  return <section className="mt-6 rounded-2xl border border-blue-200 bg-blue-50/50 p-5" aria-label="AI Voice Registration">
    <div className="flex items-start justify-between gap-4"><div><h3 className="text-lg font-bold text-slate-900">🎙 AI Voice Registration</h3><p className="mt-1 text-sm text-slate-600">Speak naturally in your preferred language. You will review and edit everything before submitting.</p></div><button type="button" onClick={onCancel} className="text-sm font-semibold text-slate-500 hover:text-slate-800">Use manual</button></div>
    <label className="mt-4 block text-sm font-semibold text-slate-700">Language<select value={language} disabled={recording || processing} onChange={event => setLanguage(event.target.value)} className="input-field mt-1.5"><option value="">Select language</option>{languages.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <div className="mt-4 rounded-xl bg-white p-4 text-center shadow-sm"><p className={`text-sm font-semibold ${recording && speechDetected ? "text-emerald-700" : "text-slate-600"}`}>{recording ? (speechDetected ? "Voice detected" : "Listening for speech…") : "Ready to record"}</p>{recording && <><div className="mx-auto mt-3 h-2 max-w-xs overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-blue-600 transition-all" style={{ width: `${Math.max(3, volume)}%` }} /></div><p className="mt-2 text-xs text-slate-500">{Math.floor(seconds / 60).toString().padStart(2, "0")}:{Math.floor(seconds % 60).toString().padStart(2, "0")}</p></>}
      <button type="button" onClick={recording ? stopRecording : () => void startRecording()} disabled={processing} className={`mt-4 rounded-full px-5 py-3 font-semibold text-white disabled:opacity-50 ${recording ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"}`}>{processing ? "Processing recording…" : recording ? "Stop & extract profile" : "Start Voice Registration"}</button></div>
    {error && <p role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
  </section>;
}
