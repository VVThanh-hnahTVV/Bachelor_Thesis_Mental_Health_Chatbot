import Image from "next/image";
import { EnvironmentOutlined, SmileOutlined, HeartOutlined, MehOutlined } from "@ant-design/icons";
import "./HeroImage.css";

export function HeroImage() {
  return (
    <div className="heroImage">
      <div className="heroImage__blob" aria-hidden />

      <div className="heroImage__frame">
        <Image
          src="/hero-serene.png"
          alt="Sunlit misty forest path"
          fill
          className="heroImage__img"
          sizes="(max-width: 1024px) 100vw, 55vw"
          priority
        />
      </div>

      <div className="heroImage__glass heroImage__glass--calm">
        <div className="heroImage__glassRow">
          <div className="heroImage__glassIcon" aria-hidden>
            <EnvironmentOutlined />
          </div>
          <span className="heroImage__glassTitle">Daily Calm</span>
        </div>
        <p className="heroImage__quote">
          &ldquo;In the middle of every difficulty lies opportunity.&rdquo;
        </p>
      </div>

      <div className="heroImage__glass heroImage__glass--mood">
        <span className="heroImage__moodLabel">How do you feel?</span>
        <div className="heroImage__moods">
          <button type="button" className="heroImage__moodBtn heroImage__moodBtn--happy" aria-label="Happy mood">
            <SmileOutlined />
          </button>
          <button type="button" className="heroImage__moodBtn heroImage__moodBtn--calm" aria-label="Calm mood">
            <HeartOutlined />
          </button>
          <button type="button" className="heroImage__moodBtn heroImage__moodBtn--neutral" aria-label="Neutral mood">
            <MehOutlined />
          </button>
        </div>
      </div>
    </div>
  );
}
