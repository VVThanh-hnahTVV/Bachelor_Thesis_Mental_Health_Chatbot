"use client";

import { Button } from "antd";
import { ArrowRightOutlined } from "@ant-design/icons";
import { PrivacyCard } from "../PrivacyCard/PrivacyCard";
import "./HeroContent.css";

export function HeroContent() {
  return (
    <div className="heroContent">
      <div className="heroContent__intro">
        <h1 className="heroContent__title">
          Welcome to <span className="heroContent__titleAccent">Wye.</span>
        </h1>
        <p className="heroContent__subtitle">
          Your safe space to talk, track your mood, and find peace.
        </p>
      </div>

      <div className="heroContent__actions">
        <Button
          type="primary"
          className="heroContent__cta"
          icon={<ArrowRightOutlined />}
          iconPosition="end"
        >
          Get Started
        </Button>
        <PrivacyCard />
      </div>
    </div>
  );
}
