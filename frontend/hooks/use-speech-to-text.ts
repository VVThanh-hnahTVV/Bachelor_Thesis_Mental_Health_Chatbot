"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeSpeech } from "@/lib/api/speech";

export type SpeechToTextStatus = "idle" | "recording" | "transcribing";

const MAX_RECORDING_MS = 120_000;

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}

interface UseSpeechToTextOptions {
  onTranscript: (text: string) => void;
  onError?: (message: string) => void;
  disabled?: boolean;
}

export function useSpeechToText({
  onTranscript,
  onError,
  disabled = false,
}: UseSpeechToTextOptions) {
  const [status, setStatus] = useState<SpeechToTextStatus>("idle");
  const [audioLevel, setAudioLevel] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);

  const stopLevelMonitor = useCallback(() => {
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    analyserRef.current = null;
    void audioContextRef.current?.close();
    audioContextRef.current = null;
    setAudioLevel(0);
  }, []);

  const startLevelMonitor = useCallback((stream: MediaStream) => {
    stopLevelMonitor();
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.75;
    source.connect(analyser);

    audioContextRef.current = audioContext;
    analyserRef.current = analyser;

    const buffer = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      if (!analyserRef.current) return;
      analyserRef.current.getByteFrequencyData(buffer);
      const sum = buffer.reduce((acc, value) => acc + value, 0);
      setAudioLevel(sum / buffer.length / 255);
      animationRef.current = requestAnimationFrame(tick);
    };
    animationRef.current = requestAnimationFrame(tick);
  }, [stopLevelMonitor]);

  const cleanupStream = useCallback(() => {
    if (stopTimerRef.current) {
      clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }
    stopLevelMonitor();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
  }, [stopLevelMonitor]);

  useEffect(() => cleanupStream, [cleanupStream]);

  const stopRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;

    setStatus("transcribing");

    const blob = await new Promise<Blob>((resolve, reject) => {
      recorder.onstop = () => {
        const mime = recorder.mimeType || "audio/webm";
        resolve(new Blob(chunksRef.current, { type: mime }));
      };
      recorder.onerror = () => reject(new Error("Recording failed"));
      recorder.stop();
    });

    cleanupStream();

    try {
      const result = await transcribeSpeech(blob);
      onTranscript(result.text);
      setStatus("idle");
    } catch (err) {
      setStatus("idle");
      onError?.(err instanceof Error ? err.message : "Transcription failed");
    }
  }, [cleanupStream, onError, onTranscript]);

  const startRecording = useCallback(async () => {
    if (disabled || status !== "idle") return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      startLevelMonitor(stream);

      const mimeType = pickMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorderRef.current = recorder;
      recorder.start(250);
      setStatus("recording");

      stopTimerRef.current = setTimeout(() => {
        void stopRecording();
      }, MAX_RECORDING_MS);
    } catch (err) {
      cleanupStream();
      setStatus("idle");
      onError?.(
        err instanceof Error
          ? err.message
          : "Microphone permission denied or unavailable"
      );
    }
  }, [cleanupStream, disabled, onError, startLevelMonitor, status, stopRecording]);

  const toggle = useCallback(() => {
    if (disabled || status === "transcribing") return;
    if (status === "recording") {
      void stopRecording();
      return;
    }
    void startRecording();
  }, [disabled, startRecording, status, stopRecording]);

  return {
    status,
    toggle,
    audioLevel,
    isRecording: status === "recording",
    isTranscribing: status === "transcribing",
  };
}
