import { Card } from "@/components/ui/card";
import { Container } from "@/components/ui/container";
import { ResetPasswordForm } from "./reset-password-form";

export default function ResetPasswordPage({
  searchParams,
}: {
  searchParams: { token?: string };
}) {
  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-serene-bg">
      <Container className="flex flex-col items-center justify-center w-full">
        <Card className="w-full max-w-md p-8 rounded-2xl border-serene-green/20 bg-white shadow-lg mt-20">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold text-gray-800 mb-1">
              Đặt lại mật khẩu
            </h1>
            <p className="text-sm text-gray-500">
              Nhập mật khẩu mới của bạn bên dưới.
            </p>
          </div>
          <ResetPasswordForm token={searchParams.token ?? ""} />
        </Card>
      </Container>
    </div>
  );
}
