import { HeroContent } from "../HeroContent/HeroContent";
import { HeroImage } from "../HeroImage/HeroImage";
import "./HomeHero.css";

export function HomeHero() {
  return (
    <section className="homeHero">
      <div className="homeHero__grid">
        <HeroContent />
        <HeroImage />
      </div>
    </section>
  );
}
