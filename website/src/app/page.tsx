import Hero from "@/components/Hero";
import ProofStrip from "@/components/ProofStrip";
import LiveTrace from "@/components/LiveTrace";
import HowItWorks from "@/components/HowItWorks";
import FeatureShowcase from "@/components/FeatureShowcase";
import AgentsGrid from "@/components/AgentsGrid";
import HermesSpotlight from "@/components/HermesSpotlight";
import Privacy from "@/components/Privacy";
import FAQ from "@/components/FAQ";
import FinalCTA from "@/components/FinalCTA";
import Footer from "@/components/Footer";

export default function Page() {
  return (
    <main>
      <Hero />
      <ProofStrip />
      <LiveTrace />
      <HowItWorks />
      <FeatureShowcase />
      <AgentsGrid />
      <HermesSpotlight />
      <Privacy />
      <FAQ />
      <FinalCTA />
      <Footer />
    </main>
  );
}
