"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  MessageCircleHeart,
  BookOpen,
  LayoutDashboard,
  History,
  Wind,
  ShieldAlert,
  UserCircle,
  ArrowRight,
  Brain,
} from "lucide-react";

const features = [
  {
    icon: MessageCircleHeart,
    title: "Trò chuyện sức khỏe tâm thần",
    description:
      "Trao đổi với Helios về lo âu, căng thẳng, trầm cảm và các chủ đề tâm lý. Hệ thống ghi nhớ ngữ cảnh trong phiên và trả lời bằng ngôn ngữ dễ hiểu.",
  },
  {
    icon: BookOpen,
    title: "Tra cứu có căn cứ",
    description:
      "Helios tra cứu tài liệu tham khảo đã chọn lọc để giải thích khái niệm và hướng dẫn chăm sóc bản thân một cách rõ ràng.",
  },
  {
    icon: Brain,
    title: "Tư vấn & gợi ý thực hành",
    description:
      "Ngoài giải thích thông tin, Helios có thể gợi ý bài tập thở, âm thanh thư giãn khi phù hợp với nội dung trò chuyện.",
  },
  {
    icon: LayoutDashboard,
    title: "Bảng điều khiển wellness",
    description:
      "Theo dõi phiên trò chuyện và hoạt động thư giãn đã hoàn thành trong ngày từ một màn hình tổng quan gọn gàng.",
  },
  {
    icon: History,
    title: "Lịch sử phiên chat",
    description:
      "Tạo phiên mới hoặc tiếp tục cuộc trò chuyện trước đó. Mỗi phiên giữ ngữ cảnh riêng để bạn kể tiếp câu chuyện của mình.",
  },
  {
    icon: Wind,
    title: "Bài tập thư giãn",
    description:
      "Hít thở, mini-game thư giãn và âm thanh calming — dùng ngay trong chat khi cần ổn định cảm xúc.",
  },
  {
    icon: ShieldAlert,
    title: "An toàn nội dung",
    description:
      "Helios kiểm tra nội dung đầu vào/đầu ra và nhắc rõ: đây là hỗ trợ tham khảo, không phải cấp cứu hay chẩn đoán lâm sàng.",
  },
  {
    icon: UserCircle,
    title: "Tài khoản riêng tư",
    description:
      "Đăng ký để lưu phiên chat và đồng bộ trên nhiều thiết bị. Dữ liệu được bảo vệ bằng xác thực an toàn.",
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
            Tra cứu & tư vấn sức khỏe tâm thần
          </p>
          <h1 className="text-4xl md:text-5xl font-bold text-gray-800 mb-6">
            Tính năng của Helios
          </h1>
          <p className="text-lg text-gray-500 max-w-2xl mx-auto leading-relaxed">
            Không gian nhẹ nhàng để tra cứu thông tin, được tư vấn về sức khỏe tâm thần
            và thực hành thư giãn — bổ trợ chăm sóc hằng ngày, không thay thế điều trị
            chuyên môn.
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
            Sẵn sàng bắt đầu?
          </h2>
          <p className="text-gray-500 mb-6 max-w-lg mx-auto">
            Bắt đầu trò chuyện với Helios ngay để được tra cứu & tư vấn sức khỏe tâm thần.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button
              asChild
              className="rounded-full bg-serene-green hover:bg-serene-accent text-white px-8"
            >
              <Link href="/therapy/new">
                Bắt đầu trò chuyện
                <ArrowRight className="ml-2 w-4 h-4" />
              </Link>
            </Button>
            <Button
              asChild
              variant="outline"
              className="rounded-full border-serene-green/30 text-serene-accent hover:bg-[#E8F0E7]"
            >
              <Link href="/signup">Tạo tài khoản</Link>
            </Button>
          </div>
          <p className="text-xs text-gray-400 mt-6 italic">
            Helios chỉ cung cấp thông tin tham khảo và hỗ trợ sức khỏe tâm thần — không
            thay thế chẩn đoán, điều trị hay dịch vụ cấp cứu.
          </p>
        </motion.div>
      </div>
    </div>
  );
}
