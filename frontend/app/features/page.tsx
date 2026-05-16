"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  MessageCircleHeart,
  BookOpen,
  Smile,
  LayoutDashboard,
  History,
  Wind,
  ShieldAlert,
  UserCircle,
  ArrowRight,
} from "lucide-react";

const features = [
  {
    icon: MessageCircleHeart,
    title: "AI Companion Chat",
    description:
      "Talk with Luna anytime through guided therapy sessions. Conversations are powered by LangGraph with multi-turn memory, empathetic replies, and optional LLM providers (OpenAI, Groq, Gemini, and more).",
  },
  {
    icon: BookOpen,
    title: "Knowledge-Grounded Guidance",
    description:
      "Responses are enriched with retrieval from a curated wellness knowledge base, so coping ideas and psychoeducation stay aligned with evidence-based content—not generic chatbot guesses.",
  },
  {
    icon: Smile,
    title: "Mood Check-ins",
    description:
      "Log how you feel on a simple mood scale from the home page or dashboard. Track patterns over time and pair mood entries with your daily activities.",
  },
  {
    icon: LayoutDashboard,
    title: "Wellness Dashboard",
    description:
      "On the dashboard, track your mood, view today’s wellness stats, see how many therapy sessions you’ve started, and read short insights based on your recent patterns.",
  },
  {
    icon: History,
    title: "Therapy Sessions",
    description:
      "Start a new AI chat from the dashboard or resume past conversations. Luna remembers context within each session and can suggest calming exercises when you need them.",
  },
  {
    icon: Wind,
    title: "Calming Mini-Games",
    description:
      "Take a break with interactive exercises: breathing patterns, Zen Garden, Mindful Forest, and Ocean Waves—available from the dashboard and inside chat when you need to ground yourself.",
  },
  {
    icon: ShieldAlert,
    title: "Built-in Safety Checks",
    description:
      "Each message is screened for elevated risk. When needed, Luna shares crisis resources and reminds you this app is for wellness support, not emergency or clinical care.",
  },
  {
    icon: UserCircle,
    title: "Your Private Account",
    description:
      "Sign up to save chat sessions and mood check-ins to your account. Your data is tied to secure authentication—so your journey stays personal and persistent.",
  },
];

export default function FeaturesPage() {
  return (
    <div className="min-h-screen bg-serene-bg">
      <div className="container mx-auto px-4 py-28 md:py-32 max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-16"
        >
          <p className="text-xs uppercase tracking-widest text-serene-accent font-medium mb-4">
            Luna 2.0
          </p>
          <h1 className="text-4xl md:text-5xl font-bold text-gray-800 mb-6">
            What Luna Offers
          </h1>
          <p className="text-lg text-gray-500 max-w-2xl mx-auto leading-relaxed">
            A calm space for emotional support—AI conversation, mood tracking,
            wellness tools, and grounding exercises. Built for everyday
            well-being, not as a replacement for professional care.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: index * 0.06 }}
            >
              <Card className="p-6 h-full border border-serene-green/15 bg-white/80 hover:border-serene-green/30 hover:shadow-md hover:shadow-serene-green/10 transition-all duration-300 rounded-2xl">
                <div className="mb-4 inline-flex p-3 rounded-xl bg-[#E8F0E7]">
                  <feature.icon className="w-7 h-7 text-serene-accent" />
                </div>
                <h3 className="text-lg font-semibold text-gray-800 mb-2">
                  {feature.title}
                </h3>
                <p className="text-sm text-gray-500 leading-relaxed">
                  {feature.description}
                </p>
              </Card>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="text-center mt-16 p-8 rounded-2xl bg-white/60 border border-serene-green/15"
        >
          <h2 className="text-2xl font-semibold text-gray-800 mb-3">
            Ready to begin?
          </h2>
          <p className="text-gray-500 mb-6 max-w-lg mx-auto">
            Create an account or sign in, then open the dashboard to log your
            mood, start a chat session, or try a calming exercise.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button
              asChild
              className="rounded-full bg-serene-green hover:bg-serene-accent text-white px-8"
            >
              <Link href="/dashboard">
                Go to Dashboard
                <ArrowRight className="ml-2 w-4 h-4" />
              </Link>
            </Button>
            <Button
              asChild
              variant="outline"
              className="rounded-full border-serene-green/30 text-serene-accent hover:bg-[#E8F0E7]"
            >
              <Link href="/signup">Create account</Link>
            </Button>
          </div>
          <p className="text-xs text-gray-400 mt-6 italic">
            Luna is for educational and wellness support only—not medical
            advice, diagnosis, or emergency services.
          </p>
        </motion.div>
      </div>
    </div>
  );
}

