import { FloatingChatButton } from "../components/FloatingChatButton/FloatingChatButton";
import { Footer } from "../components/Footer/Footer";
import { Header } from "../components/Header/Header";
import { HomeHero } from "../components/HomeHero/HomeHero";

export default function Home() {
  return (
    <>
      <Header />
      <main>
        <HomeHero />
      </main>
      <Footer />
      <FloatingChatButton />
    </>
  );
}
