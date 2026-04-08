"use client";

import { Switch } from "antd";
import { SafetyCertificateOutlined } from "@ant-design/icons";
import "./PrivacyCard.css";

export function PrivacyCard() {
  return (
    <div className="privacyCard">
      <div className="privacyCard__top">
        <div className="privacyCard__iconWrap" aria-hidden>
          <SafetyCertificateOutlined />
        </div>
        <div>
          <h3 className="privacyCard__title">Privacy &amp; Safety</h3>
          <p className="privacyCard__text">
            Your data is encrypted and private. We never sell your personal information to third
            parties.
          </p>
        </div>
      </div>
      <div className="privacyCard__footer">
        <span className="privacyCard__label" id="privacy-terms-label">
          I agree to the Terms of Service
        </span>
        <Switch aria-labelledby="privacy-terms-label" />
      </div>
    </div>
  );
}
