"use client";

import { Button } from "antd";
import { CommentOutlined } from "@ant-design/icons";
import "./FloatingChatButton.css";

export function FloatingChatButton() {
  return (
    <div className="floatingChat">
      <Button
        type="text"
        shape="circle"
        className="floatingChat__btn floatingChat__pulse"
        aria-label="Open chat or help"
        icon={<CommentOutlined />}
      />
    </div>
  );
}
