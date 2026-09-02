import { Cpu } from "lucide-react";
import { PageHeader, Section } from "@/components/ui";
import { PowerSettings } from "@/components/settings/PowerSettings";
import LocalPowerInsights from "@/components/insights/LocalPowerInsights";
import LocalRuntimePanel from "@/components/insights/LocalRuntimePanel";

export default function LocalModelsPage() {
  return (
    <div className="px-8 py-8 max-w-[1100px] mx-auto space-y-10 pb-20">
      <PageHeader
        eyebrow="Hardware"
        title="Local Models & Power"
        description="Energy, throughput, cloud savings, and live runtime for Ollama / local GPUs — plus power settings for electricity pricing on every OS."
        icon={<Cpu size={20} strokeWidth={2.25} />}
      />

      <LocalPowerInsights forceShow={true} />

      <Section
        title="Live local runtime"
        description="Loopback probe of Ollama (installed + loaded models) and optional NVIDIA GPU stats. Works on macOS, Linux, and Windows."
      >
        <LocalRuntimePanel />
      </Section>

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
            TokenTelemetry will sample your power draw for a few seconds and suggest a wattage. Save it so local model costs use real electricity instead of cloud API rates.
          </p>
        </div>
      </Section>

      <Section
        title="Power configuration"
        description="Set your wattage, electricity rate, grid carbon intensity, and the cloud reference model used for savings. These price Ollama / vLLM / LM Studio sessions."
      >
        <PowerSettings />
      </Section>
    </div>
  );
}
