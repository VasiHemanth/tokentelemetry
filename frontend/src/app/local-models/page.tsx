import { Cpu } from "lucide-react";
import { PageHeader, Section } from "@/components/ui";
import { PowerSettings } from "@/components/settings/PowerSettings";
import LocalPowerInsights from "@/components/insights/LocalPowerInsights";

export default function LocalModelsPage() {
  return (
    <div className="px-8 py-8 max-w-[900px] mx-auto space-y-10 pb-20">
      <PageHeader
        eyebrow="Hardware"
        title="Local Models & Power"
        description="Configure your local machine's power and electricity rates to accurately track local model costs."
        icon={<Cpu size={20} strokeWidth={2.25} />}
      />

      <LocalPowerInsights forceShow={true} />

      <Section
        title="How to measure local power"
        description="Follow these steps to accurately measure how much electricity your local AI models use:"
      >
        <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-6 space-y-4 text-sm text-[var(--tt-fg-dim)]">
          <p>
            TokenTelemetry can automatically measure your machine&apos;s real power draw. Depending on your hardware and OS, this reads your GPU directly (e.g. nvidia-smi) or uses your system&apos;s battery discharge rate.
          </p>
          <ol className="list-decimal list-inside space-y-2 ml-2 text-[var(--tt-fg)]">
            <li><strong>If on a Mac/laptop:</strong> Unplug it from the wall charger (if plugged in, the battery isn&apos;t draining, so power can&apos;t be measured without admin privileges).</li>
            <li><strong>Start a heavy prompt</strong> in Ollama or your local AI tool to put your machine under load.</li>
            <li><strong>Click &quot;Measure&quot;</strong> below while the model is actively generating text.</li>
          </ol>
          <p className="mt-4">
            TokenTelemetry will sample your power draw for 5 seconds and lock in the wattage. This ensures your local model costs are based on actual electricity usage rather than cloud API rates!
          </p>
        </div>
      </Section>

      <Section
        title="Power configuration"
        description="Set your wattage and local electricity rate. These numbers are used to price sessions on local models (Ollama, vLLM, etc.) and calculate your carbon footprint."
      >
        <PowerSettings />
      </Section>
    </div>
  );
}
