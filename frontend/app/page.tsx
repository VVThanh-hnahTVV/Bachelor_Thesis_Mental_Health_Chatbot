"use client";

import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import {
  Brain,
  Shield,
  Sparkles,
  Waves,
  ArrowRight,
  HeartPulse,
  Lightbulb,
  Lock,
  MessageSquareHeart,
} from "lucide-react";
import { motion } from "framer-motion";
import { Slider } from "@/components/ui/slider";
import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import React from "react";

const emotions = [
  { value: 0, emoji: "😔", label: "Down" },
  { value: 25, emoji: "😊", label: "Content" },
  { value: 50, emoji: "😌", label: "Peaceful" },
  { value: 75, emoji: "🤗", label: "Happy" },
  { value: 100, emoji: "✨", label: "Excited" },
];

const RING_SIZES = [200, 400, 600, 800];

export default function Home() {
  const [emotion, setEmotion] = useState(50);
  const [mounted, setMounted] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  const welcomeSteps = [
    {
      title: "Hi, I'm Luna 👋",
      description:
        "Your AI companion for emotional well-being. I'm here to provide a safe, judgment-free space for you to express yourself.",
      icon: Waves,
    },
    {
      title: "Personalized Support 🌱",
      description:
        "I adapt to your needs and emotional state, offering evidence-based techniques and gentle guidance when you need it most.",
      icon: Brain,
    },
    {
      title: "Your Privacy Matters 🛡️",
      description:
        "Our conversations are completely private and secure. I follow strict ethical guidelines and respect your boundaries.",
      icon: Shield,
    },
  ];

  useEffect(() => {
    setMounted(true);
  }, []);

  const features = [
    {
      icon: HeartPulse,
      title: "24/7 Support",
      description: "Always here to listen and support you, any time of day",
      delay: 0.2,
    },
    {
      icon: Lightbulb,
      title: "Smart Insights",
      description: "Personalized guidance powered by emotional intelligence",
      delay: 0.4,
    },
    {
      icon: Lock,
      title: "Private & Secure",
      description: "Your conversations are always confidential and encrypted",
      delay: 0.6,
    },
    {
      icon: MessageSquareHeart,
      title: "Evidence-Based",
      description: "Therapeutic techniques backed by clinical research",
      delay: 0.8,
    },
  ];

  return (
    <div className="flex flex-col min-h-screen overflow-hidden bg-serene-bg">
      {/* Hero */}
      <section className="relative flex-grow min-h-[calc(100vh-5rem)] mt-20 flex flex-col items-center justify-center px-4 py-12 overflow-hidden">
        <div className="blur-blob top-[-10%] left-[-10%]" />
        <div className="blur-blob bottom-[-10%] right-[-10%]" />

        <div className="ring-container">
          {RING_SIZES.map((size) => (
            <div
              key={size}
              className="serene-ring"
              style={{ width: size, height: size }}
            />
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: mounted ? 1 : 0, y: mounted ? 0 : 20 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="relative z-10 text-center max-w-3xl mx-auto flex flex-col items-center"
        >
          <div className="mb-8 px-4 py-1.5 rounded-full border border-serene-green/30 bg-white/50 text-serene-accent text-xs font-medium flex items-center gap-2">
            <Waves className="w-3.5 h-3.5 opacity-70" />
            <span>Your AI Agent Mental Health Companion</span>
          </div>

          <h1 className="text-5xl md:text-7xl lg:text-8xl font-bold text-gray-800 leading-tight mb-6">
            Find Peace
            <br />
            <span className="text-serene-accent italic font-normal">
              of Mind
            </span>
          </h1>

          <p className="text-lg text-gray-500 max-w-xl mb-16 leading-relaxed">
            Experience a new way of emotional support. Our AI companion is here
            to listen, understand, and guide you through life&apos;s journey.
          </p>

          {/* Mood tracker */}
          <div className="w-full max-w-lg space-y-8">
            <p className="text-sm font-medium text-gray-400">
              Whatever you&apos;re feeling, we&apos;re here to listen
            </p>

            <div className="flex justify-between items-end w-full px-2">
              {emotions.map((em) => {
                const active = Math.abs(emotion - em.value) < 15;
                return (
                  <button
                    key={em.value}
                    type="button"
                    onClick={() => setEmotion(em.value)}
                    className={`flex flex-col items-center gap-2 transition-all duration-300 cursor-pointer ${
                      active
                        ? "scale-110 opacity-100"
                        : "opacity-40 hover:opacity-100"
                    }`}
                  >
                    <span
                      className={`text-3xl ${active ? "drop-shadow-md" : ""}`}
                    >
                      {em.emoji}
                    </span>
                    <span
                      className={`text-[10px] uppercase tracking-widest ${
                        active
                          ? "text-serene-accent font-bold"
                          : "text-gray-500"
                      }`}
                    >
                      {em.label}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="relative w-full pt-4 px-2 mood-slider">
              <Slider
                value={[emotion]}
                onValueChange={(value) => setEmotion(value[0])}
                min={0}
                max={100}
                step={1}
                className="py-2"
              />
            </div>

            <p className="text-xs text-gray-400 italic">
              Slide to express how you&apos;re feeling today
            </p>
          </div>

          <div className="mt-20">
            <Button
              size="lg"
              onClick={() => setShowDialog(true)}
              className="group relative inline-flex items-center justify-center px-10 py-6 h-auto text-base font-bold text-white bg-serene-green rounded-full hover:bg-serene-accent shadow-lg shadow-serene-green/30 transition-all duration-200"
            >
              <span className="mr-3">Begin Your Journey</span>
              <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-1" />
            </Button>
          </div>

          <div className="mt-12 flex flex-col items-center opacity-50">
            <div className="w-5 h-8 border-2 border-serene-green rounded-full flex justify-center p-1">
              <div className="w-1 h-2 bg-serene-green rounded-full animate-bounce" />
            </div>
          </div>
        </motion.div>
      </section>

      {/* Features */}
      <section className="relative py-20 px-4 bg-serene-bg border-t border-gray-100">
        <div className="max-w-6xl mx-auto">
          <motion.div
            className="text-center mb-16 space-y-4"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
          >
            <h2 className="text-3xl font-bold text-gray-800">
              How Luna Helps You
            </h2>
            <p className="text-gray-500 max-w-2xl mx-auto text-lg">
              Experience a new kind of emotional support, powered by empathetic
              AI
            </p>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {features.map((feature, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: feature.delay, duration: 0.5 }}
                viewport={{ once: true }}
              >
                <Card className="group h-[200px] border border-serene-green/15 bg-white/70 hover:border-serene-green/30 hover:shadow-md hover:shadow-serene-green/10 transition-all duration-300 rounded-2xl">
                  <CardHeader className="pb-4">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-xl bg-[#E8F0E7] group-hover:bg-[#DCE7DA] transition-colors">
                        <feature.icon className="w-5 h-5 text-serene-accent" />
                      </div>
                      <h3 className="font-semibold text-gray-800">
                        {feature.title}
                      </h3>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-gray-500 leading-relaxed">
                      {feature.description}
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="sm:max-w-[425px] bg-white border-serene-green/20 rounded-2xl">
          <DialogHeader>
            <motion.div
              key={currentStep}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="space-y-4"
            >
              <div className="mx-auto w-16 h-16 rounded-full bg-[#E8F0E7] flex items-center justify-center">
                {welcomeSteps[currentStep] &&
                  React.createElement(welcomeSteps[currentStep].icon, {
                    className: "w-8 h-8 text-serene-accent",
                  })}
              </div>
              <DialogTitle className="text-2xl text-center text-gray-800">
                {welcomeSteps[currentStep]?.title}
              </DialogTitle>
              <DialogDescription className="text-center text-base leading-relaxed text-gray-500">
                {welcomeSteps[currentStep]?.description}
              </DialogDescription>
            </motion.div>
          </DialogHeader>
          <div className="flex justify-between items-center mt-8">
            <div className="flex gap-2">
              {welcomeSteps.map((_, index) => (
                <div
                  key={index}
                  className={`h-2 rounded-full transition-all duration-300 ${
                    index === currentStep
                      ? "w-4 bg-serene-green"
                      : "w-2 bg-serene-green/20"
                  }`}
                />
              ))}
            </div>
            <Button
              onClick={() => {
                if (currentStep < welcomeSteps.length - 1) {
                  setCurrentStep((c) => c + 1);
                } else {
                  setShowDialog(false);
                  setCurrentStep(0);
                }
              }}
              className="rounded-full bg-serene-green hover:bg-serene-accent text-white px-6"
            >
              <span className="flex items-center gap-2">
                {currentStep === welcomeSteps.length - 1 ? (
                  <>
                    Let&apos;s Begin
                    <Sparkles className="w-4 h-4" />
                  </>
                ) : (
                  <>
                    Next
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </span>
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
