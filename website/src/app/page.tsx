import Hero from "@/components/Hero";
import ProofStrip from "@/components/ProofStrip";
import HowItWorks from "@/components/HowItWorks";
import FeatureShowcase from "@/components/FeatureShowcase";
import HermesSpotlight from "@/components/HermesSpotlight";
import SecondBrainSpotlight from "@/components/SecondBrainSpotlight";
import Privacy from "@/components/Privacy";
import AgentsGrid from "@/components/AgentsGrid";
import FAQ from "@/components/FAQ";
import FinalCTA from "@/components/FinalCTA";
import Footer from "@/components/Footer";

export default function Page() {
  return (
    <main>
      <Hero />
      <ProofStrip />
      <HowItWorks />
      <FeatureShowcase />
      <HermesSpotlight />
      <SecondBrainSpotlight />
      <Privacy />
      <AgentsGrid />
      <FAQ />
      <FinalCTA />
      <Footer />
    </main>
  );
}
