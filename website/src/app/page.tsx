import Hero from "@/components/Hero";
import Ledger from "@/components/Ledger";
import BootShowcase from "@/components/BootShowcase";
import LiveTrace from "@/components/LiveTrace";
import HowItWorks from "@/components/HowItWorks";
import FeatureShowcase from "@/components/FeatureShowcase";
import AgentsGrid from "@/components/AgentsGrid";
import HermesSpotlight from "@/components/HermesSpotlight";
import Privacy from "@/components/Privacy";
import FAQ from "@/components/FAQ";
import FinalCTA from "@/components/FinalCTA";
import Footer from "@/components/Footer";
import SectionNav from "@/components/SectionNav";

export default function Page() {
  return (
    <main>
      <SectionNav />
      <Hero />
      <BootShowcase />
      <Ledger />
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
