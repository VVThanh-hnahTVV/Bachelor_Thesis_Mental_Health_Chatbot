"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { Form, Input, message } from "antd";
import { ApiError } from "../../api/apiMethod";
import { login, register } from "../../api/auth";
import "./AuthModal.css";

export type AuthMode = "login" | "register";

type AuthModalProps = {
  open: boolean;
  onClose: () => void;
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;
  onAuthSuccess: () => void;
};

type AuthFormValues = {
  fullName?: string;
  email: string;
  password: string;
};

function BrandPanel() {
  return (
    <aside className="authModal__brand" aria-hidden={false}>
      <div>
        <p className="authModal__brandLogo">Wye</p>
        <p className="authModal__brandHeadline">Bắt đầu hành trình tĩnh lặng của bạn.</p>
      </div>
      <p className="authModal__brandTagline">
        Cùng kiến tạo không gian sống chậm mỗi ngày.
      </p>
      <span className="authModal__brandBlob1" aria-hidden />
      <span className="authModal__brandBlob2" aria-hidden />
    </aside>
  );
}

export function AuthModal({ open, onClose, mode, onModeChange, onAuthSuccess }: AuthModalProps) {
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const isRegister = mode === "register";

  const setAccessTokenCookie = (accessToken: string) => {
    const maxAgeSeconds = 60 * 60 * 24 * 7;
    document.cookie = `accessToken=${encodeURIComponent(accessToken)}; Max-Age=${maxAgeSeconds}; Path=/; SameSite=Lax`;
  };

  const handleFinish = async (values: AuthFormValues) => {
    try {
      if (isRegister) {
        const response = await register({
          name: values.fullName?.trim() ?? "",
          email: values.email.trim(),
          password: values.password,
        });
        setAccessTokenCookie(response.access_token);
        messageApi.success("Đăng ký thành công");
      } else {
        const response = await login({
          email: values.email.trim(),
          password: values.password,
        });
        setAccessTokenCookie(response.access_token);
        messageApi.success("Đăng nhập thành công");
      }

      onAuthSuccess();
      onClose();
    } catch (error) {
      if (error instanceof ApiError) {
        const detail =
          (typeof error.payload?.detail === "string" && error.payload.detail) ||
          (typeof error.payload?.message === "string" && error.payload.message) ||
          error.message;
        messageApi.error(detail);
        return;
      }

      messageApi.error("Không thể kết nối máy chủ, vui lòng thử lại.");
    }
  };

  const formBlock = (
    <div className="authModal__formWrap">
      <h1 className="authModal__title" id="auth-modal-title">
        {isRegister ? "Tạo tài khoản" : "Đăng nhập"}
      </h1>
      <p className="authModal__subtitle">
        {isRegister
          ? "Hãy dành một chút thời gian cho chính mình."
          : "Chào mừng bạn quay lại không gian của riêng mình."}
      </p>
      {isRegister && (
        <button
          type="button"
          className="authModal__backToLoginBtn"
          onClick={() => {
            onModeChange("login");
            form.resetFields();
          }}
        >
          ← Quay về đăng nhập
        </button>
      )}

      <Form
        form={form}
        layout="vertical"
        className="authModal__form"
        requiredMark={false}
        onFinish={handleFinish}
      >
        {isRegister && (
          <Form.Item
            label="Họ và tên"
            name="fullName"
            rules={[{ required: true, message: "Vui lòng nhập họ và tên" }]}
          >
            <Input className="authModal__input" placeholder="Nguyễn Văn A" autoComplete="name" />
          </Form.Item>
        )}

        <Form.Item
          label="Email"
          name="email"
          rules={[
            { required: true, message: "Vui lòng nhập email" },
            { type: "email", message: "Email không hợp lệ" },
          ]}
        >
          <Input className="authModal__input" placeholder="example@wye.vn" autoComplete="email" />
        </Form.Item>

        <Form.Item
          label="Mật khẩu"
          name="password"
          rules={[
            { required: true, message: "Vui lòng nhập mật khẩu" },
            ...(isRegister ? [{ min: 8, message: "Mật khẩu tối thiểu 8 ký tự" }] : []),
          ]}
        >
          <Input.Password
            className="authModal__input"
            placeholder="••••••••"
            autoComplete={isRegister ? "new-password" : "current-password"}
          />
        </Form.Item>

        <Form.Item className="authModal__submitWrap" style={{ marginBottom: 0 }}>
          <button type="submit" className="authModal__submit">
            {isRegister ? "Đăng ký tài khoản" : "Đăng nhập"}
          </button>
        </Form.Item>
      </Form>

      <div className="authModal__footer">
        {isRegister && (
          <p className="authModal__terms">
            Bằng cách đăng ký, bạn đồng ý với{" "}
            <a href="#" onClick={(e) => e.preventDefault()}>
              Điều khoản dịch vụ
            </a>
          </p>
        )}
        <div className="authModal__switchRow">
          {isRegister ? (
            <>
              Đã có tài khoản?
              <button
                type="button"
                className="authModal__switchBtn"
                onClick={() => {
                  onModeChange("login");
                  form.resetFields();
                }}
              >
                Đăng nhập
              </button>
            </>
          ) : (
            <>
              Chưa có tài khoản?
              <button
                type="button"
                className="authModal__switchBtn"
                onClick={() => {
                  onModeChange("register");
                  form.resetFields();
                }}
              >
                Đăng ký
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );

  useEffect(() => {
    if (open) {
      form.resetFields();
    }
  }, [open, form]);

  useEffect(() => {
    if (!open) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <>
      {contextHolder}
      <div className="authModal__portal" role="presentation">
        <button
          type="button"
          className="authModal__portalMask"
          aria-label="Đóng"
          onClick={onClose}
        />
        <div
          className="authModal__portalDialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="auth-modal-title"
        >
          <button type="button" className="authModal__portalClose" onClick={onClose} aria-label="Đóng">
            ×
          </button>
          <div className="authModal__card" data-auth-mode={mode}>
            <div className="authModal__cardTrack">
              <div className="authModal__cardHalf authModal__cardHalf--brand">
                <BrandPanel />
              </div>
              <div className="authModal__cardHalf authModal__cardHalf--form">{formBlock}</div>
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}
