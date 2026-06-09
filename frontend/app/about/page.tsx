"use client";

import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Heart, Target, Sparkles } from "lucide-react";

const missions = [
  {
    icon: <Heart className="w-8 h-8 text-primary" />,
    title: "Sứ mệnh",
    description:
      "Mang đến không gian an toàn để mọi người tra cứu và được tư vấn về sức khỏe tâm thần — dễ tiếp cận, dễ hiểu và tôn trọng quyền riêng tư.",
  },
  {
    icon: <Target className="w-8 h-8 text-primary" />,
    title: "Tầm nhìn",
    description:
      "Một nền tảng nơi thông tin sức khỏe tâm thần minh bạch, có căn cứ và được hỗ trợ bởi AI có trách nhiệm.",
  },
  {
    icon: <Sparkles className="w-8 h-8 text-primary" />,
    title: "Giá trị",
    description:
      "Riêng tư, đồng cảm, minh bạch và an toàn — Helios luôn nhắc bạn đây là hỗ trợ tham khảo, không thay thế chuyên gia.",
  },
];

export default function AboutPage() {
  return (
    <div className="container mx-auto px-4 py-24">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="text-center mb-20"
      >
        <h1 className="text-4xl font-bold mb-6 bg-gradient-to-r from-primary to-primary/80 bg-clip-text text-transparent">
          Về Helios
        </h1>
        <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
          Helios là nền tảng hỗ trợ <strong>tra cứu và tư vấn sức khỏe tâm thần</strong> —
          kết hợp trò chuyện AI, tài liệu tham khảo và bài tập thư giãn trong một không gian
          nhẹ nhàng, riêng tư.
        </p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-20">
        {missions.map((mission, index) => (
          <motion.div
            key={mission.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: index * 0.1 }}
          >
            <Card className="p-6 text-center h-full bg-card/50 backdrop-blur supports-[backdrop-filter]:bg-background/60">
              <div className="mb-4 flex justify-center">{mission.icon}</div>
              <h3 className="text-xl font-semibold mb-3">{mission.title}</h3>
              <p className="text-muted-foreground">{mission.description}</p>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
